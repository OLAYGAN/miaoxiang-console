from pathlib import Path

import asyncio
import pytest

from backend.events import EventBus
from backend.models import AccountConfig, LyricData, LyricTemplateConfig, PipelineSnapshot
from backend.pipeline_queue import PipelineQueueEngine
from backend.pipeline import PipelineEngine
from backend.storage import PipelineStateRepository
from backend.storage import PipelineQueueStateRepository


def make_account(tmp_path: Path, name: str) -> AccountConfig:
    return AccountConfig(
        id=name,
        account_name=name,
        chrome_profile_dir=tmp_path / "chrome" / name,
        chrome_debug_port=9222,
        lyric_dir=tmp_path / "lyrics" / name,
        output_dir=tmp_path / "output" / name,
        download_dir=tmp_path / "downloads" / name,
    )


def make_template(account: AccountConfig, count: int = 1) -> LyricTemplateConfig:
    return LyricTemplateConfig(
        account_id=account.id,
        name=f"{account.account_name}模板",
        lyric_tone="温暖叙事",
        song_style="pop",
        themes=["成长"],
        generation_count=count,
    )


class FakePipelineEngine:
    def __init__(self, *, pause_before_upload: bool = False) -> None:
        self.pause_before_upload = pause_before_upload
        self.started: list[tuple[AccountConfig, LyricTemplateConfig]] = []
        self.real_names: list[str | None] = []
        self.auto_replace_options: list[bool] = []
        self.resume_count = 0
        self.stop_count = 0
        self.current: PipelineSnapshot | None = None
        self._sequence = 0

    @property
    def is_running(self) -> bool:
        return False

    @property
    def is_waiting_user(self) -> bool:
        return self.current is not None and self.current.status == "waiting_user"

    def start(
        self,
        account: AccountConfig,
        template: LyricTemplateConfig,
        *,
        day: str,
        pause_before_upload: bool,
        ai_created: bool,
        real_name: str | None,
        auto_replace_noncompliant: bool = False,
        stop_after_stage: str | None = None,
    ) -> PipelineSnapshot:
        self.started.append((account, template))
        self.real_names.append(real_name)
        self.auto_replace_options.append(auto_replace_noncompliant)
        self._sequence += 1
        stage = "report"
        status = "completed"
        if stop_after_stage == "lyrics":
            stage = "generation"
            status = "stage_completed"
        elif stop_after_stage == "generation":
            stage = "pre_upload"
            status = "stage_completed"
        self.current = PipelineSnapshot(
            run_id=f"run-{self._sequence}",
            account_id=account.id,
            account_name=account.account_name,
            template_id=template.id,
            template_name=template.name,
            day=day,
            status=status,
            stage=stage,
            pause_before_upload=pause_before_upload,
            ai_created=ai_created,
            real_name=real_name,
            auto_replace_noncompliant=auto_replace_noncompliant,
        )
        return self.current

    def start_from(
        self,
        snapshot: PipelineSnapshot,
        *,
        stop_after_stage: str | None = None,
    ) -> PipelineSnapshot:
        self.current = snapshot.model_copy(deep=True)
        self.current.status = "stage_completed" if stop_after_stage == "generation" else "completed"
        self.current.stage = "pre_upload" if stop_after_stage == "generation" else "report"
        return self.current

    async def wait(self) -> PipelineSnapshot | None:
        return self.current

    def resume(self) -> PipelineSnapshot:
        self.resume_count += 1
        assert self.current is not None
        self.current.status = "completed"
        self.current.stage = "report"
        return self.current

    async def stop(self) -> PipelineSnapshot:
        self.stop_count += 1
        assert self.current is not None
        self.current.status = "stopped"
        return self.current


def make_engine(tmp_path: Path, pipeline: FakePipelineEngine) -> PipelineQueueEngine:
    return PipelineQueueEngine(
        state_repository=PipelineQueueStateRepository(tmp_path / "queue.json"),
        event_bus=EventBus(),
        pipeline_engine=pipeline,
    )


@pytest.mark.asyncio
async def test_pipeline_queue_propagates_noncompliant_replacement_policy(tmp_path: Path) -> None:
    account = make_account(tmp_path, "first")
    template = make_template(account)
    pipeline = FakePipelineEngine()
    engine = make_engine(tmp_path, pipeline)

    engine.start(
        [(account, template)],
        day="2026-09-21",
        auto_replace_noncompliant=True,
    )
    await engine.wait()

    assert pipeline.auto_replace_options == [True]
    assert engine.current.auto_replace_noncompliant is True


