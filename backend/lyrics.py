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


def parse_lyrics(text: str) -> LyricData:
    song_name = _extract_title(text)
    lyrics = _extract_section(text, _LYRIC_SECTION, section_name="歌词")
    style = _extract_section(text, _STYLE_SECTION, section_name="歌曲风格")
    lyrics = _remove_repeated_title(lyrics, song_name).strip()
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
    account: str,
    day: str | None = None,
) -> list[Path]:
    day_value = day or date.today().isoformat()
    directory = Path(root) / day_value / account
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.md") if path.is_file())
