"""Deterministic page operations for the Miaoxiang studio workflow."""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from backend.errors import BrowserFlowError, GenerationLimitError
from backend.models import AccountConfig, ConsoleSettings, LyricData


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

    async def ensure_create_page_ready(self) -> None:
        try:
            await self.page.goto(
                self.account.create_url,
                wait_until="domcontentloaded",
                timeout=self.settings.page_load_timeout_seconds * 1000,
            )
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
            dropdown = self.page.locator(".semi-select").filter(
                has_text="自动"
            ).first
            if self.account.model_name in await dropdown.inner_text():
                return
            await trusted_click(self.page, dropdown, "模型下拉框")
            await self.page.wait_for_timeout(1000)

            switches = await self.page.locator(".semi-switch").all()
            for switch in switches:
                parent_text = await switch.locator("xpath=ancestor::*[1]").inner_text()
                if "自动" in parent_text:
                    checked = "semi-switch-checked" in (await switch.get_attribute("class") or "")
                    if checked:
                        await dom_click(switch, "自动模型开关")
                        await self.page.wait_for_timeout(1000)
                    break

            await self.page.evaluate(
                """() => {
                    const containers = document.querySelectorAll(
                        '.semi-select-option-list,[class*="option-list"]'
                    );
                    containers.forEach(container => container.scrollTop = container.scrollHeight);
                }"""
            )
            await self.page.wait_for_timeout(1000)
            option = self.page.locator(".semi-select-option").filter(
                has_text=self.account.model_name
            ).first
            await dom_click(option, self.account.model_name)
            await self.page.wait_for_timeout(1000)
            if self.account.model_name not in await dropdown.inner_text():
                raise BrowserFlowError(f"模型选择验证失败: {self.account.model_name}")
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("模型选择", error)

    async def select_singer(self) -> None:
        try:
            label = self.page.get_by_text("使用虚拟歌手音色", exact=True).first
            switch = label.locator(
                "xpath=following::div[contains(@class,'semi-switch')][1]"
            )
            state = await switch.get_attribute("aria-checked")
            css = await switch.get_attribute("class")
            if state != "true" and "semi-switch-checked" not in (css or ""):
                await dom_click(switch, "虚拟歌手开关")
                await self.page.wait_for_timeout(1000)
            await trusted_click(
                self.page,
                self.page.get_by_text("选择虚拟歌手音色", exact=True).first,
                "选择虚拟歌手音色",
            )
            await self.page.wait_for_timeout(2000)
            singer_card = self.page.locator("*").filter(
                has_text=self.account.singer_name
            ).first
            choose = singer_card.get_by_role("button", name="选择").first
            await trusted_click(choose, f"选择歌手 {self.account.singer_name}")
            await self.page.wait_for_timeout(1000)
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("虚拟歌手选择", error)

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
        while datetime.now().timestamp() < deadline:
            current = await self.first_asset_title()
            if current and current != before_title:
                return current
            last_title = current
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
            top_export = self.page.locator("button").filter(has_text="导出").first
            await trusted_click(self.page, top_export, "顶部导出")
            await self.page.wait_for_timeout(5000)
            name_input = self.page.locator("input").filter(
                has_value=re.compile("新项目|项目")
            ).first
            await clear_and_type(name_input, song_name)
            await self.page.wait_for_timeout(2000)
            confirm = self.page.locator(".semi-modal button, [role='dialog'] button").filter(
                has_text="导出"
            ).last
            await trusted_click(self.page, confirm, "确认导出")
            deadline = datetime.now().timestamp() + self.settings.export_timeout_seconds
            while datetime.now().timestamp() < deadline:
                if "assets" in self.page.url:
                    await self.page.wait_for_timeout(3000)
                    return
                await self.page.wait_for_timeout(3000)
            raise BrowserFlowError(f"导出跳转超时: {self.page.url}")
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("导出歌曲", error)

    async def download_song(self, song_name: str) -> Path:
        try:
            results_tab = self.page.get_by_text("生成结果", exact=True).first
            await trusted_click(self.page, results_tab, "生成结果标签")
            await self.page.wait_for_timeout(3000)
            title = self.page.get_by_text(song_name, exact=False).first
            card = title.locator(
                "xpath=ancestor::div[contains(@class,'song') or contains(@class,'asset') or contains(@class,'card')][1]"
            )
            trigger = card.locator("div[class*='trigger']").last
            await trigger.scroll_into_view_if_needed(timeout=5000)
            await trigger.hover(timeout=5000)
            await self.page.wait_for_timeout(500)
            box = await trigger.bounding_box()
            if not box:
                raise BrowserFlowError("下载更多按钮不可见")
            await self.page.mouse.click(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
            )
            await self.page.wait_for_timeout(3000)
            download_item = self.page.get_by_text("下载", exact=True).first
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
        if isinstance(error, GenerationLimitError):
            raise error
        raise BrowserFlowError(f"{step}失败: {error}{suffix}") from error