@pytest.mark.asyncio
async def test_pipeline_queue_stop_does_not_hang_when_pipeline_stop_hangs(tmp_path: Path) -> None:
    from backend.models import PipelineSnapshot

    class HangingStopPipeline:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release_wait = asyncio.Event()
            self.current: PipelineSnapshot | None = None
            self.running = False

        @property
        def is_running(self) -> bool:
            return self.running

        @property
        def is_waiting_user(self) -> bool:
            return False

        def start(self, account, template, *, day, **kwargs):
            self.current = PipelineSnapshot(
                account_id=account.id,
                account_name=account.account_name,
                template_id=template.id,
                template_name=template.name,
                day=day,
            )
            self.running = True
            self.started.set()
            return self.current

        async def wait(self):
            await self.release_wait.wait()
            return self.current

        def resume(self):
            return self.current or PipelineSnapshot.model_validate({"day": ""})

        async def stop(self):
            await asyncio.sleep(3600)
            return self.current

    pipeline = HangingStopPipeline()
    engine = PipelineQueueEngine(
        state_repository=PipelineQueueStateRepository(tmp_path / "queue.json"),
        event_bus=EventBus(),
        pipeline_engine=pipeline,
        stop_timeout=0.01,
    )
    account = make_account(tmp_path, "first")
    queue = engine.start([(account, make_template(account))], day="2026-09-22")
    await asyncio.wait_for(pipeline.started.wait(), timeout=1)

    stopped = await asyncio.wait_for(engine.stop(), timeout=1)

    assert stopped.status == "stopped"
    assert queue.items[0].status == "stopped"


