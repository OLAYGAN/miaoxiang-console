from pathlib import Path
from datetime import date

import pytest
from types import SimpleNamespace

from backend.errors import BrowserFlowError, GenerationLimitError
import backend.page_flow as page_flow_module
from backend.models import AccountConfig, ConsoleSettings, LyricData
from backend.page_flow import (
        PageFlow,
        archive_download,
        clear_and_type,
        is_login_challenge,
        refresh_asset_tabs,
        select_model,
        select_singer,
        verify_generated_song,
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


def test_detects_platform_login_challenge_text() -> None:
    logged_in_text = "灵感创作模式 专业模式 模型选择 自动 生成歌曲"
    challenge_text = "扫码登录 验证码登录 登录即代表同意用户协议"

    assert is_login_challenge(logged_in_text) is False
    assert is_login_challenge(challenge_text) is True


class FakeModelPage:
    def __init__(self, initial_text: str = "自动", switch_checked: bool = True) -> None:
        self.dropdown = FakeModelLocator("dropdown", self)
        self.switch = FakeModelLocator("switch", self)
        self.option = FakeModelLocator("option", self)
        self.dropdown_text = initial_text
        self.switch_checked = switch_checked
        self.calls: list[str] = []

    def locator(self, selector: str):
        if selector.startswith(".semi-select-option-custom"):
            return self.option
        if selector.startswith(".semi-select"):
            return self.dropdown
        if selector == ".semi-popover .semi-switch":
            return self.switch
        if selector.startswith(".semi-select-option-custom"):
            return self.option
        raise AssertionError(f"unexpected selector: {selector}")

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append("wait")

    async def evaluate(self, script: str) -> None:
        self.calls.append("scroll-model-list")


class FakeModelLocator:
    def __init__(self, name: str, page: FakeModelPage) -> None:
        self.name = name
        self.page = page

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        return self

    def locator(self, selector: str):
        if self.name == "item" and selector == "button":
            return self.page.choose
        raise AssertionError(f"unexpected nested selector: {selector}")

    async def inner_text(self) -> str:
        return self.page.dropdown_text

    async def get_attribute(self, name: str):
        if self.name == "switch" and name == "class":
            return "semi-switch semi-switch-checked" if self.page.switch_checked else "semi-switch"
        return None

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")
        if self.name == "switch":
            self.page.switch_checked = False
        if self.name == "option":
            self.page.dropdown_text = "Sway v5.5"

    async def scroll_into_view_if_needed(self, **kwargs) -> None:
        self.page.calls.append(f"scroll-{self.name}")


@pytest.mark.asyncio
async def test_select_model_closes_auto_switches_and_clicks_custom_option() -> None:
    page = FakeModelPage()

    await select_model(page, "Sway v5.5")

    assert page.calls == [
        "click-dropdown",
        "wait",
        "click-switch",
        "wait",
        "scroll-model-list",
        "scroll-option",
        "click-option",
        "wait",
    ]
    assert page.dropdown_text == "Sway v5.5"


@pytest.mark.asyncio
async def test_select_model_keeps_existing_choice() -> None:
    page = FakeModelPage(initial_text="Sway v5.5")

    await select_model(page, "Sway v5.5")

    assert page.calls == []


class FakeSingerPage:
    def __init__(self, trigger_text: str = "选择虚拟歌手音色", switch_checked: bool = False) -> None:
        self.switch = FakeSingerLocator("switch", self)
        self.trigger = FakeSingerLocator("trigger", self)
        self.item = FakeSingerLocator("item", self)
        self.choose = FakeSingerLocator("choose", self)
        self.trigger_text = trigger_text
        self.switch_checked = switch_checked
        self.calls: list[str] = []

    def locator(self, selector: str):
        if selector == '[class*="vocalTimbreWrapper"] .semi-switch':
            return self.switch
        if selector == '[class*="singerTrigger"]':
            return self.trigger
        if selector == '[class*="singerItem"]':
            return self.item
        if selector == 'button':
            return self.choose
        raise AssertionError(f"unexpected selector: {selector}")

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append("wait")


class FakeSingerLocator:
    def __init__(self, name: str, page: FakeSingerPage) -> None:
        self.name = name
        self.page = page

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        return self

    def locator(self, selector: str):
        if self.name == "item" and selector == "button":
            return self.page.choose
        raise AssertionError(f"unexpected nested selector: {selector}")

    async def inner_text(self) -> str:
        return self.page.trigger_text

    async def get_attribute(self, name: str):
        if self.name == "switch" and name == "class":
            return "semi-switch semi-switch-checked" if self.page.switch_checked else "semi-switch"
        return None

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")
        if self.name == "switch":
            self.page.switch_checked = True
        if self.name == "choose":
            self.page.trigger_text = "老岩 男低音 摇滚 Hiphop 沙哑 粗犷"


@pytest.mark.asyncio
async def test_select_singer_opens_switch_dialog_and_confirms_choice() -> None:
    page = FakeSingerPage()

    await select_singer(page, "老岩")

    assert page.calls == [
        "click-switch",
        "wait",
        "click-trigger",
        "wait",
        "click-choose",
        "wait",
    ]
    assert "老岩" in page.trigger_text


@pytest.mark.asyncio
async def test_select_singer_keeps_existing_choice() -> None:
    page = FakeSingerPage(trigger_text="老岩 男低音", switch_checked=True)

    await select_singer(page, "老岩")

    assert page.calls == []


class FakeAssetTabsPage:
    def __init__(self) -> None:
        self.tabs = FakeAssetTabsLocator(self)
        self.calls: list[str] = []

    def locator(self, selector: str):
        assert selector == '[class*="tabItem"]'
        return self.tabs

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append(f"wait-{timeout}")


class FakeAssetTabsLocator:
    def __init__(self, page: FakeAssetTabsPage) -> None:
        self.page = page

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        pattern = kwargs["has_text"]
        if "歌词" in pattern.pattern:
            return FakeAssetTab("lyric", self.page)
        if "歌曲" in pattern.pattern:
            return FakeAssetTab("song", self.page)
        raise AssertionError(f"unexpected tab pattern: {pattern.pattern}")


class FakeAssetTab:
    def __init__(self, name: str, page: FakeAssetTabsPage) -> None:
        self.name = name
        self.page = page

    @property
    def first(self):
        return self

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")


@pytest.mark.asyncio
async def test_refresh_asset_tabs_switches_lyrics_and_back_to_songs() -> None:
    page = FakeAssetTabsPage()

    await refresh_asset_tabs(page)

    assert page.calls == [
        "click-lyric",
        "wait-500",
        "click-song",
        "wait-1000",
    ]


@pytest.mark.asyncio
async def test_wait_for_generation_refreshes_assets_once_and_waits_for_title(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account

    class FakeClockPage:
        def __init__(self) -> None:
            self.clock = 0.0

        async def wait_for_timeout(self, timeout: int) -> None:
            self.clock += timeout / 1000

    fake_page = FakeClockPage()
    flow = PageFlow(
        page=fake_page,
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    refresh_times: list[float] = []

    async def refresh_assets(page) -> None:
        refresh_times.append(page.clock)

    async def read_generation_state() -> dict:
        if fake_page.clock >= 65:
            return {"title": "新课本", "has_placeholder": False}
        return {"title": "", "has_placeholder": True}

    monkeypatch.setattr(page_flow_module, "refresh_asset_tabs", refresh_assets)
    monkeypatch.setattr(flow, "asset_generation_state", read_generation_state)
    monkeypatch.setattr(
        page_flow_module,
        "datetime",
        SimpleNamespace(now=lambda: SimpleNamespace(timestamp=lambda: fake_page.clock)),
    )

    result = await flow.wait_for_generation("旧歌曲")

    assert result == "新课本"
    assert refresh_times == [0]


class FakeDetailPage:
    def __init__(self, detail_content: str) -> None:
        self.card = FakeDetailLocator("card", self)
        self.title = FakeDetailLocator("title", self)
        self.content = FakeDetailLocator("content", self)
        self.source_content = FakeDetailLocator("source_content", self)
        self.detail_content = detail_content
        self.source_content_text = "这一段是灵感来源，不是歌词"
        self.calls: list[str] = []
        self.filter_calls: list[dict] = []
        self.read_counts = {"source_content": 0, "content": 0}

    def locator(self, selector: str):
        if selector == '[class*="libraryItemWrapper"]':
            return self.card
        if selector == '[class*="detailPanel"] [class*="sectionTitle"]':
            return self.title
        if selector == '[class*="detailPanel"] [class*="sectionContent"]':
            return self.source_content
        raise AssertionError(f"unexpected selector: {selector}")

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append("wait")


class FakeDetailLocator:
    def __init__(self, name: str, page: FakeDetailPage) -> None:
        self.name = name
        self.page = page

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        if "visible" in kwargs:
            self.page.filter_calls.append(kwargs)
        return self

    def locator(self, selector: str):
        if self.name == "title" and selector.startswith("xpath=following-sibling"):
            return self.page.content
        raise AssertionError(f"unexpected nested selector from {self.name}: {selector}")

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")

    async def inner_text(self) -> str:
        if self.name in self.page.read_counts:
            self.page.read_counts[self.name] += 1
        if self.name == "source_content":
            return self.page.source_content_text
        return self.page.detail_content


@pytest.mark.asyncio
async def test_verify_generated_song_clicks_card_and_checks_lyric_content() -> None:
    page = FakeDetailPage(
        "歌名：《新课本》\n油 墨 还 没 散 尽！书 页 白 得 发 亮\n第一行 名字\n"
        "油 墨 还 没 散 尽！书 页 白 得 发 亮\n写 得 歪 歪 扭 扭"
    )

    await verify_generated_song(
        page,
        "油墨还没散尽，书页白得发亮。\n第一行名字\n"
        "油墨还没散尽，书页白得发亮。\n写得歪歪扭扭",
    )

    assert page.calls == ["click-card", "wait"]
    assert page.filter_calls == [{"visible": True}]
    assert page.read_counts == {"source_content": 0, "content": 1}


@pytest.mark.asyncio
async def test_verify_generated_song_ignores_structural_lyric_directives() -> None:
    page = FakeDetailPage(
        "油 墨 还 没 散 尽\n书 页 白 得 发 亮\n第一行 名字\n写 得 歪 歪 扭 扭"
    )

    await verify_generated_song(
        page,
        "[主歌1][成人独唱，温暖中低音男声rap]\n油墨还没散尽，书页白得发亮。\n"
        "第一行名字\n写得歪歪扭扭",
    )


@pytest.mark.asyncio
async def test_verify_generated_song_rejects_mismatched_lyric_content() -> None:
    page = FakeDetailPage("完全不同的歌词内容")

    with pytest.raises(BrowserFlowError, match="歌词详情不匹配"):
        await verify_generated_song(
            page,
            "油墨还没散尽，书页白得发亮。\n第一行名字\n油墨还没散尽，书页白得发亮。",
        )


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
    flow.verify_generated_song = lambda lyrics: step("verify_generated_song")
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
        "verify_generated_song",
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
        "verify_details",
        "enter_editor",
        "export_song",
        "download_song",
    ]
    assert result == tmp_path / "output" / date.today().isoformat() / "夜色引擎.mp3"


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
