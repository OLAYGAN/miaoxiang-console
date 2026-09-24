import asyncio
import json
from pathlib import Path

import pytest

from backend.errors import (
    BrowserFlowError,
    ConflictError,
    GenerationLimitError,
    LoginRequiredError,
    SongVerificationError,
    ValidationFailed,
)
from backend.events import EventBus
from backend.models import AccountConfig, ConsoleSettings, SongRecord
from backend.models import BatchSongResult
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


class FakeBatchFlow:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.results: list[list[BatchSongResult]] = []

    async def process_batch(self, lyric_data_list, on_step) -> list[BatchSongResult]:
        submitted = [item.song_name for item in lyric_data_list]
        self.batches.append(submitted)
        for item in lyric_data_list:
            on_step("generate", item.song_name)
        result = self.results.pop(0)
        return result


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


async def test_batch_mode_submits_two_songs_together(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeBatchFlow()
    flow.results = [
        [
            BatchSongResult(song_name="01_first", status="success", output_path="output/a.mp3"),
            BatchSongResult(song_name="02_second", status="success", output_path="output/b.mp3"),
        ]
    ]
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert flow.batches == [["01_first", "02_second"]]
    assert engine.current.status == "completed"
    assert state.get("2026-09-17", "账号01", "01_first.md").status == "成功"
    assert state.get("2026-09-17", "账号01", "02_second.md").status == "成功"


async def test_batch_mode_retries_only_generation_failures(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeBatchFlow()
    flow.results = [
        [
            BatchSongResult(song_name="01_first", status="success", output_path="output/a.mp3"),
            BatchSongResult(song_name="02_second", status="generation_failed", error="没有匹配结果"),
        ],
        [
            BatchSongResult(song_name="02_second", status="success", output_path="output/b.mp3"),
        ],
    ]
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert flow.batches == [["01_first", "02_second"], ["02_second"]]
    assert state.get("2026-09-17", "账号01", "01_first.md").status == "成功"
    assert state.get("2026-09-17", "账号01", "02_second.md").status == "成功"
    assert state.get("2026-09-17", "账号01", "02_second.md").attempts == 2


async def test_batch_description_rejection_is_not_retried(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_first")
    flow = FakeBatchFlow()
    flow.results = [
        [
            BatchSongResult(
                song_name="01_first",
                status="description_rejected",
                error="平台提示生成失败: 无法根据描述生成，请修改",
            ),
        ]
    ]
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    assert flow.batches == [["01_first"]]
    record = state.get("2026-09-17", "账号01", "01_first.md")
    assert record.status == "描述不符合"
    assert record.attempts == 1
    assert "无法根据描述生成" in record.error


async def test_batch_title_mismatch_is_not_retried(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_first")
    flow = FakeBatchFlow()
    flow.results = [
        [
            BatchSongResult(
                song_name="01_first",
                status="title_unmatched",
                error="生成结果标题与歌名不匹配，已跳过",
            ),
        ]
    ]
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    assert flow.batches == [["01_first"]]
    record = state.get("2026-09-17", "账号01", "01_first.md")
    assert record.status == "详情歌名不匹配"
    assert record.attempts == 1


async def test_batch_export_failure_does_not_regenerate(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_first")
    flow = FakeBatchFlow()
    flow.results = [
        [BatchSongResult(song_name="01_first", status="export_failed", error="下载失败")],
    ]
    engine, state, _ = make_engine(tmp_path, flow)

    engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    assert flow.batches == [["01_first"]]
    assert state.get("2026-09-17", "账号01", "01_first.md").status == "导出失败"
    assert state.get("2026-09-17", "账号01", "01_first.md").attempts == 1


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


async def test_all_completed_songs_finish_without_opening_browser(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_first")
    flow = FakeFlow()
    engine, state, browser = make_engine(tmp_path, flow)
    state.mark("2026-09-17", "账号01", SongRecord(
        file_name=song.name,
        song_name="01_first",
        status="成功",
        current_step="done",
        output_path="output/01_first.mp3",
    ))

    engine.start(account, [song], day="2026-09-17")
    await engine.wait()

    assert engine.current.status == "completed"
    assert engine.current.skipped_count == 1
    assert browser.entered == browser.exited == 0


async def test_stop_upload_cancels_waiting_upload_task(tmp_path: Path) -> None:
    class WaitingUploadFlow:
        async def upload_album(self, items, on_step, on_verification_requested):
            on_step("waiting_external_verification_code", len(items))
            await on_verification_requested()
            await asyncio.Event().wait()

    class WaitingUploadBrowser:
        async def __aenter__(self):
            return WaitingUploadFlow()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    account = make_account(tmp_path)
    engine = TaskEngine(
        state_repository=RunStateRepository(tmp_path / "state.json"),
        event_bus=EventBus(),
        settings=ConsoleSettings(),
        browser_factory=lambda account, settings: WaitingUploadBrowser(),
        poll_interval=0.01,
    )
    engine.start_upload(account, [{"title": "第一首"}], "2026-09-17")
    await asyncio.sleep(0)

    await engine.stop_upload()
    await engine.wait_upload()

    assert engine.current_upload["status"] == "stopped"
    assert engine.current_upload["step"] == "stopped"


@pytest.mark.asyncio
async def test_upload_manifest_records_only_platform_confirmed_songs(tmp_path: Path) -> None:
    class SuccessfulUploadFlow:
        async def upload_album(self, items, on_step, on_verification_requested):
            return [items[0]]

    class SuccessfulUploadBrowser:
        async def __aenter__(self):
            return SuccessfulUploadFlow()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    account = make_account(tmp_path)
    first = tmp_path / "output" / "2026-09-17" / "第一首.mp3"
    second = tmp_path / "output" / "2026-09-17" / "第二首.mp3"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"audio")
    second.write_bytes(b"audio")
    engine = TaskEngine(
        state_repository=RunStateRepository(tmp_path / "state.json"),
        event_bus=EventBus(),
        settings=ConsoleSettings(),
        browser_factory=lambda account, settings: SuccessfulUploadBrowser(),
        poll_interval=0.01,
    )

    engine.start_upload(
        account,
        [{"title": "第一首", "path": str(first)}, {"title": "第二首", "path": str(second)}],
        "2026-09-17",
    )
    await engine.wait_upload()

    manifest = json.loads(
        (tmp_path / "output" / "2026-09-17" / ".uploaded.json").read_text(encoding="utf-8")
    )
    assert manifest == [str(first.resolve())]
    rejected = json.loads(
        (tmp_path / "output" / "2026-09-17" / ".rejected.json").read_text(encoding="utf-8")
    )
    assert rejected[0]["title"] == "第二首"
    assert engine.current_upload["status"] == "completed"
    assert engine.current_upload["uploaded_paths"] == [str(first.resolve())]


@pytest.mark.asyncio
async def test_upload_replaces_noncompliant_song_with_alternate_version(tmp_path: Path) -> None:
    class FirstUploadFlow:
        async def upload_album(self, items, on_step, on_verification_requested):
            return [items[0]]

    class AlternateFlow:
        async def export_alternate_version(self, song_name, lyrics):
            output = tmp_path / "output" / "2026-09-17" / f"{song_name}.mp3"
            output.write_bytes(b"second-version")
            return output

    class SecondUploadFlow:
        async def upload_album(self, items, on_step, on_verification_requested):
            return items

    class SequenceBrowser:
        def __init__(self, flow):
            self.flow = flow

        async def __aenter__(self):
            return self.flow

        async def __aexit__(self, exc_type, exc, tb):
            return False

    flows = [FirstUploadFlow(), AlternateFlow(), SecondUploadFlow()]
    calls = iter(range(3))

    def factory(account, settings):
        next(calls)
        return SequenceBrowser(flows.pop(0))

    account = make_account(tmp_path)
    first = tmp_path / "output" / "2026-09-17" / "第一首.mp3"
    second = tmp_path / "output" / "2026-09-17" / "第二首.mp3"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first-version")
    second.write_bytes(b"rejected-first-version")
    engine = TaskEngine(
        state_repository=RunStateRepository(tmp_path / "state.json"),
        event_bus=EventBus(),
        settings=ConsoleSettings(),
        browser_factory=factory,
        poll_interval=0.01,
    )

    engine.start_upload(
        account,
        [
            {"title": "第一首", "path": str(first), "lyrics": "第一首歌词"},
            {"title": "第二首", "path": str(second), "lyrics": "第二首歌词"},
        ],
        "2026-09-17",
        auto_replace_noncompliant=True,
    )
    await engine.wait_upload()

    manifest = json.loads(
        (tmp_path / "output" / "2026-09-17" / ".uploaded.json").read_text(encoding="utf-8")
    )
    assert engine.current_upload["status"] == "completed"
    assert engine.current_upload["rejected_titles"] == []
    assert engine.current_upload["replaced_titles"] == ["第二首"]
    assert set(manifest) == {str(first.resolve()), str(second.resolve())}
    assert second.read_bytes() == b"second-version"
    assert not (second.parent / "不及格").exists()


@pytest.mark.asyncio
async def test_regeneration_upload_generates_songs_before_reuploading(
    tmp_path: Path,
) -> None:
    class GenerationFlow:
        async def process_batch(self, lyric_data_list, on_step):
            results = []
            for lyric_data in lyric_data_list:
                output = tmp_path / "output" / "2026-09-17" / f"{lyric_data.song_name}.mp3"
                output.write_bytes(b"regenerated-version")
                results.append(BatchSongResult(
                    song_name=lyric_data.song_name,
                    status="success",
                    output_path=str(output),
                ))
            return results

    class UploadFlow:
        async def upload_album(self, items, on_step, on_verification_requested):
            return items

    class Browser:
        def __init__(self, flow):
            self.flow = flow

        async def __aenter__(self):
            return self.flow

        async def __aexit__(self, exc_type, exc, tb):
            return False

    flows = [GenerationFlow(), UploadFlow()]
    calls: list[str] = []

    def factory(account, settings):
        flow = flows.pop(0)
        calls.append(type(flow).__name__)
        return Browser(flow)

    account = make_account(tmp_path)
    output = tmp_path / "output" / "2026-09-17" / "第二首.mp3"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"original-rejected")
    lyric = make_song(account.lyric_dir, "01_lyric", title="第二首")
    engine = TaskEngine(
        state_repository=RunStateRepository(tmp_path / "state.json"),
        event_bus=EventBus(),
        settings=ConsoleSettings(),
        browser_factory=factory,
        poll_interval=0.01,
    )

    engine.start_regeneration_upload(
        account,
        [{"title": "第二首", "path": str(output), "lyrics": "第二首歌词"}],
        [lyric],
        "2026-09-17",
        model_name="Sway v5.5",
        singer_name="老岩",
    )
    await engine.wait_upload()

    assert calls == ["GenerationFlow", "UploadFlow"]
    assert output.read_bytes() == b"regenerated-version"
    manifest = json.loads((output.parent / ".uploaded.json").read_text(encoding="utf-8"))
    assert manifest == [str(output.resolve())]


@pytest.mark.asyncio
async def test_regeneration_upload_uploads_successful_songs_when_one_fails(
    tmp_path: Path,
) -> None:
    class GenerationFlow:
        async def process_batch(self, lyric_data_list, on_step):
            first = lyric_data_list[0]
            output = tmp_path / "output" / "2026-09-17" / f"{first.song_name}.mp3"
            output.write_bytes(b"regenerated-first")
            return [
                BatchSongResult(
                    song_name=first.song_name,
                    status="success",
                    output_path=str(output),
                ),
                BatchSongResult(
                    song_name=lyric_data_list[1].song_name,
                    status="title_unmatched",
                    error="生成失败",
                ),
            ]

    uploaded: list[str] = []

    class UploadFlow:
        async def upload_album(self, items, on_step, on_verification_requested):
            uploaded.extend(item["title"] for item in items)
            return items

    class Browser:
        def __init__(self, flow):
            self.flow = flow

        async def __aenter__(self):
            return self.flow

        async def __aexit__(self, exc_type, exc, tb):
            return False

    flows = [GenerationFlow(), UploadFlow()]

    def factory(account, settings):
        return Browser(flows.pop(0))

    account = make_account(tmp_path)
    first = tmp_path / "output" / "2026-09-17" / "第一首.mp3"
    second = tmp_path / "output" / "2026-09-17" / "第二首.mp3"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    first_lyric = make_song(account.lyric_dir, "01_first", title="第一首")
    second_lyric = make_song(account.lyric_dir, "02_second", title="第二首")
    engine = TaskEngine(
        state_repository=RunStateRepository(tmp_path / "state.json"),
        event_bus=EventBus(),
        settings=ConsoleSettings(),
        browser_factory=factory,
        poll_interval=0.01,
    )

    engine.start_regeneration_upload(
        account,
        [
            {"title": "第一首", "path": str(first), "lyrics": "第一首歌词"},
            {"title": "第二首", "path": str(second), "lyrics": "第二首歌词"},
        ],
        [first_lyric, second_lyric],
        "2026-09-17",
    )
    await engine.wait_upload()

    assert uploaded == ["第一首"]
    assert first.read_bytes() == b"regenerated-first"
    assert second.read_bytes() == b"old-second"
    manifest = json.loads((first.parent / ".uploaded.json").read_text(encoding="utf-8"))
    assert manifest == [str(first.resolve())]


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


async def test_login_required_stops_without_retries(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeFlow()

    async def require_login(lyric_data, on_step):
        raise LoginRequiredError("请先登录妙响账号")

    flow.process_song = require_login
    engine, state, _ = make_engine(tmp_path, flow)
    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert len(flow.processed) == 0
    assert engine.current.status == "login_required"
    assert state.get("2026-09-17", "账号01", "01_first.md").status == "需要登录"
    assert state.get("2026-09-17", "账号01", "01_first.md").attempts == 1
    assert state.get("2026-09-17", "账号01", "02_second.md") is None


async def test_song_verification_failure_stops_whole_run(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    songs = [make_song(account.lyric_dir, "01_first"), make_song(account.lyric_dir, "02_second")]
    flow = FakeFlow()

    async def reject_details(lyric_data, on_step):
        raise SongVerificationError("歌词详情不匹配")

    flow.process_song = reject_details
    engine, state, _ = make_engine(tmp_path, flow)
    engine.start(account, songs, day="2026-09-17")
    await engine.wait()

    assert len(flow.processed) == 0
    assert engine.current.status == "verification_failed"
    assert state.get("2026-09-17", "账号01", "01_first.md").status == "标题校验失败"
    assert state.get("2026-09-17", "账号01", "01_first.md").attempts == 1
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


async def test_stop_cancels_long_running_browser_step(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    song = make_song(account.lyric_dir, "01_first")
    flow = FakeFlow()

    async def long_step(lyric_data, on_step):
        on_step("wait_generation")
        await asyncio.sleep(30)
        return Path("output/should-not-exist.mp3")

    flow.process_song = long_step
    engine, _, browser = make_engine(tmp_path, flow)
    engine.start(account, [song], day="2026-09-17")
    while browser.entered == 0:
        await asyncio.sleep(0.01)

    await engine.stop()
    await asyncio.wait_for(engine.wait(), timeout=1.5)

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
