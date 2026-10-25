import asyncio
from pathlib import Path

import pytest
import httpx

from backend.browser import (
    BrowserManager,
    ChromeSession,
    build_chrome_command,
    resolve_chrome_executable,
    validate_profile_dir,
    wait_for_cdp,
)
from backend.errors import BrowserFlowError
from backend.models import ConsoleSettings

from .test_task_engine import make_account


def test_resolve_chrome_executable_prefers_override_and_common_paths(
    tmp_path: Path,
) -> None:
    override = tmp_path / "chrome.exe"
    override.write_text("", encoding="utf-8")
    common = tmp_path / "common-chrome.exe"
    common.write_text("", encoding="utf-8")

    assert resolve_chrome_executable(override=override) == override
    assert resolve_chrome_executable(
        candidates=[tmp_path / "missing.exe", common],
    ) == common


def test_resolve_chrome_executable_rejects_missing_override(tmp_path: Path) -> None:
    with pytest.raises(BrowserFlowError, match="Chrome"):
        resolve_chrome_executable(override=tmp_path / "missing.exe")


def test_profile_dir_is_isolated_and_unsafe_roots_rejected(tmp_path: Path) -> None:
    account = make_account(tmp_path)

    assert account.chrome_profile_dir.endswith("账号01")
    with pytest.raises(BrowserFlowError, match="用户数据目录"):
        validate_profile_dir(Path("F:/"))
    with pytest.raises(BrowserFlowError, match="用户数据目录"):
        validate_profile_dir(Path.home())


def test_chrome_command_contains_isolation_and_debug_arguments(tmp_path: Path) -> None:
    executable = tmp_path / "chrome.exe"
    profile = tmp_path / "profiles" / "账号01"
    command = build_chrome_command(executable, profile=profile, port=9333)

    assert command[0] == str(executable)
    assert "--remote-debugging-port=9333" in command
    assert f"--user-data-dir={profile}" in command
    assert "--no-first-run" in command
    assert "--no-default-browser-check" in command
    assert "--disable-background-timer-throttling" in command


def test_hidden_chrome_command_uses_new_headless_mode(tmp_path: Path) -> None:
    executable = tmp_path / "chrome.exe"
    profile = tmp_path / "profiles" / "账号01"

    command = build_chrome_command(executable, profile=profile, port=9333, hidden=True)

    assert "--headless=new" in command
    assert "--window-size=1280,800" in command


@pytest.mark.asyncio
async def test_wait_for_cdp_has_bounded_attempts() -> None:
    calls: list[str] = []

    async def always_fail(url: str) -> dict:
        calls.append(url)
        raise ConnectionError("not ready")

    with pytest.raises(BrowserFlowError, match="Chrome 调试端口"):
        await wait_for_cdp(
            port=9333,
            fetch_json=always_fail,
            attempts=3,
            interval=0,
        )

    assert calls == ["http://127.0.0.1:9333/json/version"] * 3


@pytest.mark.asyncio
async def test_wait_for_cdp_returns_version() -> None:
    async def succeed(url: str) -> dict:
        return {"Browser": "Chrome/1"}

    result = await wait_for_cdp(port=9333, fetch_json=succeed, attempts=1, interval=0)
    assert result["Browser"] == "Chrome/1"


