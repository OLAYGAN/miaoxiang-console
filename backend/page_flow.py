"""Deterministic page operations for the Miaoxiang studio workflow."""

import re
import inspect
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from backend.errors import (
    BrowserFlowError,
    GenerationLimitError,
    LoginRequiredError,
    SongVerificationError,
)
from backend.models import AccountConfig, ConsoleSettings, LyricData
from backend.models import BatchSongResult, GeneratedCandidate


T = TypeVar("T")


async def trusted_click(
    page: Any,
    locator: Any,
    description: str,
    hover_ms: int = 500,
) -> None:
    try:
        await locator.scroll_into_view_if_needed(timeout=3000)
        box = await locator.bounding_box()
        if not box:
            raise BrowserFlowError(f"元素不可见: {description}")
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        await page.mouse.move(x, y)
        if hover_ms:
            await page.wait_for_timeout(hover_ms)
        await page.mouse.click(x, y)
    except BrowserFlowError:
        raise
    except Exception as error:
        raise BrowserFlowError(f"点击失败: {description}: {error}") from error


async def dom_click(locator: Any, description: str) -> None:
    try:
        await locator.click(timeout=5000)
    except Exception as error:
        raise BrowserFlowError(f"DOM click 失败: {description}: {error}") from error


async def type_segmented(
    locator: Any,
    text: str,
    *,
    chunk_size: int = 50,
    delay: int = 10,
) -> None:
    try:
        await locator.click(timeout=5000)
        await locator.press("Control+a")
        await locator.press("Delete")
        for index in range(0, len(text), chunk_size):
            await locator.type(text[index : index + chunk_size], delay=delay)
    except Exception as error:
        raise BrowserFlowError(f"分段输入失败: {error}") from error


async def clear_and_type(
    locator: Any,
    text: str,
    *,
    delay: int = 10,
    verify_min_length: int | None = None,
) -> None:
    try:
        await locator.click(timeout=5000)
        await locator.press("Control+a")
        await locator.press("Delete")
        await locator.type(text, delay=delay)
        if verify_min_length is not None:
            value = await locator.input_value()
            if len(value.strip()) < verify_min_length:
                raise BrowserFlowError(f"输入验证失败: 长度 {len(value.strip())} < {verify_min_length}")
    except BrowserFlowError:
        raise
    except Exception as error:
        raise BrowserFlowError(f"输入失败: {error}") from error


def archive_download(
    downloaded_file: Path,
    output_root: Path,
    song_name: str,
    day: str,
) -> Path:
    source = Path(downloaded_file)
    if not source.is_file() or source.stat().st_size == 0:
        raise BrowserFlowError(f"下载文件为空或不存在: {source}")

    safe_song = re.sub(r'[\\/:*?"<>|]+', "_", song_name).strip() or "未命名歌曲"
    directory = Path(output_root) / day
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{safe_song}.mp3"
    counter = 2
    while destination.exists():
        destination = directory / f"{safe_song}-{counter}.mp3"
        counter += 1
    shutil.move(str(source), str(destination))
    if not destination.is_file() or destination.stat().st_size == 0:
        raise BrowserFlowError(f"归档验证失败: {destination}")
    return destination


def is_login_challenge(body_text: str) -> bool:
    markers = ("扫码登录", "验证码登录", "登录二维码")
    return any(marker in body_text for marker in markers)


async def select_model(page: Any, model_name: str) -> None:
    dropdown = page.locator(".semi-select").first
    if model_name in await dropdown.inner_text():
        return

    await dropdown.click(timeout=5000)
    await page.wait_for_timeout(1000)

    switch = page.locator(".semi-popover .semi-switch").first
    switch_class = await switch.get_attribute("class") or ""
    if "semi-switch-checked" in switch_class:
        await switch.click(timeout=5000)
        await page.wait_for_timeout(1000)

    await page.evaluate(
        """() => {
            document.querySelectorAll(
                '.semi-select-option-list,[class*="option-list"]'
            ).forEach(container => {
                container.scrollTop = container.scrollHeight;
            });
        }"""
    )
    option = page.locator(
        ".semi-select-option-custom, .semi-select-option"
    ).filter(has_text=model_name).first
    await option.scroll_into_view_if_needed(timeout=5000)
    await option.click(timeout=5000)
    await page.wait_for_timeout(1000)

    if model_name not in await dropdown.inner_text():
        raise BrowserFlowError(f"模型选择验证失败: {model_name}")


