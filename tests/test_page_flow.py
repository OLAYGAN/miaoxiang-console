from pathlib import Path

import pytest

from backend.errors import BrowserFlowError, GenerationLimitError
from backend.models import AccountConfig, ConsoleSettings, LyricData
from backend.page_flow import (
        PageFlow,
        archive_download,
        clear_and_type,
        trusted_click,
        type_segmented,
)

from .test_task_engine import make_account


class FakeMouse:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def move(self, x: float, y: float, **kwargs) -> None:
        self.calls.append(("move", x, y))

    async def click(self, x: float, y: float, **kwargs) -> None:
        self.calls.append(("click", x, y))


class FakePage:
    def __init__(self) -> None:
        self.mouse = FakeMouse()

    async def wait_for_timeout(self, timeout: int) -> None:
        return None


class FakeLocator:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[str] = []

    async def bounding_box(self) -> dict:
        return {"x": 100, "y": 200, "width": 40, "height": 20}

    async def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        self.calls.append("scroll")

    async def click(self, **kwargs) -> None:
        self.calls.append("click")

    async def type(self, text: str, delay: int = 0) -> None:
        self.calls.append(("type", text, delay))

    async def press(self, key: str) -> None:
        self.calls.append(("press", key))

    async def fill(self, text: str) -> None:
        self.calls.append(("fill", text))


@pytest.mark.asyncio
async def test_trusted_click_moves_hovers_and_clicks_center() -> None:
    page = FakePage()
    locator = FakeLocator()

    await trusted_click(page, locator, "生成按钮", hover_ms=10)

    assert locator.calls == ["scroll"]
    assert page.mouse.calls == [("move", 120.0, 210.0), ("click", 120.0, 210.0)]


@pytest.mark.asyncio
async def test_type_segmented_uses_fifty_character_chunks() -> None:
    locator = FakeLocator()
    text = "a" * 115

    await type_segmented(locator, text, chunk_size=50, delay=1)

    assert locator.calls[0] == "click"
    assert locator.calls[1] == ("press", "Control+a")
    assert locator.calls[2] == ("press", "Delete")
    typed = [call for call in locator.calls if call[0] == "type"]
    assert [len(call[1]) for call in typed] == [50, 50, 15]


@pytest.mark.asyncio
async def test_clear_and_type_fills_and_verifies_length() -> None:
    locator = FakeLocator()
    locator.calls.clear()

    await clear_and_type(locator, "style text")

    assert ("press", "Control+a") in locator.calls
    assert ("type", "style text", 10) in locator.calls


def test_archive_download_moves_file_and_handles_collision(tmp_path: Path) -> None:
    downloaded = tmp_path / "downloaded.mp3"
    downloaded.write_bytes(b"audio")
    output_root = tmp_path / "成品"
    account = make_account(tmp_path)

    first = archive_download(downloaded, output_root, "夜色引擎", "2026-09-17")
    assert first == output_root / "2026-09-17" / "夜色引擎.mp3"
    assert first.read_bytes() == b"audio"
    assert not downloaded.exists()

    downloaded.write_bytes(b"audio2")
    second = archive_download(downloaded, output_root, "夜色引擎", "2026-09-17")
    assert second.name == "夜色引擎-2.mp3"
    assert second.read_bytes() == b"audio2"

    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    with pytest.raises(BrowserFlowError, match="下载文件为空"):
        archive_download(empty, output_root, "坏文件", "2026-09-17")


@pytest.mark.asyncio
async def test_process_song_runs_all_states_in_order(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    flow = PageFlow(page=FakePage(), account=account, settings=ConsoleSettings(), screenshot_dir=tmp_path)
    calls: list[str] = []
    steps: list[str] = []
    downloaded_file = tmp_path / "夜色引擎.mp3"
    downloaded_file.write_bytes(b"audio")

    async def ensure_create_page_ready():
        calls.append("ensure_create_page_ready")
        return None

    async def step(name):
        calls.append(name)
        if name == "first_asset_title":
            return "旧歌"
        if name == "wait_for_generation":
            return "新歌"
        if name == "download_song":
            return downloaded_file

    flow.ensure_create_page_ready = ensure_create_page_ready
    flow.fill_inputs = lambda lyric_data: step("fill_inputs")
    flow.first_asset_title = lambda: step("first_asset_title")
    flow.generate = lambda: step("generate")
    flow.check_generation_limit = lambda: step("check_generation_limit")
    flow.wait_for_generation = lambda before: step("wait_for_generation")
    flow.enter_editor = lambda song_name: step("enter_editor")
    flow.export_song = lambda song_name: step("export_song")
    flow.download_song = lambda song_name: step("download_song")

    result = await flow.process_song(
        LyricData(song_name="夜色引擎", lyrics="x" * 120, style="s" * 60),
        steps.append,
    )

    assert calls == [
        "ensure_create_page_ready",
        "fill_inputs",
        "first_asset_title",
        "generate",
        "check_generation_limit",
        "wait_for_generation",
        "enter_editor",
        "export_song",
        "download_song",
    ]
    assert steps == [
        "page_ready",
        "fill_inputs",
        "record_before",
        "generate",
        "check_limit",
        "wait_generation",
        "enter_editor",
        "export_song",
        "download_song",
    ]
    assert result == tmp_path / "output" / "2026-09-17" / "夜色引擎.mp3"


@pytest.mark.asyncio
async def test_process_song_propagates_generation_limit(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    flow = PageFlow(page=FakePage(), account=account, settings=ConsoleSettings(), screenshot_dir=tmp_path)

    async def ensure_create_page_ready():
        return None

    flow.ensure_create_page_ready = ensure_create_page_ready

    async def fill_inputs(lyric_data):
        return None

    async def first_asset_title():
        return "旧歌"

    async def generate():
        return None

    async def check_generation_limit():
        raise GenerationLimitError("上限")

    flow.fill_inputs = fill_inputs
    flow.first_asset_title = first_asset_title
    flow.generate = generate
    flow.check_generation_limit = check_generation_limit

    with pytest.raises(GenerationLimitError):
        await flow.process_song(
            LyricData(song_name="夜色引擎", lyrics="x" * 120, style="s" * 60),
            lambda step: None,
        )