@pytest.mark.asyncio
async def test_cdp_availability_does_not_require_launching_chrome(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = ChromeSession(make_account(tmp_path), ConsoleSettings())

    async def available(**kwargs) -> dict:
        return {"Browser": "Chrome/1"}

    monkeypatch.setattr("backend.browser.wait_for_cdp", available)
    assert await session._cdp_available() is True

    async def unavailable(**kwargs) -> dict:
        raise BrowserFlowError("not ready")

    monkeypatch.setattr("backend.browser.wait_for_cdp", unavailable)
    assert await session._cdp_available() is False


@pytest.mark.asyncio
async def test_chrome_session_cleanup_is_idempotent(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    session = ChromeSession(account, ConsoleSettings())
    session._process = FakeProcess()
    session.browser = FakeBrowser()
    session._playwright = FakePlaywright()
    browser = session.browser
    playwright = session._playwright
    process = session._process
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "backend.browser.subprocess.run",
        lambda command, **kwargs: process.terminate(),
    )

    await session.cleanup()
    await session.cleanup()
    monkeypatch.undo()

    assert browser.closed_count == 1
    assert playwright.stopped_count == 1
    assert process.terminated


@pytest.mark.asyncio
async def test_chrome_session_cleanup_kills_windows_process_tree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    account = make_account(tmp_path)
    session = ChromeSession(account, ConsoleSettings())
    process = FakeProcess(pid=34567)
    session._process = process
    commands: list[list[str]] = []

    monkeypatch.setattr(
        "backend.browser.subprocess.run",
        lambda command, **kwargs: commands.append(command),
    )

    await session.cleanup()

    assert commands == [["taskkill", "/PID", "34567", "/T", "/F"]]


@pytest.mark.asyncio
async def test_hidden_cleanup_closes_only_attached_page(tmp_path: Path) -> None:
    session = ChromeSession(make_account(tmp_path), ConsoleSettings(), hidden=True)
    browser = FakeBrowser()
    page = FakePage()
    playwright = FakePlaywright()
    session.browser = browser
    session.page = page
    session._playwright = playwright
    session._connected_to_existing = True
    session._opened_page = True

    await session.cleanup()

    assert page.closed_count == 1
    assert browser.closed_count == 0
    assert playwright.stopped_count == 1


@pytest.mark.asyncio
async def test_cdp_health_check_bypasses_environment_proxy(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"Browser": "Chrome/1"}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    session = ChromeSession(make_account(tmp_path), ConsoleSettings())
    result = await session._fetch_json("http://127.0.0.1:9222/json/version")

    assert result == {"Browser": "Chrome/1"}
    assert captured["trust_env"] is False


@pytest.mark.asyncio
async def test_start_failure_still_terminates_chrome(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "chrome.exe"
    executable.write_text("", encoding="utf-8")
    process = FakeProcess()
    session = ChromeSession(make_account(tmp_path), ConsoleSettings())

    async def failed_wait(**kwargs):
        raise BrowserFlowError("Chrome 调试端口未就绪")

    monkeypatch.setattr("backend.browser.resolve_chrome_executable", lambda: executable)
    monkeypatch.setattr("backend.browser.subprocess.Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr("backend.browser.wait_for_cdp", failed_wait)

    with pytest.raises(BrowserFlowError, match="调试端口"):
        await session.start()

    assert process.terminated


@pytest.mark.asyncio
async def test_browser_manager_reuses_and_replaces_login_session(tmp_path: Path) -> None:
    sessions: list[FakeSession] = []

    def factory(account, settings):
        session = FakeSession(account.id)
        sessions.append(session)
        return session

    manager = BrowserManager(session_factory=factory)
    account = make_account(tmp_path)
    other = account.model_copy(update={"id": "other", "account_name": "账号02"})

    first = await manager.open(account, ConsoleSettings())
    same = await manager.open(account, ConsoleSettings())
    second = await manager.open(other, ConsoleSettings())
    await manager.close()
    await manager.close()

    assert first is same is sessions[0]
    assert second is sessions[1]
    assert sessions[0].started == 1
    assert sessions[0].cleaned == 1
    assert sessions[1].started == 1
    assert sessions[1].cleaned == 1
    assert manager.current is None


class FakeSession:
    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        self.started = 0
        self.cleaned = 0

    async def start(self):
        self.started += 1
        return self

    async def cleanup(self):
        self.cleaned += 1


class FakeProcess:
    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def poll(self) -> int | None:
        return None if not self.terminated else 0

    def wait(self, timeout: float | None = None) -> int:
        return 0


class FakeBrowser:
    def __init__(self) -> None:
        self.closed_count = 0

    async def close(self) -> None:
        self.closed_count += 1


class FakePage:
    def __init__(self) -> None:
        self.closed_count = 0

    async def close(self) -> None:
        self.closed_count += 1


class FakePlaywright:
    def __init__(self) -> None:
        self.stopped_count = 0

    async def stop(self) -> None:
        self.stopped_count += 1
