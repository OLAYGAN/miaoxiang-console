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
) -> list[str]:
    safe_profile = validate_profile_dir(profile)
    return [
        str(Path(executable)),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={safe_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
    ]


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
    def __init__(self, account: AccountConfig, settings: ConsoleSettings) -> None:
        self.account = account
        self.settings = settings
        self.browser: Any = None
        self.page: Any = None
        self._playwright: Any = None
        self._process: subprocess.Popen | None = None

    async def start(self) -> "ChromeSession":
        executable = resolve_chrome_executable()
        profile = Path(self.account.chrome_profile_dir)
        profile.mkdir(parents=True, exist_ok=True)
        command = build_chrome_command(
            executable,
            profile=profile,
            port=self.account.chrome_debug_port,
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
        if self.browser is not None:
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
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        self._process = None
        self.page = None

    async def __aenter__(self) -> "ChromeSession":
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await self.cleanup()
        return False