async def select_singer(page: Any, singer_name: str) -> None:
    switch = page.locator('[class*="vocalTimbreWrapper"] .semi-switch').first
    switch_class = await switch.get_attribute("class") or ""
    if "semi-switch-checked" not in switch_class:
        await switch.click(timeout=5000)
        await page.wait_for_timeout(1000)

    trigger = page.locator('[class*="singerTrigger"]').first
    if singer_name in await trigger.inner_text():
        return

    await trigger.click(timeout=5000)
    await page.wait_for_timeout(1500)
    singer_item = page.locator('[class*="singerItem"]').filter(
        has_text=singer_name
    ).first
    choose_button = singer_item.locator("button").filter(has_text="选择").first
    await choose_button.click(timeout=5000)
    await page.wait_for_timeout(1000)

    if singer_name not in await trigger.inner_text():
        raise BrowserFlowError(f"虚拟歌手选择验证失败: {singer_name}")


async def refresh_asset_tabs(page: Any) -> None:
    tabs = page.locator('[class*="tabItem"]')
    lyric_tab = tabs.filter(has_text=re.compile(r"^\s*歌词\s*$")).first
    song_tab = tabs.filter(has_text=re.compile(r"^\s*歌曲\s*$")).first
    await lyric_tab.click(timeout=3000)
    await page.wait_for_timeout(500)
    await song_tab.click(timeout=3000)
    await page.wait_for_timeout(1000)


def _normalize_lyric_content(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text.lower()))


def _lyric_probe(lyrics: str) -> str:
    # Structural labels are authoring directives; the platform detail may omit them.
    content = re.sub(r"\[[^\]]+\]", "", lyrics)
    return _normalize_lyric_content(content)


async def verify_generated_song(page: Any, lyrics: str) -> None:
    lyric_probe = _lyric_probe(lyrics)
    if len(lyric_probe) < 20:
        raise BrowserFlowError("输入歌词太短，无法做详情校验")

    card = page.locator('[class*="libraryItemWrapper"]').filter(visible=True).first
    await card.click(timeout=5000)
    await page.wait_for_timeout(1000)

    lyric_title = page.locator(
        '[class*="detailPanel"] [class*="sectionTitle"]'
    ).filter(has_text=re.compile(r"^\s*歌词\s*$")).first
    detail_content = lyric_title.locator(
        "xpath=following-sibling::*[contains(@class,'sectionContent')][1]"
    )
    detail_text = await detail_content.inner_text()
    normalized_detail = _normalize_lyric_content(detail_text)
    if lyric_probe not in normalized_detail:
        raise SongVerificationError("歌词详情不匹配：生成卡片详情中没有找到本次输入的歌词片段")


async def export_song(
    page: Any,
    song_name: str,
    *,
    timeout_seconds: int = 60,
) -> None:
    top_export = page.locator("button").filter(has_text="导出").first
    await top_export.click(timeout=5000)
    await page.wait_for_timeout(5000)

    modal = page.locator(".semi-modal-content").filter(visible=True).last
    name_input = modal.locator("input.semi-input").first
    await clear_and_type(name_input, song_name)
    await page.wait_for_timeout(2000)

    confirm = modal.locator(".semi-modal-footer button").filter(
        has_text="导出"
    ).last
    await confirm.click(timeout=5000)

    deadline = datetime.now().timestamp() + timeout_seconds
    while datetime.now().timestamp() < deadline:
        if "assets" in page.url:
            await page.wait_for_timeout(3000)
            return
        await page.wait_for_timeout(3000)
    raise BrowserFlowError(f"导出跳转超时: {page.url}")


