"""Small scheduler for multi-account single-stage tasks."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from backend.events import EventBus
from backend.models import MultiStageItem, MultiStageSnapshot


ItemRunner = Callable[[MultiStageItem], Awaitable[dict[str, Any]]]


class MultiStageEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._task: asyncio.Task | None = None
        self._stop_requested = False
        self.current: MultiStageSnapshot | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(
        self,
        *,
        stage: str,
        day: str,
        items: list[MultiStageItem],
        runner: ItemRunner,
        concurrency: int = 1,
    ) -> MultiStageSnapshot:
        if self.is_running:
            raise RuntimeError("multi-stage queue is already running")
        if not items:
            raise ValueError("multi-stage queue needs at least one account")

        self._stop_requested = False
        self.current = MultiStageSnapshot(
            stage=stage,
            day=day,
            concurrency=max(1, concurrency),
            items=items,
        )
        self._task = asyncio.create_task(
            self._run(runner, serial=concurrency <= 1)
        )
        self._publish()
        return self.current

    async def stop(self) -> MultiStageSnapshot:
        if not self.is_running or self.current is None:
            # A queue can finish between the UI rendering the stop button and
            # this request arriving. Treat that stop as successful and return
            # the terminal snapshot instead of surfacing a race as an error.
            if self.current is not None:
                return self.current
            raise RuntimeError("multi-stage queue is not running")
        self._stop_requested = True
        self.current.status = "stopping"
        self._touch()
        self._publish()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return self.current or MultiStageSnapshot(stage="", day="")

    async def _run(self, runner: ItemRunner, *, serial: bool) -> None:
        assert self.current is not None
        try:
            if serial:
                for index, item in enumerate(self.current.items):
                    if self._stop_requested:
                        break
                    self.current.current_index = index
                    await self._run_one(runner, item)
            else:
                self.current.current_index = 0
                semaphore = asyncio.Semaphore(self.current.concurrency)

                async def worker(item: MultiStageItem) -> None:
                    async with semaphore:
                        if not self._stop_requested:
                            await self._run_one(runner, item)

                await asyncio.gather(*(worker(item) for item in self.current.items))

            if self.current.status not in {"stopping", "stopped"}:
                self.current.status = (
                    "failed" if all(item.status == "failed" for item in self.current.items) else "completed"
                )
        except asyncio.CancelledError:
            assert self.current is not None
            self.current.status = "stopped"
            for item in self.current.items:
                if item.status in {"pending", "running"}:
                    item.status = "stopped"
            self._touch()
            self._publish()
            raise
        except Exception as error:
            assert self.current is not None
            self.current.status = "failed"
            self.current.error = str(error)
        self._touch()
        self._publish()

    async def _run_one(self, runner: ItemRunner, item: MultiStageItem) -> None:
        assert self.current is not None
        item.status = "running"
        item.error = None
        self._touch()
        self._publish()
        try:
            item.result = await runner(item)
            item.status = "completed" if self._result_ok(item.result) else "failed"
            if item.status == "failed":
                item.error = self._result_error(item.result)
        except asyncio.CancelledError:
            item.status = "stopped"
            raise
        except Exception as error:
            item.status = "failed"
            item.error = str(error)
        self._touch()
        self._publish()

    @staticmethod
    def _result_ok(result: dict[str, Any] | None) -> bool:
        if not result:
            return False
        status = result.get("status")
        if status is not None:
            return status in {"completed", "success"}
        return not result.get("error")

    @staticmethod
    def _result_error(result: dict[str, Any] | None) -> str | None:
        if not result:
            return "任务没有返回结果"
        return result.get("error") or None

    def _touch(self) -> None:
        if self.current is not None:
            self.current.updated_at = datetime.now()

    def _publish(self) -> None:
        if self.current is None:
            return
        payload = self.current.model_dump(mode="json")
        asyncio.create_task(self._events.publish({"type": "multi_stage_status", "data": payload}))
