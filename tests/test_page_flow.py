from pathlib import Path
from datetime import date

import asyncio
import pytest
from types import SimpleNamespace
import re

from backend.errors import (
    BrowserFlowError,
    GenerationLimitError,
    SongGenerationFailureError,
    SongVerificationError,
)
import backend.page_flow as page_flow_module
from backend.models import AccountConfig, ConsoleSettings, LyricData
from backend.page_flow import (
        PageFlow,
        _detail_song_name,
        _lyric_probe,
        _normalize_generated_detail,
        archive_download,
        clear_and_type,
        is_login_challenge,
        refresh_asset_tabs,
        select_model,
        select_singer,
        verify_generated_song,
        export_song,
        open_download_menu,
        find_exported_download_card,
        new_cards_above_anchor,
        paste_text,
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
        self.wait_calls: list[int] = []
        self.url = "https://music.douyin.com/console/songs"
        self.frames = []
        self.context = SimpleNamespace(
            grant_permissions=lambda permissions: _completed_future(),
        )
        self.clipboard = ""

    async def wait_for_timeout(self, timeout: int) -> None:
        self.wait_calls.append(timeout)
        return None

    async def evaluate(self, script: str, *args: object) -> object:
        if "readText" in script:
            return {"ok": True, "text": self.clipboard}
        if "writeText" in script:
            self.clipboard = str(args[0])
            return None
        raise AssertionError(f"Unexpected evaluate script: {script}")


class FakeLocator:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[str] = []
        self.visible = True

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

    async def set_input_files(self, file_name: str, **kwargs) -> None:
        self.calls.append(("set_input_files", file_name))

    def filter(self, **kwargs) -> "FakeLocator":
        self.calls.append("filter")
        return self

    @property
    def first(self) -> "FakeLocator":
        return self

    async def input_value(self) -> str:
        return self.text

    async def is_visible(self) -> bool:
        return self.visible

    async def evaluate(self, script: str, value: object = None) -> None:
        self.text = str(value)


class FakeSequentialUploadPage(FakePage):
    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator("原创")


class FakeUploadAlbumPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.body_text = "发布全曲"

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator("")

    async def goto(self, url: str, **kwargs) -> None:
        self.calls = getattr(self, "calls", [])

    async def inner_text(self, selector: str = "body") -> str:
        return self.body_text


class FakeAuthorizationLocator:
    def __init__(self, mode: str, page: "FakeAuthorizationPage") -> None:
        self.mode = mode
        self.page = page

    @property
    def first(self) -> "FakeAuthorizationLocator":
        return self

    def filter(self, **kwargs) -> "FakeAuthorizationLocator":
        has_text = kwargs.get("has_text")
        if (
            self.mode == "option"
            and isinstance(has_text, re.Pattern)
            and "平台个人信息" in has_text.pattern
            and ("其它" in has_text.pattern or "其他" in has_text.pattern)
        ):
            self.mode = "alternative"
        return self

    async def count(self) -> int:
        if self.mode == "name": return len(self.page.names)
        if self.mode == "producer": return self.page.producer_count
        if self.mode == "link": return self.page.link_count
        if self.mode == "option": return self.page.option_count
        if self.mode == "alternative": return self.page.alternative_count
        return 0

    def nth(self, index: int) -> "FakeAuthorizationLocator":
        self.index = index
        return self

    async def input_value(self) -> str:
        return self.page.names[self.index]

    async def fill(self, value: str) -> None:
        self.page.names[self.index] = value

    async def click(self, timeout: int = 0) -> None:
        if self.mode == "producer":
            self.page.producer_count = 0
        if self.mode == "option":
            self.page.link_count = 0
            self.page.option_count = 0
        if self.mode == "alternative":
            self.page.link_count = 0
            self.page.alternative_count = 0


class FakeAuthorizationPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.names = ["tonyxx"]
        self.producer_count = 1
        self.link_count = 1
        self.option_count = 0
        self.alternative_count = 0

    def locator(self, selector: str) -> FakeAuthorizationLocator:
        if selector.startswith("input[placeholder"):
            mode = "name"
        elif selector.startswith(".douyin-music-select:visible"):
            mode = "link"
        elif "select-item" in selector or "option" in selector:
            mode = "option"
        else:
            mode = "producer"
        return FakeAuthorizationLocator(mode, self)

    async def evaluate(self, script: str, value: object = None) -> None:
        if "realName" in script:
            self.names = [str(value)]
        elif "添加自己" in script:
            self.producer_count = 0


def _completed_future() -> object:
    from asyncio import Future

    future = Future()
    future.set_result(None)
    return future


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


@pytest.mark.asyncio
async def test_paste_text_uses_clipboard_and_restores_previous_content() -> None:
    page = FakePage()
    page.clipboard = "用户原来的剪贴板"
    locator = FakeLocator("old value")

    async def press(key: str) -> None:
        locator.calls.append(("press", key))
        if key == "Control+v":
            locator.text = page.clipboard

    locator.press = press

    pasted = await paste_text(page, locator, "style text")

    assert pasted is True
    assert ("press", "Control+v") in locator.calls
    assert locator.text == "style text"
    assert page.clipboard == "用户原来的剪贴板"


@pytest.mark.asyncio
async def test_paste_text_falls_back_to_clear_and_type_when_clipboard_fails() -> None:
    page = FakePage()

    async def evaluate(script: str, *args: object) -> object:
        if "writeText" in script:
            raise PermissionError("clipboard denied")
        return await FakePage.evaluate(page, script, *args)

    page.evaluate = evaluate
    locator = FakeLocator()

    pasted = await paste_text(page, locator, "style text")

    assert pasted is False
    assert ("type", "style text", 10) in locator.calls


@pytest.mark.asyncio
async def test_upload_hidden_control_is_written_through_input_events(
    tmp_path: Path,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    locator = FakeLocator()
    locator.visible = False

    await flow._fill_upload_control(locator, "隐藏歌词输入")

    assert locator.text == "隐藏歌词输入"


@pytest.mark.asyncio
async def test_fill_upload_song_adds_next_song_without_waiting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakeSequentialUploadPage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    calls: list[str] = []

    async def add_next(index: int) -> None:
        calls.append(f"add-next:{index + 2}")

    async def wait_ready() -> None:
        calls.append("wait")

    monkeypatch.setattr(flow, "_add_next_upload_song", add_next)
    monkeypatch.setattr(flow, "_wait_upload_audio_ready", wait_ready)

    await flow._fill_upload_song(
        {"title": "第一首", "lyrics": "歌词", "path": str(tmp_path / "第一首.mp3")},
        0,
        is_last=False,
    )

    assert calls == ["add-next:2"]


@pytest.mark.asyncio
async def test_fill_authorization_uses_generic_no_link_options(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page = FakeAuthorizationPage()
    flow = PageFlow(
        page=page,
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    clicks: list[str] = []

    async def fake_click(page, locator, description, **kwargs):
        clicks.append(description)
        if description == "切换无主页链接":
            page.option_count = 1

    monkeypatch.setattr(page_flow_module, "trusted_click", fake_click)

    await flow._fill_authorization("甘斯敏")

    assert page.names == ["甘斯敏"]
    assert page.producer_count == 0
    assert page.link_count == 0
    assert clicks == ["切换无主页链接"]


@pytest.mark.asyncio
async def test_fill_authorization_skips_name_when_real_name_is_blank(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page = FakeAuthorizationPage()
    flow = PageFlow(
        page=page,
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    clicks: list[str] = []

    async def fake_click(page, locator, description, **kwargs):
        clicks.append(description)
        if description == "切换无主页链接":
            page.option_count = 1

    monkeypatch.setattr(page_flow_module, "trusted_click", fake_click)

    await flow._fill_authorization("")

    assert page.names == ["tonyxx"]
    assert page.producer_count == 0
    assert page.link_count == 0
    assert clicks == ["切换无主页链接"]


@pytest.mark.asyncio
async def test_fill_authorization_accepts_platform_info_without_homepage_link(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page = FakeAuthorizationPage()
    page.alternative_count = 1
    flow = PageFlow(
        page=page,
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )

    async def reject_old_dropdown(page, locator, description, **kwargs):
        raise AssertionError(f"不应再走旧下拉流程: {description}")

    monkeypatch.setattr(page_flow_module, "trusted_click", reject_old_dropdown)

    await flow._fill_authorization("龙英")

    assert page.link_count == 0
    assert page.alternative_count == 0


@pytest.mark.asyncio
async def test_upload_album_waits_for_all_files_after_album_info(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakeUploadAlbumPage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    calls: list[str] = []
    items = [
        {"title": "第一首", "path": "a.mp3", "lyrics": "a", "cover_prompt": "校园", "real_name": "李四"},
        {"title": "第二首", "path": "b.mp3", "lyrics": "b", "cover_prompt": "校园", "real_name": "李四"},
    ]

    async def configure(*args, **kwargs): calls.append("configure")
    async def fill_song(item, index, *, is_last): calls.append(f"fill-song:{index + 1}")
    async def use_cover(*args, **kwargs): calls.append("cover")
    async def wait_ready(): calls.append("wait-all")
    async def remove_noncompliant(): calls.append("remove"); return []
    async def song_states(): return [{"title": item["title"]} for item in items]
    async def wait_authorization(): calls.append("authorization-page")
    async def fill_authorization(*args, **kwargs): calls.append("authorization")
    async def submit_verification(*args, **kwargs): calls.append("verification")

    async def fake_click(page, locator, description, **kwargs):
        calls.append(f"click:{description}")

    monkeypatch.setattr(flow, "_configure_upload_ai_tools", configure)
    monkeypatch.setattr(flow, "_fill_upload_song", fill_song)
    monkeypatch.setattr(flow, "_use_smart_cover", use_cover)
    monkeypatch.setattr(flow, "_wait_upload_audio_ready", wait_ready)
    monkeypatch.setattr(flow, "_remove_noncompliant_upload_songs", remove_noncompliant)
    monkeypatch.setattr(flow, "_upload_song_states", song_states)
    monkeypatch.setattr(flow, "_wait_authorization_step", wait_authorization)
    monkeypatch.setattr(flow, "_fill_authorization", fill_authorization)
    monkeypatch.setattr(flow, "_submit_sign_verification", submit_verification)
    monkeypatch.setattr(page_flow_module, "trusted_click", fake_click)

    await flow.upload_album(
        items,
        lambda step, processed: calls.append(f"step:{step}"),
        lambda: _completed_future(),
    )

    assert calls.index("fill-song:2") < calls.index("cover")
    assert calls.index("cover") < calls.index("wait-all")
    assert calls.index("wait-all") < calls.index("remove")
    assert calls.index("remove") < calls.index("click:专辑下一步")
    assert calls.count("wait-all") == 1


@pytest.mark.asyncio
async def test_external_verification_polls_every_ten_seconds_until_popup_closes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    popup_states = [True, False, False]

    async def popup_visible():
        return popup_states.pop(0)

    async def publish_success_visible():
        return True

    monkeypatch.setattr(flow, "_verification_popup_visible", popup_visible)
    monkeypatch.setattr(flow, "_publish_success_visible", publish_success_visible)

    await flow._wait_for_external_verification()

    assert flow.page.wait_calls == [10000, 3000, 3000]


@pytest.mark.asyncio
async def test_external_verification_does_not_time_out_while_popup_stays_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )

    async def popup_visible():
        return True

    async def wait_for_timeout(timeout: int) -> None:
        flow.page.wait_calls.append(timeout)
        await asyncio.sleep(0)

    monkeypatch.setattr(flow, "_verification_popup_visible", popup_visible)
    monkeypatch.setattr(flow.page, "wait_for_timeout", wait_for_timeout)
    task = asyncio.create_task(flow._wait_for_external_verification())
    while len(flow.page.wait_calls) < 3:
        await asyncio.sleep(0)

    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_publish_completion_waits_for_review_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    confirmed = False

    async def success_visible():
        return confirmed

    async def wait_for_timeout(timeout: int) -> None:
        nonlocal confirmed
        flow.page.wait_calls.append(timeout)
        confirmed = True

    monkeypatch.setattr(flow, "_publish_success_visible", success_visible)
    monkeypatch.setattr(flow.page, "wait_for_timeout", wait_for_timeout)
    await flow._wait_publish_completion()

    assert flow.page.wait_calls == [3000, 3000]


@pytest.mark.asyncio
async def test_publish_completion_captures_success_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    captured: list[str] = []

    async def publish_success_visible():
        return True

    async def screenshot(step: str):
        captured.append(step)
        return tmp_path / f"{step}.png"

    monkeypatch.setattr(flow, "_publish_success_visible", publish_success_visible)
    monkeypatch.setattr(flow, "_screenshot", screenshot)

    await flow._wait_publish_completion()

    assert captured == ["upload-publish-success"]


@pytest.mark.asyncio
async def test_publish_completion_does_not_time_out_before_review_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    confirmed = False

    async def success_visible():
        return confirmed

    async def wait_for_timeout(timeout: int) -> None:
        flow.page.wait_calls.append(timeout)
        await asyncio.sleep(0)

    monkeypatch.setattr(flow, "_publish_success_visible", success_visible)
    monkeypatch.setattr(flow.page, "wait_for_timeout", wait_for_timeout)
    task = asyncio.create_task(flow._wait_publish_completion())
    while len(flow.page.wait_calls) < 3:
        await asyncio.sleep(0)

    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_enter_editor_refreshes_assets_and_retries_transient_card(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class RetryCard:
        def __init__(self) -> None:
            self.hovered = 0

        async def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
            return None

        async def hover(self, timeout: int = 0) -> None:
            self.hovered += 1

        def locator(self, selector: str) -> "FakeLocator":
            return FakeLocator("编辑")

    class RetryPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.url = "https://music.douyin.com/studio/create"

        def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
            return FakeLocator(text)

    flow = PageFlow(
        page=RetryPage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(editor_import_wait_seconds=1),
        screenshot_dir=tmp_path,
    )
    card = RetryCard()
    refreshes: list[int] = []

    async def visible_asset_card(song_name: str):
        if len(refreshes) == 0:
            return None
        return card

    async def refresh(page) -> None:
        refreshes.append(1)

    async def click(page, locator, description, **kwargs) -> None:
        page.url = "https://music.douyin.com/playground/editor"

    monkeypatch.setattr(flow, "_visible_asset_card", visible_asset_card)
    monkeypatch.setattr(page_flow_module, "refresh_asset_tabs", refresh)
    monkeypatch.setattr(page_flow_module, "trusted_click", click)

    await flow.enter_editor("闹钟响三遍")

    assert len(refreshes) == 1
    assert card.hovered == 1


def test_noncompliant_upload_song_detection() -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(Path.cwd()),
        settings=ConsoleSettings(),
        screenshot_dir=Path.cwd() / "screenshots",
    )

    rejected = {"index": 0, "title": "闹钟响三遍", "text": "音频结尾有明显截断感，请调整淡出效果后重新上传"}
    normal = {"index": 1, "title": "拐角有风", "text": "完整版\n拐角有风\n2.9MB"}

    assert flow._is_noncompliant_upload_song(rejected)
    assert not flow._is_noncompliant_upload_song(normal)


@pytest.mark.asyncio
async def test_remove_noncompliant_upload_songs_removes_rejected_cards_in_reverse_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    calls: list[int] = []
    states = [
        [
            {"index": 0, "title": "第一首", "text": "音频检测未通过，请重新上传"},
            {"index": 1, "title": "第二首", "text": "音频结尾有明显截断感，请调整淡出效果后重新上传"},
            {"index": 2, "title": "第三首", "text": "完整版 第三首 3.0MB"},
        ],
        [{"index": 0, "title": "第三首", "text": "完整版 第三首 3.0MB"}],
    ]

    async def upload_states():
        if states:
            return states.pop(0)
        return states[-1]

    async def remove_at(index: int):
        calls.append(index)

    monkeypatch.setattr(flow, "_upload_song_states", upload_states)
    monkeypatch.setattr(flow, "_remove_upload_song_at", remove_at)

    removed = await flow._remove_noncompliant_upload_songs()

    assert calls == [1, 0]
    assert removed == ["第二首", "第一首"]


@pytest.mark.asyncio
async def test_classify_generated_cards_matches_detail_song_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(
        song_name="本地歌名",
        lyrics=(
            "[Chorus 1]\n风 把 灯光 吹成 一 条 街\n"
            "[Verse 1]\n我们 把 昨天 放进 口袋"
        ),
        style="s" * 60,
    )

    async def read_detail(card_index: int) -> str:
        assert card_index == 0
        return "歌曲详情\n歌词\n歌名：《本地歌名》\n[Chorus 1]\n风 把 灯光 吹成 一 条 街"

    monkeypatch.setattr(flow, "_read_song_detail_for_card", read_detail)

    matches = await flow.classify_generated_cards(
        [{"title": "平台随机标题", "index": 0, "loading": False}],
        [lyric],
    )

    assert matches["本地歌名"][0].generated_title == "平台随机标题"


@pytest.mark.asyncio
async def test_export_alternate_version_skips_exported_card(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    selected: list[GeneratedCandidate] = []

    async def ensure_ready(): return None
    async def refresh_tabs(page): return None
    async def asset_states():
        return [
            {"index": 0, "title": "已导出随机标题", "source_tag": "编辑器导出", "exported": True, "loading": False},
            {"index": 1, "title": "第二版随机标题", "source_tag": "", "exported": False, "loading": False},
            {"index": 2, "title": "其它歌曲", "source_tag": "", "exported": False, "loading": False},
        ]

    async def read_detail(card_index: int) -> str:
        if card_index == 1:
            return "歌词\n歌名：《本地歌名》\n[Chorus 1]\n风"
        return "歌词\n歌名：《其它歌曲》\n[Chorus 1]\n风"

    async def export_candidate(candidate, lyric_data):
        selected.append(candidate)
        return tmp_path / "本地歌名.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr("backend.page_flow.refresh_asset_tabs", refresh_tabs)
    monkeypatch.setattr(flow, "asset_card_states", asset_states)
    monkeypatch.setattr(flow, "_read_song_detail_for_card", read_detail)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    result = await flow.export_alternate_version("本地歌名", "风 把 灯光 吹成 一 条 街")

    assert result == tmp_path / "本地歌名.mp3"
    assert len(selected) == 1
    assert selected[0].generated_title == "第二版随机标题"
    assert selected[0].card_index == 1


@pytest.mark.asyncio
async def test_process_batch_marks_unmatched_titles_as_terminal_skip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(song_name="第一首", lyrics="风 把 灯光 吹成 一 条 街", style="s" * 60)

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list): return {}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        return [{"title": "平台随机标题", "index": 0, "loading": False}]
    async def classify_generated_cards(cards, lyric_data_list): return {"第一首": []}

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(flow, "asset_card_states", lambda: [])
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)

    results = await flow.process_batch([lyric], lambda step, song=None: None)

    assert len(results) == 1
    assert results[0].song_name == "第一首"
    assert results[0].status == "title_unmatched"
    assert results[0].error == "歌曲详情歌名与歌词歌名不匹配，已跳过"


def test_archive_download_moves_file_and_overwrites_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(page_flow_module, "read_mp3_duration_seconds", lambda _: 61.0)
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
    assert second == first
    assert second.read_bytes() == b"audio2"

    same_path = output_root / "2026-09-17" / "同路径.mp3"
    same_path.write_bytes(b"same-path-audio")
    result = archive_download(same_path, output_root, "同路径", "2026-09-17")
    assert result == same_path
    assert result.read_bytes() == b"same-path-audio"

    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    with pytest.raises(BrowserFlowError, match="下载文件为空"):
        archive_download(empty, output_root, "坏文件", "2026-09-17")


def test_archive_download_rejects_song_shorter_than_sixty_seconds(tmp_path: Path) -> None:
    # MPEG 2.5 Layer III, 8 kbps, 8 kHz: each 72-byte frame is 0.072 seconds.
    frame = bytes([0xFF, 0xE3, 0x18, 0x00]) + b"\x00" * 68
    downloaded = tmp_path / "short.mp3"
    downloaded.write_bytes(frame * 800)
    output_root = tmp_path / "成品"
    destination = output_root / "2026-09-17" / "短歌.mp3"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old-valid-song")

    with pytest.raises(BrowserFlowError, match="音乐时长 57\\.6 秒，必须大于 60 秒"):
        archive_download(downloaded, output_root, "短歌", "2026-09-17")

    assert destination.read_bytes() == b"old-valid-song"
    assert downloaded.is_file()


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

    async def count(self) -> int:
        return 1

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


@pytest.mark.asyncio
async def test_select_singer_blank_skips_platform_singer_control() -> None:
    page = FakeSingerPage()

    await select_singer(page, "")

    assert page.calls == []


@pytest.mark.asyncio
async def test_create_page_ready_auto_model_skips_model_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeReadyLocator:
        @property
        def first(self):
            return self

        async def wait_for(self, **kwargs) -> None:
            return None

    class FakeReadyPage(FakePage):
        def locator(self, selector: str) -> FakeReadyLocator:
            assert selector == ".ql-editor"
            return FakeReadyLocator()

        async def goto(self, url: str, **kwargs) -> None:
            return None

        async def inner_text(self, selector: str = "body") -> str:
            return "创作页"

    account = make_account(tmp_path)
    flow = PageFlow(
        page=FakeReadyPage(),
        account=account,
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    calls: list[str] = []

    async def select_model() -> None:
        calls.append("model")

    async def select_singer() -> None:
        calls.append("singer")

    monkeypatch.setattr(flow, "select_model", select_model)
    monkeypatch.setattr(flow, "select_singer", select_singer)

    await flow.ensure_create_page_ready()

    assert calls == []


@pytest.mark.asyncio
async def test_create_page_ready_selects_singer_for_sway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeReadyLocator:
        @property
        def first(self):
            return self

        async def wait_for(self, **kwargs) -> None:
            return None

    class FakeReadyPage(FakePage):
        def locator(self, selector: str) -> FakeReadyLocator:
            assert selector == ".ql-editor"
            return FakeReadyLocator()

        async def goto(self, url: str, **kwargs) -> None:
            return None

        async def inner_text(self, selector: str = "body") -> str:
            return "创作页"

    flow = PageFlow(
        page=FakeReadyPage(),
        account=make_account(tmp_path).model_copy(update={"model_name": "Sway v5.5"}),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    calls: list[str] = []

    async def select_model() -> None:
        calls.append("model")

    async def select_singer() -> None:
        calls.append("singer")

    monkeypatch.setattr(flow, "select_model", select_model)
    monkeypatch.setattr(flow, "select_singer", select_singer)

    await flow.ensure_create_page_ready()

    assert calls == ["model", "singer"]


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

    async def count(self) -> int:
        return 2

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

    async def count(self) -> int:
        return 1

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")


def test_detail_song_name_is_read_from_explicit_title_line() -> None:
    detail = "歌曲详情\n歌词\n歌名：《一只耳机》\n[Chorus 1]\n一只 耳机 躺 在 抽屉"

    assert _detail_song_name(detail) == "一只耳机"


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
async def test_refresh_asset_tabs_supports_new_button_tabs() -> None:
    class NewAssetTabsPage:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def locator(self, selector: str):
            assert selector in {
                '[class*="tabItem"]',
                'button:visible, [role="tab"]:visible',
            }
            return NewAssetTabsLocator(self)

        async def wait_for_timeout(self, timeout: int) -> None:
            self.calls.append(f"wait-{timeout}")

    class NewAssetTabsLocator:
        def __init__(self, page: NewAssetTabsPage) -> None:
            self.page = page

        async def count(self) -> int:
            return 0 if self.page.calls == [] else 4

        def filter(self, **kwargs):
            pattern = kwargs["has_text"]
            if "歌词" in pattern.pattern:
                return NewAssetTab("lyric", self.page)
            if "歌曲" in pattern.pattern:
                return NewAssetTab("song", self.page)
            if "生成结果" in pattern.pattern:
                return NewAssetTab("generation", self.page)
            raise AssertionError(f"unexpected tab pattern: {pattern.pattern}")

    class NewAssetTab:
        def __init__(self, name: str, page: NewAssetTabsPage) -> None:
            self.name = name
            self.page = page

        @property
        def first(self):
            return self

        async def count(self) -> int:
            return 1 if self.name == "generation" else 0

        async def click(self, **kwargs) -> None:
            self.page.calls.append(f"click-{self.name}")

    page = NewAssetTabsPage()

    await refresh_asset_tabs(page)

    assert page.calls == [
        "click-generation",
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
        if selector == '[class*="detailLyricsSection"]':
            return FakeDetailLocator("missing", self)
        if selector == '[class*="libraryItemWrapper"], [class*="generatedSongListItem"]':
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
        if self.name == "card" and selector == '[class*="title"]':
            return FakeDetailLocator("card-title", self.page)
        raise AssertionError(f"unexpected nested selector from {self.name}: {selector}")

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")

    async def count(self) -> int:
        return 0 if self.name == "missing" else 1

    async def inner_text(self) -> str:
        if self.name in self.page.read_counts:
            self.page.read_counts[self.name] += 1
        if self.name == "source_content":
            return self.page.source_content_text
        if self.name == "card-title":
            return self.page.detail_content
        return self.page.detail_content


@pytest.mark.asyncio
async def test_verify_generated_song_matches_asset_list_title() -> None:
    page = FakeDetailPage("新课本")

    await verify_generated_song(
        page,
        "平台模型可以改写这些歌词内容",
        song_name="新课本",
    )

    assert page.calls == []
    assert page.filter_calls == [{"visible": True}]
    assert page.read_counts == {"source_content": 0, "content": 0}


@pytest.mark.asyncio
async def test_verify_generated_song_without_title_remains_compatible() -> None:
    page = FakeDetailPage("任意内容")

    await verify_generated_song(
        page,
        "旧调用方未提供歌名时不打开详情",
    )

    assert page.calls == []


@pytest.mark.asyncio
async def test_verify_generated_song_rejects_different_asset_title() -> None:
    page = FakeDetailPage("另一首歌")

    with pytest.raises(SongVerificationError, match="生成结果名称不匹配"):
        await verify_generated_song(
            page,
            "平台模型可以改写这些歌词内容",
            song_name="新课本",
        )


@pytest.mark.asyncio
class FakeExportPage:
    def __init__(self) -> None:
        self.url = "https://music.douyin.com/studio/playground"
        self.top_export = FakeExportLocator("top-export", self)
        self.modal = FakeExportLocator("modal", self)
        self.name_input = FakeExportLocator("name-input", self)
        self.confirm = FakeExportLocator("confirm", self)
        self.calls: list[str] = []
        self.locator_calls: list[str] = []

    def locator(self, selector: str):
        self.locator_calls.append(selector)
        if selector == "button":
            return self.top_export
        if selector == ".semi-modal-content":
            return self.modal
        raise AssertionError(f"unexpected page selector: {selector}")

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append(f"wait-{timeout}")


class FakeExportLocator:
    def __init__(self, name: str, page: FakeExportPage) -> None:
        self.name = name
        self.page = page

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def filter(self, **kwargs):
        self.page.calls.append(f"filter-{self.name}")
        return self

    def locator(self, selector: str):
        if self.name == "modal" and selector == "input.semi-input":
            return self.page.name_input
        if self.name == "modal" and selector == ".semi-modal-footer button":
            return self.page.confirm
        raise AssertionError(f"unexpected modal selector: {selector}")

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")
        if self.name == "confirm":
            self.page.url = "https://music.douyin.com/studio/assets"

    async def press(self, key: str) -> None:
        self.page.calls.append(f"press-{self.name}-{key}")

    async def type(self, text: str, delay: int = 0) -> None:
        self.page.calls.append(f"type-{self.name}-{text}")

    async def input_value(self) -> str:
        return "新课本"


@pytest.mark.asyncio
async def test_export_song_uses_modal_name_input_and_footer_button() -> None:
    page = FakeExportPage()

    await export_song(page, "新课本", timeout_seconds=1)

    assert "click-top-export" in page.calls
    assert "press-name-input-Control+a" in page.calls
    assert "press-name-input-Delete" in page.calls
    assert "type-name-input-新课本" in page.calls
    assert "click-confirm" in page.calls
    assert page.url.endswith("/assets")


class FakeDownloadPage:
    def __init__(self) -> None:
        self.result_tab = FakeDownloadLocator("result-tab", self)
        self.card = FakeDownloadLocator("card", self)
        self.trigger = FakeDownloadLocator("trigger", self)
        self.download_item = FakeDownloadLocator("download-item", self)
        self.mouse = FakeDownloadMouse()
        self.calls: list[str] = []

    def locator(self, selector: str):
        if selector == "button":
            return self.result_tab
        if selector == '[class*="generatedSongCard"]':
            return self.card
        if selector == '[role="menuitem"]':
            return self.download_item
        raise AssertionError(f"unexpected selector: {selector}")

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append(f"wait-{timeout}")


class FakeDownloadLocator:
    def __init__(self, name: str, page: FakeDownloadPage) -> None:
        self.name = name
        self.page = page

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def filter(self, **kwargs):
        self.page.calls.append(f"filter-{self.name}")
        return self

    def locator(self, selector: str):
        if self.name == "card" and selector == "div[class*='trigger']":
            return self.page.trigger
        raise AssertionError(f"unexpected nested selector: {selector}")

    async def hover(self, **kwargs) -> None:
        self.page.calls.append(f"hover-{self.name}")

    async def click(self, **kwargs) -> None:
        self.page.calls.append(f"click-{self.name}")

    async def scroll_into_view_if_needed(self, **kwargs) -> None:
        self.page.calls.append(f"scroll-{self.name}")

    async def bounding_box(self) -> dict:
        return {"x": 100, "y": 200, "width": 28, "height": 28}


class FakeDownloadMouse:
    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    async def click(self, x: float, y: float, **kwargs) -> None:
        self.clicks.append((x, y))


@pytest.mark.asyncio
async def test_open_download_menu_uses_generated_card_trigger_and_menu_item() -> None:
    page = FakeDownloadPage()

    item = await open_download_menu(page, "新课本")

    assert item is page.download_item
    assert "click-result-tab" in page.calls
    assert "filter-card" in page.calls
    assert "hover-trigger" in page.calls
    assert page.mouse.clicks == [(114.0, 214.0)]
    assert "filter-download-item" in page.calls


class FakeExportCardLocator:
    def __init__(self, name: str, text: str = "", children: dict[str, "FakeExportCardLocator"] | None = None):
        self.name = name
        self.text = text
        self.children = children or {}
        self.clicked = False

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        return self

    async def count(self) -> int:
        return 1

    def locator(self, selector: str):
        if selector in self.children:
            return self.children[selector]
        raise AssertionError(f"unexpected selector from {self.name}: {selector}")

    async def inner_text(self) -> str:
        return self.text

    async def click(self, **kwargs) -> None:
        self.clicked = True


class FakeExportCardsLocator:
    def __init__(self, cards):
        self.cards = cards

    def filter(self, **kwargs):
        return self

    async def count(self) -> int:
        return len(self.cards)

    def nth(self, index: int):
        return self.cards[index]


class FakeExportDetailPage:
    def __init__(self, cards, detail_title, detail_lyrics):
        self.cards_locator = FakeExportCardsLocator(cards)
        self.detail_title = FakeExportCardLocator("detail-title", detail_title)
        self.detail_lyrics = FakeExportCardLocator("detail-lyrics", detail_lyrics)

    def locator(self, selector: str):
        if selector == '[class*="detailLyricsSection"]':
            return FakeExportMissingLocator()
        if selector == '[class*="generatedSongCard"]':
            return self.cards_locator
        if selector == '[class*="detailPanel"] [class*="infoTitle"]':
            return self.detail_title
        if selector == '[class*="detailPanel"] [class*="sectionTitle"]':
            return FakeExportCardLocator(
                "lyric-title",
                children={"xpath=following-sibling::*[contains(@class,'sectionContent')][1]": self.detail_lyrics},
            )
        raise AssertionError(f"unexpected page selector: {selector}")


class FakeExportMissingLocator:
    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 0

    async def inner_text(self) -> str:
        raise AssertionError("new detail section should not be read when absent")


@pytest.mark.asyncio
async def test_find_exported_download_card_uses_title_without_details() -> None:
    raw = FakeExportCardLocator(
        "raw",
        children={
            '[class*="sourceTag"]': FakeExportCardLocator("raw-source", "老岩"),
            '[class*="title"]': FakeExportCardLocator("raw-title", "新课本"),
        },
    )
    exported = FakeExportCardLocator(
        "exported",
        children={
            '[class*="sourceTag"]': FakeExportCardLocator("export-source", "编辑器导出"),
            '[class*="title"]': FakeExportCardLocator("export-title", "新课本"),
        },
    )
    page = FakeExportDetailPage(
        [raw, exported],
        "新课本",
        "歌名：《新课本》\n平台模型改写后的歌词内容",
    )

    result = await find_exported_download_card(page, "新课本", "油墨还没散尽，书页白得发亮。第一行名字")

    assert result is exported
    assert exported.clicked is False
    assert raw.clicked is False


@pytest.mark.asyncio
async def test_process_batch_exports_newest_matching_candidate_per_lyric(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    calls: list[str] = []
    submitted: list[str] = []
    first = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)
    second = LyricData(song_name="第二首", lyrics="b" * 120, style="s" * 60)

    async def ensure_ready():
        calls.append("ready")

    async def recover_existing_candidates(lyric_data_list):
        return {}

    async def fill_inputs(lyric_data):
        submitted.append(lyric_data.song_name)

    async def generate():
        calls.append("generate")

    async def check_limit():
        calls.append("check-limit")

    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        assert baseline_count == 5
        assert lyric_count == 2
        return [
            {"title": "第二首版本一", "loading": False},
            {"title": "第二首版本二", "loading": False},
            {"title": "第一首版本一", "loading": False},
            {"title": "第一首版本二", "loading": False},
        ]

    async def classify_generated_cards(cards, lyric_data_list):
        return {
            "第一首": [
                GeneratedCandidate(song_name="第一首", generated_title="第一首版本二", card_index=3),
                GeneratedCandidate(song_name="第一首", generated_title="第一首版本一", card_index=2),
            ],
            "第二首": [
                GeneratedCandidate(song_name="第二首", generated_title="第二首版本一", card_index=0),
            ],
        }

    async def export_candidate(candidate, lyric_data):
        calls.append(f"export:{candidate.generated_title}:{lyric_data.song_name}")
        return tmp_path / f"{lyric_data.song_name}.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(
        flow,
        "asset_card_states",
        lambda: [
            {"index": 0, "title": "旧锚点", "loading": False},
        ] + [{"index": i, "title": f"旧歌{i}", "loading": False} for i in range(1, 5)],
    )
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([first, second], lambda step, song=None: calls.append(step))

    assert submitted == ["第一首", "第二首"]
    assert calls == [
        "page_ready", "ready", "recover_existing_generation",
        "fill_inputs", "generate", "generate", "check_limit", "check-limit",
        "fill_inputs", "generate", "generate", "check_limit", "check-limit",
        "wait_generation", "match_titles",
        "export_song", "export:第一首版本二:第一首",
        "export_song", "export:第二首版本一:第二首",
    ]
    assert [result.status for result in results] == ["success", "success"]
    assert [result.output_path for result in results] == [
        str(tmp_path / "第一首.mp3"), str(tmp_path / "第二首.mp3")
    ]


@pytest.mark.asyncio
async def test_process_batch_reports_missing_and_export_failures_separately(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    first = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)
    second = LyricData(song_name="第二首", lyrics="b" * 120, style="s" * 60)

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list): return {}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        return [{"title": "第一首版本", "loading": False}]
    async def classify_generated_cards(cards, lyric_data_list):
        return {"第一首": [GeneratedCandidate(song_name="第一首", generated_title="第一首版本", card_index=0)]}

    async def export_candidate(candidate, lyric_data):
        if lyric_data.song_name == "第一首":
            raise BrowserFlowError("下载失败")
        return tmp_path / "第二首.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(flow, "asset_card_states", lambda: [])
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([first, second], lambda step, song=None: None)

    assert results[0].status == "export_failed"
    assert "下载失败" in results[0].error
    assert results[1].status == "title_unmatched"
    assert results[1].error == "歌曲详情歌名与歌词歌名不匹配，已跳过"


@pytest.mark.asyncio
async def test_process_batch_classifies_platform_generation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list): return {}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        return [{"title": "第一首版本", "loading": False}]
    async def classify_generated_cards(cards, lyric_data_list):
        return {"第一首": [GeneratedCandidate(song_name="第一首", generated_title="第一首版本", card_index=0)]}

    async def export_candidate(candidate, lyric_data):
        raise SongGenerationFailureError("平台提示生成失败: 歌曲生成失败")

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(flow, "asset_card_states", lambda: [])
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([lyric], lambda step, song=None: None)

    assert results[0].status == "generation_failed"
    assert "平台提示生成失败" in results[0].error


@pytest.mark.asyncio
async def test_process_batch_retries_transient_export_failure_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)
    export_calls = 0

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list): return {}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        return [{"title": "第一首版本", "loading": False}]
    async def classify_generated_cards(cards, lyric_data_list):
        return {"第一首": [GeneratedCandidate(song_name="第一首", generated_title="第一首版本", card_index=0)]}

    async def export_candidate(candidate, lyric_data):
        nonlocal export_calls
        export_calls += 1
        if export_calls == 1:
            raise BrowserFlowError("导出弹窗未打开")
        return tmp_path / "第一首.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(flow, "asset_card_states", lambda: [])
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([lyric], lambda step, song=None: None)

    assert export_calls == 2
    assert results[0].status == "success"


@pytest.mark.asyncio
async def test_export_song_checks_platform_generation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )

    async def failure_message():
        return "歌曲生成失败"

    monkeypatch.setattr(flow, "_visible_generation_failure", failure_message)
    with pytest.raises(SongGenerationFailureError, match="平台提示生成失败"):
        await flow.export_song("第一首")


@pytest.mark.asyncio
async def test_visible_generation_failure_detects_description_rejection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )

    async def failure_message():
        return "无法根据描述生成，请修改"

    monkeypatch.setattr(flow, "_visible_generation_failure", failure_message)
    with pytest.raises(SongGenerationFailureError, match="无法根据描述生成"):
        await flow.export_song("第一首")


@pytest.mark.asyncio
async def test_process_batch_marks_description_rejection_without_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list): return {}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None

    async def ensure_no_failure():
        raise SongGenerationFailureError("平台提示生成失败: 无法根据描述生成，请修改")

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "_ensure_no_generation_failure", ensure_no_failure)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(flow, "asset_card_states", lambda: [])

    results = await flow.process_batch([lyric], lambda step, song=None: None)

    assert len(results) == 1
    assert results[0].song_name == "第一首"
    assert results[0].status == "description_rejected"
    assert results[0].output_path is None
    assert "无法根据描述生成" in (results[0].error or "")