async def open_download_menu(page: Any, song_name: str) -> Any:
    results_tab = page.locator("button").filter(has_text="生成结果").first
    await results_tab.click(timeout=5000)
    await page.wait_for_timeout(3000)

    card = page.locator('[class*="generatedSongCard"]').filter(
        has_text=song_name
    ).first
    trigger = card.locator("div[class*='trigger']").last
    await trigger.scroll_into_view_if_needed(timeout=5000)
    await trigger.hover(timeout=5000)
    await page.wait_for_timeout(500)
    box = await trigger.bounding_box()
    if not box:
        raise BrowserFlowError("下载更多按钮不可见")
    await page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + box["height"] / 2,
    )
    await page.wait_for_timeout(3000)
    return page.locator('[role="menuitem"]').filter(has_text="下载").first


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class PageFlow:
    def __init__(
        self,
        *,
        page: Any,
        account: AccountConfig,
        settings: ConsoleSettings,
        screenshot_dir: Path,
    ) -> None:
        self.page = page
        self.account = account
        self.settings = settings
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def process_song(
        self,
        lyric_data: LyricData,
        on_step: Callable[[str], None],
    ) -> Path:
        on_step("page_ready")
        await self.ensure_create_page_ready()

        on_step("fill_inputs")
        await self.fill_inputs(lyric_data)

        on_step("record_before")
        before = await self.first_asset_title()

        on_step("generate")
        await self.generate()

        on_step("check_limit")
        await self.check_generation_limit()

        on_step("wait_generation")
        actual_song_name = await self.wait_for_generation(before)

        on_step("verify_details")
        await self.verify_generated_song(lyric_data.lyrics)

        on_step("enter_editor")
        await self.enter_editor(actual_song_name)

        on_step("export_song")
        await self.export_song(lyric_data.song_name)

        on_step("download_song")
        downloaded = await self.download_song(lyric_data.song_name)
        return archive_download(
            downloaded,
            Path(self.account.output_dir),
            lyric_data.song_name,
            datetime.now().strftime("%Y-%m-%d"),
        )

    async def process_batch(
        self,
        lyric_data_list: list[LyricData],
        on_step: Callable[[str, str | None], None],
    ) -> list[BatchSongResult]:
        on_step("page_ready", None)
        await self.ensure_create_page_ready()
        baseline_count = await _maybe_await(self.asset_card_count())

        for lyric_data in lyric_data_list:
            on_step("fill_inputs", lyric_data.song_name)
            await self.fill_inputs(lyric_data)
            on_step("generate", lyric_data.song_name)
            await self.generate()
            on_step("check_limit", lyric_data.song_name)
            await self.check_generation_limit()

        on_step("wait_generation", None)
        generated_cards = await self.wait_for_batch_generation(
            baseline_count,
            len(lyric_data_list),
        )
        on_step("verify_details", None)
        candidates = await self.classify_generated_cards(
            generated_cards,
            lyric_data_list,
        )

        results: list[BatchSongResult] = []
        for lyric_data in lyric_data_list:
            matches = candidates.get(lyric_data.song_name, [])
            if not matches:
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="generation_failed",
                        error="没有匹配的生成结果",
                    )
                )
                continue

            # Asset cards are newest first; export the first matching version.
            selected = matches[0]
            on_step("export_song", lyric_data.song_name)
            try:
                output_path = await self.export_candidate(selected, lyric_data)
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="success",
                        output_path=str(output_path),
                    )
                )
            except GenerationLimitError:
                raise
            except LoginRequiredError:
                raise
            except SongVerificationError:
                raise
            except Exception as error:
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="export_failed",
                        error=str(error),
                    )
                )
        return results

    async def ensure_create_page_ready(self) -> None:
        try:
            await self.page.goto(
                self.account.create_url,
                wait_until="domcontentloaded",
                timeout=self.settings.page_load_timeout_seconds * 1000,
            )
            body_text = await self.page.inner_text("body")
            if is_login_challenge(body_text):
                await self._screenshot("login-required")
                raise LoginRequiredError("检测到妙响登录弹窗，请先登录当前账号的 Chrome 配置")
            editor = self.page.locator(".ql-editor").first
            try:
                await editor.wait_for(state="visible", timeout=8000)
            except Exception:
                await trusted_click(
                    self.page,
                    self.page.get_by_text("专业模式", exact=True).first,
                    "专业模式切换",
                )
                await self.page.wait_for_timeout(3000)
                await editor.wait_for(state="visible", timeout=10000)
            await self.select_model()
            await self.select_singer()
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("创作页初始化", error)

    async def select_model(self) -> None:
        try:
            await select_model(self.page, self.account.model_name)
        except GenerationLimitError:
            raise
        except SongVerificationError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("模型选择", error)

    async def select_singer(self) -> None:
        try:
            await select_singer(self.page, self.account.singer_name)
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("虚拟歌手选择", error)

    async def verify_generated_song(self, lyrics: str) -> None:
        try:
            await verify_generated_song(self.page, lyrics)
        except GenerationLimitError:
            raise
        except SongVerificationError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("生成歌曲详情校验", error)

    async def fill_inputs(self, lyric_data: LyricData) -> None:
        try:
            editor = self.page.locator(".ql-editor").first
            await type_segmented(editor, lyric_data.lyrics)
            await self.page.wait_for_timeout(2000)
            lyric_value = await editor.inner_text()
            if len(lyric_value.strip()) <= 100:
                raise BrowserFlowError(f"歌词输入验证失败: 长度 {len(lyric_value.strip())}")

            style = self.page.locator(
                'textarea[placeholder*="创作灵感"], textarea[placeholder*="歌曲风格"], textarea[placeholder*="旋律"]'
            ).first
            await clear_and_type(
                style,
                lyric_data.style,
                verify_min_length=50,
            )
            await self.page.wait_for_timeout(2000)
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("歌词风格输入", error)

    async def first_asset_title(self) -> str:
        try:
            value = await self.page.evaluate(
                """() => {
                    const selectors = '[class*="song-title"],[class*="title"],[class*="name"]';
                    const elements = Array.from(document.querySelectorAll(selectors));
                    const width = window.innerWidth || document.documentElement.clientWidth;
                    const visible = elements.filter(element => {
                        const rect = element.getBoundingClientRect();
                        const text = element.textContent.trim();
                        return rect.width > 0 && rect.height > 0 &&
                            rect.right > width * 0.55 && text.length > 1 && text.length < 40;
                    });
                    if (visible.length) return visible[0].textContent.trim();
                    const all = Array.from(document.querySelectorAll('div,span,p,a'));
                    const fallback = all.filter(element => {
                        const rect = element.getBoundingClientRect();
                        const text = element.textContent.trim();
                        return rect.right > width * 0.55 && rect.width > 0 &&
                            text.length >= 2 && text.length <= 20 &&
                            /[\\u4e00-\\u9fa5A-Za-z0-9]/.test(text);
                    });
                    return fallback.length ? fallback[0].textContent.trim() : '';
                }"""
            )
            return str(value or "")
        except Exception as error:
            await self._raise_with_screenshot("资产列表读取", error)

    async def asset_generation_state(self) -> dict:
        try:
            value = await self.page.evaluate(
                """() => {
                    const width = window.innerWidth || document.documentElement.clientWidth;
                    const cards = Array.from(document.querySelectorAll(
                        '[class*="libraryItemWrapper"],[class*="songItem"],[class*="assetItem"]'
                    )).filter(element => {
                        const rect = element.getBoundingClientRect();
                        return rect.left > width * 0.45 &&
                            rect.right > width * 0.55 &&
                            rect.width > 0 &&
                            rect.height > 0;
                    });
                    if (!cards.length) return {title: '', has_placeholder: false};
                    const card = cards[0];
                    const titleNode = card.querySelector(
                        '[class*="title"],[class*="songName"],[class*="name"]'
                    );
                    const title = (titleNode ? titleNode.textContent : '').trim();
                    const markerText = `${card.className} ${card.textContent}`;
                    const loadingMarker = /生成中|loading|skeleton|placeholder/i.test(markerText);
                    return {
                        title,
                        has_placeholder: !title || loadingMarker,
                    };
                }"""
            )
            return value if isinstance(value, dict) else {"title": "", "has_placeholder": False}
        except Exception as error:
            await self._raise_with_screenshot("生成状态读取", error)

    async def asset_card_states(self) -> list[dict]:
        try:
            value = await self.page.evaluate(
                """() => {
                    const width = window.innerWidth || document.documentElement.clientWidth;
                    const cards = Array.from(document.querySelectorAll(
                        '[class*="libraryItemWrapper"],[class*="songItem"],[class*="assetItem"]'
                    )).filter(element => {
                        const rect = element.getBoundingClientRect();
                        return rect.left > width * 0.45 &&
                            rect.right > width * 0.55 &&
                            rect.width > 0 &&
                            rect.height > 0;
                    });
                    return cards.map((card, index) => {
                        const titleNode = card.querySelector(
                            '[class*="title"],[class*="songName"],[class*="name"]'
                        );
                        const title = (titleNode ? titleNode.textContent : '').trim();
                        const markerText = `${card.className} ${card.textContent}`;
                        const loading = !title || /生成中|loading|skeleton|placeholder/i.test(markerText);
                        return {index, title, loading};
                    });
                }"""
            )
            return value if isinstance(value, list) else []
        except Exception as error:
            await self._raise_with_screenshot("资产卡片读取", error)

    async def asset_card_count(self) -> int:
        return len(await self.asset_card_states())

    async def wait_for_batch_generation(
        self,
        baseline_count: int,
        lyric_count: int,
    ) -> list[dict]:
        await refresh_asset_tabs(self.page)
        started_at = datetime.now().timestamp()
        deadline = started_at + self.settings.generation_timeout_seconds
        stable_polls = 0
        last_completed: list[dict] = []

        while datetime.now().timestamp() < deadline:
            states = await self.asset_card_states()
            new_count = max(len(states) - baseline_count, 0)
            new_states = states[:new_count]
            completed = [state for state in new_states if not state.get("loading")]
            has_loading = any(state.get("loading") for state in new_states)
            last_completed = [
                {"title": state.get("title", ""), "index": state.get("index", 0), "loading": False}
                for state in completed
            ]

            expected_max = lyric_count * 2
            if len(completed) >= expected_max:
                return last_completed
            if completed and not has_loading:
                stable_polls += 1
                if stable_polls >= 2:
                    return last_completed
            else:
                stable_polls = 0
            # A submitted batch that produces no card or placeholder at all is a platform failure.
            if not new_states and datetime.now().timestamp() - started_at >= 30:
                return []
            await self.page.wait_for_timeout(5000)

        await self._screenshot("batch-generation-timeout")
        return last_completed

    async def _read_lyric_detail_for_card(self, card_index: int) -> str:
        card = self.page.locator('[class*="libraryItemWrapper"]').filter(visible=True).nth(card_index)
        await card.click(timeout=5000)
        await self.page.wait_for_timeout(1000)
        lyric_title = self.page.locator(
            '[class*="detailPanel"] [class*="sectionTitle"]'
        ).filter(has_text=re.compile(r"^\s*歌词\s*$")).first
        detail_content = lyric_title.locator(
            "xpath=following-sibling::*[contains(@class,'sectionContent')][1]"
        )
        return await detail_content.inner_text()

    async def classify_generated_cards(
        self,
        generated_cards: list[dict],
        lyric_data_list: list[LyricData],
    ) -> dict[str, list[GeneratedCandidate]]:
        matches: dict[str, list[GeneratedCandidate]] = {
            lyric_data.song_name: [] for lyric_data in lyric_data_list
        }
        probes = {
            lyric_data.song_name: _lyric_probe(lyric_data.lyrics)
            for lyric_data in lyric_data_list
        }
        for fallback_index, generated in enumerate(generated_cards):
            title = str(generated.get("title") or "").strip()
            card_index = int(generated.get("index", fallback_index))
            if not title:
                continue
            detail_text = await self._read_lyric_detail_for_card(card_index)
            normalized_detail = _normalize_lyric_content(detail_text)
            for song_name, probe in probes.items():
                if probe and probe in normalized_detail:
                    matches[song_name].append(
                        GeneratedCandidate(
                            song_name=song_name,
                            generated_title=title,
                            card_index=card_index,
                        )
                    )
                    break
        return matches

    async def generate(self) -> None:
        try:
            button = self.page.locator("button").filter(
                has_text=re.compile("生成歌曲|生成")
            ).first
            await trusted_click(self.page, button, "生成歌曲")
            await self.page.wait_for_timeout(10000)
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("生成歌曲", error)

    async def check_generation_limit(self) -> None:
        try:
            for _ in range(10):
                html = await self.page.content()
                if "上限" in html or "已达上限" in html or ("次数" in html and "用完" in html):
                    await self._screenshot("generation-limit")
                    raise GenerationLimitError("检测到生成次数上限")
                await self.page.wait_for_timeout(1000)
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("生成上限检测", error)

    async def wait_for_generation(self, before_title: str) -> str:
        deadline = datetime.now().timestamp() + self.settings.generation_timeout_seconds
        last_title = before_title
        saw_placeholder = False
        await refresh_asset_tabs(self.page)
        while datetime.now().timestamp() < deadline:
            state = await self.asset_generation_state()
            current = str(state.get("title") or "")
            last_title = current or "生成中"
            if state.get("has_placeholder"):
                saw_placeholder = True
            elif current and (saw_placeholder or current != before_title):
                return current
            await self.page.wait_for_timeout(5000)
        await self._screenshot("generation-timeout")
        raise BrowserFlowError(
            f"等待生成超时：{self.settings.generation_timeout_seconds} 秒；生成前={before_title!r}, 最后={last_title!r}"
        )

    async def enter_editor(self, song_name: str) -> None:
        try:
            title = self.page.get_by_text(song_name, exact=False).first
            card = title.locator(
                "xpath=ancestor::div[contains(@class,'song') or contains(@class,'asset') or contains(@class,'card')][1]"
            )
            await card.hover(timeout=5000)
            await self.page.wait_for_timeout(2000)
            edit = card.locator("button").filter(has_text="编辑").first
            await trusted_click(self.page, edit, "歌曲编辑按钮")
            await self.page.wait_for_timeout(3000)
            editor_item = self.page.get_by_text("编辑器", exact=True).first
            await trusted_click(self.page, editor_item, "编辑器菜单")
            deadline = datetime.now().timestamp() + 30
            while datetime.now().timestamp() < deadline:
                url = self.page.url
                if "playground" in url or "editor" in url:
                    await self.page.wait_for_timeout(self.settings.editor_import_wait_seconds * 1000)
                    return
                await self.page.wait_for_timeout(3000)
            raise BrowserFlowError(f"进入编辑器超时: {self.page.url}")
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("进入编辑器", error)

    async def export_song(self, song_name: str) -> None:
        try:
            await export_song(
                self.page,
                song_name,
                timeout_seconds=self.settings.export_timeout_seconds,
            )
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("导出歌曲", error)

    async def export_candidate(
        self,
        candidate: GeneratedCandidate,
        lyric_data: LyricData,
    ) -> Path:
        try:
            if "playground" in self.page.url or "assets" in self.page.url:
                await self.page.goto(
                    self.account.create_url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.page_load_timeout_seconds * 1000,
                )
                await self.ensure_create_page_ready()

            await self.enter_editor(candidate.generated_title)
            await self.export_song(lyric_data.song_name)
            downloaded = await self.download_song(lyric_data.song_name)
            return archive_download(
                downloaded,
                Path(self.account.output_dir),
                lyric_data.song_name,
                datetime.now().strftime("%Y-%m-%d"),
            )
        except GenerationLimitError:
            raise
        except LoginRequiredError:
            raise
        except SongVerificationError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("导出选中版本", error)

    async def download_song(self, song_name: str) -> Path:
        try:
            download_item = await open_download_menu(self.page, song_name)
            async with self.page.expect_download(
                timeout=self.settings.download_timeout_seconds * 1000
            ) as download_info:
                await trusted_click(self.page, download_item, "下载菜单")
            download = await download_info.value
            suggested = download.suggested_filename or f"{song_name}.mp3"
            target = Path(self.account.download_dir) / suggested
            target.parent.mkdir(parents=True, exist_ok=True)
            await download.save_as(target)
            return target
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("下载歌曲", error)

    async def _screenshot(self, step: str) -> Path | None:
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = self.screenshot_dir / f"{stamp}-{step}.png"
            await self.page.screenshot(path=path, full_page=True)
            return path
        except Exception:
            return None

    async def _raise_with_screenshot(self, step: str, error: Exception) -> None:
        path = await self._screenshot(re.sub(r"[^a-z0-9-]+", "-", step).strip("-"))
        suffix = f"；截图: {path}" if path else ""
        if isinstance(
            error,
            (GenerationLimitError, LoginRequiredError, SongVerificationError),
        ):
            raise error
        raise BrowserFlowError(f"{step}失败: {error}{suffix}") from error
