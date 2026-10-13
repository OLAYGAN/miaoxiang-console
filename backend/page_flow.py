"""Deterministic page operations for the Miaoxiang studio workflow."""

import asyncio
import re
import inspect
import os
import shutil
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from backend.errors import (
    BrowserFlowError,
    GenerationLimitError,
    LoginRequiredError,
    SongDownloadError,
    SongExportError,
    SongGenerationFailureError,
    SongVerificationError,
)
from backend.lyrics import sanitize_lyrics_for_generation
from backend.models import AccountConfig, ConsoleSettings, LyricData
from backend.models import BatchSongResult, GeneratedCandidate


T = TypeVar("T")

MIN_DOWNLOAD_DURATION_SECONDS = 60.0

_MPEG1_BITRATE_TABLE = {
    1: [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    3: [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
}
_MPEG2_LAYER1_BITRATE_TABLE = [32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256]
_MPEG2_LAYER23_BITRATE_TABLE = [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]


def read_mp3_duration_seconds(path: Path) -> float:
    """Parse MP3 frame headers to obtain duration without external media tools."""
    data = Path(path).read_bytes()
    offset = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (
            (data[6] & 0x7F) << 21
            | (data[7] & 0x7F) << 14
            | (data[8] & 0x7F) << 7
            | (data[9] & 0x7F)
        )
        offset = min(len(data), size + 10)

    frame_offset = -1
    scan_limit = min(len(data) - 4, offset + 1_048_576)
    while offset <= scan_limit:
        if data[offset] == 0xFF and (data[offset + 1] & 0xE0) == 0xE0:
            header = int.from_bytes(data[offset:offset + 4], "big")
            version = (header >> 19) & 3
            layer = (header >> 17) & 3
            bitrate_index = (header >> 12) & 0xF
            sample_index = (header >> 10) & 3
            padding = (header >> 9) & 1
            if (
                version in {0, 2, 3}
                and layer in {1, 2, 3}
                and 1 <= bitrate_index <= 14
                and sample_index != 3
            ):
                frame_offset = offset
                break
        offset += 1
    if frame_offset < 0:
        raise BrowserFlowError(f"无法解析 MP3 音频时长: {path}")

    duration = 0.0
    frames = 0
    cursor = frame_offset
    while cursor + 4 <= len(data):
        if data[cursor] != 0xFF or (data[cursor + 1] & 0xE0) != 0xE0:
            break
        header = int.from_bytes(data[cursor:cursor + 4], "big")
        version = (header >> 19) & 3
        layer = (header >> 17) & 3
        bitrate_index = (header >> 12) & 0xF
        sample_index = (header >> 10) & 3
        padding = (header >> 9) & 1
        if (
            version not in {0, 2, 3}
            or layer not in {1, 2, 3}
            or bitrate_index in {0, 15}
            or sample_index == 3
        ):
            break

        if version == 3:
            bitrate = _MPEG1_BITRATE_TABLE[layer][bitrate_index - 1]
            sample_rate = (44100, 48000, 32000)[sample_index]
            samples_per_frame = 384 if layer == 3 else 1152
        else:
            bitrate = (
                _MPEG2_LAYER1_BITRATE_TABLE
                if layer == 3
                else _MPEG2_LAYER23_BITRATE_TABLE
            )[bitrate_index - 1]
            sample_rate = (
                (11025, 12000, 8000) if version == 0 else (22050, 24000, 16000)
            )[sample_index]
            samples_per_frame = 576 if layer == 1 else 1152

        coefficient = samples_per_frame // 8
        frame_length = (
            coefficient * bitrate * 1000 // sample_rate
            + padding
        )
        if layer == 3:
            frame_length *= 4
        if frame_length < 4:
            break
        duration += samples_per_frame / sample_rate
        frames += 1
        cursor += frame_length

    if frames == 0:
        raise BrowserFlowError(f"无法解析 MP3 音频时长: {path}")
    return duration


async def trusted_click(
    page: Any,
    locator: Any,
    description: str,
    hover_ms: int = 500,
) -> None:
    try:
        await locator.scroll_into_view_if_needed(timeout=3000)
        # Locator clicks remain real mouse events and correctly account for
        # nested scroll containers; raw page.mouse coordinates do not.
        await locator.click(timeout=5000)
    except BrowserFlowError:
        raise
    except Exception as error:
        raise BrowserFlowError(f"点击失败: {description}: {error}") from error


async def dom_click(locator: Any, description: str) -> None:
    try:
        await locator.evaluate("(element) => element.click()")
        return
    except Exception as dom_error:
        try:
            await locator.click(timeout=5000)
        except Exception as click_error:
            raise BrowserFlowError(
                f"DOM click 失败: {description}: {click_error}"
            ) from dom_error


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


def _normalize_pasted_text(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


async def paste_text(
    page: Any,
    locator: Any,
    text: str,
    *,
    contenteditable: bool = False,
    segmented_fallback: bool = False,
) -> bool:
    """Paste through the real clipboard, falling back to typing if needed."""
    try:
        try:
            await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        previous_clipboard = await page.evaluate(
            """async () => {
                try {
                    const text = await navigator.clipboard.readText();
                    return { ok: true, text };
                } catch {
                    return { ok: false, text: "" };
                }
            }"""
        )
        await page.evaluate("text => navigator.clipboard.writeText(text)", text)

        await locator.click(timeout=5000)
        await locator.press("Control+a")
        await locator.press("Delete")
        await locator.press("Control+v")
        await page.wait_for_timeout(300)

        value = await locator.inner_text() if contenteditable else await locator.input_value()
        pasted = _normalize_pasted_text(value)
        expected = _normalize_pasted_text(text)
        if not expected or pasted != expected:
            raise BrowserFlowError("粘贴内容校验失败")

        if isinstance(previous_clipboard, dict) and previous_clipboard.get("ok"):
            try:
                await page.evaluate(
                    "text => navigator.clipboard.writeText(text)",
                    str(previous_clipboard.get("text") or ""),
                )
            except Exception:
                pass
        return True
    except Exception:
        if segmented_fallback:
            await type_segmented(locator, text)
            return False
        await clear_and_type(locator, text)
        return False


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
    duration = read_mp3_duration_seconds(source)
    if duration <= MIN_DOWNLOAD_DURATION_SECONDS:
        raise BrowserFlowError(
            f"下载音乐时长 {duration:.1f} 秒，必须大于 60 秒；已保留原成品文件"
        )

    safe_song = re.sub(r'[\\/:*?"<>|]+', "_", song_name).strip() or "未命名歌曲"
    directory = Path(output_root) / day
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{safe_song}.mp3"
    if source.resolve() != destination.resolve():
        temporary = directory / f".{safe_song}.{datetime.now().strftime('%Y%m%d%H%M%S%f')}.tmp"
        try:
            shutil.copy2(source, temporary)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise BrowserFlowError(f"临时归档验证失败: {temporary}")
            # Replace only after the complete new file is ready. This keeps
            # the previous song intact if copying or validation fails.
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        source.unlink()
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
    for _ in range(3):
        # Turning off "auto" rerenders the option list and can select a default
        # model. Re-resolve the option node before every click.
        option = page.locator(
            ".semi-select-option-custom, .semi-select-option"
        ).filter(has_text=model_name).first
        await option.scroll_into_view_if_needed(timeout=5000)
        await option.click(timeout=5000)
        await page.wait_for_timeout(1000)
        if model_name in await dropdown.inner_text():
            return

    raise BrowserFlowError(f"模型选择验证失败: {model_name}")


async def select_singer(page: Any, singer_name: str) -> None:
    if not singer_name.strip():
        return

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
    try:
        legacy_tab_count = await tabs.count()
    except Exception:
        legacy_tab_count = 0
    if legacy_tab_count == 0:
        tabs = page.locator('button:visible, [role="tab"]:visible')
    lyric_tab = tabs.filter(has_text=re.compile(r"^\s*歌词\s*$")).first
    song_tab = tabs.filter(has_text=re.compile(r"^\s*歌曲\s*$")).first
    if not await song_tab.count():
        generation_tab = tabs.filter(has_text=re.compile(r"^\s*生成结果\s*$")).first
        if await generation_tab.count():
            await generation_tab.click(timeout=3000)
            await page.wait_for_timeout(1000)
            return
    await lyric_tab.click(timeout=3000)
    await page.wait_for_timeout(500)
    await song_tab.click(timeout=3000)
    await page.wait_for_timeout(1000)


def _normalize_lyric_content(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text.lower()))


_PLATFORM_SECTION_LABELS = re.compile(
    r"(?:pre[- ]?chorus|chorus(?:\s*[12])?|verse(?:\s*[12])?|bridge|outro|"
    r"预副歌|副歌(?:\s*[12])?|主歌(?:\s*[12])?|桥段|尾奏)",
    re.IGNORECASE,
)

_SONG_TITLE_PATTERN = re.compile(
    r"歌名\s*[：:]\s*[《\[]?(?P<title>[^》\]\r\n]+)[》\]]?",
    re.IGNORECASE,
)

_ASSET_CARD_SELECTION_JS = """
const visibleAssetCard = (element) => {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
};
const preferredCards = Array.from(document.querySelectorAll(
    '[class*="libraryItemWrapper"],[class*="generatedSongListItem"]'
)).filter(visibleAssetCard);
const fallbackCards = Array.from(document.querySelectorAll(
    '[class*="songItem"],[class*="assetItem"]'
)).filter(visibleAssetCard);
const cards = preferredCards.length ? preferredCards : fallbackCards;
const assetIdStore = window.__codexAssetCardIds ||
    (window.__codexAssetCardIds = new WeakMap());
let assetIdSequence = window.__codexAssetCardIdSequence || 0;
for (const card of cards) {
    if (!assetIdStore.has(card)) {
        assetIdStore.set(card, String(++assetIdSequence));
    }
}
window.__codexAssetCardIdSequence = assetIdSequence;
"""

_EDITOR_BUSY_MARKERS = ("正在添加素材到轨道", "检测中")
_EDITOR_READY_MIN_TIMEOUT_SECONDS = 120
_RECENT_ASSET_SCAN_ROUNDS = 16
_MAX_SONGS_TO_CHECK = 10
_GENERATED_VERSIONS_PER_SONG = 2
_MAX_GENERATION_ASSET_CHECK = _MAX_SONGS_TO_CHECK * _GENERATED_VERSIONS_PER_SONG


def _detail_song_name(detail_text: str) -> str:
    match = _SONG_TITLE_PATTERN.search(detail_text)
    return match.group("title").strip() if match else ""


def _same_song_title(first: str, second: str) -> bool:
    return bool(first.strip()) and first.strip() == second.strip()


def first_generated_candidate(
    candidates: list[GeneratedCandidate],
) -> GeneratedCandidate | None:
    """Return the first generated card in the platform's display order."""
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate.card_index)


async def _read_visible_lyric_detail(page: Any) -> str:
    new_section = _visible_only(page.locator('[class*="detailLyricsSection"]'))
    if await new_section.count():
        return await _locator_inner_text(new_section.first)
    lyric_title = page.locator(
        '[class*="detailPanel"] [class*="sectionTitle"]'
    ).filter(has_text=re.compile(r"^\s*歌词\s*$"))
    lyric_title = _visible_only(lyric_title).first
    detail_content = lyric_title.locator(
        "xpath=following-sibling::*[contains(@class,'sectionContent')][1]"
    )
    detail_content = _visible_only(detail_content)
    if await detail_content.count():
        return await _locator_inner_text(detail_content.first)
    return ""


def _visible_only(locator: Any) -> Any:
    try:
        return locator.filter(visible=True)
    except Exception:
        return locator


async def _locator_inner_text(locator: Any, timeout_ms: int = 1500) -> str:
    try:
        return await locator.inner_text(timeout=timeout_ms)
    except TypeError:
        # Focused tests use a minimal locator without Playwright keyword args.
        return await locator.inner_text()


async def _close_visible_song_detail(page: Any) -> None:
    try:
        close_button = page.locator('[aria-label="关闭详情"]')
        if await close_button.count():
            await close_button.first.click(timeout=2000)
            await page.wait_for_timeout(400)
    except Exception:
        pass


async def _click_song_card_title(card: Any) -> None:
    """Open a card's detail panel without accidentally triggering playback."""
    title = card.locator('[class*="title"]').first
    try:
        if await title.count():
            await title.scroll_into_view_if_needed(timeout=5000)
            await title.click(timeout=5000)
            return
    except Exception:
        pass
    await card.click(timeout=5000)


def _normalize_generated_detail(text: str) -> str:
    # The editor treats section labels as authoring directives, while the
    # current asset detail renders them as visible text. Remove that rendering
    # difference before comparing the submitted lyrics with the detail page.
    return _normalize_lyric_content(_PLATFORM_SECTION_LABELS.sub("", text))


def _lyric_probe(lyrics: str) -> str:
    # Structural labels are authoring directives; the platform detail may omit them.
    content = re.sub(r"\[[^\]]+\]", "", lyrics)
    return _normalize_lyric_content(content)


_LYRIC_MATCH_MIN_RATIO = 0.9
_LYRIC_MATCH_MIN_LENGTH = 12
_LYRIC_ANCHOR_MIN_LENGTH = 12
_LYRIC_LINE_COVERAGE_MIN_RATIO = 0.75
_FIRST_BATCH_LYRIC_CHARS = 80


def _lyric_similarity(first: str, second: str) -> float:
    if not first or not second:
        return 0.0
    if first in second or second in first:
        return 1.0
    if min(len(first), len(second)) < _LYRIC_MATCH_MIN_LENGTH:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


def _normalized_lyric_lines(text: str) -> list[str]:
    return [
        normalized
        for line in text.splitlines()
        if (normalized := _normalize_generated_detail(line))
    ]


def _lyric_anchor_lines(lyrics: str) -> list[str]:
    """Return the opening lines, using multiple lines only when needed."""
    anchor: list[str] = []
    anchor_length = 0
    for line in _normalized_lyric_lines(lyrics):
        anchor.append(line)
        anchor_length += len(line)
        if anchor_length >= _LYRIC_ANCHOR_MIN_LENGTH:
            break
    return anchor


def _lyric_match_score(actual_lyrics: str, expected_lyrics: str) -> float:
    actual = _normalize_generated_detail(actual_lyrics)
    expected = _lyric_probe(expected_lyrics)
    if not actual or not expected:
        return 0.0
    if actual in expected or expected in actual:
        return 1.0
    if min(len(actual), len(expected)) < _LYRIC_MATCH_MIN_LENGTH:
        return 0.0

    overall = _lyric_similarity(actual, expected)
    anchor_lines = _lyric_anchor_lines(expected_lyrics)
    if not anchor_lines:
        return overall

    expected_lines = set(_normalized_lyric_lines(expected_lyrics))
    actual_lines = set(_normalized_lyric_lines(actual_lyrics))
    if any(line not in actual_lines for line in anchor_lines):
        return overall
    expected_chars = sum(len(line) for line in expected_lines)
    if not expected_chars:
        return overall
    matched_chars = sum(
        len(line) for line in expected_lines if line in actual_lines
    )
    coverage = matched_chars / expected_chars
    if coverage < _LYRIC_LINE_COVERAGE_MIN_RATIO:
        return overall
    return max(overall, coverage)


def _lyrics_match(actual_lyrics: str, expected_lyrics: str) -> bool:
    return _lyric_match_score(actual_lyrics, expected_lyrics) >= _LYRIC_MATCH_MIN_RATIO


def _lyric_identity(lyrics: str, limit: int = _FIRST_BATCH_LYRIC_CHARS) -> str:
    """Return a stable leading slice used by exported-card searches."""
    normalized = _lyric_probe(lyrics)
    return normalized[:limit] if normalized else ""


async def verify_generated_song(page: Any, lyrics: str, song_name: str | None = None) -> None:
    if not lyrics.strip():
        return

    card = page.locator(
        '[class*="libraryItemWrapper"], [class*="generatedSongListItem"]'
    ).filter(visible=True).first
    try:
        await card.click(timeout=5000)
        await page.wait_for_timeout(1000)
        detail_lyrics = await _read_visible_lyric_detail(page)
    finally:
        await _close_visible_song_detail(page)

    if _lyrics_match(detail_lyrics, lyrics):
        return
    raise SongVerificationError(
        "生成结果歌词不匹配：平台详情歌词与本地歌词不一致"
        + (f"（本地歌名《{song_name}》）" if song_name else "")
    )


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


async def open_download_menu(
    page: Any,
    song_name: str,
    lyrics: str | None = None,
) -> Any:
    results_tab = page.locator("button").filter(has_text="生成结果").first
    await results_tab.click(timeout=5000)
    await page.wait_for_timeout(3000)

    if lyrics is None:
        card = page.locator('[class*="generatedSongCard"]').filter(
            has_text=song_name
        ).first
    else:
        card = await find_exported_download_card(page, song_name, lyrics)
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


async def find_exported_download_card(
    page: Any,
    song_name: str,
    lyrics: str,
) -> Any:
    """Find an editor-exported card in the newest generation window."""
    await _set_asset_scroll_position(page, "top")
    seen_cards: set[str] = set()
    checked_cards = 0
    last_total = -1
    last_scroll_height = -1
    stable_bottom_rounds = 0

    for _ in range(_RECENT_ASSET_SCAN_ROUNDS):
        summaries = await _asset_card_summaries(page)
        for summary in summaries:
            if checked_cards >= _MAX_GENERATION_ASSET_CHECK:
                break
            card_key = str(summary.get("asset_id") or "").strip()
            if not card_key:
                card_key = "|".join(
                    (
                        str(summary.get("title") or ""),
                        str(summary.get("source_tag") or ""),
                        str(summary.get("index") or ""),
                    )
                )
            if card_key in seen_cards:
                continue
            seen_cards.add(card_key)
            if not str(summary.get("title") or "").strip():
                continue
            checked_cards += 1
            if "编辑器导出" not in str(summary.get("source_tag") or ""):
                continue
            # Export names are written by our own export step. Trust an exact
            # title match because exported cards cannot open the lyrics detail.
            if _same_song_title(str(summary.get("title") or ""), song_name):
                return page.locator(
                    '[class*="generatedSongCard"]'
                ).filter(visible=True).nth(int(summary.get("index") or 0))

        if checked_cards >= _MAX_GENERATION_ASSET_CHECK:
            break

        position = await _step_asset_scroll(page)
        if not position:
            break

        scroll_height = int(position.get("scroll_height") or 0)
        at_bottom = int(position.get("scroll_top") or 0) >= max(
            int(position.get("max_scroll") or 0) - 1,
            0,
        )
        if (
            at_bottom
            and len(summaries) == last_total
            and scroll_height == last_scroll_height
        ):
            stable_bottom_rounds += 1
        else:
            stable_bottom_rounds = 0
        last_total = len(summaries)
        last_scroll_height = scroll_height

        await page.wait_for_timeout(700)
        if stable_bottom_rounds >= 2:
            break

    raise BrowserFlowError(
        f"未找到可下载的导出歌曲：未找到与本地歌词匹配且标记为编辑器导出的《{song_name}》"
    )


async def _asset_card_summaries(page: Any) -> list[dict]:
    try:
        value = await page.evaluate(
            """() => {
                """
            + _ASSET_CARD_SELECTION_JS
            + """
                return cards.map((card, index) => {
                    const titleNode = card.querySelector(
                        '[class*="title"],[class*="songName"],[class*="name"]'
                    );
                    const sourceNode = card.querySelector('[class*="sourceTag"]');
                    return {
                        index,
                        asset_id: assetIdStore.get(card) || '',
                        title: (titleNode ? titleNode.textContent : '').trim(),
                        source_tag: (sourceNode ? sourceNode.textContent : '').trim(),
                    };
                });
            }"""
        )
        if isinstance(value, list):
            return value
    except Exception:
        pass

    cards = page.locator('[class*="generatedSongCard"]').filter(visible=True)
    card_count = await cards.count()
    summaries: list[dict] = []
    for index in range(card_count):
        card = cards.nth(index)
        source_tags = card.locator('[class*="sourceTag"]')
        source_text = (
            await _locator_inner_text(source_tags.first)
            if await source_tags.count()
            else ""
        )
        title_node = card.locator('[class*="title"]').first
        summaries.append(
            {
                "index": index,
                "asset_id": "",
                "title": (await _locator_inner_text(title_node)).strip(),
                "source_tag": source_text.strip(),
            }
        )
    return summaries


async def _set_asset_scroll_position(page: Any, position: str) -> dict:
    return await _asset_scroll_action(page, position, 0)


async def _step_asset_scroll(page: Any) -> dict:
    return await _asset_scroll_action(page, "step", 0.8)


async def _asset_scroll_action(page: Any, action: str, ratio: float) -> dict:
    try:
        return await page.evaluate(
            """([action, ratio]) => {
                const container = Array.from(document.querySelectorAll('*')).find(
                    (element) => {
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 &&
                            (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                            element.scrollHeight > element.clientHeight + 5;
                    }
                );
                if (!container) return {};
                const maxScroll = Math.max(
                    container.scrollHeight - container.clientHeight,
                    0
                );
                if (action === 'top') {
                    container.scrollTop = 0;
                } else if (action === 'bottom') {
                    container.scrollTop = maxScroll;
                } else if (action === 'step') {
                    container.scrollTop = Math.min(
                        maxScroll,
                        container.scrollTop + container.clientHeight * ratio
                    );
                }
                return {
                    scroll_top: container.scrollTop,
                    scroll_height: container.scrollHeight,
                    client_height: container.clientHeight,
                    max_scroll: maxScroll,
                };
            }""",
            [action, ratio],
        )
    except Exception:
        return {}


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def new_cards_above_anchor(
    current_states: list[dict],
    anchor_title: str,
    *,
    baseline_count: int,
) -> list[dict]:
    """Return inserted cards even when a virtual list keeps a fixed length."""
    if anchor_title:
        for index, state in enumerate(current_states):
            if str(state.get("title") or "") == anchor_title:
                return current_states[:index]
    new_count = max(len(current_states) - baseline_count, 0)
    return current_states[:new_count]


class PageFlow:
    def __init__(
        self,
        *,
        page: Any,
        account: AccountConfig,
        settings: ConsoleSettings,
        screenshot_dir: Path,
        day: str | None = None,
    ) -> None:
        self.page = page
        self.account = account
        self.settings = settings
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.classification_retry_delay_ms = 5000
        self.day = day or datetime.now().strftime("%Y-%m-%d")
        self.force_new_generation = False
        self.redownload_stage = "auto"

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

        on_step("match_lyrics")
        await self.verify_generated_song(lyric_data.lyrics, lyric_data.song_name)

        on_step("enter_editor")
        await self.enter_editor(actual_song_name)

        on_step("export_song")
        await self.export_song(lyric_data.song_name)

        on_step("download_song")
        downloaded = await self.download_song(
            lyric_data.song_name,
            lyric_data.lyrics,
        )
        return archive_download(
            downloaded,
            Path(self.account.output_dir),
            lyric_data.song_name,
            self.day,
        )

    async def _mouse_click_text(self, text: str, description: str, *, exact: bool = False) -> None:
        try:
            target = self.page.get_by_text(text, exact=exact).first
            await target.scroll_into_view_if_needed(timeout=5000)
            await trusted_click(self.page, target, description)
        except Exception as error:
            raise BrowserFlowError(f"{description}失败: {error}") from error

    async def _click_option_after_label(self, label_text: str, option_text: str) -> None:
        try:
            point = await self.page.evaluate(
                """([labelText, optionText]) => {
                    const nodes = Array.from(document.querySelectorAll('label,div,section'));
                    const label = nodes.find(node => node.textContent.trim().includes(labelText));
                    if (!label) return null;
                    let scope = label;
                    for (let depth = 0; depth < 8 && scope.parentElement; depth += 1) {
                        scope = scope.parentElement;
                        const options = Array.from(scope.querySelectorAll('*')).filter(node => {
                            const ownText = Array.from(node.childNodes)
                                .filter(child => child.nodeType === Node.TEXT_NODE)
                                .map(child => child.textContent.trim()).join('');
                            return ownText === optionText;
                        });
                        const option = options.find(node => {
                            const rect = node.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        });
                        if (option) {
                            const rect = option.getBoundingClientRect();
                            return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
                        }
                    }
                    return null;
                }""",
                [label_text, option_text],
            )
            if not point:
                raise BrowserFlowError(f"找不到选项: {label_text} / {option_text}")
            await self.page.mouse.move(point["x"], point["y"])
            await self.page.wait_for_timeout(300)
            await self.page.mouse.click(point["x"], point["y"])
            await self.page.wait_for_timeout(600)
        except BrowserFlowError:
            raise
        except Exception as error:
            raise BrowserFlowError(f"点击选项失败: {label_text} / {option_text}: {error}") from error

    async def _fill_field_near(self, label_text: str, value: str, *, multiline: bool = False) -> None:
        try:
            field = await self.page.evaluate_handle(
                """([labelText, multiline]) => {
                    const nodes = Array.from(document.querySelectorAll('label,div,section'));
                    const label = nodes.find(node => node.textContent.trim().includes(labelText));
                    if (!label) return null;
                    let scope = label;
                    for (let depth = 0; depth < 10 && scope.parentElement; depth += 1) {
                        scope = scope.parentElement;
                        const fields = Array.from(scope.querySelectorAll(multiline ? 'textarea' : 'input:not([type=file])'));
                        const field = fields.find(node => {
                            const rect = node.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        });
                        if (field) return field;
                    }
                    return null;
                }""",
                [label_text, multiline],
            )
            element = field.as_element()
            if not element:
                raise BrowserFlowError(f"找不到输入框: {label_text}")
            await element.scroll_into_view_if_needed(timeout=5000)
            if multiline:
                await type_segmented(element, value, chunk_size=80)
            else:
                await clear_and_type(element, value)
            await self.page.wait_for_timeout(500)
        except BrowserFlowError:
            raise
        except Exception as error:
            raise BrowserFlowError(f"填写失败: {label_text}: {error}") from error

    async def _upload_song_count(self) -> int:
        return await self.page.locator(
            'input[id^="songs["][id$="[title]"]'
        ).count()

    async def _upload_song_states(self) -> list[dict]:
        states = await self.page.evaluate(
            r"""() => Array.from(
                document.querySelectorAll('input[id^="songs["][id$="[title]"]')
            ).map((input, index) => {
                let root = input;
                while (root && !root.querySelector('button span[aria-label="delete_stroked"]')) {
                    root = root.parentElement;
                }
                return {
                    index,
                    title: input.value.trim(),
                    text: root ? root.innerText : '',
                };
            })"""
        )
        return states if isinstance(states, list) else []

    @staticmethod
    def _is_noncompliant_upload_song(state: dict) -> bool:
        text = str(state.get("text") or "")
        markers = (
            "重新上传",
            "音频结尾有明显截断感",
            "音频检测未通过",
            "音频质量",
            "不符合平台",
            "不达标",
            "请调整淡出效果",
        )
        return any(marker in text for marker in markers)

    async def _dismiss_blocking_upload_modal(self) -> None:
        modal = self.page.locator(".douyin-music-modal-content").filter(visible=True).last
        if not await modal.count():
            return
        try:
            text = await modal.inner_text()
        except Exception:
            text = ""
        if "删除后" in text:
            return

        accept = modal.locator("button:visible").filter(
            has_text=re.compile(r"^\s*(?:我知道了|知道了|我已知晓|确定|确认|取消)\s*$")
        ).first
        if await accept.count():
            await dom_click(accept, "关闭上传提示弹窗")
        else:
            await self.page.keyboard.press("Escape")
        try:
            await modal.wait_for(state="hidden", timeout=2000)
        except Exception:
            pass

    async def _remove_upload_song_at(self, index: int) -> None:
        before_count = await self._upload_song_count()
        await self._dismiss_blocking_upload_modal()
        button = (
            self.page.locator('span[aria-label="delete_stroked"]')
            .nth(index)
            .locator("xpath=ancestor::button[1]")
        )
        await button.scroll_into_view_if_needed(timeout=5000)
        await self.page.wait_for_timeout(300)
        await trusted_click(
            self.page,
            button,
            f"删除第 {index + 1} 首上传歌曲",
        )

        dialog = self.page.locator(".douyin-music-modal-content").filter(
            has_text="删除后"
        )
        await dialog.wait_for(state="visible", timeout=5000)
        confirm = dialog.locator("button").filter(has_text="确定").last
        await trusted_click(self.page, confirm, "确认删除上传歌曲")

        for _ in range(20):
            if await self._upload_song_count() == before_count - 1:
                await self.page.wait_for_timeout(500)
                return
            await self.page.wait_for_timeout(500)

        path = await self._screenshot("upload-remove-song-timeout")
        raise BrowserFlowError(f"移除不合格歌曲超时；截图: {path}")

    async def _remove_noncompliant_upload_songs(self) -> list[str]:
        removed: list[str] = []
        for _ in range(20):
            states = await self._upload_song_states()
            if not states:
                break
            rejected = [state for state in states if self._is_noncompliant_upload_song(state)]
            if not rejected:
                break
            for state in reversed(rejected):
                await self._remove_upload_song_at(int(state["index"]))
                removed.append(str(state.get("title") or f"第 {int(state['index']) + 1} 首"))
            await self.page.wait_for_timeout(1000)
        return list(dict.fromkeys(removed))

    async def _wait_upload_audio_ready(self) -> None:
        stable = 0
        for _ in range(180):
            body = await self.page.inner_text("body")
            busy_markers = (
                "音频检测中",
                "智能生成高光片段中",
                "上传中",
                "请等待封面上传完成",
            )
            has_percentage = bool(re.search(r"\d+(?:\.\d+)?%", body))
            stable = (
                stable + 1
                if not any(marker in body for marker in busy_markers) and not has_percentage
                else 0
            )
            if stable >= 5:
                return
            await self.page.wait_for_timeout(1000)
        path = await self._screenshot("upload-audio-inspection-timeout")
        raise BrowserFlowError(f"音频检测超时；截图: {path}")

    async def _visible_upload_diagnostics(self) -> str:
        errors = await self.page.evaluate(
            """() => Array.from(document.querySelectorAll(
                '.douyin-music-form-field-error, .douyin-music-toast, .ant-message, .semi-toast'
            )).filter(node => node.offsetParent).map(node => node.innerText.trim()).filter(Boolean)
            """
        )
        body = await self.page.inner_text("body")
        busy_lines = [
            line.strip()
            for line in body.splitlines()
            if any(
                marker in line
                for marker in (
                    "音频检测中",
                    "智能生成高光片段中",
                    "上传中",
                    "请等待封面上传完成",
                )
            )
            or re.search(r"\d+(?:\.\d+)?%", line)
        ]
        details = []
        if errors:
            details.append("平台错误: " + " | ".join(errors))
        if busy_lines:
            details.append("未完成状态: " + " | ".join(busy_lines[:20]))
        return "; ".join(details)

    async def _wait_authorization_step(self) -> None:
        title_input = self.page.locator('input[id="songs[0][title]"]')
        for _ in range(30):
            body = await self.page.inner_text("body")
            title_visible = await title_input.is_visible()
            if "授权信息" in body and not title_visible:
                return
            await self.page.wait_for_timeout(1000)
        diagnostics = await self._visible_upload_diagnostics()
        next_buttons = await self.page.evaluate(
            """() => Array.from(document.querySelectorAll('button'))
                .filter(node => node.offsetParent && node.innerText.trim() === '下一步')
                .map(node => {
                    const rect = node.getBoundingClientRect();
                    return {
                        text: node.innerText.trim(),
                        disabled: node.disabled,
                        rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    };
                })
            """
        )
        path = await self._screenshot("upload-next-validation-failed")
        message = f"点击下一步后未进入授权页；截图: {path}"
        if diagnostics:
            message = f"{message}; {diagnostics}"
        if next_buttons:
            message = f"{message}; 可见下一步: {next_buttons}"
        raise BrowserFlowError(message)

    async def _authorization_step_ready(self) -> bool:
        body = await self.page.inner_text("body")
        title_input = self.page.locator('input[id="songs[0][title]"]')
        title_visible = await title_input.is_visible()
        return "授权信息" in body and not title_visible

    async def _wait_authorization_step_ready(self, *, timeout_seconds: int = 10) -> bool:
        deadline = datetime.now().timestamp() + timeout_seconds
        while datetime.now().timestamp() < deadline:
            if await self._authorization_step_ready():
                return True
            await self.page.wait_for_timeout(500)
        return False

    async def _configure_upload_ai_tools(self, *, ai_created: bool) -> None:
        radio_scope = self.page.locator(
            'div[x-field-id="aiTools[isMakeByAITools]"] label.douyin-music-radio'
        )
        option_text = "是" if ai_created else "否"
        option = radio_scope.filter(
            has_text=re.compile(rf"^\s*{option_text}\s*$")
        ).first
        await trusted_click(
            self.page,
            option,
            f"AI创作声明选择{option_text}",
        )
        await self.page.wait_for_timeout(800)

        if not ai_created:
            return

        combo = self.page.locator(
            '[role=combobox][aria-labelledby="aiTools[makeWithAIToolNames]-label"]'
        )
        await trusted_click(self.page, combo, "AI工具下拉")
        await self.page.wait_for_timeout(800)
        other = self.page.locator("[role=option]").filter(
            has_text=re.compile(r"其他")
        ).first
        await other.click(timeout=5000)
        await self.page.wait_for_timeout(1000)

        other_tool = self.page.locator(
            'input[id="aiTools[makeWithOtherAIToolNames]"]'
        )
        await other_tool.fill("妙响")

    async def _add_next_upload_song(self, current_index: int) -> None:
        expected_count = current_index + 2
        add_control = self.page.locator(".fYIL9")
        # Continue adding songs while earlier files upload in parallel. The
        # normal click retries if the control rerenders during uploading.
        for attempt in range(3):
            try:
                await add_control.click(timeout=10000)
            except Exception:
                if attempt == 2:
                    raise

            for _ in range(20):
                if await self._upload_song_count() >= expected_count:
                    return
                await self.page.wait_for_timeout(500)

        path = await self._screenshot("upload-add-song-still-failed")
        raise BrowserFlowError(
            f"添加第 {current_index + 2} 首歌曲失败；截图: {path}"
        )

    async def _fill_upload_control(self, locator: Any, value: str) -> None:
        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        if await locator.is_visible():
            await locator.fill(value)
            return

        # The publish form can keep a textarea attached but hidden while its
        # card is collapsed. Update React's controlled value through the native
        # setter and bubble input/change events so platform state stays in sync.
        await locator.evaluate(
            """(element, value) => {
                const prototype = element instanceof HTMLTextAreaElement
                    ? HTMLTextAreaElement.prototype
                    : HTMLInputElement.prototype;
                const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
                descriptor?.set?.call(element, value);
                element.dispatchEvent(new Event("input", { bubbles: true }));
                element.dispatchEvent(new Event("change", { bubbles: true }));
            }""",
            value,
        )
        if (await locator.input_value()).strip() != value.strip():
            raise BrowserFlowError("上传表单隐藏输入框写入失败")

    async def _select_upload_original(self, locator: Any, description: str) -> None:
        # Upload cards keep moving while earlier files are being processed.
        # Activate the attached radio through the DOM so Playwright does not
        # wait for the element to become stable after scrolling.
        try:
            await locator.evaluate("(element) => element.click()")
            return
        except Exception as js_error:
            try:
                await trusted_click(self.page, locator, description)
            except Exception as click_error:
                raise BrowserFlowError(
                    f"点击失败: {description}: {click_error}"
                ) from js_error

    async def _fill_upload_song(self, item: dict, index: int, *, is_last: bool) -> None:
        try:
            original = self.page.locator(
                f'div[x-field-id="songs[{index}][originalType]"] label.douyin-music-radio'
            ).filter(has_text=re.compile(r"^\s*原创")).first
            await self._select_upload_original(
                original,
                f"第 {index + 1} 首选择原创",
            )

            file_input = self.page.locator(
                f'xpath=//label[@for="songs[{index}][_fullAudios]"]/'
                f'following::input[@type="file" and contains(@class,"douyin-music-upload-hidden-input")][1]'
            )
            await file_input.set_input_files(item["path"])

            title = self.page.locator(f'input[id="songs[{index}][title]"]')
            lyrics = self.page.locator(f'textarea[id="songs[{index}][lyricText]"]')
            await self._fill_upload_control(title, item["title"])
            await self._fill_upload_control(lyrics, item["lyrics"])
            await self.page.wait_for_timeout(500)

            if not is_last:
                await self._add_next_upload_song(index)
        except BrowserFlowError:
            raise
        except Exception as error:
            raise BrowserFlowError(f"填写上传歌曲失败: {item['title']}: {error}") from error

    async def _use_smart_cover(self, prompt: str, cover_path: str | None = None) -> None:
        smart = self.page.locator("button:visible").filter(
            has_text=re.compile(r"^\s*智能封面\s*$")
        ).first
        try:
            await smart.wait_for(state="visible", timeout=120000)
            deadline = datetime.now().timestamp() + 120
            while not await smart.is_enabled():
                if datetime.now().timestamp() >= deadline:
                    raise TimeoutError("smart cover control did not become enabled")
                await self.page.wait_for_timeout(1000)
        except Exception:
            if not cover_path:
                raise BrowserFlowError("智能封面不可用，且本地封面文件不存在")
            cover_input = self.page.locator(
                'div[x-field-id="album[_coverValue]"] '
                'input.douyin-music-upload-hidden-input'
            ).first
            await self._upload_local_cover(cover_path)
            return
            for _ in range(30):
                body = await self.page.inner_text("body")
                if "重新上传" in body:
                    await self.page.wait_for_timeout(2000)
                    return
                await self.page.wait_for_timeout(1000)
            path = await self._screenshot("upload-local-cover-timeout")
            raise BrowserFlowError(f"本地封面上传超时；截图: {path}")
        await dom_click(smart, "智能封面")
        await self.page.wait_for_timeout(1000)

        notice = self.page.locator("button:visible").filter(
            has_text=re.compile(r"^\s*我已知晓\s*$")
        ).first
        if await notice.count():
            await dom_click(notice, "智能封面提示确认")
            await self.page.wait_for_timeout(2000)

        prompt_field = self.page.locator(
            "textarea#prompt:visible, .douyin-music-modal-content textarea:visible, "
            ".semi-modal-content textarea:visible"
        ).first
        await prompt_field.wait_for(state="visible", timeout=10000)
        await prompt_field.fill(prompt[:50])
        generate = self.page.locator("button:visible").filter(
            has_text=re.compile(r"一键生成封面")
        ).first
        await dom_click(generate, "一键生成封面")
        deadline = datetime.now().timestamp() + 300
        stable_enabled = 0
        while True:
            button = self.page.locator("button:visible").filter(
                has_text=re.compile(r"^\s*使用封面\s*$")
            ).first
            enabled = await button.is_enabled()
            stable_enabled = stable_enabled + 1 if enabled else 0
            if stable_enabled >= 2:
                await dom_click(button, "使用封面")
                for _ in range(20):
                    confirm = self.page.locator("button:visible").filter(
                        has_text=re.compile(r"^\s*确定使用\s*$")
                    ).first
                    if await confirm.count():
                        await dom_click(confirm, "确定使用封面")
                    await self.page.wait_for_timeout(500)
                    if not await self.page.locator(
                        "textarea#prompt:visible, .douyin-music-modal-content textarea:visible, "
                        ".semi-modal-content textarea:visible"
                    ).count():
                        await self.page.wait_for_timeout(1000)
                        if cover_path:
                            await self._upload_local_cover(cover_path)
                            return
                        if await self._wait_for_album_cover(timeout_seconds=30):
                            return
                        path = await self._screenshot("upload-smart-cover-not-applied")
                        raise BrowserFlowError(
                            f"smart cover was not applied to the album field; screenshot: {path}"
                        )
                path = await self._screenshot("upload-use-cover-not-closed")
                raise BrowserFlowError(f"点击使用封面后弹窗未关闭；截图: {path}")
            await self.page.wait_for_timeout(3000)
        raise BrowserFlowError("智能封面生成超时")

    async def _album_cover_state(self) -> dict:
        state = await self.page.evaluate(
            r"""() => {
                const field = document.querySelector('div[x-field-id="album[_coverValue]"]');
                if (!field) return {exists: false, text: '', images: 0, backgrounds: 0};
                const images = Array.from(field.querySelectorAll('img')).filter(image => {
                    const rect = image.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
                const backgrounds = Array.from(field.querySelectorAll('*')).filter(node => {
                    const value = node.style?.backgroundImage || '';
                    return /url\(/i.test(value);
                });
                return {
                    exists: true,
                    text: field.innerText || '',
                    images: images.length,
                    backgrounds: backgrounds.length,
                };
            }"""
        )
        return state if isinstance(state, dict) else {}

    async def _wait_for_album_cover(self, *, timeout_seconds: int = 60) -> bool:
        deadline = datetime.now().timestamp() + timeout_seconds
        stable = 0
        while datetime.now().timestamp() < deadline:
            state = await self._album_cover_state()
            ready = bool(
                state.get("images")
                or state.get("backgrounds")
                or ("重新上传" in str(state.get("text") or ""))
            )
            stable = stable + 1 if ready else 0
            if stable >= 2:
                return True
            await self.page.wait_for_timeout(1000)
        return False

    async def _upload_local_cover(self, cover_path: str) -> None:
        cover_input = self.page.locator(
            'div[x-field-id="album[_coverValue]"] '
            'input.douyin-music-upload-hidden-input'
        ).first
        await cover_input.set_input_files(cover_path)
        await self._confirm_cover_adjustment()
        if not await self._wait_for_album_cover(timeout_seconds=60):
            path = await self._screenshot("upload-local-cover-timeout")
            state = await self._album_cover_state()
            raise BrowserFlowError(
                f"local cover was not applied; state={state}; screenshot={path}"
            )

    async def _confirm_cover_adjustment(self) -> None:
        modal = self.page.locator(".douyin-music-modal-content").filter(
            has_text=re.compile(r"调整图片")
        ).last
        try:
            await modal.wait_for(state="visible", timeout=15000)
        except Exception:
            return

        confirm = modal.locator('button[aria-label="confirm"]').last
        await trusted_click(self.page, confirm, "确认调整封面")
        try:
            await modal.wait_for(state="hidden", timeout=15000)
        except Exception:
            path = await self._screenshot("upload-cover-adjust-not-closed")
            raise BrowserFlowError(f"调整封面弹窗未关闭；截图: {path}")

    async def _add_self_to_upload_producers(
        self,
        expected_songs: int | None = None,
    ) -> None:
        fields = self.page.locator(
            'div.semi-form-field[class*="producerArtists"]'
        )
        expected = max(int(expected_songs or 0), 0)
        deadline = datetime.now().timestamp() + 30
        while True:
            count = await fields.count()
            if (expected and count >= expected) or (not expected and count):
                break
            if datetime.now().timestamp() >= deadline:
                break
            await self.page.wait_for_timeout(500)

        count = await fields.count()
        if not count:
            return
        if expected and count < expected:
            path = await self._screenshot("upload-producer-fields-incomplete")
            raise BrowserFlowError(
                f"授权页制作人字段未加载完整，预期 {expected} 首，"
                f"实际 {count} 首；截图: {path}"
            )

        add_text = re.compile(r"^\s*添加自己\s*$")
        for index in range(count):
            field = fields.nth(index)
            selected = field.locator(".douyin-music-tag-group")
            if await selected.count():
                continue

            added = False
            for _ in range(3):
                button = field.locator("button").filter(has_text=add_text).first
                if not await button.count():
                    break
                await dom_click(button, f"第 {index + 1} 首添加自己")
                for _ in range(20):
                    if await selected.count():
                        added = True
                        break
                    await self.page.wait_for_timeout(250)
                if added:
                    break

            if not added:
                path = await self._screenshot("upload-add-self-failed")
                raise BrowserFlowError(
                    f"第 {index + 1} 首添加自己失败；截图: {path}"
                )

    async def _fill_authorization(
        self,
        real_name: str,
        expected_songs: int | None = None,
    ) -> None:
        if real_name.strip():
            await self.page.evaluate(
                """(realName) => {
                    const fields = Array.from(document.querySelectorAll(
                        'input[placeholder="请输入真实姓名"]'
                    )).filter(field => field.offsetParent);
                    for (const field of fields) {
                        const descriptor = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype,
                            "value"
                        );
                        descriptor?.set?.call(field, realName);
                        field.dispatchEvent(new Event("input", { bubbles: true }));
                        field.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }""",
                real_name,
            )

        await self._add_self_to_upload_producers(expected_songs)
        await self.page.wait_for_timeout(1000)

        for _ in range(10):
            link = self.page.locator(
                ".douyin-music-select:visible"
            ).filter(
                has_text=re.compile(r"^\s*有主页链接\s*$")
            ).first
            if not await link.count():
                return

            # Newer publish pages expose artist-link type as direct radio
            # chips instead of the old homepage-link dropdown.
            platform_info = self.page.locator(
                "label:visible, button:visible, [role=button]:visible, "
                ".douyin-music-radio:visible, .douyin-music-select-item:visible"
            ).filter(
                has_text=re.compile(r"^\s*(?:其它|其他)平台个人信息\s*$")
            ).first
            if await platform_info.count():
                await dom_click(platform_info, "选择其他平台个人信息")
                await self.page.wait_for_timeout(800)
                continue

            await dom_click(link, "切换无主页链接")
            await self.page.wait_for_timeout(800)
            no_link = self.page.locator(
                ".douyin-music-select-option-list:visible > *, "
                ".douyin-music-select-item:visible, .douyin-music-select-option:visible, "
                "[role=option]:visible"
            ).filter(
                has_text=re.compile(r"^\s*无主页链接\s*$")
            ).first
            if not await no_link.count():
                diagnostics = await self.page.evaluate(
                    """() => Array.from(document.querySelectorAll(
                        '.douyin-music-select-dropdown, .douyin-music-select-option-list-wrapper, .douyin-music-select-option-list > *, .douyin-music-select-item, .douyin-music-select-option, [role=option], [class*="option"], [class*="item"]'
                    )).filter(node => node.offsetParent).map(node => ({
                        tag: node.tagName,
                        className: String(node.className),
                        text: node.innerText.trim(),
                    })).slice(0, 80)"""
                )
                path = await self._screenshot("upload-no-link-option-missing")
                raise BrowserFlowError(
                    f"未找到无主页链接选项；可见选项: {diagnostics}；截图: {path}"
                )
            await dom_click(no_link, "选择无主页链接")
            await self.page.wait_for_timeout(800)
        path = await self._screenshot("upload-link-switch-failed")
        raise BrowserFlowError(f"切换无主页链接次数异常；截图: {path}")

    async def _sign_frame_ready(self, frame: Any) -> bool:
        try:
            body = await frame.locator("body").inner_text(timeout=1000)
        except Exception:
            return False
        return (
            ("签约主体" in body or "文件签署" in body)
            and "签署" in body
        )

    async def _find_sign_frame(self):
        for frame in self.page.frames:
            if frame is self.page.main_frame:
                continue
            if await self._sign_frame_ready(frame):
                return frame
        return None

    async def _wait_sign_frame(self):
        # A multi-song contract can take longer to initialize its iframe.
        deadline = datetime.now().timestamp() + 240
        while datetime.now().timestamp() < deadline:
            frame = await self._find_sign_frame()
            if frame is not None:
                try:
                    await frame.locator("button").filter(
                        has_text=re.compile(r"^\s*签署\s*$")
                    ).last.wait_for(state="visible", timeout=1000)
                    return frame
                except Exception:
                    pass
            await self.page.wait_for_timeout(1000)
        path = await self._screenshot("upload-sign-frame-timeout")
        raise BrowserFlowError(f"签署协议窗口加载超时；截图: {path}")

    async def _current_sign_frame(self):
        return await self._find_sign_frame()

    async def _verification_popup_visible(self) -> bool:
        frame = await self._current_sign_frame()
        if frame is None:
            return False
        try:
            body = await frame.locator("body").inner_text(timeout=1000)
            return "意愿认证" in body and "获取验证码" in body
        except Exception:
            return False

    async def _wait_for_external_verification(self) -> None:
        # The user enters the SMS code directly in the platform popup. Poll at
        # a relaxed interval and complete once that popup is dismissed. SMS
        # verification is a human action, so waiting has no automatic deadline.
        while True:
            if not await self._verification_popup_visible():
                await self.page.wait_for_timeout(3000)
                if not await self._verification_popup_visible():
                    await self._wait_publish_completion()
                    return
            await self.page.wait_for_timeout(10000)

    async def _publish_success_visible(self) -> bool:
        try:
            body = await self.page.inner_text("body")
        except Exception:
            return False
        return "已完成作品上传" in body and "审核中" in body

    async def _wait_publish_completion(self) -> None:
        # Keep the task browser open until the platform explicitly shows its
        # final upload-review confirmation. A human can still stop the task.
        while True:
            if await self._publish_success_visible():
                await self.page.wait_for_timeout(3000)
                await self._screenshot("upload-publish-success")
                return
            await self.page.wait_for_timeout(3000)

    async def _submit_sign_verification(
        self,
        on_verification_requested: Callable[[], Awaitable[None]],
    ) -> None:
        frame = await self._wait_sign_frame()
        sign_button = frame.locator("button").filter(
            has_text=re.compile(r"^\s*签署\s*$")
        ).last
        await sign_button.click(timeout=5000)

        refreshed_frame = None
        for _ in range(20):
            refreshed_frame = await self._current_sign_frame()
            if refreshed_frame is not None:
                try:
                    body = await refreshed_frame.locator("body").inner_text(timeout=1000)
                    if "意愿认证" in body and "获取验证码" in body:
                        break
                except Exception:
                    pass
            await self.page.wait_for_timeout(500)
        if refreshed_frame is None:
            path = await self._screenshot("upload-verification-frame-timeout")
            raise BrowserFlowError(f"签署验证窗口加载超时；截图: {path}")
        frame = refreshed_frame

        verification_title = frame.get_by_text("意愿认证", exact=True)
        await verification_title.wait_for(state="visible", timeout=15000)
        get_code = frame.get_by_text("获取验证码", exact=True).last
        await get_code.click(timeout=5000)

        await on_verification_requested()
        await self._wait_for_external_verification()

    async def upload_album(
        self,
        items: list[dict],
        on_step: Callable[[str, int], None],
        on_verification_requested: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            on_step("open_publish_page", 0)
            await self._ensure_active_page()
            await self._open_publish_tab()
            await self.page.goto(
                "https://music.douyin.com/console/publish?enter_from=publish_main_button",
                wait_until="domcontentloaded",
                timeout=self.settings.page_load_timeout_seconds * 1000,
            )
            body_text = await self.page.inner_text("body")
            if is_login_challenge(body_text):
                raise LoginRequiredError("检测到汽水音乐登录页，请先登录当前账号")
            publish_full = self.page.locator("button").filter(
                has_text=re.compile(r"^\s*发布全曲\s*$")
            ).first
            # This entry rerenders while the locator is being scrolled into
            # view. Playwright's normal click retries against the fresh DOM.
            await publish_full.click(timeout=10000)
            await self.page.wait_for_timeout(5000)

            await self._configure_upload_ai_tools(
                ai_created=bool(items[0].get("ai_created", True)),
            )
            for index, item in enumerate(items):
                on_step("add_song", index)
                await self._fill_upload_song(
                    item,
                    index,
                    is_last=index == len(items) - 1,
                )
            remaining_titles = {
                str(state.get("title") or "")
                for state in await self._upload_song_states()
            }
            active_items = [item for item in items if item["title"] in remaining_titles]
            if not active_items:
                return []

            on_step("album_info", len(active_items))
            album_name = self.page.locator('input[id="album[albumName]"]')
            await self._fill_upload_control(album_name, active_items[0]["title"])

            on_step("wait_uploads", len(active_items))
            await self._wait_upload_audio_ready()
            await self._use_smart_cover(
                active_items[0]["cover_prompt"],
                active_items[0].get("cover_path"),
            )
            await self._wait_upload_audio_ready()

            removed_items = await self._remove_noncompliant_upload_songs()
            if removed_items:
                on_step("remove_noncompliant_songs", len(removed_items))

            remaining_titles = {
                str(state.get("title") or "")
                for state in await self._upload_song_states()
            }
            active_items = [item for item in items if item["title"] in remaining_titles]
            if not active_items:
                return []

            if await album_name.input_value() != active_items[0]["title"]:
                await self._fill_upload_control(
                    album_name,
                    active_items[0]["title"],
                )
            next_button = self.page.locator("button:visible").filter(
                has_text=re.compile(r"^\s*下一步\s*$")
            ).first
            await trusted_click(self.page, next_button, "专辑下一步")
            if not await self._wait_authorization_step_ready():
                await self._wait_upload_audio_ready()
                next_button = self.page.locator("button:visible").filter(
                    has_text=re.compile(r"^\s*下一步\s*$")
                ).first
                await trusted_click(self.page, next_button, "专辑下一步")
            await self._wait_authorization_step()
            on_step("authorization", len(items))
            await self._fill_authorization(
                items[0]["real_name"],
                expected_songs=len(active_items),
            )
            authorization_next = self.page.locator("button:visible").filter(
                has_text=re.compile(r"^\s*下一步\s*$")
            ).first
            await trusted_click(
                self.page, authorization_next, "授权下一步"
            )
            await self.page.wait_for_timeout(2000)
            await self._submit_sign_verification(on_verification_requested)
            on_step("done", len(items))
            return active_items
        except (GenerationLimitError, LoginRequiredError, SongVerificationError):
            raise
        except Exception as error:
            await self._raise_with_screenshot("发布全曲", error)

    async def process_batch(
        self,
        lyric_data_list: list[LyricData],
        on_step: Callable[[str, str | None], None],
    ) -> list[BatchSongResult]:
        on_step("page_ready", None)
        await self.ensure_create_page_ready()
        on_step("recover_existing_generation", None)
        recovered_candidates = (
            {}
            if self.force_new_generation
            else await self.recover_existing_candidates(lyric_data_list)
        )
        lyrics_to_submit = [
            lyric_data
            for lyric_data in lyric_data_list
            if not recovered_candidates.get(lyric_data.song_name)
        ]
        baseline_states = await _maybe_await(self.asset_card_states())
        baseline_count = len(baseline_states)
        baseline_anchor = next(
            (
                str(state.get("title") or "")
                for state in baseline_states
                if not state.get("loading")
            ),
            "",
        )

        generated_cards: list[dict] = []
        for lyric_data in lyrics_to_submit:
            on_step("fill_inputs", lyric_data.song_name)
            await self.fill_inputs(lyric_data)
            on_step("generate", lyric_data.song_name)
            await self.generate()
            try:
                await self._ensure_no_generation_failure()
            except SongGenerationFailureError as error:
                if "无法根据描述生成" not in str(error):
                    raise
                return [
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="description_rejected",
                        error=str(error),
                    )
                ]
            on_step("check_limit", lyric_data.song_name)
            await self.check_generation_limit()

        on_step("wait_generation", None)
        if lyrics_to_submit:
            generated_cards = await self.wait_for_batch_generation(
                baseline_count,
                len(lyrics_to_submit),
                baseline_anchor=baseline_anchor,
            )
        on_step("match_lyrics", None)
        candidates = await self.classify_generated_cards(
            generated_cards,
            lyrics_to_submit,
        ) if lyrics_to_submit else {}
        missing_after_first_classification = any(
            not candidates.get(lyric_data.song_name)
            for lyric_data in lyrics_to_submit
        )
        if lyrics_to_submit and generated_cards and missing_after_first_classification:
            on_step("match_lyrics_settling", None)
            await self.page.wait_for_timeout(self.classification_retry_delay_ms)
            current_states = await _maybe_await(self.asset_card_states())
            settled_cards = new_cards_above_anchor(
                current_states,
                baseline_anchor,
                baseline_count=baseline_count,
            )
            settled_candidates = await self.classify_generated_cards(
                settled_cards,
                lyrics_to_submit,
            )
            for song_name, song_candidates in settled_candidates.items():
                merged = {
                    (candidate.generated_title, candidate.card_index): candidate
                    for candidate in candidates.get(song_name, [])
                }
                for candidate in song_candidates:
                    merged[(candidate.generated_title, candidate.card_index)] = candidate
                candidates[song_name] = list(merged.values())
        for song_name, song_candidates in recovered_candidates.items():
            if song_candidates:
                candidates[song_name] = song_candidates

        results: list[BatchSongResult] = []
        for lyric_data in lyric_data_list:
            matches = candidates.get(lyric_data.song_name, [])
            if not matches:
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="lyric_unmatched",
                        error="歌曲详情歌词与本地歌词不匹配，已跳过",
                    )
                )
                continue

            # The platform lists the generated versions in result order. Keep
            # using the first matching card instead of the newest card overall.
            selected = first_generated_candidate(matches)
            assert selected is not None
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
            except SongGenerationFailureError as error:
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="generation_failed",
                        error=str(error),
                    )
                )
                continue
            except SongExportError as error:
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="export_failed",
                        error=str(error),
                    )
                )
                continue
            except SongDownloadError as error:
                results.append(
                    BatchSongResult(
                        song_name=lyric_data.song_name,
                        status="download_failed",
                        error=str(error),
                    )
                )
                continue
            except Exception as error:
                # Export dialogs can be swallowed by a page rerender. Retry the
                # already-generated candidate once before declaring export failure.
                fallback_status = (
                    "export_failed"
                    if isinstance(error, SongExportError)
                    else "download_failed"
                )
                try:
                    await self.page.wait_for_timeout(2000)
                    output_path = await self.export_candidate(selected, lyric_data)
                    results.append(
                        BatchSongResult(
                            song_name=lyric_data.song_name,
                            status="success",
                            output_path=str(output_path),
                        )
                    )
                    continue
                except SongGenerationFailureError as retry_error:
                    results.append(
                        BatchSongResult(
                            song_name=lyric_data.song_name,
                            status="generation_failed",
                            error=str(retry_error),
                        )
                    )
                    continue
                except SongExportError as retry_error:
                    results.append(
                        BatchSongResult(
                            song_name=lyric_data.song_name,
                            status="export_failed",
                            error=str(retry_error),
                        )
                    )
                    continue
                except SongDownloadError as retry_error:
                    results.append(
                        BatchSongResult(
                            song_name=lyric_data.song_name,
                            status="download_failed",
                            error=str(retry_error),
                        )
                    )
                    continue
                except Exception as retry_error:
                    results.append(
                        BatchSongResult(
                            song_name=lyric_data.song_name,
                            status=fallback_status,
                            error=str(retry_error),
                        )
                    )
        return results

    async def ensure_create_page_ready(self) -> None:
        try:
            await self._ensure_active_page()
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
            if self.account.model_name != "自动":
                await self.select_model()
            # Only Sway exposes the virtual-singer timbre selector.
            if self.account.model_name == "Sway v5.5":
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

    async def verify_generated_song(self, lyrics: str, song_name: str | None = None) -> None:
        try:
            await verify_generated_song(self.page, lyrics, song_name)
        except GenerationLimitError:
            raise
        except SongVerificationError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("生成结果歌词校验", error)

    async def fill_inputs(self, lyric_data: LyricData) -> None:
        try:
            editor = self.page.locator(".ql-editor").first
            await paste_text(
                self.page,
                editor,
                sanitize_lyrics_for_generation(lyric_data.lyrics),
                contenteditable=True,
                segmented_fallback=True,
            )
            await self.page.wait_for_timeout(2000)
            lyric_value = await editor.inner_text()
            if len(lyric_value.strip()) <= 100:
                raise BrowserFlowError(f"歌词输入验证失败: 长度 {len(lyric_value.strip())}")

            style = self.page.locator(
                'textarea[placeholder*="创作灵感"], textarea[placeholder*="歌曲风格"], textarea[placeholder*="旋律"]'
            ).first
            pasted = await paste_text(self.page, style, lyric_data.style)
            if not pasted:
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
                    """
                + _ASSET_CARD_SELECTION_JS
                + """
                    if (!cards.length) return '';
                    const titleNode = cards[0].querySelector(
                        '[class*="title"],[class*="songName"],[class*="name"]'
                    );
                    return titleNode ? titleNode.textContent.trim() : '';
                }"""
            )
            return str(value or "")
        except Exception as error:
            await self._raise_with_screenshot("资产列表读取", error)

    async def asset_generation_state(self) -> dict:
        try:
            value = await self.page.evaluate(
                """() => {
                    """
                + _ASSET_CARD_SELECTION_JS
                + """
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
                    """
                + _ASSET_CARD_SELECTION_JS
                + """
                    return cards.map((card, index) => {
                        const titleNode = card.querySelector(
                            '[class*="title"],[class*="songName"],[class*="name"]'
                        );
                        const title = (titleNode ? titleNode.textContent : '').trim();
                        const sourceNode = card.querySelector('[class*="sourceTag"]');
                        const sourceTag = (sourceNode ? sourceNode.textContent : '').trim();
                        const markerText = `${card.className} ${card.textContent}`;
                        const loading = !title || /生成中|loading|skeleton|placeholder/i.test(markerText);
                        return {
                            index,
                            asset_id: assetIdStore.get(card) || '',
                            title,
                            source_tag: sourceTag,
                            exported: sourceTag.includes('编辑器导出'),
                            loading,
                        };
                    });
                }"""
            )
            return value if isinstance(value, list) else []
        except Exception as error:
            await self._raise_with_screenshot("资产卡片读取", error)

    async def asset_card_count(self) -> int:
        return len(await self.asset_card_states())

    async def all_asset_card_states(self) -> list[dict]:
        """Return the newest cards from the lazy-loaded asset list."""
        collected: dict[str, dict] = {}
        await _set_asset_scroll_position(self.page, "top")
        last_count = -1
        last_scroll_height = -1
        stable_bottom_rounds = 0

        for _ in range(_RECENT_ASSET_SCAN_ROUNDS):
            ready_count = sum(
                1 for state in collected.values()
                if str(state.get("title") or "").strip()
            )
            if ready_count >= _MAX_GENERATION_ASSET_CHECK:
                break
            states = await self.asset_card_states()
            for state in states:
                key = str(state.get("asset_id") or "").strip()
                if not key:
                    key = "|".join(
                        (
                            str(state.get("title") or ""),
                            str(state.get("source_tag") or ""),
                            str(state.get("loading") or ""),
                        )
                )
                collected.setdefault(key, state)
            ready_cards = [
                state for state in collected.values() if str(state.get("title") or "").strip()
            ]
            if len(ready_cards) >= _MAX_GENERATION_ASSET_CHECK:
                break

            position = await _step_asset_scroll(self.page)
            if not position:
                break

            scroll_height = int(position.get("scroll_height") or 0)
            at_bottom = int(position.get("scroll_top") or 0) >= max(
                int(position.get("max_scroll") or 0) - 1,
                0,
            )
            if (
                at_bottom
                and len(states) == last_count
                and scroll_height == last_scroll_height
            ):
                stable_bottom_rounds += 1
            else:
                stable_bottom_rounds = 0
            last_count = len(states)
            last_scroll_height = scroll_height

            await self.page.wait_for_timeout(700)
            if stable_bottom_rounds >= 2:
                break

        ready_cards = [
            state for state in collected.values() if str(state.get("title") or "").strip()
        ]
        if len(ready_cards) >= _MAX_GENERATION_ASSET_CHECK:
            return ready_cards[:_MAX_GENERATION_ASSET_CHECK]
        return list(collected.values())

    async def recover_existing_candidates(
        self,
        lyric_data_list: list[LyricData],
    ) -> dict[str, list[GeneratedCandidate]]:
        initial_states = await self.all_asset_card_states()
        if not any(state.get("loading") for state in initial_states):
            return await self.classify_generated_cards(
                [
                    state
                    for state in initial_states
                    if not state.get("loading")
                ],
                lyric_data_list,
            )

        anchor_state = next(
            (state for state in initial_states if not state.get("loading")),
            None,
        )
        anchor_title = str(anchor_state.get("title") or "") if anchor_state else ""
        await refresh_asset_tabs(self.page)
        deadline = datetime.now().timestamp() + self.settings.generation_timeout_seconds

        while datetime.now().timestamp() < deadline:
            states = await self.all_asset_card_states()
            if anchor_title:
                anchor_index = next(
                    (index for index, state in enumerate(states)
                     if str(state.get("title") or "") == anchor_title),
                    0,
                )
                resolving_cards = states[:anchor_index]
            else:
                resolving_cards = states

            if not any(state.get("loading") for state in resolving_cards):
                return await self.classify_generated_cards(
                    [
                        state
                        for state in states
                        if not state.get("loading")
                    ],
                    lyric_data_list,
                )
            await self.page.wait_for_timeout(5000)

        await self._screenshot("preexisting-generation-timeout")
        return {}

    async def wait_for_batch_generation(
        self,
        baseline_count: int,
        lyric_count: int,
        baseline_anchor: str = "",
    ) -> list[dict]:
        await refresh_asset_tabs(self.page)
        started_at = datetime.now().timestamp()
        deadline = started_at + self.settings.generation_timeout_seconds
        stable_polls = 0
        last_completed: list[dict] = []

        while datetime.now().timestamp() < deadline:
            states = await self.asset_card_states()
            new_states = new_cards_above_anchor(
                states,
                baseline_anchor,
                baseline_count=baseline_count,
            )
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
        card = self.page.locator(
            '[class*="libraryItemWrapper"], [class*="generatedSongListItem"]'
        ).filter(visible=True).nth(card_index)
        await card.click(timeout=5000)
        await self.page.wait_for_timeout(1000)
        new_lyrics_section = self.page.locator('[class*="detailLyricsSection"]')
        if await new_lyrics_section.count():
            return await new_lyrics_section.first.inner_text()
        lyric_title = self.page.locator(
            '[class*="detailPanel"] [class*="sectionTitle"]'
        ).filter(has_text=re.compile(r"^\s*歌词\s*$")).first
        detail_content = lyric_title.locator(
            "xpath=following-sibling::*[contains(@class,'sectionContent')][1]"
        )
        return await detail_content.inner_text()

    async def _read_song_detail_for_card(self, card_index: int) -> str:
        card = self.page.locator(
            '[class*="libraryItemWrapper"], [class*="generatedSongListItem"], '
            '[class*="songItem"], [class*="assetItem"]'
        ).filter(visible=True).nth(card_index)
        try:
            await _click_song_card_title(card)
            await self.page.wait_for_timeout(1000)
            # The detail panel also contains inspiration and style metadata.
            # Match against the isolated lyrics section first so those fields
            # do not dilute the similarity score.
            lyrics_text = await _read_visible_lyric_detail(self.page)
            if lyrics_text.strip():
                return lyrics_text
            lyrics_section = self.page.locator('[class*="detailLyricsSection"]')
            if await lyrics_section.count():
                return await lyrics_section.first.inner_text()
            detail_panel = self.page.locator('[class*="detailPanel"]').last
            if await detail_panel.count():
                return await detail_panel.inner_text()
            return await self.page.locator("body").inner_text()
        finally:
            await self._close_song_detail()

    async def _close_song_detail(self) -> None:
        await _close_visible_song_detail(self.page)

    async def classify_generated_cards(
        self,
        generated_cards: list[dict],
        lyric_data_list: list[LyricData],
    ) -> dict[str, list[GeneratedCandidate]]:
        """Match cards to local lyrics by detail content, not platform title."""
        matches: dict[str, list[GeneratedCandidate]] = {
            lyric_data.song_name: [] for lyric_data in lyric_data_list
        }
        for fallback_index, generated in enumerate(generated_cards):
            if generated.get("exported"):
                continue
            title = str(generated.get("title") or "").strip()
            card_index = int(generated.get("index", fallback_index))
            if not title:
                continue
            detail_text = await self._read_song_detail_for_card(card_index)
            detail_song_name = _detail_song_name(detail_text)
            scored: list[tuple[float, int, int, LyricData]] = []
            for order, lyric_data in enumerate(lyric_data_list):
                similarity = _lyric_match_score(detail_text, lyric_data.lyrics)
                if similarity < _LYRIC_MATCH_MIN_RATIO:
                    continue
                title_bonus = 1 if _same_song_title(detail_song_name, lyric_data.song_name) else 0
                scored.append((similarity, title_bonus, order, lyric_data))
            if not scored:
                continue

            # A platform card belongs to exactly one local lyric; keep the best
            # match and use the shared title only to break near-identical scores.
            scored.sort(key=lambda item: (item[0], item[1], -item[2]), reverse=True)
            best_lyric = scored[0][3]
            matches[best_lyric.song_name].append(
                GeneratedCandidate(
                    song_name=best_lyric.song_name,
                    generated_title=title,
                    card_index=card_index,
                )
            )
        return matches

    async def find_first_generated_candidate(
        self,
        lyric_data: LyricData,
    ) -> GeneratedCandidate | None:
        """Find the first platform card whose detail lyrics match the local song."""
        states = await self.all_asset_card_states()
        for state in states:
            if state.get("loading") or state.get("exported"):
                continue
            card_index = int(state.get("index", 0))
            detail_text = await self._read_song_detail_for_card(card_index)
            similarity = _lyric_match_score(detail_text, lyric_data.lyrics)
            if similarity < _LYRIC_MATCH_MIN_RATIO:
                continue
            return GeneratedCandidate(
                song_name=lyric_data.song_name,
                generated_title=str(state.get("title") or ""),
                card_index=card_index,
            )
        return None

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
            source_page = self.page
            context = getattr(source_page, "context", None)
            card = None
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    card = await self._visible_asset_card(song_name)
                    if card is None:
                        raise BrowserFlowError(f"资产列表中未找到可见卡片: {song_name}")
                    await card.scroll_into_view_if_needed(timeout=3000)
                    await card.hover(timeout=5000)
                    break
                except Exception as error:
                    last_error = error
                    await refresh_asset_tabs(self.page)
                    await self.page.wait_for_timeout(1000)
            if card is None:
                raise last_error or BrowserFlowError(f"资产列表中未找到可见卡片: {song_name}")
            await self.page.wait_for_timeout(2000)
            edit = card.locator("button").filter(has_text="编辑").first
            await trusted_click(self.page, edit, "歌曲编辑按钮")
            await self.page.wait_for_timeout(3000)
            editor_item = None
            if hasattr(self.page, "locator"):
                dropdown = self.page.locator(
                    '[class*="aiEditDropdown"]:visible'
                ).last
                try:
                    await dropdown.wait_for(state="visible", timeout=5000)
                except Exception:
                    dropdown = None
                if dropdown is not None:
                    menu_items = dropdown.locator(
                        '[class*="aiEditMenuItem"]'
                    ).filter(has_text=re.compile(r"^\s*编辑器\s*$"))
                    if await menu_items.count():
                        editor_item = menu_items.first
            if editor_item is None:
                # Keep compatibility with older page shells and focused tests.
                editor_item = self.page.get_by_text("编辑器", exact=True).last
            await trusted_click(self.page, editor_item, "编辑器菜单")
            deadline = datetime.now().timestamp() + 30
            editor_page = await self._wait_for_editor_page(
                context,
                source_page,
                deadline,
            )
            if editor_page is None:
                raise BrowserFlowError("进入编辑器超时")

            self.page = editor_page
            try:
                await editor_page.bring_to_front()
            except Exception:
                pass
            # Keep the source tab alive while the editor owns the workflow.
            # If the platform closes the editor after export, Chrome still has
            # a page left and the replacement upload can reuse that session.
            await self._wait_for_editor_ready(song_name)
        except GenerationLimitError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("进入编辑器", error)

    async def _page_is_closed(self, page: Any) -> bool:
        checker = getattr(page, "is_closed", None)
        if checker is None:
            return False
        try:
            return bool(await _maybe_await(checker()))
        except Exception:
            return True

    async def _ensure_active_page(self) -> None:
        if self.page is not None and not await self._page_is_closed(self.page):
            return

        context = getattr(self.page, "context", None)
        for page in list(getattr(context, "pages", []) or []):
            if not await self._page_is_closed(page):
                self.page = page
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
                return

        if context is None:
            raise BrowserFlowError("Chrome 会话已关闭，无法恢复发布页面")
        self.page = await context.new_page()

    async def _open_publish_tab(self) -> None:
        context = getattr(self.page, "context", None)
        factory = getattr(context, "new_page", None)
        if factory is None:
            return
        publish_page = await factory()
        if publish_page is None:
            return
        self.page = publish_page
        try:
            await publish_page.bring_to_front()
        except Exception:
            pass

    async def _wait_for_editor_page(
        self,
        context: Any,
        source_page: Any,
        deadline: float,
    ) -> Any | None:
        while datetime.now().timestamp() < deadline:
            pages = list(getattr(context, "pages", []) or [])
            if source_page not in pages:
                pages.append(source_page)
            matches: list[Any] = []
            for page in pages:
                if await self._page_is_closed(page):
                    continue
                try:
                    url = str(page.url or "")
                except Exception:
                    continue
                if "playground" in url or "editor" in url:
                    matches.append(page)
            if matches:
                return matches[-1]

            sleeper = None
            for page in pages:
                if not await self._page_is_closed(page):
                    sleeper = page
                    break
            if sleeper is None:
                await asyncio.sleep(0.5)
            else:
                try:
                    await sleeper.wait_for_timeout(1000)
                except Exception:
                    await asyncio.sleep(0.5)
        return None

    async def _wait_for_editor_ready(self, song_name: str) -> None:
        timeout_seconds = max(
            self.settings.editor_import_wait_seconds,
            _EDITOR_READY_MIN_TIMEOUT_SECONDS,
        )
        deadline = datetime.now().timestamp() + timeout_seconds
        last_text = ""
        while datetime.now().timestamp() < deadline:
            try:
                last_text = await self.page.inner_text("body")
            except Exception:
                last_text = ""
            busy = any(marker in last_text for marker in _EDITOR_BUSY_MARKERS)
            if not busy and song_name in last_text:
                return
            if not busy and hasattr(self.page, "locator"):
                try:
                    track = self.page.locator(
                        '[class*="trackHeader"]'
                    ).filter(has_text=song_name)
                    if await track.count():
                        return
                except Exception:
                    pass
            await self.page.wait_for_timeout(1000)

        await self._screenshot("editor-import-timeout")
        raise BrowserFlowError(
            f"编辑器素材导入超时：{timeout_seconds} 秒；"
            f"等待歌曲 {song_name!r}"
        )

    async def _visible_asset_card(self, song_name: str) -> Any | None:
        card_sets = (
            self.page.locator(
                '[class*="libraryItemWrapper"], [class*="generatedSongListItem"]'
            ).filter(has_text=song_name),
            self.page.locator('[class*="generatedSongListItem"]').filter(has_text=song_name),
            self.page.locator('[class*="generatedSongCard"]').filter(has_text=song_name),
        )
        for cards in card_sets:
            for index in range(await cards.count()):
                card = cards.nth(index)
                if await card.is_visible():
                    return card
        return None

    async def _visible_generation_failure(self) -> str | None:
        messages: list[str] = []
        try:
            titles = self.page.locator(
                ".semi-notification-notice-title, .semi-notification-notice-content"
            ).filter(visible=True)
            count = await titles.count()
            messages = [
                (await titles.nth(index).inner_text()).strip()
                for index in range(count)
            ]
        except Exception:
            messages = []
        for message in messages:
            if (
                "歌曲生成失败" in message
                or "生成失败" in message
                or "无法根据描述生成" in message
            ):
                return message
        try:
            body = await self.page.inner_text("body")
        except Exception:
            return None
        if "无法根据描述生成" in body:
            return "无法根据描述生成，请修改"
        return None

    async def _ensure_no_generation_failure(self) -> None:
        message = await self._visible_generation_failure()
        if message:
            await self._screenshot("platform-generation-failed")
            raise SongGenerationFailureError(f"平台提示生成失败: {message}")

    async def export_song(self, song_name: str) -> None:
        try:
            await self._ensure_no_generation_failure()
            await export_song(
                self.page,
                song_name,
                timeout_seconds=self.settings.export_timeout_seconds,
            )
        except GenerationLimitError:
            raise
        except SongGenerationFailureError:
            raise
        except SongExportError:
            raise
        except Exception as error:
            await self._raise_with_screenshot(
                "导出歌曲",
                error,
                error_type=SongExportError,
            )

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

            await self._ensure_no_generation_failure()
            await self.enter_editor(candidate.generated_title)
            await self.export_song(lyric_data.song_name)
            downloaded = await self.download_song(
                lyric_data.song_name,
                lyric_data.lyrics,
            )
            try:
                return archive_download(
                    downloaded,
                    Path(self.account.output_dir),
                    lyric_data.song_name,
                    self.day,
                )
            except Exception as error:
                await self._raise_with_screenshot(
                    "保存下载歌曲",
                    error,
                    error_type=SongDownloadError,
                )
        except GenerationLimitError:
            raise
        except LoginRequiredError:
            raise
        except SongVerificationError:
            raise
        except SongGenerationFailureError:
            raise
        except SongExportError:
            raise
        except SongDownloadError:
            raise
        except Exception as error:
            await self._raise_with_screenshot(
                "导出选中版本",
                error,
                error_type=SongExportError,
            )

    async def export_alternate_version(self, song_name: str, lyrics: str) -> Path:
        """Export the newest unexported asset version for a local song name."""
        try:
            await self.ensure_create_page_ready()
            await refresh_asset_tabs(self.page)
            states = await self.all_asset_card_states()
            for state in states:
                if state.get("loading") or state.get("exported"):
                    continue

                card_index = int(state.get("index", 0))
                detail_text = await self._read_song_detail_for_card(card_index)
                if _lyric_match_score(detail_text, lyrics) < _LYRIC_MATCH_MIN_RATIO:
                    continue

                candidate = GeneratedCandidate(
                    song_name=song_name,
                    generated_title=str(state.get("title") or ""),
                    card_index=card_index,
                )
                lyric_data = LyricData(
                    song_name=song_name,
                    lyrics=lyrics,
                    style="",
                )
                return await self.export_candidate(candidate, lyric_data)

            # A prior replacement can already have been exported and named,
            # while its upload failed later. Re-download that newest exported
            # card instead of telling the user there is no alternate version.
            downloaded = await self.download_song(song_name, lyrics)
            return archive_download(
                downloaded,
                Path(self.account.output_dir),
                song_name,
                self.day,
            )
        except GenerationLimitError:
            raise
        except LoginRequiredError:
            raise
        except SongVerificationError:
            raise
        except SongGenerationFailureError:
            raise
        except SongExportError:
            raise
        except SongDownloadError:
            raise
        except Exception as error:
            await self._raise_with_screenshot("替换不及格歌曲", error)

    async def redownload_song(
        self,
        lyric_data: LyricData,
        on_step: Callable[[str], None] | None = None,
    ) -> Path:
        """Re-download an existing generation without submitting a new prompt."""
        report = on_step or (lambda step: None)
        try:
            report("open_assets")
            await self.ensure_create_page_ready()
            await refresh_asset_tabs(self.page)

            force_export = self.redownload_stage in {
                "export_failed",
                "导出失败",
                "生成失败",
            }
            if not force_export:
                report("find_exported_download")
                try:
                    await find_exported_download_card(
                        self.page,
                        lyric_data.song_name,
                        lyric_data.lyrics,
                    )
                except BrowserFlowError:
                    pass
                else:
                    report("download_song")
                    downloaded = await self.download_song(
                        lyric_data.song_name,
                        lyric_data.lyrics,
                    )
                    return archive_download(
                        downloaded,
                        Path(self.account.output_dir),
                        lyric_data.song_name,
                        self.day,
                    )

            report("match_lyrics")
            candidate = await self.find_first_generated_candidate(lyric_data)
            if candidate is None:
                raise SongExportError(
                    f"未找到与本地歌词匹配的生成结果：《{lyric_data.song_name}》"
                )
            report("export_song")
            return await self.export_candidate(candidate, lyric_data)
        except GenerationLimitError:
            raise
        except LoginRequiredError:
            raise
        except SongVerificationError:
            raise
        except SongGenerationFailureError:
            raise
        except SongExportError:
            raise
        except SongDownloadError:
            raise
        except Exception as error:
            await self._raise_with_screenshot(
                "重新下载歌曲",
                error,
                error_type=SongDownloadError,
            )

    async def download_song(
        self,
        song_name: str,
        lyrics: str | None = None,
    ) -> Path:
        try:
            download_item = await open_download_menu(self.page, song_name, lyrics)
            async with self.page.expect_download(
                timeout=self.settings.download_timeout_seconds * 1000
            ) as download_info:
                # The menu closes as soon as a synthetic mouse click moves
                # across it in some Chromium versions. A DOM click keeps the
                # expected browser download tied to the real menu item.
                await dom_click(download_item, "下载菜单")
            download = await download_info.value
            suggested = download.suggested_filename or f"{song_name}.mp3"
            target = Path(self.account.download_dir, datetime.now().strftime("%Y-%m-%d")) / suggested
            target.parent.mkdir(parents=True, exist_ok=True)
            await download.save_as(target)
            if not target.is_file() or target.stat().st_size == 0:
                failure = await download.failure()
                try:
                    target.unlink()
                except OSError:
                    pass
                raise BrowserFlowError(
                    f"下载文件为空: {target}"
                    + (f"; Chrome: {failure}" if failure else "")
                )
            return target
        except GenerationLimitError:
            raise
        except SongDownloadError:
            raise
        except Exception as error:
            await self._raise_with_screenshot(
                "下载歌曲",
                error,
                error_type=SongDownloadError,
            )

    async def _screenshot(self, step: str) -> Path | None:
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = self.screenshot_dir / f"{stamp}-{step}.png"
            await self.page.screenshot(path=path, full_page=True)
            return path
        except Exception:
            return None

    async def _raise_with_screenshot(
        self,
        step: str,
        error: Exception,
        *,
        error_type: type[BrowserFlowError] = BrowserFlowError,
    ) -> None:
        path = await self._screenshot(re.sub(r"[^a-z0-9-]+", "-", step).strip("-"))
        suffix = f"；截图: {path}" if path else ""
        if isinstance(
            error,
            (
                GenerationLimitError,
                LoginRequiredError,
                SongVerificationError,
                SongGenerationFailureError,
                SongExportError,
                SongDownloadError,
            ),
        ):
            raise error
        raise error_type(f"{step}失败: {error}{suffix}") from error
