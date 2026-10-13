"""Deterministic quality checks for generated lyric batches."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from pypinyin import Style, lazy_pinyin

from backend.errors import ValidationFailed
from backend.models import LyricData


_SECTION_TAG = re.compile(r"^\[([^\]]+)\]\s*$")
_HAN_CHAR = re.compile(r"[\u3400-\u9fff]")
_PARTICLES = frozenset("的了着地得吗吧呢啊呀哦么嘛")

# The first style line must declare a motif audible in the opening seconds.
# Accept either the literal word or the common "first beat / first second"
# phrasing models use instead.
_FIRST_SECOND_SIGNATURE = re.compile(
    r"signature"
    r"|first\s+(?:beat|second|1-2\s*seconds?)"
    r"|in\s+the\s+first"
    r"|at\s+the\s+(?:very\s+)?top"
    r"|from\s+the\s+(?:very\s+)?(?:top|start|opening)"
    r"|right\s+away"
    r"|immediately"
    r"|cold[-\s]+open(?:ing)?"
    r"|no\s+intro"
    r"|without\s+(?:an?\s+)?intro"
    r"|(?:opens?|starts?)\s+the\s+(?:song|track|record)"
    r"|\bstarts?\s+the\s+track",
    re.IGNORECASE,
)

FATIGUE_TERMS = (
    "风",
    "灯",
    "光",
    "窗",
    "月",
    "夜",
    "雨",
    "影子",
    "街",
    "门",
    "伞",
    "站台",
    "车票",
)

_SLOGAN_PATTERNS = (
    re.compile(r"(?:才是|就是)我的主场"),
    re.compile(r"替我(?:做|下)结论"),
    re.compile(r"站起来(?:才|就|去|让)"),
    re.compile(r"明天会更好"),
    re.compile(r"逆风翻盘"),
    re.compile(r"相信自己"),
    re.compile(r"别怕"),
    re.compile(r"不认输"),
)

_AWKWARD_PATTERNS = (
    re.compile(r"锁藏"),
    re.compile(r"省了没教"),
    re.compile(r"不充电就能留住"),
)

# pypinyin's FINALS style returns the full final (iou / uei / uen), so the map
# is keyed on those exact values. Finals that differ only by a front/back nasal
# ending are grouped together: Chinese pop lyrics treat an/ang and en/eng/in/ing
# as acceptable near rhymes, and the prompt explicitly allows近韵.
_RHYME_FAMILIES = {
    "a": "a",
    "ia": "a",
    "ua": "a",
    "o": "o-e",
    "uo": "o-e",
    "e": "o-e",
    "ie": "o-e",
    "ve": "o-e",
    "ai": "ai",
    "uai": "ai",
    "ei": "ei",
    "uei": "ei",
    "ao": "ao",
    "iao": "ao",
    "ou": "ou",
    "iou": "ou",
    "an": "an-ang",
    "ian": "an-ang",
    "uan": "an-ang",
    "van": "an-ang",
    "ang": "an-ang",
    "iang": "an-ang",
    "uang": "an-ang",
    "en": "en-eng",
    "in": "en-eng",
    "uen": "en-eng",
    "vn": "en-eng",
    "eng": "en-eng",
    "ing": "en-eng",
    "ueng": "en-eng",
    "ong": "en-eng",
    "iong": "en-eng",
    "i": "i",
    "u": "u",
    "v": "v",
    "er": "er",
}


@dataclass
class _Section:
    name: str
    lines: list[str]


def validate_lyric_batch(songs: list[LyricData]) -> None:
    """Reject a generated batch when it violates the v2.9 quality contract."""

    if not songs:
        raise ValidationFailed("歌词批次为空")

    parsed = [_parse_sections(song.lyrics) for song in songs]
    for song, sections in zip(songs, parsed, strict=True):
        _validate_structure_and_style(song, sections)
        _validate_rhymes(song, sections)
        _validate_language(song, sections)

    _validate_batch_diversity(songs, parsed)
    _validate_fatigue_terms(songs)


def validate_title_assignments(
    songs: list[LyricData], assignments: list[dict[str, object]] | None
) -> None:
    """Check each song title against the per-song title length assignment."""

    if not assignments:
        return
    if len(assignments) != len(songs):
        raise ValidationFailed("歌名长度分配与歌曲数量不一致")
    for song, assignment in zip(songs, assignments, strict=True):
        required = assignment.get("required_title_length")
        if not required:
            continue
        actual = len(_han_chars(song.song_name))
        if actual != int(required):
            raise ValidationFailed(
                f"《{song.song_name}》歌名应为 {required} 字，实际 {actual} 字"
            )


def _parse_sections(lyrics: str) -> list[_Section]:
    sections: list[_Section] = []
    current: _Section | None = None
    for raw_line in lyrics.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tag = _SECTION_TAG.fullmatch(line)
        if tag:
            current = _Section(name=tag.group(1).strip(), lines=[])
            sections.append(current)
            continue
        if current is not None and _HAN_CHAR.search(line):
            current.lines.append(line)
    return sections


def _validate_structure_and_style(song: LyricData, sections: list[_Section]) -> None:
    chorus_sections = [section for section in sections if _is_chorus(section.name)]
    if len(chorus_sections) < 2:
        raise ValidationFailed(f"《{song.song_name}》必须包含两遍副歌")
    if any(len(section.lines) < 2 for section in chorus_sections):
        raise ValidationFailed(f"《{song.song_name}》副歌至少需要两行歌词")

    first_hook = _normalized_line(chorus_sections[0].lines[0])
    second_hook = _normalized_line(chorus_sections[1].lines[0])
    first_follow = _normalized_line(chorus_sections[0].lines[1])
    second_follow = _normalized_line(chorus_sections[1].lines[1])
    if (first_hook, first_follow) != (second_hook, second_follow):
        raise ValidationFailed(f"《{song.song_name}》两遍副歌的前两行不一致")

    style_lines = [line.strip() for line in song.style.splitlines() if line.strip()]
    if len(style_lines) < 3:
        raise ValidationFailed(f"《{song.song_name}》style 必须至少包含三行")
    if _HAN_CHAR.search(song.style):
        raise ValidationFailed(f"《{song.song_name}》style 只能使用英文")
    if "Arrangement:" not in song.style:
        raise ValidationFailed(f"《{song.song_name}》style 缺少 Arrangement 情绪弧线")
    signature_declared = _FIRST_SECOND_SIGNATURE.search(style_lines[0]) or any(
        "signature" in line.lower() for line in style_lines[1:]
    )
    if not signature_declared:
        raise ValidationFailed(
            f"《{song.song_name}》style 缺少首秒声音签名：{song.style[:160]}"
        )


def _validate_rhymes(song: LyricData, sections: list[_Section]) -> None:
    for section in sections:
        if _is_chorus(section.name):
            _require_dominant_rhyme(song, section, minimum_ratio=0.75)
        elif section.name.lower().startswith("verse"):
            _require_dominant_rhyme(song, section, minimum_ratio=0.60)


def _require_dominant_rhyme(song: LyricData, section: _Section, *, minimum_ratio: float) -> None:
    rhyme_keys = [_rhyme_key(line) for line in section.lines]
    rhyme_keys = [key for key in rhyme_keys if key]
    if len(rhyme_keys) < 2:
        raise ValidationFailed(f"《{song.song_name}》{section.name} 缺少可检查的句尾韵脚")

    counts = Counter(rhyme_keys)
    dominant_count = max(counts.values())
    minimum_count = max(2, math.ceil(len(rhyme_keys) * minimum_ratio))
    if _has_consistent_rhyme_scheme(rhyme_keys):
        return
    if dominant_count < minimum_count:
        raise ValidationFailed(
            f"《{song.song_name}》{section.name} 押韵混散，"
            f"同一主韵仅 {dominant_count}/{len(rhyme_keys)} 行"
        )


def _has_consistent_rhyme_scheme(rhyme_keys: list[str]) -> bool:
    """Accept common four-line pop/rap schemes: AAAA, AABB, and ABAB."""

    if len(rhyme_keys) < 4 or len(rhyme_keys) % 2:
        return False
    paired = all(
        rhyme_keys[index] == rhyme_keys[index + 1]
        for index in range(0, len(rhyme_keys), 2)
    )
    alternating = all(
        rhyme_keys[index] == rhyme_keys[index + 2]
        for index in range(0, len(rhyme_keys) - 2)
    )
    return paired or alternating


def _validate_language(song: LyricData, sections: list[_Section]) -> None:
    for section in sections:
        for line in section.lines:
            for pattern in _SLOGAN_PATTERNS:
                if pattern.search(line):
                    raise ValidationFailed(
                        f"《{song.song_name}》出现口号句：{pattern.pattern}"
                    )
            for pattern in _AWKWARD_PATTERNS:
                if pattern.search(line):
                    raise ValidationFailed(
                        f"《{song.song_name}》出现生硬表达：{pattern.pattern}"
                    )

    third_person_seen = False
    for section in sections:
        section_has_third_person = any(
            re.search(r"[他她]", line) for line in section.lines
        )
        if (
            _is_bridge(section.name)
            and section_has_third_person
            and not third_person_seen
        ):
            raise ValidationFailed(
                f"《{song.song_name}》第三人称首次出现在 Bridge，指代不明确"
            )
        third_person_seen = third_person_seen or section_has_third_person


def _validate_batch_diversity(songs: list[LyricData], parsed: list[list[_Section]]) -> None:
    first_lines = [_first_sung_line(sections) for sections in parsed]
    if any(not line for line in first_lines):
        raise ValidationFailed("批次中存在没有歌词正文的歌曲")

    first_chars = [
        chars[0]
        for line in first_lines
        for chars in [_han_chars(line)]
        if chars
    ]
    first_bigrams = [
        "".join(chars[:2])
        for line in first_lines
        for chars in [_han_chars(line)]
        if len(chars) >= 2
    ]
    max_same_first = max(2, math.ceil(len(songs) * 0.20))
    if first_chars:
        char, count = Counter(first_chars).most_common(1)[0]
        if count > max_same_first:
            raise ValidationFailed(
                f"批次开场同质化：{count} 首以“{char}”开头，上限 {max_same_first}"
            )
    if first_bigrams:
        bigram, count = Counter(first_bigrams).most_common(1)[0]
        if count > 2:
            raise ValidationFailed(
                f"批次开场同质化：{count} 首以“{bigram}”开头，上限 2"
            )

    title_lengths = [len(_han_chars(song.song_name)) for song in songs]
    if any(length == 0 for length in title_lengths):
        raise ValidationFailed("批次中存在空歌名或纯符号歌名")
    if len(songs) >= 6 and len(set(title_lengths)) < 3:
        raise ValidationFailed("批次歌名长度过于单一，至少需要 3 种不同长度")
    max_same_length = max(2, math.ceil(len(songs) * 0.40))
    length, count = Counter(title_lengths).most_common(1)[0]
    if count > max_same_length:
        raise ValidationFailed(
            f"批次歌名长度同质化：{count} 首都是 {length} 字，上限 {max_same_length}"
        )


def _validate_fatigue_terms(songs: list[LyricData]) -> None:
    song_counts: Counter[str] = Counter()
    for song in songs:
        for term in FATIGUE_TERMS:
            if term in song.lyrics or term in song.song_name:
                song_counts[term] += 1
    maximum_songs = max(1, math.ceil(len(songs) * 0.15))
    overused = [
        (term, count)
        for term, count in song_counts.items()
        if count > maximum_songs
    ]
    if overused:
        details = "、".join(
            f"{term} {count} 首" for term, count in sorted(overused)
        )
        raise ValidationFailed(
            f"疲劳意象频率过高：{details}，当前最多允许 {maximum_songs} 首"
        )


def _first_sung_line(sections: list[_Section]) -> str:
    for section in sections:
        if section.lines:
            return section.lines[0]
    return ""


def _is_chorus(name: str) -> bool:
    return name.strip().lower().startswith("chorus")


def _is_bridge(name: str) -> bool:
    return name.strip().lower().startswith("bridge")


def _normalized_line(line: str) -> str:
    return re.sub(r"[\s，。！？、；：,.!?;:]+", "", line)


def _han_chars(text: str) -> list[str]:
    return _HAN_CHAR.findall(text)


def _rhyme_key(line: str) -> str | None:
    chars = _han_chars(line)
    while chars and chars[-1] in _PARTICLES:
        chars.pop()
    if not chars:
        return None
    final = lazy_pinyin(chars[-1], style=Style.FINALS, errors="ignore")
    if not final or not final[0]:
        return None
    return _RHYME_FAMILIES.get(final[0].lower(), final[0].lower())


# Kept as a private alias for diagnostic scripts that already import it.
_FATIGUE_TERMS = FATIGUE_TERMS
