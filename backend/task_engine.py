"""Serialized task orchestration with bounded and controllable execution."""

import asyncio
import json
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
    SongVerificationError,
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
    BatchSongResult,
)
from backend.storage import RunStateRepository
from backend.upload_rejections import clear_rejected_titles, write_rejected


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
        self._upload_task: asyncio.Task | None = None
        self._verification_future: asyncio.Future[str] | None = None
        self.current: TaskSnapshot | None = None
        self.current_upload: dict | None = None
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
        model_name: str = "自动",
        singer_name: str = "老岩",
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
            self._run(
                account,
                song_files,
                day or date.today().isoformat(),
                fresh_run,
                model_name,
                singer_name,
            )
        )
        return self.current

    @property
    def upload_is_running(self) -> bool:
        return self._upload_task is not None and not self._upload_task.done()

    def start_upload(
        self,
        account: AccountConfig,
        items: list[dict],
        day: str,
        *,
        auto_replace_noncompliant: bool = False,
    ) -> dict:
        if self.is_running:
            raise ConflictError("生成任务正在运行，请先停止后再上传")
        if self.upload_is_running:
            raise ConflictError("已有上传任务正在运行")
        if not items:
            raise ValidationFailed("没有可上传的歌曲")
        self._verification_future = asyncio.get_running_loop().create_future()
        self.current_upload = {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
            "auto_replace_noncompliant": auto_replace_noncompliant,
            "rejected_titles": [],
            "replaced_titles": [],
            "unreplaced_titles": [],
        }
        self._upload_task = asyncio.create_task(
            self._run_upload(
                account,
                items,
                day,
                auto_replace_noncompliant,
            )
        )
        return self.current_upload

    def start_regeneration_upload(
        self,
        account: AccountConfig,
        items: list[dict],
        lyric_files: list[Path],
        day: str,
        *,
        model_name: str = "自动",
        singer_name: str = "老岩",
        auto_replace_noncompliant: bool = False,
    ) -> dict:
        if self.is_running:
            raise ConflictError("生成任务正在运行，请先停止后再操作")
        if self.upload_is_running:
            raise ConflictError("已有上传任务正在运行")
        if not items or not lyric_files:
            raise ValidationFailed("没有可重新生成发布的歌曲")

        self._verification_future = asyncio.get_running_loop().create_future()
        self.current_upload = {
            "status": "running",
            "step": "regenerating_songs",
            "day": day,
            "account_id": account.id,
            "account_name": account.account_name,
            "total": len(items),
            "processed": 0,
            "verification_requested": False,
            "error": None,
            "auto_replace_noncompliant": auto_replace_noncompliant,
            "rejected_titles": [],
            "replaced_titles": [],
            "unreplaced_titles": [],
        }
        self._upload_task = asyncio.create_task(
            self._run_regeneration_upload(
                account,
                items,
                lyric_files,
                day,
                model_name,
                singer_name,
                auto_replace_noncompliant,
            )
        )
        return self.current_upload

    async def submit_upload_code(self, code: str) -> dict:
        if not self.upload_is_running or self._verification_future is None:
            raise ConflictError("当前没有等待验证码的上传任务")
        if not self._verification_future.done():
            self._verification_future.set_result(code)
        self._update_upload(step="submitting_verification_code")
        return self.current_upload or {}

    async def stop_upload(self) -> dict:
        if not self.upload_is_running:
            raise ConflictError("当前没有正在运行的上传任务")
        self._update_upload(status="stopping", step="stopping")
        if self._verification_future is not None and not self._verification_future.done():
            self._verification_future.cancel()
        self._upload_task.cancel()
        return self.current_upload or {}

    async def wait(self) -> None:
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def wait_upload(self) -> None:
        if self._upload_task is not None:
            try:
                await self._upload_task
            except asyncio.CancelledError:
                pass

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
        if self._task is not None:
            self._task.cancel()

    async def shutdown(self) -> None:
        if self.is_running:
            await self.stop()
            try:
                await asyncio.wait_for(self.wait(), timeout=5)
            except asyncio.CancelledError:
                pass
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
        model_name: str = "自动",
        singer_name: str = "老岩",
    ) -> None:
        assert self.current is not None
        try:
            self._update_status("running", step="checking_completed")
            prepared: list[tuple[Path, SongProgress, object]] = []
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
                prepared.append((path, progress, lyric_data))

            if self._stop_requested.is_set():
                self._complete("stopped")
                return
            if not prepared:
                if self.current.failure_count:
                    self._complete("failed")
                else:
                    self._log(
                        "info",
                        "resume",
                        "选中歌曲均已完成；如需重新处理请勾选“全部重跑”",
                    )
                    self._complete("completed")
                return

            self._update_status("running", step="opening_browser")
            run_account = account.model_copy(update={
                "model_name": model_name,
                "singer_name": singer_name,
            })
            async with self._browser_factory(run_account, self._settings) as flow:
                if hasattr(flow, "day"):
                    flow.day = day
                use_batch_flow = hasattr(flow, "process_batch")
                batches = range(0, len(prepared), account.generation_batch_size) if use_batch_flow else range(0, len(prepared), 1)
                last_batch_index = len(batches) - 1 if isinstance(batches, range) else 0
                for batch_index, start in enumerate(batches):
                    if self._stop_requested.is_set():
                        break
                    await self._wait_while_paused()
                    if self._stop_requested.is_set():
                        break
                    batch = prepared[start:start + account.generation_batch_size] if use_batch_flow else prepared[start:start + 1]
                    if use_batch_flow:
                        await self._process_batch_with_retries(
                            account, flow, day, batch
                        )
                    else:
                        path, progress, lyric_data = batch[0]
                        await self._process_with_retries(account, flow, day, path, progress, lyric_data)
                    if self.current.status in {
                        "generation_limit",
                        "login_required",
                        "verification_failed",
                    }:
                        return
                    if batch_index < last_batch_index and account.song_interval_seconds > 0:
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
            return
        except Exception as error:
            self._log("error", "task", f"任务异常: {error}", traceback.format_exc(limit=2))
            self._complete("failed", error=str(error))

    async def _run_regeneration_upload(
        self,
        account: AccountConfig,
        items: list[dict],
        lyric_files: list[Path],
        day: str,
        model_name: str,
        singer_name: str,
        auto_replace_noncompliant: bool,
    ) -> None:
        try:
            self._update_upload(status="running", step="regenerating_songs")
            self.start(
                account,
                lyric_files,
                day=day,
                fresh_run=True,
                model_name=model_name,
                singer_name=singer_name,
            )
            await self.wait()
            assert self.current is not None
            successful_titles = {
                str(song.song_name)
                for song in self.current.songs
                if song.status == "成功" and song.song_name
            }
            upload_items = [
                item for item in items
                if str(item.get("title") or "") in successful_titles
            ]
            if not upload_items:
                raise BrowserFlowError("重新生成完成，但没有可上传的新歌曲")
            if self.current.status != "completed":
                self._log(
                    "warning",
                    "upload_regenerate",
                    f"部分歌曲重新生成失败，继续上传成功的 {len(upload_items)} 首",
                )

            self.current_upload["total"] = len(upload_items)
            self._update_upload(step="reupload_replaced_songs")
            await self._run_upload(
                account,
                upload_items,
                day,
                auto_replace_noncompliant,
            )
        except asyncio.CancelledError:
            if self.is_running:
                await self.stop()
            self._update_upload(status="stopped", step="stopped")
        except Exception as error:
            self._log("error", "upload_regenerate", f"再次生成发布失败: {error}")
            self._update_upload(status="failed", step="failed", error=str(error))

    async def _run_upload(
        self,
        account: AccountConfig,
        items: list[dict],
        day: str,
        auto_replace_noncompliant: bool = False,
    ) -> None:
        def on_step(step: str, processed: int) -> None:
            self._update_upload(step=step, processed=processed)
            self._log("info", f"upload_{step}", f"上传步骤: {step}")

        async def notify_verification_requested() -> None:
            self._update_upload(
                verification_requested=True,
                step="waiting_external_verification_code",
            )
            self._log(
                "warning",
                "upload_verification",
                "请在平台验证码弹窗中输入短信验证码；弹窗消失后任务自动完成",
            )

        try:
            async def upload_once(batch: list[dict]) -> list[dict]:
                self._update_upload(status="running", step="opening_browser")
                # Upload never needs to change the model selector; leave the
                # platform's current/default choice untouched.
                upload_account = account.model_copy(update={"model_name": "自动"})
                async with self._browser_factory(upload_account, self._settings) as flow:
                    result = await flow.upload_album(batch, on_step, notify_verification_requested)
                return result if isinstance(result, list) else batch

            assert self.current_upload is not None
            confirmed_items = await upload_once(items)
            if not confirmed_items and not auto_replace_noncompliant:
                raise BrowserFlowError("所有歌曲均未通过平台音频检测，已停止发布")
            confirmed_keys = {
                str(Path(item["path"]).resolve()) for item in confirmed_items
            }
            rejected_items = [
                item for item in items
                if str(Path(item["path"]).resolve()) not in confirmed_keys
            ]
            if rejected_items:
                write_rejected(account, day, rejected_items)
            self.current_upload["rejected_titles"] = [item["title"] for item in rejected_items]

            if rejected_items and auto_replace_noncompliant:
                self._update_upload(step="replace_noncompliant_songs")
                self._log(
                    "warning",
                    "upload_replace",
                    f"平台剔除 {len(rejected_items)} 首，准备尝试未导出的第二版本",
                )
                replacement_items: list[dict] = []
                replacement_account = account.model_copy(update={"model_name": "自动"})
                async with self._browser_factory(replacement_account, self._settings) as flow:
                    for item in rejected_items:
                        try:
                            output_path = await flow.export_alternate_version(
                                item["title"],
                                item["lyrics"],
                            )
                            replacement_items.append({
                                **item,
                                "path": str(output_path),
                            })
                            self.current_upload["replaced_titles"].append(item["title"])
                            self._log(
                                "info",
                                "upload_replace",
                                f"已导出第二版本: {item['title']}",
                                item["title"],
                            )
                        except Exception as error:
                            self.current_upload["unreplaced_titles"].append(item["title"])
                            self._log(
                                "warning",
                                "upload_replace",
                                f"第二版本导出失败: {item['title']}: {error}",
                                item["title"],
                            )

                if replacement_items:
                    self._update_upload(step="reupload_replaced_songs")
                    reconfirmed = await upload_once(replacement_items)
                    confirmed_items.extend(reconfirmed)
                    confirmed_keys.update(
                        str(Path(item["path"]).resolve()) for item in reconfirmed
                    )
                    self.current_upload["unreplaced_titles"] = [
                        item["title"] for item in replacement_items
                        if str(Path(item["path"]).resolve()) not in confirmed_keys
                    ]

            uploaded_paths = list(dict.fromkeys(
                str(Path(item["path"]).resolve()) for item in confirmed_items
            ))
            if not uploaded_paths:
                raise BrowserFlowError("所有歌曲均未通过平台音频检测，且没有可用替换版本")
            manifest = Path(account.output_dir) / day / ".uploaded.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            existing = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else []
            existing.extend(uploaded_paths)
            manifest.write_text(json.dumps(sorted(set(existing)), ensure_ascii=False, indent=2), encoding="utf-8")
            assert self.current_upload is not None
            self.current_upload["uploaded_paths"] = uploaded_paths
            clear_rejected_titles(
                account,
                day,
                {str(item["title"]) for item in confirmed_items},
            )
            self.current_upload["rejected_titles"] = [
                title for title in self.current_upload["rejected_titles"]
                if title not in self.current_upload["replaced_titles"]
                or title in self.current_upload["unreplaced_titles"]
            ]
            self._update_upload(status="completed", step="done", processed=len(confirmed_items))
            self._log(
                "info",
                "upload_done",
                f"平台确认发布完成: {len(confirmed_items)} 首"
                + (f"；平台剔除 {len(items) - len(confirmed_items)} 首" if len(confirmed_items) < len(items) else ""),
            )
        except asyncio.CancelledError:
            self._update_upload(status="stopped", step="stopped")
        except Exception as error:
            self._log("error", "upload", f"上传任务异常: {error}", traceback.format_exc(limit=2))
            self._update_upload(status="failed", step="failed", error=str(error))

    def _update_upload(
        self, *, status: str | None = None, step: str | None = None,
        processed: int | None = None, verification_requested: bool | None = None,
        error: str | None = None,
    ) -> None:
        if self.current_upload is None:
            return
        if status is not None: self.current_upload["status"] = status
        if step is not None: self.current_upload["step"] = step
        if processed is not None: self.current_upload["processed"] = processed
        if verification_requested is not None: self.current_upload["verification_requested"] = verification_requested
        if error is not None: self.current_upload["error"] = error
        self._events_task({"type": "upload_status", "data": self.current_upload})

    async def _process_batch_with_retries(
        self,
        account: AccountConfig,
        flow: object,
        day: str,
        batch: list[tuple[Path, SongProgress, object]],
    ) -> None:
        remaining = list(batch)
        last_errors = {progress.file_name: "生成失败" for _, progress, _ in batch}
        for attempt in range(1, account.max_retries + 1):
            if self._stop_requested.is_set() or not remaining:
                return
            await self._wait_while_paused()
            for _, progress, _ in remaining:
                progress.attempts += 1
                progress.status = "running"
                progress.current_step = "batch_generate"
            self.current.current_file = remaining[0][1].file_name
            self._update_status("running", step="batch_generate")

            def on_step(step: str, song_name: str | None = None) -> None:
                targets = [
                    item for item in remaining
                    if song_name is None or item[2].song_name == song_name
                ]
                for _, progress, _ in targets:
                    progress.current_step = step
                self.current.current_step = step
                self._emit_status()

            try:
                results = await flow.process_batch(
                    [lyric_data for _, _, lyric_data in remaining],
                    on_step,
                )
                result_by_song = {result.song_name: result for result in results}
            except GenerationLimitError as error:
                for _, progress, _ in remaining:
                    self._finish_song(
                        day, account, progress,
                        status="生成上限", current_step="batch_generate", error=error.message,
                    )
                self._complete("generation_limit", error.message)
                return
            except LoginRequiredError as error:
                for _, progress, _ in remaining:
                    self._finish_song(
                        day, account, progress,
                        status="需要登录", current_step="batch_generate", error=error.message,
                    )
                self._complete("login_required", error.message)
                return
            except SongVerificationError as error:
                for _, progress, _ in remaining:
                    self._finish_song(
                        day, account, progress,
                        status="标题校验失败", current_step="match_titles", error=error.message,
                    )
                self._complete("verification_failed", error.message)
                return
            except Exception as error:
                message = str(error)
                self._log("warning", "batch_generate", f"第 {attempt}/{account.max_retries} 批次失败: {message}")
                for _, progress, _ in remaining:
                    last_errors[progress.file_name] = message
                if attempt < account.max_retries and not self._stop_requested.is_set():
                    await self._interruptible_sleep(min(5, self._settings.page_load_timeout_seconds))
                continue

            next_remaining: list[tuple[Path, SongProgress, object]] = []
            for path, progress, lyric_data in remaining:
                result = result_by_song.get(lyric_data.song_name)
                if result is None:
                    result = BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="generation_failed",
                        error="批次结果缺少该歌词",
                    )
                if result.status == "success":
                    self._finish_song(
                        day,
                        account,
                        progress,
                        status="成功",
                        current_step="done",
                        output_path=result.output_path,
                    )
                elif result.status == "description_rejected":
                    self._finish_song(
                        day,
                        account,
                        progress,
                        status="描述不符合",
                        current_step="generation_rejected",
                        error=result.error or "无法根据描述生成，请修改",
                    )
                elif result.status == "export_failed":
                    self._finish_song(
                        day,
                        account,
                        progress,
                        status="导出失败",
                        current_step="export_song",
                        error=result.error or "导出失败",
                    )
                else:
                    last_errors[progress.file_name] = result.error or "生成失败"
                    progress.status = "running"
                    progress.current_step = "generation_failed"
                    next_remaining.append((path, progress, lyric_data))
            remaining = next_remaining
            if remaining and attempt < account.max_retries and not self._stop_requested.is_set():
                self._log(
                    "warning",
                    "batch_generate",
                    f"批次生成缺失 {len(remaining)} 首，准备只重试缺失歌词",
                )
                await self._interruptible_sleep(min(5, self._settings.page_load_timeout_seconds))

        for _, progress, _ in remaining:
            self._finish_song(
                day,
                account,
                progress,
                status="生成失败",
                current_step="batch_generate",
                error=last_errors.get(progress.file_name, "生成失败"),
            )

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
            except SongVerificationError as error:
                self._finish_song(
                    day,
                    account,
                    progress,
                    status="标题校验失败",
                    current_step=current_step,
                    error=error.message,
                )
                self._complete("verification_failed", error.message)
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