@pytest.mark.asyncio
async def test_pipeline_queue_runs_accounts_sequentially(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first")
    second = make_account(tmp_path, "second")
    first_template = make_template(first)
    second_template = make_template(second)
    pipeline = FakePipelineEngine()
    engine = make_engine(tmp_path, pipeline)

    queue = engine.start(
        [(first, first_template), (second, second_template)],
        day="2026-09-21",
        pause_before_upload=False,
        ai_created=True,
        real_name=None,
    )
    await engine.wait()

    assert [account.account_name for account, _ in pipeline.started] == ["first", "second"]
    assert queue.status == "completed"
    assert [item.status for item in queue.items] == ["completed", "completed"]
    assert [item.run_id for item in queue.items] == ["run-1", "run-2"]
    assert [item.pipeline_snapshot.account_name for item in queue.items] == ["first", "second"]
    assert [item.pipeline_snapshot.status for item in queue.items] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_pipeline_queue_runs_each_stage_across_all_accounts(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first")
    second = make_account(tmp_path, "second")
    calls: list[tuple[str, str]] = []
    pipeline: PipelineEngine | None = None

    async def generate_lyrics(template: LyricTemplateConfig, count: int) -> list[LyricData]:
        assert pipeline is not None and pipeline.current is not None
        calls.append((pipeline.current.account_name, "lyrics"))
        return [
            LyricData(song_name=f"第{index}首", lyrics="风 把 灯光 吹成 街", style="s" * 60)
            for index in range(count)
        ]

    async def save_lyrics(account: AccountConfig, day: str, songs: list[LyricData]):
        return [
            {
                "song_name": song.song_name,
                "file_name": f"{index + 1:02d}_{song.song_name}.md",
                "path": str(tmp_path / account.account_name / f"{index + 1:02d}_{song.song_name}.md"),
            }
            for index, song in enumerate(songs)
        ]

    async def run_generation(account: AccountConfig, day: str, files: list[Path]):
        assert pipeline is not None and pipeline.current is not None
        calls.append((pipeline.current.account_name, "generation"))
        return {
            path.name: {
                "status": "成功",
                "output_path": str(tmp_path / pipeline.current.account_name / f"{path.stem}.mp3"),
            }
            for path in files
        }

    async def run_upload(account: AccountConfig, day: str, files: list[str], *args):
        assert pipeline is not None and pipeline.current is not None
        calls.append((pipeline.current.account_name, "upload"))
        return {"status": "completed"}

    pipeline = PipelineEngine(
        state_repository=PipelineStateRepository(tmp_path / "pipeline.json"),
        event_bus=EventBus(),
        lyric_generator=generate_lyrics,
        lyric_saver=save_lyrics,
        generation_runner=run_generation,
        upload_runner=run_upload,
    )
    engine = PipelineQueueEngine(
        state_repository=PipelineQueueStateRepository(tmp_path / "queue.json"),
        event_bus=EventBus(),
        pipeline_engine=pipeline,
    )

    queue = engine.start(
        [(first, make_template(first)), (second, make_template(second))],
        day="2026-09-29",
    )
    await engine.wait()

    assert calls == [
        ("first", "lyrics"),
        ("second", "lyrics"),
        ("first", "generation"),
        ("second", "generation"),
        ("first", "upload"),
        ("second", "upload"),
    ]
    assert queue.phase == "report"
    assert queue.status == "completed"
    assert [item.status for item in queue.items] == ["completed", "completed"]
    assert [item.stage for item in queue.items] == ["report", "report"]


@pytest.mark.asyncio
async def test_pipeline_queue_pauses_once_after_all_generation(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first")
    second = make_account(tmp_path, "second")
    calls: list[tuple[str, str]] = []
    pipeline: PipelineEngine | None = None

    async def generate_lyrics(template: LyricTemplateConfig, count: int) -> list[LyricData]:
        assert pipeline is not None and pipeline.current is not None
        calls.append((pipeline.current.account_name, "lyrics"))
        return [LyricData(song_name="第一首", lyrics="风 把 灯光 吹成 街", style="s" * 60)]

    async def save_lyrics(account: AccountConfig, day: str, songs: list[LyricData]):
        return [{"song_name": "第一首", "file_name": "01_第一首.md", "path": str(tmp_path / "01.md")}]

    async def run_generation(account: AccountConfig, day: str, files: list[Path]):
        assert pipeline is not None and pipeline.current is not None
        calls.append((pipeline.current.account_name, "generation"))
        return {files[0].name: {"status": "成功", "output_path": str(tmp_path / "out.mp3")}}

    async def run_upload(account: AccountConfig, day: str, files: list[str], *args):
        assert pipeline is not None and pipeline.current is not None
        calls.append((pipeline.current.account_name, "upload"))
        return {"status": "completed"}

    pipeline = PipelineEngine(
        state_repository=PipelineStateRepository(tmp_path / "pipeline.json"),
        event_bus=EventBus(),
        lyric_generator=generate_lyrics,
        lyric_saver=save_lyrics,
        generation_runner=run_generation,
        upload_runner=run_upload,
    )
    engine = PipelineQueueEngine(
        state_repository=PipelineQueueStateRepository(tmp_path / "queue.json"),
        event_bus=EventBus(),
        pipeline_engine=pipeline,
    )
    queue = engine.start(
        [(first, make_template(first)), (second, make_template(second))],
        day="2026-09-29",
        pause_before_upload=True,
    )
    for _ in range(100):
        if queue.status == "waiting_user":
            break
        await asyncio.sleep(0.01)

    assert queue.phase == "upload"
    assert queue.status == "waiting_user"
    assert ("first", "upload") not in calls
    assert ("second", "upload") not in calls

    engine.resume()
    await engine.wait()

    assert calls[-2:] == [("first", "upload"), ("second", "upload")]
    assert queue.status == "completed"


@pytest.mark.asyncio
async def test_pipeline_queue_waits_for_user_resume_before_upload_phase(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first")
    second = make_account(tmp_path, "second")
    first_template = make_template(first)
    second_template = make_template(second)
    pipeline = FakePipelineEngine(pause_before_upload=True)
    engine = make_engine(tmp_path, pipeline)

    queue = engine.start(
        [(first, first_template), (second, second_template)],
        day="2026-09-21",
        pause_before_upload=True,
        ai_created=False,
        real_name="",
    )
    await asyncio.sleep(0)
    assert queue.status == "waiting_user"
    assert queue.phase == "upload"
    assert [item.status for item in queue.items] == ["pending", "pending"]
    assert [account.account_name for account, _ in pipeline.started] == ["first", "second"]

    engine.resume()
    await asyncio.sleep(0)
    await engine.wait()

    assert pipeline.resume_count == 0
    assert queue.status == "completed"
    assert [item.status for item in queue.items] == ["completed", "completed"]
    assert [account.account_name for account, _ in pipeline.started] == ["first", "second"]


@pytest.mark.asyncio
async def test_pipeline_queue_continues_after_failed_account(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first")
    second = make_account(tmp_path, "second")
    first_template = make_template(first)
    second_template = make_template(second)
    pipeline = FakePipelineEngine()
    engine = make_engine(tmp_path, pipeline)

    original_start = pipeline.start

    def failing_start(*args, **kwargs):
        if len(pipeline.started) == 0:
            snapshot = original_start(*args, **kwargs)
            snapshot.status = "failed"
            snapshot.error = "生成失败"
            return snapshot
        return original_start(*args, **kwargs)

    pipeline.start = failing_start
    queue = engine.start(
        [(first, first_template), (second, second_template)],
        day="2026-09-21",
    )
    await engine.wait()

    assert queue.status == "partial_failed"
    assert [item.status for item in queue.items] == ["failed", "completed"]
    assert queue.items[0].error == "生成失败"


@pytest.mark.asyncio
async def test_pipeline_queue_uses_each_account_real_name_by_default(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first").model_copy(update={"upload_real_name": "张三"})
    second = make_account(tmp_path, "second").model_copy(update={"upload_real_name": "李四"})
    pipeline = FakePipelineEngine()
    engine = make_engine(tmp_path, pipeline)

    engine.start(
        [(first, make_template(first)), (second, make_template(second))],
        day="2026-09-21",
        real_name=None,
    )
    await engine.wait()

    assert pipeline.real_names == ["张三", "李四"]


@pytest.mark.asyncio
async def test_pipeline_queue_stop_marks_remaining_accounts_stopped(tmp_path: Path) -> None:
    first = make_account(tmp_path, "first")
    second = make_account(tmp_path, "second")
    first_template = make_template(first)
    second_template = make_template(second)
    pipeline = FakePipelineEngine(pause_before_upload=True)
    engine = make_engine(tmp_path, pipeline)
    queue = engine.start(
        [(first, first_template), (second, second_template)],
        day="2026-09-21",
        pause_before_upload=True,
    )
    await asyncio.sleep(0)

    queue = await engine.stop()

    assert queue.status == "stopped"
    assert [item.status for item in queue.items] == ["stopped", "stopped"]
    assert queue.phase == "upload"
