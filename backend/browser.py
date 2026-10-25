"""Chrome process and Playwright CDP session management."""

import asyncio
import inspect
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

from backend.errors import BrowserFlowError
from backend.models import AccountConfig, ConsoleSettings


DEFAULT_CHROME_CANDIDATES = (
    Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    Path(r"C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    Path(r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
)


def resolve_chrome_executable(
    override: Path | None = None,
    candidates: tuple[Path, ...] | list[Path] | None = None,
) -> Path:
    if override is not None:
        executable = Path(override).expanduser()
        if not executable.is_file():
            raise BrowserFlowError(f"Chrome 可执行文件不存在: {executable}")
        return executable.resolve()

    search = tuple(candidates or DEFAULT_CHROME_CANDIDATES)
    for candidate in search:
        if Path(candidate).is_file():
            return Path(candidate).resolve()
    searched = "\n".join(str(path) for path in search)
    raise BrowserFlowError(f"未找到 Chrome，可在设置中指定完整路径。已搜索:\n{searched}")


def validate_profile_dir(profile_dir: Path) -> Path:
    profile = Path(profile_dir).expanduser().resolve()
    home = Path.home().resolve()
    if profile == profile.parent or profile in {home, home.parent}:
        raise BrowserFlowError(f"Chrome 用户数据目录不安全: {profile}")
    return profile


def build_chrome_command(
    executable: Path,
    *,
    profile: Path,
    port: int,
    hidden: bool = False,
) -> list[str]:
    safe_profile = validate_profile_dir(profile)
    command = [
        str(Path(executable)),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={safe_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
    ]
    if hidden:
        command.extend(("--headless=new", "--window-size=1280,800"))
    return command


async def wait_for_cdp(
    *,
    port: int,
    fetch_json: Callable[[str], Any],
    attempts: int = 30,
    interval: float = 0.5,
) -> dict:
    url = f"http://127.0.0.1:{port}/json/version"
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            result = await fetch_json(url)
            if isinstance(result, dict):
                return result
        except Exception as error:
            last_error = error
        if interval:
            await asyncio.sleep(interval)
    detail = f": {last_error}" if last_error else ""
    raise BrowserFlowError(f"Chrome 调试端口未就绪 ({url}){detail}")


class ChromeSession:
    def __init__(
        self,
        account: AccountConfig,
        settings: ConsoleSettings,
        *,
        hidden: bool = False,
    ) -> None:
        self.account = account
        self.settings = settings
        self.hidden = hidden
        self.browser: Any = None
        self.page: Any = None
        self._playwright: Any = None
        self._process: subprocess.Popen | None = None
        self._connected_to_existing = False
        self._opened_page = False

    async def _cdp_available(self) -> bool:
        try:
            await wait_for_cdp(
                port=self.account.chrome_debug_port,
                fetch_json=self._fetch_json,
                attempts=1,
                interval=0,
            )
            return True
        except Exception:
            return False

    async def start(self) -> "ChromeSession":
        profile = Path(self.account.chrome_profile_dir)
        profile.mkdir(parents=True, exist_ok=True)
        self._connected_to_existing = await self._cdp_available()
        if not self._connected_to_existing:
            executable = resolve_chrome_executable()
            command = build_chrome_command(
                executable,
                profile=profile,
                port=self.account.chrome_debug_port,
                hidden=self.hidden,
            )
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(
                command,
                creationflags=creationflags,
                close_fds=True,
            )
        try:
            await wait_for_cdp(
                port=self.account.chrome_debug_port,
                fetch_json=self._fetch_json,
                attempts=30,
                interval=0.5,
            )
            self._playwright = await async_playwright().start()
            cdp_url = f"http://127.0.0.1:{self.account.chrome_debug_port}"
            self.browser = await self._playwright.chromium.connect_over_cdp(
                cdp_url,
                timeout=self.settings.page_load_timeout_seconds * 1000,
            )
            context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            if self.hidden:
                self.page = await context.new_page()
                self._opened_page = True
            else:
                self.page = context.pages[0] if context.pages else await context.new_page()
            await self.page.goto(
                self.account.create_url,
                wait_until="domcontentloaded",
                timeout=self.settings.page_load_timeout_seconds * 1000,
            )
            return self
        except Exception:
            await self.cleanup()
            raise

    async def _fetch_json(self, url: str) -> dict:
        # CDP is local; system proxy settings must not intercept 127.0.0.1.
        async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def cleanup(self) -> None:
        if self._opened_page and self.page is not None:
            try:
                await self.page.close()
            except Exception:
                pass
            self.page = None
        if self.browser is not None:
            if self._connected_to_existing:
                # Disconnect instead of closing a Chrome instance this process
                # did not launch.
                self.browser = None
            else:
                try:
                    await self.browser.close()
                except Exception:
                    pass
                self.browser = None
        if self._playwright is not None:
            try:
                result = self._playwright.stop()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                pass
            self._playwright = None
        if self._process is not None and self._process.poll() is None:
            self._terminate_process_tree(self._process)
        self._process = None
        self.page = None

    def _terminate_process_tree(self, process: subprocess.Popen) -> None:
        """Close Chrome's launcher and every child renderer/utility process."""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                    check=False,
                )
            except Exception:
                process.terminate()
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    async def __aenter__(self) -> "ChromeSession":
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await self.cleanup()
        return False


class BrowserManager:
    """Keeps at most one manually opened login browser."""

    def __init__(self, session_factory: Callable[[AccountConfig, ConsoleSettings], Any] | None = None) -> None:
        self._session_factory = session_factory
        self._session: Any = None
        self._account_id: str | None = None

    @property
    def current(self) -> Any:
        return self._session

    @property
    def current_account_id(self) -> str | None:
        return self._account_id

    async def open(self, account: AccountConfig, settings: ConsoleSettings) -> Any:
        if self._session is not None and self._account_id == account.id:
            return self._session
        await self.close()
        factory = self._session_factory or ChromeSession
        session = factory(account, settings)
        try:
            await session.start()
        except Exception:
            if hasattr(session, "cleanup"):
                await session.cleanup()
            raise
        self._session = session
        self._account_id = account.id
        return session

    async def close(self) -> None:
        session = self._session
        self._session = None
        self._account_id = None
        if session is not None and hasattr(session, "cleanup"):
            await session.cleanup()
