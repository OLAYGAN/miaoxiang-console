from pathlib import Path

import asyncio
import pytest

from backend.events import EventBus
from backend.models import AccountConfig, LyricTemplateConfig, PipelineSnapshot
from backend.pipeline_queue import PipelineQueueEngine
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
    ) -> PipelineSnapshot:
        self.started.append((account, template))
        self.real_names.append(real_name)
        self.auto_replace_options.append(auto_replace_noncompliant)
        self._sequence += 1
        self.current = PipelineSnapshot(
            run_id=f"run-{self._sequence}",
            account_id=account.id,
            account_name=account.account_name,
            template_id=template.id,
            template_name=template.name,
            day=day,
            status="waiting_user" if pause_before_upload and self.pause_before_upload else "completed",
            stage="pre_upload" if pause_before_upload and self.pause_before_upload else "report",
            pause_before_upload=pause_before_upload,
            ai_created=ai_created,
            real_name=real_name,
            auto_replace_noncompliant=auto_replace_noncompliant,
        )
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
async def test_pipeline_queue_waits_for_user_resume_between_accounts(tmp_path: Path) -> None:
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
    assert queue.items[0].status == "waiting_user"
    assert [account.account_name for account, _ in pipeline.started] == ["first"]

    engine.resume()
    await asyncio.sleep(0)
    assert queue.items[1].status == "waiting_user"
    assert [account.account_name for account, _ in pipeline.started] == ["first", "second"]

    engine.resume()
    await engine.wait()

    assert pipeline.resume_count == 2
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
    assert pipeline.stop_count >= 1
