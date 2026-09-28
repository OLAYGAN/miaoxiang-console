"""FastAPI control surface for the local automation console."""

from collections.abc import Callable
from datetime import date
from datetime import datetime
import asyncio
import socket
import shutil
import os
import re
import json
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.browser import BrowserManager, ChromeSession, validate_profile_dir
from backend.ai_lyrics import (
    LyricGenerateRequest,
    LyricSaveRequest,
    SYSTEM_PROMPT,
    generate_lyrics as generate_lyrics_with_ai,
    render_lyric_markdown,
    stream_generate_lyrics as stream_lyrics_with_ai,
)
from backend.config import RuntimePaths, build_runtime_paths, ensure_runtime_directories, get_runtime_paths
from backend.errors import AppError, BrowserFlowError, ConflictError, NotFoundError, ValidationFailed
from backend.events import EventBus
from backend.lyrics import list_lyric_files, parse_lyrics
from backend.models import (
    AI_TIMEOUT_SECONDS,
    DEFAULT_AI_SYSTEM_PROMPT,
    AccountConfig,
    ConsoleSettings,
    LyricData,
    LyricTemplateConfig,
    MusicModelName,
)
from backend.page_flow import (
    MIN_DOWNLOAD_DURATION_SECONDS,
    PageFlow,
    read_mp3_duration_seconds,
)
from backend.pipeline import PipelineEngine
from backend.pipeline_queue import PipelineQueueEngine
from backend.storage import (
    AccountRepository,
    JsonStore,
    LyricTemplateRepository,
    PipelineQueueStateRepository,
    PipelineStateRepository,
    RunStateRepository,
)
from backend.task_engine import TaskEngine
from backend.upload_rejections import read_rejected


class AccountCopyRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=64)


class RunRequest(BaseModel):
    account_id: str
    song_files: list[str] = Field(min_length=1)
    day: str | None = None
    fresh_run: bool = False
    model_name: MusicModelName = Field(default="自动")
    singer_name: str = Field(default="老岩", max_length=64)


class RunControlRequest(BaseModel):
    action: str = Field(pattern="^(pause|resume|stop)$")

class UploadCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=10)


class UploadStartRequest(BaseModel):
    file_names: list[str] = Field(min_length=1)
    ai_created: bool = True
    real_name: str | None = Field(default=None, max_length=64)
    auto_replace_noncompliant: bool = False


class UploadRetryRejectedRequest(BaseModel):
    ai_created: bool = True
    real_name: str | None = Field(default=None, max_length=64)
    model_name: MusicModelName = Field(default="自动")
    singer_name: str = Field(default="老岩", max_length=64)


class UploadResetRequest(BaseModel):
    file_names: list[str] = Field(min_length=1)


class PipelineStartRequest(BaseModel):
    account_id: str
    template_id: str
    day: str | None = None
    pause_before_upload: bool = False
    ai_created: bool = True
    real_name: str | None = Field(default=None, max_length=64)
    auto_replace_noncompliant: bool = False


class PipelineQueueItemRequest(BaseModel):
    account_id: str
    template_id: str


class PipelineQueueStartRequest(BaseModel):
    items: list[PipelineQueueItemRequest] = Field(min_length=1)
    day: str | None = None
    pause_before_upload: bool = False
    ai_created: bool = True
    real_name: str | None = Field(default=None, max_length=64)
    auto_replace_noncompliant: bool = False


class FolderOpenRequest(BaseModel):
    kind: str = Field(pattern="^(logs|screenshots|data)$")


class ConsoleSettingsUpdate(BaseModel):
    page_load_timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    generation_timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    editor_import_wait_seconds: int | None = Field(default=None, ge=1, le=120)
    export_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    download_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    log_history_limit: int | None = Field(default=None, ge=100, le=10000)
    ai_api_base_url: str | None = Field(default=None, max_length=2048)
    ai_api_key: str | None = Field(default=None, max_length=4096)
    ai_model: str | None = Field(default=None, max_length=256)
    ai_max_retries: int | None = Field(default=None, ge=0, le=5)
    ai_system_prompt: str | None = Field(default=None, min_length=100, max_length=10000)


class AITestRequest(BaseModel):
    ai_api_base_url: str = Field(min_length=1, max_length=2048)
    ai_api_key: str = Field(default="", max_length=4096)
    ai_model: str = Field(min_length=1, max_length=256)


class LyricTemplateWrite(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    lyric_tone: str = ""
    song_style: str = ""
    themes: list[str] = Field(min_length=1)
    generation_count: int = Field(default=1, ge=1, le=10)


class DefaultBrowserFlow:
    def __init__(self, account: AccountConfig, settings: ConsoleSettings, screenshot_dir: Path) -> None:
        self.session = ChromeSession(account, settings)
        self.account = account
        self.settings = settings
        self.screenshot_dir = screenshot_dir

    async def __aenter__(self) -> PageFlow:
        await self.session.start()
        return PageFlow(
            page=self.session.page,
            account=self.account,
            settings=self.settings,
            screenshot_dir=self.screenshot_dir,
        )

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await self.session.cleanup()
        return False


def open_folder_on_windows(path: Path) -> None:
    os.startfile(str(path))


def pick_account_root_folder(initial_dir: str | None = None) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="选择账号总文件夹",
            initialdir=initial_dir,
        )
        root.destroy()
        return selected or ""
    except Exception:
        return ""


def find_completed_output(directory: Path, song_name: str) -> Path | None:
    if not directory.is_dir():
        return None

    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", song_name).strip()
    exact = directory / f"{safe_name}.mp3"
    if exact.is_file() and exact.stat().st_size > 0:
        return exact

    duplicate_pattern = re.compile(rf"{re.escape(safe_name)}-\d+$")
    for path in sorted(directory.glob("*.mp3")):
        if path.is_file() and path.stat().st_size > 0 and duplicate_pattern.fullmatch(path.stem):
            return path
    return None