@pytest.mark.asyncio
async def test_visible_generation_failure_reads_description_rejection_from_page_body(
    tmp_path: Path,
) -> None:
    class DescriptionFailurePage(FakePage):
        async def inner_text(self, selector: str = "body") -> str:
            assert selector == "body"
            return "生成区域提示：无法根据描述生成，请修改"

    flow = PageFlow(
        page=DescriptionFailurePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )

    assert await flow._visible_generation_failure() == "无法根据描述生成，请修改"


@pytest.mark.asyncio
async def test_process_batch_recovers_preexisting_generations_before_submitting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    first = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)
    second = LyricData(song_name="第二首", lyrics="b" * 120, style="s" * 60)
    submitted: list[str] = []

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list):
        return {
            "第一首": [
                GeneratedCandidate(song_name="第一首", generated_title="已有生成结果", card_index=0)
            ]
        }
    async def fill_inputs(lyric_data): submitted.append(lyric_data.song_name)
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        assert lyric_count == 1
        return [{"title": "第二首版本", "index": 0, "loading": False}]
    async def classify_generated_cards(cards, lyric_data_list):
        return {
            "第二首": [
                GeneratedCandidate(song_name="第二首", generated_title="第二首版本", card_index=0)
            ]
        }
    async def export_candidate(candidate, lyric_data):
        return tmp_path / f"{lyric_data.song_name}.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(
        flow,
        "asset_card_states",
        lambda: [{"index": i, "title": f"旧歌{i}", "loading": False} for i in range(10)],
    )
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([first, second], lambda step, song=None: None)

    assert submitted == ["第二首"]
    assert [result.status for result in results] == ["success", "success"]


