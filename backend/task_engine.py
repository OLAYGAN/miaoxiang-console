"""Serialized task orchestration with bounded and controllable execution."""

import asyncio
import traceback
from collections.abc import Callable
from datetime import date
from pathlib import Path
from uuid import uuid4

from backend.errors import (
    BrowserFlowError,
    ConflictError,
    GenerationLimitError,
    LoginRequiredError,
    ValidationFailed,
)
from backend.events import EventBus
from backend.lyrics import parse_lyrics
from backend.models import (
    AccountConfig,
    ConsoleSettings,
    LogEntry,
    SongProgress,
    SongRecord,
    TaskSnapshot,
)
from backend.storage import RunStateRepository


class TaskEngine:
    def __init__(
        self,
        state_repository: RunStateRepository,
        event_bus: EventBus,
        settings: ConsoleSettings,
        browser_factory: Callable[[AccountConfig, ConsoleSettings], object],
        poll_interval: float = 0.1,
    ) -> None:
        self._state = state_repository
        self._events = event_bus
        self._settings = settings
        self._browser_factory = browser_factory
        self._poll_interval = poll_interval
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.current: TaskSnapshot | None = None
        self._pause_requested = asyncio.Event()
        self._resumed = asyncio.Event()
        self._stop_requested = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def settings(self) -> ConsoleSettings:
        return self._settings

    def update_settings(self, settings: ConsoleSettings) -> None:
        if self.is_running:
            raise ConflictError("任务运行中不能修改全局等待配置")
        self._settings = settings

    def start(
        self,
        account: AccountConfig,
        song_files: list[Path],
        day: str | None = None,
        fresh_run: bool = False,
    ) -> TaskSnapshot:
        if self.is_running:
            raise ConflictError("已有任务正在运行，请先停止当前任务")
        if not song_files:
            raise ValidationFailed("请至少选择一首歌词")

        self._pause_requested.clear()
        self._resumed.clear()
        self._stop_requested.clear()
        self.current = TaskSnapshot(
            run_id=uuid4().hex,
            account_id=account.id,
            account_name=account.account_name,
            songs=[
                SongProgress(file_name=path.name)
                for path in song_files
            ],
        )
        self._task = asyncio.create_task(
            self._run(account, song_files, day or date.today().isoformat(), fresh_run)
        )
        return self.current

    async def wait(self) -> None:
        if self._task is not None:
            await self._task

    async def pause(self) -> None:
        if not self.is_running:
            raise ConflictError("当前没有正在运行的任务")
        self._pause_requested.set()
        self._resumed.clear()
        self._update_status("paused", step="paused")

    def resume(self) -> None:
        if not self.is_running:
            raise ConflictError("当前没有正在运行的任务")
        self._pause_requested.clear()
        self._resumed.set()
        self._update_status("running", step="resuming")

    async def stop(self) -> None:
        if not self.is_running:
            raise ConflictError("当前没有正在运行的任务")
        self._stop_requested.set()
        self._resumed.set()
        self._update_status("stopping", step="stopping")

    async def shutdown(self) -> None:
        if self.is_running:
            await self.stop()
            try:
                await asyncio.wait_for(self.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

    async def _run(
        self,
        account: AccountConfig,
        song_files: list[Path],
        day: str,
        fresh_run: bool,
    ) -> None:
        assert self.current is not None
        try:
            self._update_status("running", step="opening_browser")
            async with self._browser_factory(account, self._settings) as flow:
                for file_index, path in enumerate(song_files):
                    if self._stop_requested.is_set():
                        break
                    await self._wait_while_paused()
                    if self._stop_requested.is_set():
                        break

                    progress = self.current.songs[file_index]
                    self.current.current_file = progress.file_name
                    if not fresh_run:
                        previous = self._state.get(day, account.account_name, path.name)
                        if previous and previous.status == "成功":
                            progress.status = "skipped"
                            progress.current_step = "done"
                            self.current.skipped_count += 1
                            self._emit_status()
                            self._log("info", "resume", f"跳过已完成歌曲: {path.name}", path.name)
                            continue

                    try:
                        lyric_data = parse_lyrics(path.read_text(encoding="utf-8"))
                    except ValidationFailed as error:
                        self._finish_song(
                            day,
                            account,
                            progress,
                            status="解析失败",
                            error=error.message,
                        )
                        continue
                    except OSError as error:
                        self._finish_song(
                            day,
                            account,
                            progress,
                            status="解析失败",
                            error=f"读取歌词失败: {error}",
                        )
                        continue

                    progress.song_name = lyric_data.song_name
                    await self._process_with_retries(account, flow, day, path, progress, lyric_data)
                    if self.current.status == "generation_limit":
                        return
                    if self.current.status == "login_required":
                        return

                    if file_index < len(song_files) - 1 and account.song_interval_seconds > 0:
                        self._update_status(self.current.status, step="waiting_before_next_song")
                        await self._interruptible_sleep(account.song_interval_seconds)

            if self._stop_requested.is_set():
                self._complete("stopped")
            elif self.current.failure_count:
                self._complete("failed")
            else:
                self._complete("completed")
        except asyncio.CancelledError:
            self._complete("stopped")
            raise
        except Exception as error:
            self._log("error", "task", f"任务异常: {error}", traceback.format_exc(limit=2))
            self._complete("failed", error=str(error))

    async def _process_with_retries(
        self,
        account: AccountConfig,
        flow: object,
        day: str,
        path: Path,
        progress: SongProgress,
        lyric_data,
    ) -> None:
        max_attempts = account.max_retries
        last_error = "未知错误"
        for attempt in range(1, max_attempts + 1):
            if self._stop_requested.is_set():
                return
            await self._wait_while_paused()
            progress.attempts = attempt
            progress.status = "running"
            progress.current_step = "starting_browser_step"
            self._emit_status()
            current_step = "processing"

            def on_step(step: str) -> None:
                nonlocal current_step
                current_step = step
                progress.current_step = step
                self._emit_status()

            try:
                output_path = await flow.process_song(lyric_data, on_step)
                self._finish_song(
                    day,
                    account,
                    progress,
                    status="成功",
                    current_step="done",
                    output_path=str(output_path),
                )
                return
            except GenerationLimitError as error:
                self._finish_song(
                    day,
                    account,
                    progress,
                    status="生成上限",
                    current_step=current_step,
                    error=error.message,
                )
                self._complete("generation_limit", error.message)
                return
            except LoginRequiredError as error:
                self._finish_song(
                    day,
                    account,
                    progress,
                    status="需要登录",
                    current_step=current_step,
                    error=error.message,
                )
                self._complete("login_required", error.message)
                return
            except ValidationFailed as error:
                self._finish_song(
                    day,
                    account,
                    progress,
                    status="解析失败",
                    current_step=current_step,
                    error=error.message,
                )
                return
            except (BrowserFlowError, Exception) as error:
                last_error = str(error)
                self._log(
                    "warning",
                    current_step,
                    f"第 {attempt}/{max_attempts} 次处理失败: {error}",
                    path.name,
                )
                if attempt < max_attempts and not self._stop_requested.is_set():
                    await self._interruptible_sleep(min(5, self._settings.page_load_timeout_seconds))

        self._finish_song(
            day,
            account,
            progress,
            status="失败",
            current_step=current_step,
            error=last_error,
        )

    def _finish_song(
        self,
        day: str,
        account: AccountConfig,
        progress: SongProgress,
        *,
        status: str,
        current_step: str = "done",
        error: str | None = None,
        output_path: str | None = None,
    ) -> None:
        progress.status = status
        progress.current_step = current_step
        progress.error = error
        self.current.current_step = current_step
        if status == "成功":
            self.current.success_count += 1
        elif status != "skipped":
            self.current.failure_count += 1
        record = SongRecord(
            file_name=progress.file_name,
            status=status,
            current_step=current_step,
            attempts=progress.attempts,
            error=error,
            output_path=output_path,
        )
        self._state.mark(day, account.account_name, record)
        self._emit_status()
        self._log("info" if status == "成功" else "warning", current_step, f"歌曲状态: {status}", progress.file_name)

    async def _wait_while_paused(self) -> None:
        if not self._pause_requested.is_set() or self._stop_requested.is_set():
            return
        self._update_status("paused", step="paused")
        stop_task = asyncio.create_task(self._stop_requested.wait())
        resume_task = asyncio.create_task(self._resumed.wait())
        done, pending = await asyncio.wait({stop_task, resume_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if self._stop_requested.is_set():
            self._update_status("stopping", step="stopping")
        else:
            self._pause_requested.clear()
            self._update_status("running", step="resuming")

    async def _interruptible_sleep(self, seconds: float) -> None:
        if self._stop_requested.is_set():
            return
        stop_task = asyncio.create_task(self._stop_requested.wait())
        sleep_task = asyncio.create_task(asyncio.sleep(seconds))
        done, pending = await asyncio.wait({stop_task, sleep_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

    def _update_status(self, status: str, step: str | None = None) -> None:
        if self.current is None:
            return
        self.current.status = status
        if step is not None:
            self.current.current_step = step
        self._emit_status()

    def _complete(self, status: str, error: str | None = None) -> None:
        from datetime import datetime

        assert self.current is not None
        self.current.status = status
        self.current.finished_at = datetime.now()
        self.current.error = error
        self._emit_status()
        self._log("info" if status == "completed" else "warning", "task", f"任务结束: {status}")

    def _emit_status(self) -> None:
        if self.current is not None:
            self._events_task({"type": "status", "data": self.current.model_dump(mode="json")})

    def _log(
        self,
        level: str,
        step: str,
        message: str,
        song: str | None = None,
        screenshot_path: str | None = None,
    ) -> None:
        entry = LogEntry(level=level, step=step, song=song, message=message, screenshot_path=screenshot_path)
        self._events_task({"type": "log", "data": entry.model_dump(mode="json")})

    def _events_task(self, event: dict) -> None:
        task = asyncio.create_task(self._events.publish(event))
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
