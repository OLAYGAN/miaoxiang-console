
from __future__ import annotations

import asyncio
import json
import traceback
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.errors import ConflictError
from backend.events import EventBus
from backend.models import (
    AccountConfig,
    LyricData,
    LyricTemplateConfig,
    PipelineSnapshot,
    PipelineSongState,
)
from backend.storage import PipelineStateRepository


LyricGenerator = Callable[[LyricTemplateConfig, int], Awaitable[list[LyricData]]]
LyricSaver = Callable[
    [AccountConfig, str, list[LyricData]],
    Awaitable[list[dict[str, str]]],
]
GenerationRunner = Callable[
    [AccountConfig, str, list[Path]],
    Awaitable[dict[str, dict[str, Any]]],
]
UploadRunner = Callable[
    [AccountConfig, str, list[str], bool, str | None, bool],
    Awaitable[dict[str, Any]],
]


class PipelineEngine:
    def __init__(
        self,
        *,
        state_repository: PipelineStateRepository,
        event_bus: EventBus,
        lyric_generator: LyricGenerator,
        lyric_saver: LyricSaver,
        generation_runner: GenerationRunner,
        upload_runner: UploadRunner,
    ) -> None:
        self._state = state_repository
        self._events = event_bus
        self._generate_lyrics = lyric_generator
        self._save_lyrics = lyric_saver
        self._run_generation = generation_runner
        self._run_upload = upload_runner
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.current: PipelineSnapshot | None = None
        restored = state_repository.get()
        if restored and restored.status == "running":
            restored.status = "stopped"
            restored.error = "服务重启，流水线已中断"
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
        account: AccountConfig,
        template: LyricTemplateConfig,
        *,
        day: str,
        pause_before_upload: bool = False,
        ai_created: bool = True,
        real_name: str | None = None,
        auto_replace_noncompliant: bool = False,
    ) -> PipelineSnapshot:
        if self.is_running:
            raise ConflictError("完整流水线正在运行")
        if self.is_waiting_user:
            raise ConflictError("完整流水线等待确认，请先继续或停止")

        self.current = PipelineSnapshot(
            run_id=uuid4().hex,
            account_id=account.id,
            account_name=account.account_name,
            template_id=template.id,
            template_name=template.name,
            day=day,
            stage="lyrics",
            status="running",
            pause_before_upload=pause_before_upload,
            ai_created=ai_created,
            real_name=real_name,
            auto_replace_noncompliant=auto_replace_noncompliant,
            songs=[
                PipelineSongState(song_name=None)
                for _ in range(template.generation_count)
            ],
        )
        self._persist()
        self._task = asyncio.create_task(self._execute())
        return self.current

    def resume(self) -> PipelineSnapshot:
        if self.is_running:
            raise ConflictError("完整流水线正在运行")
        if not self.is_waiting_user:
            raise ConflictError("当前流水线不在等待确认状态")
        assert self.current is not None
        self.current.status = "running"
        self.current.stage = "upload"
        self.current.error = None
        self._persist()
        self._task = asyncio.create_task(self._execute(resume=True))
        return self.current

    async def wait(self) -> PipelineSnapshot | None:
        if self._task is None:
            return self.current
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return self.current

    def refresh(self, account: AccountConfig) -> PipelineSnapshot | None:
        """Sync a persisted snapshot with files and the upload manifest.

        Single-stage retries can finish after a pipeline snapshot has already
        been marked failed. Refreshing keeps the pipeline report aligned with
        the actual outputs instead of showing a stale terminal state.
        """
        if not self.current:
            return None
        if self.is_running or self.is_waiting_user:
            return self.current
        if self.current.account_id != account.id:
            return self.current

        lyric_root = Path(account.lyric_dir) / self.current.day
        output_root = Path(account.output_dir) / self.current.day
        manifest = output_root / ".uploaded.json"
        uploaded: set[str] = set()
        if manifest.is_file():
            try:
                uploaded = {
                    str(Path(value).resolve())
                    for value in json.loads(manifest.read_text(encoding="utf-8"))
                    if isinstance(value, str)
                }
            except (OSError, ValueError, TypeError):
                uploaded = set()

        downloadable: list[PipelineSongState] = []
        for song in self.current.songs:
            lyric_path = lyric_root / str(song.lyric_file or "")
            if song.lyric_file and lyric_path.is_file():
                song.lyrics_status = "completed"

            output_path = output_root / f"{song.song_name or '未命名歌曲'}.mp3"
            if output_path.is_file() and output_path.stat().st_size > 0:
                resolved_output = str(output_path.resolve())
                song.generation_status = "completed"
                song.output_path = resolved_output
                song.error = None
                downloadable.append(song)
            else:
                song.generation_status = "failed"
                song.output_path = None
                if not song.error:
                    song.error = "没有找到成品文件"

            if song.output_path and str(Path(song.output_path).resolve()) in uploaded:
                song.upload_status = "completed"
                song.upload_removed = False
                song.error = None
            elif song.output_path:
                song.upload_status = "pending"

        self.current.stage = "report"
        if downloadable and all(
            song.upload_status == "completed" or song.upload_removed
            for song in downloadable
        ):
            self.current.status = "completed"
            self.current.error = None
        elif downloadable:
            self.current.status = "failed"
        else:
            self.current.status = "failed"
            self.current.error = self.current.error or "没有可上传的成品歌曲"
        self._persist()
        return self.current

    async def stop(self) -> PipelineSnapshot:
        if not self.is_running and not self.is_waiting_user:
            raise ConflictError("当前没有可停止的完整流水线")
        if self.current:
            self.current.status = "stopped"
            self.current.error = None
            self._persist()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return self.current or PipelineSnapshot.model_validate({})

    async def _execute(self, *, resume: bool = False) -> None:
        assert self.current is not None
        try:
            if self.current.stage == "lyrics":
                await self._execute_lyrics()
            if self.current.stage == "generation":
                await self._execute_generation()
            if self.current.stage == "pre_upload":
                await self._execute_pre_upload()
            if self.current.stage == "upload":
                await self._execute_upload()
            if self.current.stage == "report":
                if self.current.status == "running":
                    self.current.status = "completed"
                self._persist()
        except asyncio.CancelledError:
            if self.current:
                self.current.status = "stopped"
                self._persist()
            raise
        except Exception as error:
            if self.current:
                self.current.status = "failed"
                self.current.error = f"{error}"
                self._persist()
            self._emit_log("error", f"完整流水线失败: {error}", traceback.format_exc(limit=2))

    async def _execute_lyrics(self) -> None:
        assert self.current is not None
        # The callback resolves the template from its identifier in the API layer;
        # the engine intentionally does not access repositories directly.
        template = LyricTemplateConfig(
            account_id=self.current.account_id,
            name=self.current.template_name,
            lyric_tone="",
            song_style="",
            themes=["流水线"],
            generation_count=len(self.current.songs),
        )
        songs = await self._generate_lyrics(template, len(self.current.songs))
        self.current.songs = [
            PipelineSongState(song_name=song.song_name)
            for song in songs
        ]
        self._persist()

        account = self._account_placeholder()
        saved = await self._save_lyrics(account, self.current.day, songs)
        for song in self.current.songs:
            match = next((item for item in saved if item["song_name"] == song.song_name), None)
            if match:
                song.lyrics_status = "completed"
                song.lyric_file = match["file_name"]
            else:
                song.lyrics_status = "failed"
                song.error = "歌词未保存"
        self.current.stage = "generation"
        self._persist()

    async def _execute_generation(self) -> None:
        assert self.current is not None
        lyric_files = [
            Path(song.lyric_file)
            for song in self.current.songs
            if song.lyric_file
        ]
        if not lyric_files:
            self.current.error = "没有可生成的歌词"
            self.current.stage = "report"
            self.current.status = "failed"
            self._persist()
            return

        results = await self._run_generation(
            self._account_placeholder(),
            self.current.day,
            lyric_files,
        )
        for song in self.current.songs:
            result = results.get(song.lyric_file or "")
            if result and result.get("status") == "成功":
                song.generation_status = "completed"
                song.output_path = result.get("output_path")
            else:
                song.generation_status = "failed"
                song.error = result.get("error") if result else "没有生成结果"
        self.current.stage = "pre_upload"
        self._persist()

    async def _execute_pre_upload(self) -> None:
        assert self.current is not None
        downloadable = [
            song for song in self.current.songs
            if song.generation_status == "completed" and song.output_path
        ]
        if not downloadable:
            self.current.error = "没有可上传的成品歌曲"
            self.current.status = "failed"
            self.current.stage = "report"
            self._persist()
            return
        if self.current.pause_before_upload:
            self.current.status = "waiting_user"
            self._persist()
            return
        self.current.stage = "upload"
        self._persist()

    async def _execute_upload(self) -> None:
        assert self.current is not None
        output_files = [
            Path(song.output_path).name
            for song in self.current.songs
            if song.generation_status == "completed" and song.output_path
        ]
        upload_args = [
            self._account_placeholder(),
            self.current.day,
            output_files,
            self.current.ai_created,
            self.current.real_name,
        ]
        if self.current.auto_replace_noncompliant:
            upload_args.append(True)
        result = await self._run_upload(*upload_args)
        upload_status = str(result.get("status") or "failed")
        uploaded_paths = result.get("uploaded_paths")
        has_confirmed_paths = isinstance(uploaded_paths, list)
        uploaded = {
            str(Path(value).resolve())
            for value in uploaded_paths or []
            if isinstance(value, str)
        } if has_confirmed_paths else None
        confirmed_count = 0
        for song in self.current.songs:
            if song.generation_status == "completed":
                if upload_status != "completed":
                    song.upload_status = upload_status
                    continue
                output_path = str(Path(song.output_path or "").resolve()) if song.output_path else ""
                if uploaded is None or output_path in uploaded:
                    song.upload_status = "completed"
                    song.upload_removed = False
                    confirmed_count += 1
                else:
                    song.upload_status = "pending"
                    song.upload_removed = True
                    song.error = None
        if upload_status == "completed":
            self.current.status = "completed" if confirmed_count or uploaded is None else "failed"
        else:
            self.current.status = upload_status
            self.current.error = str(result.get("error") or "上传发布失败")
        self.current.stage = "report"
        self._persist()

    def _account_placeholder(self) -> AccountConfig:
        assert self.current is not None
        # Callers inject account-aware operations; this placeholder preserves
        # engine testability and is never used to construct browser paths.
        return AccountConfig(
            account_name=self.current.account_name,
            chrome_profile_dir="pipeline-placeholder",
            chrome_debug_port=1024,
            lyric_dir="lyrics",
            output_dir="output",
            download_dir="downloads",
        )

    def _persist(self) -> None:
        if not self.current:
            return
        self.current.updated_at = datetime.now()
        self._state.save(self.current)
        self._emit_status()

    def _emit_status(self) -> None:
        if self.current:
            self._events_task({
                "type": "pipeline_status",
                "data": self.current.model_dump(mode="json"),
            })

    def _emit_log(self, level: str, message: str, detail: str = "") -> None:
        self._events_task({
            "type": "log",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "step": "pipeline",
                "song": None,
                "message": message + (f"\n{detail}" if detail else ""),
                "screenshot_path": None,
            },
        })

    def _events_task(self, event: dict) -> None:
        asyncio.create_task(self._events.publish(event))
