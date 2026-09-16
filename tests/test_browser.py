import asyncio
from pathlib import Path

import pytest

from backend.browser import (
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
async def test_chrome_session_cleanup_is_idempotent(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    session = ChromeSession(account, ConsoleSettings())
    session._process = FakeProcess()
    session.browser = FakeBrowser()
    session._playwright = FakePlaywright()
    browser = session.browser
    playwright = session._playwright
    process = session._process

    await session.cleanup()
    await session.cleanup()

    assert browser.closed_count == 1
    assert playwright.stopped_count == 1
    assert process.terminated


class FakeProcess:
    def __init__(self) -> None:
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


class FakePlaywright:
    def __init__(self) -> None:
        self.stopped_count = 0

    def stop(self) -> None:
        self.stopped_count += 1
