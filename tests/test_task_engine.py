import asyncio
from pathlib import Path

import pytest

from backend.errors import BrowserFlowError, ConflictError, GenerationLimitError, ValidationFailed
from backend.events import EventBus
from backend.models import AccountConfig, ConsoleSettings, SongRecord
from backend.storage import RunStateRepository
from backend.task_engine import TaskEngine


def make_account(tmp_path: Path) -> AccountConfig:
    return AccountConfig(
        account_name="账号01",
        chrome_profile_dir=tmp_path / "chrome" / "账号01",
        chrome_debug_port=9222,
        lyric_dir=tmp_path / "lyrics",
        output_dir=tmp_path / "output",
        download_dir=tmp_path / "downloads",
        max_retries=2,
        song_interval_seconds=0,
    )


def make_song(root: Path, name: str, title: str | None = None) -> Path:
    title = title or name
    directory = Path(root) / "2026-09-17" / "账号01"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    lyrics = "夜色像一台缓慢转动的引擎\n穿过城市也穿过我的呼吸\n" + "旧灯光写下未完成的旋律\n" * 20
    style = "男声摇滚，粗粝低音，鼓点密集，副歌开阔，带有都市夜行感和少量电子质感。整体情绪从压抑推进到明亮，尾奏保留城市噪声和模拟合成器余韵。"
    path.write_text(
        f"# 歌名：《{title}》\n\n## 歌词\n《{title}》\n{lyrics}\n[End]\n\n## 歌曲风格\n{style}\n",
        encoding="utf-8",
    )
    return path


class FakeFlow:
    def __init__(self, engine: TaskEngine | None = None, failures: int = 0, limit: bool = False) -> None:
        self.engine = engine
        self.failures = failures
        self.limit = limit
        self.processed: list[str] = []

    async def process_song(self, lyric_data, on_step) -> Path:
        self.processed.append(lyric_data.song_name)
        on_step("generate")
        if self.limit:
            raise GenerationLimitError("生成次数已达上限")
        if self.failures:
            raise BrowserFlowError("页面操作失败")
        if self.engine is not None and len(self.processed) == 1:
            await self.engine.pause()
        return Path("output") / f"{lyric_data.song_name}.mp3"


class FakeBrowser:
    def __init__(self, flow: FakeFlow) -> None:
        self.flow = flow
        self.entered = 0
        self.exited = 0

    async def __aenter__(self):
        self.entered += 1
        return self.flow

    async def __aexit__(self, exc_type, exc, tb):
        self.exited += 1
        return False


def make_engine(tmp_path: Path, flow: FakeFlow) -> tuple[TaskEngine, RunStateRepository, FakeBrowser]:
    state = RunStateRepository(tmp_path / "state.json")
    browser = FakeBrowser(flow)
    engine = TaskEngine(
        state_repository=state,
        event_bus=EventBus(),
        settings=ConsoleSettings(),
        browser_factory=lambda account, settings: browser,
        poll_interval=0.01,
    )
    return engine, state, browser


async def wait_for(engine: TaskEngine, status: str) -> None:
    for _ in range(300):
        if engine.current and engine.current.status == status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {status}; current={engine.current}")


async def test_successful_run_updates_state_once(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeFlow()
    engine, state, browser = make_engine(tmp_path, flow)

    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert flow.processed == ["01_first", "02_second"]
    assert browser.entered == browser.exited == 1
    assert state.get("2026-09-17", "账号01", "01_first.md").status == "成功"
    assert state.get("2026-09-17", "账号01", "02_second.md").status == "成功"
    assert engine.current.status == "completed"
    assert engine.current.success_count == 2


async def test_parse_failure_continues_without_browser_call(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    bad = make_song(account.lyric_dir, "00_bad")
    bad.write_text("# 歌名：《坏文件》\n", encoding="utf-8")
    good = make_song(account.lyric_dir, "01_good")
    flow = FakeFlow()
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, [bad, good], day="2026-09-17")
    await engine.wait()

    assert flow.processed == ["01_good"]
    assert state.get("2026-09-17", "账号01", "00_bad.md").status == "解析失败"
    assert state.get("2026-09-17", "账号01", "01_good.md").status == "成功"


async def test_retryable_failure_respects_max_retries(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_song")
    flow = FakeFlow(failures=2)
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    assert len(flow.processed) == 2
    record = state.get("2026-09-17", "账号01", "01_song.md")
    assert record.status == "失败"
    assert record.attempts == 2
    assert record.error == "页面操作失败"


async def test_generation_limit_stops_whole_run(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeFlow(limit=True)
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert flow.processed == ["01_first"]
    assert engine.current.status == "generation_limit"
    assert state.get("2026-09-17", "账号01", "02_second.md") is None


async def test_stop_prevents_next_song_and_releases_browser(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeFlow()
    original = flow.process_song

    async def stop_after_first(lyric_data, on_step):
        result = await original(lyric_data, on_step)
        await engine.stop()
        return result

    flow.process_song = stop_after_first
    engine, _, browser = make_engine(tmp_path, flow)
    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert flow.processed == ["01_first"]
    assert engine.current.status == "stopped"
    assert browser.exited == 1


async def test_pause_and_resume_between_songs(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    engine_holder: dict[str, TaskEngine] = {}
    flow = FakeFlow()
    engine, _, _ = make_engine(tmp_path, flow)
    engine_holder["engine"] = engine

    async def pause_after_first(lyric_data, on_step):
        result = await FakeFlow.process_song(flow, lyric_data, on_step)
        await engine_holder["engine"].pause()
        return result

    flow.process_song = pause_after_first
    engine.start(account, songs, day="2026-09-17")
    await wait_for(engine, "paused")
    assert flow.processed == ["01_first"]

    engine.resume()
    await engine.wait()
    assert flow.processed == ["01_first", "02_second"]
    assert engine.current.status == "completed"


async def test_completed_songs_are_skipped_unless_fresh(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_done"), make_song(account.lyric_dir, "02_todo")]
    flow = FakeFlow()
    engine, state, _ = make_engine(tmp_path, flow)
    state.mark(
        "2026-09-17",
        "账号01",
        SongRecord(file_name="01_done.md", status="成功"),
    )

    engine.start(account, songs, day="2026-09-17", fresh_run=False)
    await engine.wait()
    assert flow.processed == ["02_todo"]

    flow2 = FakeFlow()
    engine2, _, _ = make_engine(tmp_path, flow2)
    engine2.start(account, songs, day="2026-09-17", fresh_run=True)
    await engine2.wait()
    assert flow2.processed == ["01_done", "02_todo"]


async def test_conflict_and_unexpected_error_do_not_deadlock(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_song")
    flow = FakeFlow()
    engine, state, _ = make_engine(tmp_path, flow)
    engine.start(account, [song], day="2026-09-17")

    with pytest.raises(ConflictError):
        engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    async def explode(lyric_data, on_step):
        raise RuntimeError("unexpected")

    flow.process_song = explode
    engine2, state2, _ = make_engine(tmp_path, flow)
    engine2.start(account, [song], day="2026-09-17", fresh_run=True)
    await engine2.wait()

    assert engine2.current.status == "failed"
    assert state2.get("2026-09-17", "账号01", "01_song.md").error == "unexpected"


async def test_validation_failure_does_not_retry(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_song")
    flow = FakeFlow()

    async def reject(lyric_data, on_step):
        raise ValidationFailed("歌词格式错误")

    flow.process_song = reject
    engine, state, _ = make_engine(tmp_path, flow)
    engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    assert engine.current.status == "failed"
    assert state.get("2026-09-17", "账号01", "01_song.md").attempts == 1
