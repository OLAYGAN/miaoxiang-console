"""FastAPI control surface for the local automation console."""

from collections.abc import Callable
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.browser import BrowserManager, ChromeSession
from backend.config import RuntimePaths, build_runtime_paths, ensure_runtime_directories, get_runtime_paths
from backend.errors import AppError, NotFoundError
from backend.events import EventBus
from backend.lyrics import list_lyric_files, parse_lyrics
from backend.models import AccountConfig, ConsoleSettings
from backend.page_flow import PageFlow
from backend.storage import AccountRepository, JsonStore, RunStateRepository
from backend.task_engine import TaskEngine


class AccountCopyRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=64)


class RunRequest(BaseModel):
    account_id: str
    song_files: list[str] = Field(min_length=1)
    day: str | None = None
    fresh_run: bool = False


class RunControlRequest(BaseModel):
    action: str = Field(pattern="^(pause|resume|stop)$")


class FolderOpenRequest(BaseModel):
    kind: str = Field(pattern="^(logs|screenshots|data)$")


class ConsoleSettingsUpdate(BaseModel):
    page_load_timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    generation_timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    editor_import_wait_seconds: int | None = Field(default=None, ge=1, le=120)
    export_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    download_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    log_history_limit: int | None = Field(default=None, ge=100, le=10000)


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
    settings_store = JsonStore(paths.settings_file, ConsoleSettings().model_dump(mode="json"))
    settings = ConsoleSettings.model_validate(settings_store.read())
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

    app = FastAPI(title="妙响自动化控制台", version="0.2.0")
    app.state.runtime_paths = paths
    app.state.accounts = account_repository
    app.state.run_state = state_repository
    app.state.settings_store = settings_store
    app.state.settings = settings
    app.state.events = events
    app.state.engine = engine
    login_browser = BrowserManager()
    app.state.login_browser = login_browser

    async def shutdown_engine() -> None:
        await login_browser.close()
        await engine.shutdown()

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

    @app.get("/api/accounts")
    async def list_accounts() -> list[dict]:
        return [account.model_dump(mode="json") for account in account_repository.list()]

    @app.post("/api/accounts", status_code=201)
    async def create_account(account: AccountConfig) -> dict:
        return account_repository.create(account).model_dump(mode="json")

    @app.get("/api/accounts/{account_id}")
    async def get_account(account_id: str) -> dict:
        return account_repository.get(account_id).model_dump(mode="json")

    @app.put("/api/accounts/{account_id}")
    async def update_account(account_id: str, account: AccountConfig) -> dict:
        return account_repository.update(account_id, account).model_dump(mode="json")

    @app.delete("/api/accounts/{account_id}", status_code=204)
    async def delete_account(account_id: str) -> None:
        account_repository.delete(account_id)

    @app.post("/api/accounts/{account_id}/copy")
    async def copy_account(account_id: str, request: AccountCopyRequest) -> dict:
        return account_repository.copy(account_id, request.account_name).model_dump(mode="json")

    @app.get("/api/accounts/{account_id}/songs")
    async def list_songs(account_id: str, day: str | None = None) -> list[dict]:
        account = account_repository.get(account_id)
        files = list_lyric_files(Path(account.lyric_dir), account.account_name, day=day)
        result: list[dict] = []
        for path in files:
            item = {
                "file_name": path.name,
                "path": str(path),
                "valid": False,
                "song_name": None,
                "error": None,
            }
            try:
                parsed = parse_lyrics(path.read_text(encoding="utf-8"))
                item.update(valid=True, song_name=parsed.song_name)
            except Exception as error:
                item["error"] = str(error)
            result.append(item)
        return result

    @app.post("/api/runs", status_code=202)
    async def start_run(request: RunRequest) -> dict:
        account = account_repository.get(request.account_id)
        root = Path(account.lyric_dir)
        selected: list[Path] = []
        for file_name in request.song_files:
            path = (root / (request.day or "") / account.account_name / Path(file_name).name).resolve()
            if not path.is_file():
                raise NotFoundError(f"歌词文件不存在: {file_name}")
            selected.append(path)
        await login_browser.close()
        snapshot = engine.start(
            account,
            selected,
            day=request.day,
            fresh_run=request.fresh_run,
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
    async def current_run() -> dict | None:
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

    @app.post("/api/accounts/{account_id}/browser/open", status_code=202)
    async def open_login_browser(account_id: str) -> dict:
        if engine.is_running:
            raise AppError("任务运行中不能打开登录浏览器")
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

    frontend_dir = paths.project_root / "frontend"
    if frontend_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    return app