def build_upload_lyrics(lyrics: str) -> str:
    """Remove Miaoxiang authoring directives and keep plain lyrics for publishing."""
    cleaned_lines: list[str] = []
    for raw_line in lyrics.splitlines():
        line = raw_line.strip()
        if not line or line == "[End]":
            continue
        if line.startswith("歌名：") or line.startswith("歌名:"):
            continue
        if re.fullmatch(r"\[.*\]", line):
            continue
        if re.fullmatch(r"\(.*\)", line):
            continue
        # Miaoxiang lyric files intentionally insert spaces between Chinese
        # words. Publishing expects ordinary readable lyric lines.
        line = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def save_pipeline_lyrics(
    account: AccountConfig,
    day: str,
    songs: list[LyricData],
) -> list[dict[str, str]]:
    """Save pipeline drafts while reusing an existing song of the same name."""
    ensure_workflow_directories(account, day)
    directory = Path(account.lyric_dir) / day
    existing_by_name: dict[str, Path] = {}
    numbers: list[int] = []
    for path in directory.glob("*.md"):
        if match := re.match(r"^(\d+)_", path.name):
            numbers.append(int(match.group(1)))
        try:
            existing_by_name[parse_lyrics(path.read_text(encoding="utf-8")).song_name] = path
        except Exception:
            continue

    counter = max(numbers, default=0) + 1
    saved: list[dict[str, str]] = []
    for song in songs:
        parsed = parse_lyrics(render_lyric_markdown(song))
        existing = existing_by_name.get(parsed.song_name)
        if existing is not None:
            saved.append({
                "song_name": parsed.song_name,
                "file_name": existing.name,
                "path": str(existing),
            })
            continue

        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", parsed.song_name).strip() or "未命名歌曲"
        path = directory / f"{counter:02d}_{safe_name}.md"
        while path.exists():
            counter += 1
            path = directory / f"{counter:02d}_{safe_name}.md"
        path.write_text(render_lyric_markdown(parsed), encoding="utf-8", newline="\n")
        saved.append({
            "song_name": parsed.song_name,
            "file_name": path.name,
            "path": str(path),
        })
        existing_by_name[parsed.song_name] = path
        counter += 1
    return saved


def build_upload_items(
    account: AccountConfig,
    day: str,
    *,
    selected_file_names: set[str] | None = None,
    ai_created: bool = True,
    real_name: str | None = None,
) -> list[dict]:
    ensure_workflow_directories(account, day)
    directory = Path(account.output_dir) / day
    manifest = directory / ".uploaded.json"
    uploaded = set(json.loads(manifest.read_text(encoding="utf-8"))) if manifest.is_file() else set()
    lyric_by_title: dict[str, str] = {}
    for lyric_path in list_lyric_files(Path(account.lyric_dir), day=day):
        try:
            parsed = parse_lyrics(lyric_path.read_text(encoding="utf-8"))
            lyric_by_title[parsed.song_name] = build_upload_lyrics(parsed.lyrics)
        except Exception:
            continue
    output_files = {
        path.stem: path
        for path in sorted(directory.glob("*.mp3"))
        if is_uploadable_audio(path)
    }
    selected_files = {
        path.name for path in output_files.values()
        if selected_file_names is None or path.name in selected_file_names
    }
    items: list[dict] = []
    for title, lyrics in lyric_by_title.items():
        path = output_files.get(title)
        if path is None or path.name not in selected_files or str(path.resolve()) in uploaded:
            continue
        keywords = "、".join(re.findall(r"[\u4e00-\u9fff]{2,4}", lyrics)[:8]) or title
        cover_path = directory / "封面.jpg"
        items.append({
            "title": title,
            "path": str(path.resolve()),
            "lyrics": lyrics,
            "cover_prompt": keywords[:50],
            "cover_path": str(cover_path.resolve()) if cover_path.is_file() else None,
            "ai_created": ai_created,
            "real_name": account.upload_real_name if real_name is None else real_name,
        })
        if len(items) >= account.upload_batch_size:
            break
    return items


