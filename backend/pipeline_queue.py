from __future__ import annotations

import asyncio
import traceback
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from backend.errors import ConflictError
from backend.events import EventBus
from backend.models import (
    AccountConfig,
    LyricTemplateConfig,
    PipelineQueueItem,
    PipelineQueueSnapshot,
    PipelineSnapshot,
)
from backend.storage import PipelineQueueStateRepository


class QueuePipelineEngine(Protocol):
    @property
    def is_running(self) -> bool: ...

    @property
    def is_waiting_user(self) -> bool: ...

    def start(
        self,
        account: AccountConfig,
        template: LyricTemplateConfig,
        *,
        day: str,
        pause_before_upload: bool = False,
        ai_created: bool = True,
        real_name: str | None = None,
        auto_replace_noncompliant: bool = False,
        stop_after_stage: str | None = None,
    ) -> PipelineSnapshot: ...

    def start_from(
        self,
        snapshot: PipelineSnapshot,
        *,
        stop_after_stage: str | None = None,
    ) -> PipelineSnapshot: ...

    async def wait(self) -> PipelineSnapshot | None: ...

    def resume(self) -> PipelineSnapshot: ...

    async def stop(self) -> PipelineSnapshot: ...


class PipelineQueueEngine:
    def __init__(
        self,
        *,
        state_repository: PipelineQueueStateRepository,
        event_bus: EventBus,
        pipeline_engine: QueuePipelineEngine,
        stop_timeout: float = 5,
    ) -> None:
        self._state = state_repository
        self._events = event_bus
        self._pipeline = pipeline_engine
        self._stop_timeout = stop_timeout
        self._task: asyncio.Task | None = None
        self._queue_entries: list[tuple[AccountConfig, LyricTemplateConfig]] = []
        self._resume = asyncio.Event()
        self._stop_requested = False
        self.current: PipelineQueueSnapshot | None = None
        restored = state_repository.get()
        if restored and restored.status in {"running", "waiting_user"}:
            restored.status = "stopped"
            restored.error = "服务重启，多账号队列已中断"
            for item in restored.items:
                if item.status in {"pending", "running", "waiting_user"}:
                    item.status = "stopped"
                    if not item.error:
                        item.error = "服务重启中断"
            state_repository.save(restored)
        self.current = restored

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def is_waiting_user(self) -> bool:
        return self.current is not None and self.current.status == "waiting_user"

    def start(
        self,
        entries: list[tuple[AccountConfig, LyricTemplateConfig]],
        *,
        day: str,
        pause_before_upload: bool = False,
        ai_created: bool = True,
        real_name: str | None = None,
        auto_replace_noncompliant: bool = False,
    ) -> PipelineQueueSnapshot:
        if self.is_running or self.is_waiting_user:
            raise ConflictError("多账号流水线队列正在运行")
        if self._pipeline.is_running or self._pipeline.is_waiting_user:
            raise ConflictError("单账号流水线正在运行")
        if not entries:
            raise ConflictError("多账号队列至少需要一个账号")

        self._resume = asyncio.Event()
        self._stop_requested = False
        self._queue_entries = entries
        self.current = PipelineQueueSnapshot(
            queue_id=uuid4().hex,
            day=day,
            status="running",
            phase="lyrics",
            current_index=-1,
            pause_before_upload=pause_before_upload,
            ai_created=ai_created,
            real_name=real_name,
            auto_replace_noncompliant=auto_replace_noncompliant,
            items=[
                PipelineQueueItem(
                    account_id=account.id,
                    account_name=account.account_name,
                    template_id=template.id,
                    template_name=template.name,
                )
                for account, template in entries
            ],
        )
        self._persist()
        self._task = asyncio.create_task(self._execute())
        return self.current

    def resume(self) -> PipelineQueueSnapshot:
        if self.is_running and not self.is_waiting_user:
            raise ConflictError("多账号队列正在运行")
        if not self.is_waiting_user:
            raise ConflictError("当前多账号队列不在等待确认状态")
        assert self.current is not None
        self._resume.set()
        return self.current

    async def stop(self) -> PipelineQueueSnapshot:
        if not self.is_running and not self.is_waiting_user:
            raise ConflictError("当前没有可停止的多账号队列")
        self._stop_requested = True
        self._resume.set()
        self._mark_stopped()
        if self._pipeline.is_running or self._pipeline.is_waiting_user:
            try:
                await asyncio.wait_for(self._pipeline.stop(), timeout=self._stop_timeout)
            except asyncio.TimeoutError:
                self._emit_log("warning", "单账号流水线停止超时，已强制取消队列任务")
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return self.current or PipelineQueueSnapshot.model_validate({"day": ""})

    async def wait(self) -> PipelineQueueSnapshot | None:
        if self._task is None:
            return self.current
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return self.current

    async def _execute(self) -> None:
        assert self.current is not None
        try:
            entries = self._entries()

            self.current.phase = "lyrics"
            self._persist()
            for index, (account, template) in enumerate(entries):
                if self._stop_requested:
                    break
                self.current.current_index = index
                item = self.current.items[index]
                item.status = "running"
                item.stage = "lyrics"
                item.error = None
                self._persist()

                start_options = {
                    "pause_before_upload": self.current.pause_before_upload,
                    "ai_created": self.current.ai_created,
                    "real_name": (
                        account.upload_real_name
                        if self.current.real_name is None
                        else self.current.real_name
                    ),
                }
                if self.current.auto_replace_noncompliant:
                    start_options["auto_replace_noncompliant"] = True
                try:
                    snapshot = self._pipeline.start(
                        account,
                        template,
                        day=self.current.day,
                        stop_after_stage="lyrics",
                        **start_options,
                    )
                    snapshot = await self._wait_for_stage(item, snapshot)
                    if snapshot.status == "stage_completed":
                        item.status = "pending"
                        item.stage = snapshot.stage
                        item.error = None
                except Exception as error:
                    item.status = "failed"
                    item.stage = "generation"
                    item.error = str(error)
                    snapshot = None
                if self._stop_requested:
                    break

            if not self._stop_requested:
                self.current.phase = "generation"
                self.current.current_index = -1
                self._persist()
                for index, (account, _) in enumerate(entries):
                    if self._stop_requested:
                        break
                    item = self.current.items[index]
                    snapshot = item.pipeline_snapshot
                    if not snapshot or snapshot.status != "stage_completed" or snapshot.stage != "generation":
                        continue
                    self.current.current_index = index
                    item.status = "running"
                    item.stage = "generation"
                    item.error = None
                    self._persist()
                    try:
                        snapshot = self._pipeline.start_from(
                            snapshot,
                            stop_after_stage="generation",
                        )
                        snapshot = await self._wait_for_stage(item, snapshot)
                        if snapshot.status == "stage_completed":
                            item.status = "pending"
                            item.stage = snapshot.stage
                            item.error = None
                    except Exception as error:
                        item.status = "failed"
                        item.stage = "pre_upload"
                        item.error = str(error)
                    if self._stop_requested:
                        break

            if not self._stop_requested:
                self.current.phase = "upload"
                self.current.current_index = -1
                self._persist()
                if self.current.pause_before_upload:
                    self.current.status = "waiting_user"
                    self._persist()
                    await self._resume.wait()
                    self._resume.clear()
                    if self._stop_requested:
                        self._mark_stopped()
                        return
                    self.current.status = "running"
                    self._persist()

                for index, (account, _) in enumerate(entries):
                    if self._stop_requested:
                        break
                    item = self.current.items[index]
                    snapshot = item.pipeline_snapshot
                    if (
                        not snapshot
                        or snapshot.status != "stage_completed"
                        or snapshot.stage != "pre_upload"
                    ):
                        continue
                    self.current.current_index = index
                    item.status = "running"
                    item.stage = "upload"
                    item.error = None
                    self._persist()
                    try:
                        snapshot = self._pipeline.start_from(
                            snapshot.model_copy(update={
                                "stage": "upload",
                                "pause_before_upload": False,
                            })
                        )
                        snapshot = await self._wait_for_stage(item, snapshot)
                    except Exception as error:
                        item.status = "failed"
                        item.stage = "upload"
                        item.error = str(error)
                    if self._stop_requested:
                        break

            if self._stop_requested:
                self._mark_stopped()
                return
            self.current.phase = "report"
            self.current.current_index = -1
            self._finish()
        except asyncio.CancelledError:
            if self.current:
                self.current.status = "stopped"
                self._persist()
            raise
        except Exception as error:
            if self.current:
                self.current.status = "failed"
                self.current.error = str(error)
                if self.current.current_index >= 0:
                    self.current.items[self.current.current_index].status = "failed"
                    self.current.items[self.current.current_index].error = str(error)
                self._persist()
            self._emit_log(
                "error",
                f"多账号队列异常: {error}",
                traceback.format_exc(limit=2),
            )

    async def _wait_for_stage(
        self,
        item: PipelineQueueItem,
        snapshot: PipelineSnapshot,
    ) -> PipelineSnapshot:
        item.run_id = snapshot.run_id
        self._update_item_from_pipeline(item, snapshot)
        self._persist()
        snapshot = await self._pipeline.wait()
        assert snapshot is not None
        self._update_item_from_pipeline(item, snapshot)
        self._persist()
        return snapshot

    def _entries(self) -> list[tuple[AccountConfig, LyricTemplateConfig]]:
        return self._queue_entries

    def _finish(self) -> None:
        assert self.current is not None
        if self._stop_requested:
            self.current.status = "stopped"
            for item in self.current.items:
                if item.status in {"pending", "running", "waiting_user"}:
                    item.status = "stopped"
        elif all(item.status == "completed" for item in self.current.items):
            self.current.status = "completed"
        elif any(item.status == "completed" for item in self.current.items):
            self.current.status = "partial_failed"
        else:
            self.current.status = "failed"
        self._persist()

    def _mark_stopped(self) -> None:
        assert self.current is not None
        self.current.status = "stopped"
        self.current.error = None
        for item in self.current.items:
            if item.status in {"pending", "running", "waiting_user"}:
                item.status = "stopped"
                item.error = None
        self._persist()

    @staticmethod
    def _update_item_from_pipeline(item: PipelineQueueItem, snapshot: PipelineSnapshot) -> None:
        item.status = snapshot.status
        item.stage = snapshot.stage
        item.run_id = snapshot.run_id
        item.error = snapshot.error
        item.pipeline_snapshot = snapshot.model_copy(deep=True)

    def _persist(self) -> None:
        if not self.current:
            return
        self.current.updated_at = datetime.now()
        self._state.save(self.current)
        self._events_task({
            "type": "pipeline_queue_status",
            "data": self.current.model_dump(mode="json"),
        })

    def _emit_log(self, level: str, message: str, detail: str = "") -> None:
        self._events_task({
            "type": "log",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "step": "pipeline_queue",
                "song": None,
                "message": message + (f"\n{detail}" if detail else ""),
                "screenshot_path": None,
            },
        })

    def _events_task(self, event: dict) -> None:
        asyncio.create_task(self._events.publish(event))