@pytest.mark.asyncio
async def test_process_batch_keeps_new_matches_when_recovery_has_empty_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list):
        return {"第一首": []}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        return [{"title": "第一首版本", "index": 0, "loading": False}]
    async def classify_generated_cards(cards, lyric_data_list):
        return {
            "第一首": [
                GeneratedCandidate(
                    song_name="第一首",
                    generated_title="第一首版本",
                    card_index=0,
                )
            ]
        }
    async def export_candidate(candidate, lyric_data):
        return tmp_path / f"{lyric_data.song_name}.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(flow, "asset_card_states", lambda: [])
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([lyric], lambda step, song=None: None)

    assert results[0].status == "success"


@pytest.mark.asyncio
async def test_process_batch_reclassifies_settled_assets_before_declaring_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    flow.classification_retry_delay_ms = 0
    first = LyricData(song_name="第一首", lyrics="a" * 120, style="s" * 60)
    second = LyricData(song_name="第二首", lyrics="b" * 120, style="s" * 60)
    classification_calls: list[list[str]] = []

    async def ensure_ready(): return None
    async def recover_existing_candidates(lyric_data_list): return {}
    async def fill_inputs(lyric_data): return None
    async def generate(): return None
    async def check_limit(): return None
    async def wait_for_batch_generation(baseline_count, lyric_count, baseline_anchor=None):
        return [
            {"index": 0, "title": "第一首版本", "loading": False},
            {"index": 1, "title": "第二首版本", "loading": False},
        ]

    async def classify_generated_cards(cards, lyric_data_list):
        names = [item.song_name for item in lyric_data_list]
        classification_calls.append(names)
        if len(classification_calls) == 1:
            return {"第一首": [
                GeneratedCandidate(song_name="第一首", generated_title="第一首版本", card_index=0)
            ]}
        return {
            "第一首": [
                GeneratedCandidate(song_name="第一首", generated_title="第一首版本", card_index=0)
            ],
            "第二首": [
                GeneratedCandidate(song_name="第二首", generated_title="第二首版本", card_index=1)
            ],
        }

    async def export_candidate(candidate, lyric_data):
        return tmp_path / f"{lyric_data.song_name}.mp3"

    monkeypatch.setattr(flow, "ensure_create_page_ready", ensure_ready)
    monkeypatch.setattr(flow, "recover_existing_candidates", recover_existing_candidates)
    monkeypatch.setattr(flow, "fill_inputs", fill_inputs)
    monkeypatch.setattr(flow, "generate", generate)
    monkeypatch.setattr(flow, "check_generation_limit", check_limit)
    monkeypatch.setattr(
        flow,
        "asset_card_states",
        lambda: [
            {"index": 0, "title": "第一首版本", "loading": False},
            {"index": 1, "title": "第二首版本", "loading": False},
            {"index": 2, "title": "旧锚点", "loading": False},
        ],
    )
    monkeypatch.setattr(flow, "wait_for_batch_generation", wait_for_batch_generation)
    monkeypatch.setattr(flow, "classify_generated_cards", classify_generated_cards)
    monkeypatch.setattr(flow, "export_candidate", export_candidate)

    results = await flow.process_batch([first, second], lambda step, song=None: None)

    assert len(classification_calls) == 2
    assert [result.status for result in results] == ["success", "success"]