def is_uploadable_audio(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        return read_mp3_duration_seconds(path) > MIN_DOWNLOAD_DURATION_SECONDS
    except BrowserFlowError:
        return False


def ensure_workflow_directories(account: AccountConfig, day: str | None = None) -> None:
    day_value = day or date.today().isoformat()
    for root in (account.lyric_dir, account.output_dir, account.download_dir):
        Path(root, day_value).mkdir(parents=True, exist_ok=True)


def load_existing_pipeline_lyrics(
    account: AccountConfig,
    day: str,
    count: int,
) -> list[LyricData]:
    """Reuse enough valid drafts instead of appending another AI batch."""
    songs: list[LyricData] = []
    for path in list_lyric_files(Path(account.lyric_dir), day=day):
        try:
            songs.append(parse_lyrics(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(songs) == count:
            return songs
    return []


def is_local_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def next_available_debug_port(accounts: list[AccountConfig], preferred: int = 9222) -> int:
    used = {account.chrome_debug_port for account in accounts}
    candidates = [preferred, *range(9222, 9300), *range(9300, 9400, 10)]
    for port in candidates:
        if 1024 <= port <= 65535 and port not in used and is_local_port_available(port):
            return port
    raise AppError("没有找到可用的调试端口，请手动指定")


def next_chrome_profile_destination(source: Path, account_name: str) -> Path:
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", account_name).strip() or "Chrome账号"
    parent = source.parent
    candidate = parent / safe_name
    counter = 2
    while candidate.exists():
        candidate = parent / f"{safe_name}-{counter}"
        counter += 1
    return candidate.resolve()


async def test_ai_api_connection(
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
        if response.status_code in {401, 403}:
            raise ValidationFailed("API Key 无效或没有权限")
        response.raise_for_status()
        payload = response.json()
    except ValidationFailed:
        raise
    except httpx.HTTPStatusError as error:
        raise ValidationFailed(
            f"API 返回错误 {error.response.status_code}: {error.response.text[:300]}"
        ) from error
    except (httpx.RequestError, ValueError) as error:
        raise ValidationFailed(f"API 连接失败: {error}") from error

    models = payload.get("data", []) if isinstance(payload, dict) else []
    model_ids = [
        str(item.get("id"))
        for item in models
        if isinstance(item, dict) and item.get("id")
    ]
    if model not in model_ids:
        raise ValidationFailed(f"API 未返回模型 {model}，请确认模型名称")
    return {"ok": True, "model": model, "model_count": len(model_ids)}


def ensure_deletable_chrome_profile(
    profile_dir: Path,
    account: AccountConfig,
    all_accounts: list[AccountConfig],
) -> Path:
    profile = validate_profile_dir(profile_dir)
    protected = {
        Path(path).expanduser().resolve()
        for path in (account.lyric_dir, account.output_dir, account.download_dir)
    }
    if profile in protected:
        raise ValidationFailed(f"Chrome 目录与歌词/成品/下载目录重合，拒绝删除: {profile}")
    if any(
        other.id != account.id and Path(other.chrome_profile_dir).resolve() == profile
        for other in all_accounts
    ):
        raise ConflictError(f"Chrome 目录被其它账号使用，拒绝删除: {profile}")
    if profile.is_symlink():
        raise ValidationFailed(f"Chrome 目录是链接，拒绝删除: {profile}")
    if not profile.exists():
        return profile
    if any(profile.iterdir()) and not (
        (profile / "Local State").is_file() or (profile / "Default").is_dir()
    ):
        raise ValidationFailed(f"目录不像 Chrome 用户数据目录，拒绝删除: {profile}")
    return profile


def create_app(
    *,
    runtime_paths: RuntimePaths | None = None,
    browser_factory: Callable[[AccountConfig, ConsoleSettings], object] | None = None,
    poll_interval: float = 0.1,
) -> FastAPI:
    paths = runtime_paths or get_runtime_paths()
    ensure_runtime_directories(paths)
    account_repository = AccountRepository(paths.accounts_file)
    state_repository = RunStateRepository(paths.run_state_file)
    lyric_template_repository = LyricTemplateRepository(paths.lyric_templates_file)
    settings_store = JsonStore(paths.settings_file, ConsoleSettings().model_dump(mode="json"))
    settings = ConsoleSettings.model_validate(settings_store.read())
    prompt_version_marker = "AI 音乐创作 Agent 提示词 v2.1（控制台英文指令 JSON 版）"
    if prompt_version_marker not in settings.ai_system_prompt:
        settings = settings.model_copy(update={"ai_system_prompt": DEFAULT_AI_SYSTEM_PROMPT})
        settings_store.write(settings.model_dump(mode="json"))
    events = EventBus(history_limit=settings.log_history_limit)

    def default_factory(account: AccountConfig, current_settings: ConsoleSettings) -> DefaultBrowserFlow:
        return DefaultBrowserFlow(account, current_settings, paths.screenshot_dir)

    engine = TaskEngine(
        state_repository=state_repository,
        event_bus=events,
        settings=settings,
        browser_factory=browser_factory or default_factory,
        poll_interval=poll_interval,
    )
    pipeline_state_repository = PipelineStateRepository(paths.pipeline_state_file)
    pipeline_queue_state_repository = PipelineQueueStateRepository(paths.pipeline_queue_state_file)

    async def pipeline_lyric_generator(template: LyricTemplateConfig, count: int) -> list[LyricData]:
        assert pipeline_engine.current is not None
        current = pipeline_engine.current
        actual_account = account_repository.get(current.account_id)
        existing = load_existing_pipeline_lyrics(actual_account, current.day, count)
        if existing:
            return existing
        actual_template = lyric_template_repository.get(current.template_id)
        return await generate_lyrics_with_ai(
            settings,
            template=actual_template,
            count=count,
        )

    async def pipeline_lyric_saver(
        account: AccountConfig,
        day: str,
        songs: list[LyricData],
    ) -> list[dict[str, str]]:
        assert pipeline_engine.current is not None
        actual_account = account_repository.get(pipeline_engine.current.account_id)
        return await asyncio.to_thread(save_pipeline_lyrics, actual_account, day, songs)

    async def pipeline_generation_runner(
        account: AccountConfig,
        day: str,
        lyric_files: list[Path],
    ) -> dict[str, dict]:
        assert pipeline_engine.current is not None
        actual_account = account_repository.get(pipeline_engine.current.account_id)
        actual_account = actual_account.model_copy(update={
            "max_retries": pipeline_engine.current.generation_max_retries,
        })
        root = Path(actual_account.lyric_dir) / day
        paths = [(root / path.name).resolve() for path in lyric_files]
        await login_browser.close()
        try:
            engine.start(actual_account, paths, day=day, fresh_run=False)
            await engine.wait()
        except asyncio.CancelledError:
            if engine.is_running:
                await engine.stop()
            raise
        results = {
            record.file_name: {
                "status": record.status,
                "output_path": record.output_path,
                "error": record.error,
            }
            for record in state_repository.list(day, actual_account.account_name)
        }
        return results

    async def pipeline_upload_runner(
        account: AccountConfig,
        day: str,
        file_names: list[str],
        ai_created: bool,
        real_name: str | None,
        auto_replace_noncompliant: bool,
    ) -> dict:
        assert pipeline_engine.current is not None
        actual_account = account_repository.get(pipeline_engine.current.account_id)
        items = build_upload_items(
            actual_account,
            day,
            selected_file_names=set(file_names),
            ai_created=ai_created,
            real_name=real_name,
        )
        if not items:
            raise ValidationFailed("没有可上传歌曲；请确认成品文件名和歌词歌名一致")
        await login_browser.close()
        try:
            engine.start_upload(
                actual_account,
                items,
                day,
                auto_replace_noncompliant=auto_replace_noncompliant,
            )
            await engine.wait_upload()
        except asyncio.CancelledError:
            if engine.upload_is_running:
                await engine.stop_upload()
            raise
        return engine.current_upload or {"status": "failed", "error": "上传任务没有返回结果"}

    app = FastAPI(title="妙响自动化控制台", version="0.2.0")
    app.state.runtime_paths = paths
    app.state.accounts = account_repository
    app.state.run_state = state_repository
    app.state.lyric_templates = lyric_template_repository
    app.state.settings_store = settings_store
    app.state.settings = settings
    app.state.events = events
    app.state.engine = engine
    login_browser = BrowserManager()
    app.state.login_browser = login_browser
    pipeline_engine = PipelineEngine(
        state_repository=pipeline_state_repository,
        event_bus=events,
        lyric_generator=pipeline_lyric_generator,
        lyric_saver=pipeline_lyric_saver,
        generation_runner=pipeline_generation_runner,
        upload_runner=pipeline_upload_runner,
    )
    app.state.pipeline_engine = pipeline_engine
    pipeline_queue_engine = PipelineQueueEngine(
        state_repository=pipeline_queue_state_repository,
        event_bus=events,
        pipeline_engine=pipeline_engine,
    )
    app.state.pipeline_queue_engine = pipeline_queue_engine

    def pipeline_queue_busy() -> bool:
        return pipeline_queue_engine.is_running or pipeline_queue_engine.is_waiting_user

    async def shutdown_engine() -> None:
        await login_browser.close()
        await engine.shutdown()
        if pipeline_queue_engine.is_running or pipeline_queue_engine.is_waiting_user:
            await pipeline_queue_engine.stop()
            return
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user:
            await pipeline_engine.stop()

    app.router.add_event_handler("shutdown", shutdown_engine)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError):
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.message, "code": error.code},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "请求参数不正确"})

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "task_running": engine.is_running,
            "task_status": engine.current.status if engine.current else None,
        }

    @app.get("/api/available-port")
    async def available_port() -> dict:
        return {"chrome_debug_port": next_available_debug_port(account_repository.list())}

    @app.get("/api/accounts")
    async def list_accounts() -> list[dict]:
        return [account.model_dump(mode="json") for account in account_repository.list()]

    @app.post("/api/accounts", status_code=201)
    async def create_account(account: AccountConfig) -> dict:
        accounts = account_repository.list()
        port_is_duplicate = any(item.chrome_debug_port == account.chrome_debug_port for item in accounts)
        if port_is_duplicate or not is_local_port_available(account.chrome_debug_port):
            account = account.model_copy(
                update={"chrome_debug_port": next_available_debug_port(accounts, account.chrome_debug_port)}
            )
        created = account_repository.create(account)
        Path(created.chrome_profile_dir).mkdir(parents=True, exist_ok=True)
        ensure_workflow_directories(created)
        return created.model_dump(mode="json")

    @app.get("/api/accounts/{account_id}")
    async def get_account(account_id: str) -> dict:
        return account_repository.get(account_id).model_dump(mode="json")

    @app.put("/api/accounts/{account_id}")
    async def update_account(account_id: str, account: AccountConfig) -> dict:
        updated = account_repository.update(account_id, account)
        ensure_workflow_directories(updated)
        return updated.model_dump(mode="json")

    @app.delete("/api/accounts/{account_id}", status_code=204)
    async def delete_account(account_id: str, delete_chrome: bool = False) -> None:
        account = account_repository.get(account_id)
        if delete_chrome:
            if engine.is_running or (
                engine.upload_is_running
                and engine.current_upload
                and engine.current_upload.get("account_id") == account_id
            ):
                raise ConflictError("账号任务正在运行，不能删除 Chrome 目录")
            if login_browser.current_account_id == account_id:
                raise ConflictError("登录浏览器正在使用该账号，请先关闭浏览器再删除")
            profile = ensure_deletable_chrome_profile(
                Path(account.chrome_profile_dir),
                account,
                account_repository.list(),
            )
            if profile.exists():
                try:
                    await asyncio.to_thread(shutil.rmtree, profile)
                except OSError as error:
                    raise ConflictError(f"Chrome 目录删除失败，请确认浏览器已关闭: {error}") from error
        lyric_template_repository.delete_for_account(account_id)
        account_repository.delete(account_id)

    @app.post("/api/accounts/{account_id}/copy")
    async def copy_account(account_id: str, request: AccountCopyRequest) -> dict:
        if engine.is_running or engine.upload_is_running:
            raise ConflictError("任务运行中不能复制 Chrome 目录")
        if login_browser.current_account_id == account_id:
            raise ConflictError("登录浏览器正在使用该账号，请先关闭窗口再复制")

        source_account = account_repository.get(account_id)
        accounts = account_repository.list()
        if any(account.account_name == request.account_name for account in accounts):
            raise ConflictError(f"账号名称已存在: {request.account_name}")

        source_profile = validate_profile_dir(Path(source_account.chrome_profile_dir))
        if not source_profile.is_dir():
            raise ValidationFailed(f"Chrome 用户目录不存在，无法完整复制: {source_profile}")
        if source_profile.is_symlink():
            raise ValidationFailed(f"Chrome 用户目录是链接，拒绝复制: {source_profile}")

        destination = next_chrome_profile_destination(source_profile, request.account_name)
        try:
            await asyncio.to_thread(shutil.copytree, source_profile, destination)
        except OSError as error:
            if destination.exists():
                await asyncio.to_thread(shutil.rmtree, destination, ignore_errors=True)
            raise ConflictError(f"Chrome 用户目录复制失败: {error}") from error

        port = next_available_debug_port(accounts, source_account.chrome_debug_port)
        copied = source_account.model_copy(
            update={
                "id": uuid4().hex,
                "account_name": request.account_name,
                "chrome_profile_dir": str(destination),
                "chrome_debug_port": port,
            }
        )
        try:
            created = account_repository.create(copied)
        except Exception:
            await asyncio.to_thread(shutil.rmtree, destination, ignore_errors=True)
            raise
        ensure_workflow_directories(created)
        return created.model_dump(mode="json")

    @app.get("/api/accounts/{account_id}/songs")
    async def list_songs(account_id: str, day: str | None = None) -> list[dict]:
        account = account_repository.get(account_id)
        day_value = day or date.today().isoformat()
        ensure_workflow_directories(account, day_value)
        files = list_lyric_files(Path(account.lyric_dir), day=day)
        output_directory = Path(account.output_dir) / day_value
        result: list[dict] = []
        for path in files:
            item = {
                "file_name": path.name,
                "path": str(path),
                "valid": False,
                "song_name": None,
                "status": "pending",
                "current_step": "pending",
                "attempts": 0,
                "error": None,
                "output_path": None,
            }
            try:
                parsed = parse_lyrics(path.read_text(encoding="utf-8"))
                item.update(valid=True, song_name=parsed.song_name)
            except Exception as error:
                item["error"] = str(error)
                item["status"] = "failed"
                item["current_step"] = "parse"
            else:
                output_path = find_completed_output(output_directory, parsed.song_name)
                if output_path:
                    item.update(
                        status="success",
                        current_step="done",
                        output_path=str(output_path),
                    )
            result.append(item)
        return result

    @app.get("/api/accounts/{account_id}/lyric/templates")
    async def list_lyric_templates(account_id: str) -> dict:
        account_repository.get(account_id)
        return {
            "system_prompt": settings.ai_system_prompt,
            "templates": [
                template.model_dump(mode="json")
                for template in lyric_template_repository.list(account_id)
            ],
        }

    @app.post("/api/accounts/{account_id}/lyric/templates", status_code=201)
    async def create_lyric_template(account_id: str, request: LyricTemplateWrite) -> dict:
        account_repository.get(account_id)
        template = LyricTemplateConfig(account_id=account_id, **request.model_dump())
        return lyric_template_repository.create(template).model_dump(mode="json")

    @app.put("/api/accounts/{account_id}/lyric/templates/{template_id}")
    async def update_lyric_template(
        account_id: str,
        template_id: str,
        request: LyricTemplateWrite,
    ) -> dict:
        account_repository.get(account_id)
        existing = lyric_template_repository.get(template_id)
        template = LyricTemplateConfig(
            id=template_id,
            account_id=account_id,
            **request.model_dump(),
        )
        return lyric_template_repository.update(template_id, template).model_dump(mode="json")

    @app.delete("/api/accounts/{account_id}/lyric/templates/{template_id}", status_code=204)
    async def delete_lyric_template(account_id: str, template_id: str) -> None:
        existing = lyric_template_repository.get(template_id)
        if existing.account_id != account_id:
            raise ValidationFailed("歌词模板不属于该账号")
        lyric_template_repository.delete(template_id)

    @app.post("/api/accounts/{account_id}/lyrics/generate")
    async def generate_account_lyrics(account_id: str, request: LyricGenerateRequest) -> dict:
        account_repository.get(account_id)
        template = lyric_template_repository.get(request.template_id)
        if template.account_id != account_id:
            raise ValidationFailed("歌词模板不属于该账号")
        songs = await generate_lyrics_with_ai(
            settings,
            template=template,
            count=template.generation_count,
        )
        return {
            "account_id": account_id,
            "template_id": request.template_id,
            "songs": [song.model_dump(mode="json") for song in songs],
        }

    @app.post("/api/accounts/{account_id}/lyrics/generate/stream")
    async def stream_account_lyrics(account_id: str, request: LyricGenerateRequest) -> StreamingResponse:
        account_repository.get(account_id)
        template = lyric_template_repository.get(request.template_id)
        if template.account_id != account_id:
            raise ValidationFailed("歌词模板不属于该账号")

        async def event_stream():
            def sse(event: str, data: dict) -> bytes:
                payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")

            def collect_progress(progress: dict) -> None:
                event_queue.put_nowait(progress)

            event_queue: asyncio.Queue[dict] = asyncio.Queue()

            generation_task = asyncio.create_task(
                stream_lyrics_with_ai(
                    settings,
                    template=template,
                    count=template.generation_count,
                    on_progress=collect_progress,
                )
            )

            try:
                while not generation_task.done() or not event_queue.empty():
                    if event_queue.empty():
                        await asyncio.sleep(0.05)
                        continue
                    yield sse("progress", event_queue.get_nowait())
                songs = generation_task.result()
                while not event_queue.empty():
                    yield sse("progress", event_queue.get_nowait())
                yield sse("done", {
                    "account_id": account_id,
                    "template_id": request.template_id,
                    "songs": [song.model_dump(mode="json") for song in songs],
                })
            except AppError as error:
                yield sse("error", {
                    "message": error.message,
                    "code": getattr(error, "code", "APP_ERROR"),
                })

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/accounts/{account_id}/lyrics/save")
    async def save_account_lyrics(account_id: str, request: LyricSaveRequest) -> dict:
        account = account_repository.get(account_id)
        day_value = request.day or date.today().isoformat()
        try:
            datetime.strptime(day_value, "%Y-%m-%d").date()
        except ValueError as error:
            raise ValidationFailed("日期格式必须是 YYYY-MM-DD") from error

        ensure_workflow_directories(account, day_value)
        directory = Path(account.lyric_dir) / day_value
        existing_names: set[str] = set()
        for path in directory.glob("*.md"):
            try:
                existing_names.add(parse_lyrics(path.read_text(encoding="utf-8")).song_name)
            except Exception:
                continue

        numbers = [
            int(match.group(1))
            for path in directory.glob("*.md")
            if (match := re.match(r"^(\d+)_", path.name))
        ]
        counter = max(numbers, default=0) + 1
        saved: list[dict] = []
        seen_names: set[str] = set()
        for song in request.songs:
            try:
                parsed = parse_lyrics(render_lyric_markdown(song))
            except ValidationFailed as error:
                raise ValidationFailed(f"{song.song_name or '未命名歌曲'} 校验失败: {error.message}") from error
            if parsed.song_name in existing_names or parsed.song_name in seen_names:
                raise ValidationFailed(f"歌名已存在: {parsed.song_name}")
            seen_names.add(parsed.song_name)

            safe_name = re.sub(r'[\\/:*?"<>|]+', "_", parsed.song_name).strip() or "未命名歌曲"
            path = directory / f"{counter:02d}_{safe_name}.md"
            while path.exists():
                counter += 1
                path = directory / f"{counter:02d}_{safe_name}.md"
            path.write_text(render_lyric_markdown(parsed), encoding="utf-8", newline="\n")
            saved.append({"file_name": path.name, "path": str(path), "song_name": parsed.song_name})
            counter += 1

        return {"account_id": account_id, "day": day_value, "saved": saved}

    @app.get("/api/accounts/{account_id}/uploads")
    async def list_upload_batch(account_id: str, day: str | None = None) -> dict:
        account = account_repository.get(account_id)
        day_value = day or date.today().isoformat()
        ensure_workflow_directories(account, day_value)
        directory = Path(account.output_dir) / day_value
        manifest = directory / ".uploaded.json"
        uploaded = set(json.loads(manifest.read_text(encoding="utf-8"))) if manifest.is_file() else set()
        files: list[dict] = []
        uploaded_files: list[dict] = []
        rejected_files = read_rejected(account, day_value)
        if directory.is_dir():
            for path in sorted(directory.glob("*.mp3")):
                if not is_uploadable_audio(path):
                    continue
                item = {
                    "file_name": path.name,
                    "path": str(path),
                    "size": path.stat().st_size,
                }
                if str(path.resolve()) in uploaded:
                    uploaded_files.append(item)
                else:
                    files.append(item)
        return {
            "ready": bool(files),
            "day": day_value,
            "batch_size": account.upload_batch_size,
            "artist_name": account.upload_artist_name,
            "real_name": account.upload_real_name,
            "files": files,
            "uploaded_files": uploaded_files,
            "rejected_files": rejected_files,
            "overflow": max(len(files) - account.upload_batch_size, 0),
        }

    @app.post("/api/accounts/{account_id}/uploads/reset")
    async def reset_upload_batch(
        account_id: str,
        day: str | None = None,
        request: UploadResetRequest | None = None,
    ) -> dict:
        if engine.is_running or engine.upload_is_running:
            raise ConflictError("任务运行中不能重置发布记录")
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user or pipeline_queue_busy():
            raise ConflictError("完整流水线运行中不能重置发布记录")

        account = account_repository.get(account_id)
        day_value = day or date.today().isoformat()
        ensure_workflow_directories(account, day_value)
        directory = Path(account.output_dir) / day_value
        manifest = directory / ".uploaded.json"
        uploaded = set(json.loads(manifest.read_text(encoding="utf-8"))) if manifest.is_file() else set()
        requested = set(request.file_names if request else [])
        output_by_name = {
            path.name: str(path.resolve())
            for path in directory.glob("*.mp3")
            if path.is_file() and path.stat().st_size > 0
        }
        removed: list[str] = []
        for file_name in requested:
            resolved = output_by_name.get(Path(file_name).name)
            if resolved and resolved in uploaded:
                uploaded.remove(resolved)
                removed.append(file_name)

        manifest.write_text(
            json.dumps(sorted(uploaded), ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        return {"account_id": account_id, "day": day_value, "removed": removed}

    @app.post("/api/uploads/runs", status_code=202)
    async def start_upload(account_id: str, day: str | None = None, request: UploadStartRequest | None = None) -> dict:
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user or pipeline_queue_busy():
            raise ConflictError("完整流水线正在运行，请先停止后再启动单阶段上传")
        account = account_repository.get(account_id)
        day_value = day or date.today().isoformat()
        items = build_upload_items(
            account,
            day_value,
            selected_file_names=set(request.file_names) if request else None,
            ai_created=request.ai_created if request else True,
            real_name=request.real_name if request else None,
        )
        if not items:
            raise ValidationFailed("没有可上传歌曲；请确认成品文件名和歌词歌名一致")
        await login_browser.close()
        if request and request.auto_replace_noncompliant:
            return engine.start_upload(
                account,
                items,
                day_value,
                auto_replace_noncompliant=True,
            )
        return engine.start_upload(account, items, day_value)

    @app.post("/api/uploads/runs/retry-rejected", status_code=202)
    async def retry_rejected_upload(
        account_id: str,
        day: str | None = None,
        request: UploadRetryRejectedRequest | None = None,
    ) -> dict:
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user or pipeline_queue_busy():
            raise ConflictError("完整流水线正在运行，请先停止后再启动单阶段上传")
        account = account_repository.get(account_id)
        day_value = day or date.today().isoformat()
        items = build_upload_items(
            account,
            day_value,
            ai_created=request.ai_created if request else True,
            real_name=request.real_name if request else None,
        )
        if not items:
            raise ValidationFailed("没有待发布的歌曲")

        lyrics_by_name: dict[str, Path] = {}
        for lyric_path in list_lyric_files(Path(account.lyric_dir), day=day_value):
            try:
                parsed = parse_lyrics(lyric_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            lyrics_by_name[parsed.song_name] = lyric_path
        lyric_files: list[Path] = []
        missing_titles: list[str] = []
        for item in items:
            lyric_path = lyrics_by_name.get(str(item["title"]))
            if lyric_path is None:
                missing_titles.append(str(item["title"]))
            else:
                lyric_files.append(lyric_path)
        if missing_titles:
            raise ValidationFailed(
                "以下歌曲找不到对应歌词，无法重新生成: "
                + "、".join(missing_titles)
            )

        await login_browser.close()
        return engine.start_regeneration_upload(
            account,
            items,
            lyric_files,
            day_value,
            model_name=request.model_name if request else "自动",
            singer_name=request.singer_name if request else "老岩",
            auto_replace_noncompliant=True,
        )

    @app.get("/api/uploads/runs/current")
    async def current_upload(account_id: str | None = None) -> dict | None:
        if account_id and engine.current_upload and engine.current_upload.get("account_id") != account_id:
            return None
        return engine.current_upload

    @app.post("/api/uploads/runs/code")
    async def submit_upload_code(request: UploadCodeRequest) -> dict:
        return await engine.submit_upload_code(request.code)

    @app.post("/api/uploads/runs/stop")
    async def stop_upload() -> dict:
        return await engine.stop_upload()

    @app.post("/api/pipeline/runs", status_code=202)
    async def start_pipeline(request: PipelineStartRequest) -> dict:
        if engine.is_running or engine.upload_is_running:
            raise ConflictError("已有单阶段任务正在运行，请先停止后再启动完整流水线")
        if pipeline_queue_busy():
            raise ConflictError("多账号流水线队列正在运行")
        account = account_repository.get(request.account_id)
        template = lyric_template_repository.get(request.template_id)
        if template.account_id != account.id:
            raise ValidationFailed("歌词模板不属于该账号")
        day_value = request.day or date.today().isoformat()
        try:
            datetime.strptime(day_value, "%Y-%m-%d").date()
        except ValueError as error:
            raise ValidationFailed("日期格式必须是 YYYY-MM-DD") from error
        ensure_workflow_directories(account, day_value)
        snapshot = pipeline_engine.start(
            account,
            template,
            day=day_value,
            pause_before_upload=request.pause_before_upload,
            ai_created=request.ai_created,
            real_name=account.upload_real_name if request.real_name is None else request.real_name,
            **({"auto_replace_noncompliant": True} if request.auto_replace_noncompliant else {}),
        )
        return snapshot.model_dump(mode="json")

    @app.get("/api/pipeline/queue/options")
    async def pipeline_queue_options() -> dict:
        accounts = []
        for account in account_repository.list():
            templates = lyric_template_repository.list(account.id)
            accounts.append({
                "account_id": account.id,
                "account_name": account.account_name,
                "upload_real_name": account.upload_real_name,
                "templates": [
                    {
                        "template_id": template.id,
                        "template_name": template.name,
                        "generation_count": template.generation_count,
                    }
                    for template in templates
                ],
            })
        return {"accounts": accounts}

    @app.post("/api/pipeline/queue/runs", status_code=202)
    async def start_pipeline_queue(request: PipelineQueueStartRequest) -> dict:
        if engine.is_running or engine.upload_is_running:
            raise ConflictError("已有单阶段任务正在运行，请先停止后再启动多账号队列")
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user:
            raise ConflictError("单账号流水线正在运行，请先停止后再启动多账号队列")
        if pipeline_queue_busy():
            raise ConflictError("多账号流水线队列正在运行")

        entries: list[tuple[AccountConfig, LyricTemplateConfig]] = []
        account_ids: set[str] = set()
        for item in request.items:
            account = account_repository.get(item.account_id)
            template = lyric_template_repository.get(item.template_id)
            if template.account_id != account.id:
                raise ValidationFailed(f"模板不属于账号 {account.account_name}")
            if account.id in account_ids:
                raise ValidationFailed(f"队列中不能重复选择账号 {account.account_name}")
            account_ids.add(account.id)
            entries.append((account, template))

        day_value = request.day or date.today().isoformat()
        try:
            datetime.strptime(day_value, "%Y-%m-%d").date()
        except ValueError as error:
            raise ValidationFailed("日期格式必须是 YYYY-MM-DD") from error
        for account, _ in entries:
            ensure_workflow_directories(account, day_value)
        snapshot = pipeline_queue_engine.start(
            entries,
            day=day_value,
            pause_before_upload=request.pause_before_upload,
            ai_created=request.ai_created,
            real_name=request.real_name,
            **({"auto_replace_noncompliant": True} if request.auto_replace_noncompliant else {}),
        )
        return snapshot.model_dump(mode="json")

    @app.get("/api/pipeline/queue/runs/current")
    async def current_pipeline_queue(day: str | None = None) -> dict | None:
        if day and pipeline_queue_engine.current and pipeline_queue_engine.current.day != day:
            return None
        return pipeline_queue_engine.current.model_dump(mode="json") if pipeline_queue_engine.current else None

    @app.post("/api/pipeline/queue/runs/resume", status_code=202)
    async def resume_pipeline_queue() -> dict:
        return pipeline_queue_engine.resume().model_dump(mode="json")

    @app.post("/api/pipeline/queue/runs/stop", status_code=202)
    async def stop_pipeline_queue() -> dict:
        return (await pipeline_queue_engine.stop()).model_dump(mode="json")

    @app.get("/api/pipeline/runs/current")
    async def current_pipeline(day: str | None = None, account_id: str | None = None) -> dict | None:
        if day and pipeline_engine.current and pipeline_engine.current.day != day:
            return None
        if account_id and pipeline_engine.current and pipeline_engine.current.account_id != account_id:
            return None
        return pipeline_engine.current.model_dump(mode="json") if pipeline_engine.current else None

    @app.post("/api/pipeline/runs/refresh", status_code=202)
    async def refresh_pipeline() -> dict:
        if not pipeline_engine.current:
            raise ConflictError("暂无完整流水线记录")
        account = account_repository.get(pipeline_engine.current.account_id)
        snapshot = pipeline_engine.refresh(account)
        return snapshot.model_dump(mode="json") if snapshot else {}

    @app.post("/api/pipeline/runs/resume", status_code=202)
    async def resume_pipeline() -> dict:
        return pipeline_engine.resume().model_dump(mode="json")

    @app.post("/api/pipeline/runs/stop", status_code=202)
    async def stop_pipeline() -> dict:
        return (await pipeline_engine.stop()).model_dump(mode="json")

    @app.post("/api/runs", status_code=202)
    async def start_run(request: RunRequest) -> dict:
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user or pipeline_queue_busy():
            raise ConflictError("完整流水线正在运行，请先停止后再启动单阶段任务")
        account = account_repository.get(request.account_id)
        day = request.day or date.today().isoformat()
        ensure_workflow_directories(account, day)
        root = Path(account.lyric_dir)
        selected: list[Path] = []
        for file_name in request.song_files:
            path = (root / day / Path(file_name).name).resolve()
            if not path.is_file():
                raise NotFoundError(f"歌词文件不存在: {file_name}")
            selected.append(path)
        await login_browser.close()
        snapshot = engine.start(
            account,
            selected,
            day=day,
            fresh_run=request.fresh_run,
            model_name=request.model_name,
            singer_name=request.singer_name,
        )
        return snapshot.model_dump(mode="json")

    @app.post("/api/runs/control", status_code=202)
    async def control_run(request: RunControlRequest) -> dict:
        if engine.is_running:
            if request.action == "pause":
                await engine.pause()
            elif request.action == "resume":
                engine.resume()
            else:
                await engine.stop()
        return engine.current.model_dump(mode="json") if engine.current else {}

    @app.get("/api/runs/current")
    async def current_run(account_id: str | None = None) -> dict | None:
        if account_id and engine.current and engine.current.account_id != account_id:
            return None
        return engine.current.model_dump(mode="json") if engine.current else None

    @app.get("/api/logs/recent")
    async def recent_logs() -> list[dict]:
        return events.recent()

    @app.post("/api/folders/open", status_code=204)
    async def open_folder(request: FolderOpenRequest) -> None:
        folders = {
            "logs": paths.log_dir,
            "screenshots": paths.screenshot_dir,
            "data": paths.data_dir,
        }
        folder = folders[request.kind]
        folder.mkdir(parents=True, exist_ok=True)
        open_folder_on_windows(folder)

    @app.post("/api/folders/pick-account-root")
    async def pick_account_root() -> dict:
        selected = await asyncio.to_thread(
            pick_account_root_folder,
            str(Path.home() / "Music"),
        )
        return {"path": str(Path(selected).resolve()) if selected else ""}

    @app.post("/api/accounts/{account_id}/browser/open", status_code=202)
    async def open_login_browser(account_id: str) -> dict:
        if engine.is_running or engine.upload_is_running:
            raise AppError("任务运行中不能打开登录浏览器")
        if pipeline_engine.is_running or pipeline_engine.is_waiting_user or pipeline_queue_busy():
            raise AppError("完整流水线运行中不能打开登录浏览器")
        account = account_repository.get(account_id)
        await login_browser.open(account, settings)
        return {"account_id": account.id, "account_name": account.account_name}

    @app.post("/api/browser/close", status_code=204)
    async def close_login_browser() -> None:
        await login_browser.close()

    @app.get("/api/browser/current")
    async def current_login_browser() -> dict | None:
        account_id = login_browser.current_account_id
        if not account_id:
            return None
        account = account_repository.get(account_id)
        return {"account_id": account.id, "account_name": account.account_name}

    @app.get("/api/settings")
    async def get_settings() -> dict:
        return settings.model_dump(mode="json")

    @app.put("/api/settings")
    async def update_settings(request: ConsoleSettingsUpdate) -> dict:
        nonlocal settings
        if engine.is_running:
            raise AppError("任务运行中不能修改全局等待配置")
        updated = ConsoleSettings.model_validate(
            {**settings.model_dump(mode="json"), **request.model_dump(exclude_unset=True)}
        )
        engine.update_settings(updated)
        settings = updated
        settings_store.write(updated.model_dump(mode="json"))
        app.state.settings = updated
        return updated.model_dump(mode="json")

    @app.post("/api/settings/ai/test")
    async def test_ai_settings(request: AITestRequest) -> dict:
        return await test_ai_api_connection(
            base_url=request.ai_api_base_url,
            api_key=request.ai_api_key,
            model=request.ai_model,
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "ready", "data": events.recent()})
        async def send_event(event: dict) -> None:
            await websocket.send_json(event)

        unsubscribe = events.subscribe(send_event)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            unsubscribe()

    frontend_dir = (paths.resource_root or paths.project_root) / "frontend"
    if frontend_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(
                frontend_dir / "index.html",
                headers={"Cache-Control": "no-store"},
            )

    return app
