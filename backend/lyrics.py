"""Parse the Markdown lyric format used by the local workflow."""

import re
from datetime import date
from pathlib import Path

from backend.errors import ValidationFailed
from backend.models import LyricData


_TITLE_PATTERNS = (
    re.compile(r"歌名：[《\[]?(?P<title>[^》\]\r\n]+)[》\]]?"),
    re.compile(r"歌名:\s*(?P<title>[^\r\n]+)"),
)
_LYRIC_SECTION = re.compile(r"##\s*歌词\s*\r?\n(?P<body>.*?)(?=##\s*歌曲风格)", re.S)
_STYLE_SECTION = re.compile(r"##\s*歌曲风格\s*\r?\n(?P<body>.*)", re.S)
_SECTION_TAG_PREFIX = re.compile(r"^\s*\[(?P<tag>[^\]]+)\](?P<rest>.*)$")
_PARENTHETICAL_ONLY = re.compile(r"^\s*\([^)]*\)\s*$")
_SECTION_TAG_ALIASES = {
    "主歌": "Verse",
    "主歌1": "Verse 1",
    "主歌2": "Verse 2",
    "预副歌": "Pre-Chorus",
    "副歌": "Chorus",
    "副歌1": "Chorus",
    "副歌2": "Chorus",
    "桥段": "Bridge",
    "间奏": "Bridge",
    "尾奏": "Outro",
    "chorus": "Chorus",
    "chorus1": "Chorus",
    "chorus 1": "Chorus",
    "chorus2": "Chorus",
    "chorus 2": "Chorus",
    "verse": "Verse",
    "verse1": "Verse 1",
    "verse 1": "Verse 1",
    "verse2": "Verse 2",
    "verse 2": "Verse 2",
    "prechorus": "Pre-Chorus",
    "pre-chorus": "Pre-Chorus",
    "pre chorus": "Pre-Chorus",
    "bridge": "Bridge",
    "outro": "Outro",
}


def _canonical_section_tag(tag: str) -> str:
    value = re.sub(r"\s+", " ", tag.strip())
    return _SECTION_TAG_ALIASES.get(value.lower(), value)


def sanitize_lyrics_for_generation(text: str) -> str:
    """Keep only section labels and sung lyric lines.

    Older generated files put bars, arrangement, and performance directions in
    the same field as the lyrics. Miaoxiang receives that field verbatim, so
    those authoring notes can compete with the style description. This
    normalizer is intentionally deterministic and is also used by the browser
    input path so existing drafts are protected.
    """
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == "[End]" or line.startswith(("歌名：", "歌名:")):
            continue
        if _PARENTHETICAL_ONLY.fullmatch(line):
            continue

        match = _SECTION_TAG_PREFIX.match(line)
        if match:
            tag = _canonical_section_tag(match.group("tag"))
            if tag.lower() == "end":
                continue
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[{tag}]")
            remainder = match.group("rest").strip()
            if remainder and re.search(r"[\u4e00-\u9fff]", remainder) and not remainder.startswith("["):
                lines.append(remainder)
            continue

        lines.append(line)

    normalized: list[str] = []
    for line in lines:
        if not line:
            if normalized and normalized[-1] != "":
                normalized.append("")
            continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def parse_lyrics(text: str) -> LyricData:
    song_name = _extract_title(text)
    lyrics = _extract_section(text, _LYRIC_SECTION, section_name="歌词")
    style = _extract_section(text, _STYLE_SECTION, section_name="歌曲风格")
    lyrics = _remove_repeated_title(lyrics, song_name).strip()
    lyrics = sanitize_lyrics_for_generation(lyrics)
    style = style.strip()

    if len(lyrics) <= 100:
        raise ValidationFailed(f"歌词长度不足：当前 {len(lyrics)} 字符，必须大于 100")
    if len(style) <= 50:
        raise ValidationFailed(f"风格描述长度不足：当前 {len(style)} 字符，必须大于 50")

    return LyricData(song_name=song_name, lyrics=lyrics, style=style)


def _extract_title(text: str) -> str:
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            title = match.group("title").strip()
            if title:
                return title
    raise ValidationFailed("未找到歌名，需使用“歌名：《歌曲名》”或“歌名: 歌曲名”")


def _extract_section(text: str, pattern: re.Pattern[str], section_name: str) -> str:
    match = pattern.search(text)
    if not match:
        raise ValidationFailed(f"未找到“## {section_name}”章节")
    return match.group("body").strip()


def _remove_repeated_title(lyrics: str, song_name: str) -> str:
    lines = lyrics.splitlines()
    for index, line in enumerate(lines):
        value = line.strip()
        if not value:
            continue
        if value in {song_name, f"《{song_name}》", f"[{song_name}]"}:
            return "\n".join(lines[index + 1 :])
        return lyrics
    return lyrics


def list_lyric_files(
    root: Path,
    day: str | None = None,
) -> list[Path]:
    day_value = day or date.today().isoformat()
    directory = Path(root) / day_value
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.md") if path.is_file())