@pytest.mark.asyncio
async def test_recover_existing_candidates_includes_completed_top_cards(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from .test_task_engine import make_account
    from backend.models import GeneratedCandidate

    flow = PageFlow(
        page=FakePage(),
        account=make_account(tmp_path),
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
    )
    lyric = LyricData(song_name="粉笔灰", lyrics="粉笔灰" * 40, style="s" * 60)

    async def states():
        return [
            {"index": 0, "title": "已完成版本", "loading": False},
            {"index": 1, "title": "旧歌曲", "loading": False},
        ]

    async def classify(cards, lyric_data_list):
        assert cards == [
            {"index": 0, "title": "已完成版本", "loading": False},
            {"index": 1, "title": "旧歌曲", "loading": False},
        ]
        return {
            "粉笔灰": [
                GeneratedCandidate(song_name="粉笔灰", generated_title="已完成版本", card_index=0)
            ]
        }

    monkeypatch.setattr(flow, "asset_card_states", states)
    monkeypatch.setattr(flow, "classify_generated_cards", classify)

    result = await flow.recover_existing_candidates([lyric])

    assert result["粉笔灰"][0].generated_title == "已完成版本"


def test_new_cards_above_anchor_supports_fixed_length_virtual_lists() -> None:
    baseline_anchor = "导出前的第一首"
    current = [
        {"index": 0, "title": "新歌二", "loading": False},
        {"index": 1, "title": "新歌一", "loading": False},
        {"index": 2, "title": baseline_anchor, "loading": False},
        {"index": 3, "title": "旧歌", "loading": False},
    ]

    assert new_cards_above_anchor(current, baseline_anchor, baseline_count=3) == [
        {"index": 0, "title": "新歌二", "loading": False},
        {"index": 1, "title": "新歌一", "loading": False},
    ]


def test_new_cards_above_anchor_returns_empty_when_generation_fails() -> None:
    current = [
        {"index": 0, "title": "旧歌一", "loading": False},
        {"index": 1, "title": "旧歌二", "loading": False},
    ]

    assert new_cards_above_anchor(current, "旧歌一", baseline_count=2) == []


@pytest.mark.asyncio
async def test_process_song_runs_all_states_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(page_flow_module, "read_mp3_duration_seconds", lambda _: 61.0)
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
    flow.verify_generated_song = lambda lyrics, song_name=None: step("verify_generated_song")
    flow.enter_editor = lambda song_name: step("enter_editor")
    flow.export_song = lambda song_name: step("export_song")
    flow.download_song = lambda song_name, lyrics=None: step("download_song")

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
        "match_titles",
        "enter_editor",
        "export_song",
        "download_song",
    ]
    assert result == tmp_path / "output" / date.today().isoformat() / "夜色引擎.mp3"


@pytest.mark.asyncio
async def test_process_song_uses_configured_run_day_for_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(page_flow_module, "read_mp3_duration_seconds", lambda _: 61.0)
    account = make_account(tmp_path)
    flow = PageFlow(
        page=FakePage(),
        account=account,
        settings=ConsoleSettings(),
        screenshot_dir=tmp_path,
        day="2026-09-22",
    )
    downloaded = tmp_path / "旧任务歌曲.mp3"
    downloaded.write_bytes(b"audio")

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
        return None

    async def wait_for_generation(before):
        return "新歌"

    async def verify_generated_song(lyrics, song_name=None):
        return None

    async def enter_editor(song_name):
        return None

    async def export_song(song_name):
        return None

    async def download_song(song_name, lyrics=None):
        return downloaded

    flow.fill_inputs = fill_inputs
    flow.first_asset_title = first_asset_title
    flow.generate = generate
    flow.check_generation_limit = check_generation_limit
    flow.wait_for_generation = wait_for_generation
    flow.verify_generated_song = verify_generated_song
    flow.enter_editor = enter_editor
    flow.export_song = export_song
    flow.download_song = download_song

    result = await flow.process_song(
        LyricData(song_name="旧任务歌曲", lyrics="x" * 120, style="s" * 60),
        lambda step: None,
    )

    assert result == tmp_path / "output" / "2026-09-22" / "旧任务歌曲.mp3"


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
