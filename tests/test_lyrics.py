from pathlib import Path

import pytest

from backend.errors import ValidationFailed
from backend.lyrics import list_lyric_files, parse_lyrics, sanitize_lyrics_for_generation


def sample_markdown(song_name: str = "夜色引擎") -> str:
    lyric_body = "夜色像一台缓慢转动的引擎\n穿过城市也穿过我的呼吸\n" + "旧灯光写下未完成的旋律\n" * 20
    style_body = (
        "男声摇滚，粗粝低音，鼓点密集，副歌开阔，带有都市夜行感和少量电子质感。"
        "整体情绪从压抑推进到明亮，尾奏保留城市噪声和模拟合成器余韵。"
    )
    return f"""# 歌名：《{song_name}》

## 歌词
《{song_name}》
{lyric_body}
[End]

## 歌曲风格
{style_body}
"""


def test_parse_lyrics_with_full_width_title() -> None:
    parsed = parse_lyrics(sample_markdown("夜色引擎"))

    assert parsed.song_name == "夜色引擎"
    assert parsed.lyrics.startswith("夜色像一台缓慢转动的引擎")
    assert "[End]" not in parsed.lyrics
    assert parsed.style.startswith("男声摇滚")


def test_sanitize_lyrics_separates_structure_from_authoring_notes() -> None:
    lyrics = (
        "[Chorus 1][no intro, 4 bars, fuzz bass + 808 + girls' choir hook]\n"
        "风 把 灯光 吹成 一 条 街\n"
        "(bright, close-mic)\n"
        "[Verse 1][4 bars, kick, muted guitar, male rap low]\n"
        "你 站在 路口 没有 回头"
    )

    assert sanitize_lyrics_for_generation(lyrics) == (
        "[Chorus]\n"
        "风 把 灯光 吹成 一 条 街\n\n"
        "[Verse 1]\n"
        "你 站在 路口 没有 回头"
    )


def test_parse_lyrics_with_half_width_title() -> None:
    text = sample_markdown("City Signal").replace("歌名：《City Signal》", "歌名: City Signal")
    parsed = parse_lyrics(text)

    assert parsed.song_name == "City Signal"


def test_parse_lyrics_removes_repeated_first_title_line() -> None:
    parsed = parse_lyrics(sample_markdown("夜色引擎"))
    lines = parsed.lyrics.splitlines()

    assert "《夜色引擎》" not in lines
    assert not lines[0].startswith("《")


def test_parse_lyrics_trims_style() -> None:
    text = sample_markdown().replace("## 歌曲风格\n男声摇滚", "## 歌曲风格\n\n\n男声摇滚")
    parsed = parse_lyrics(text)

    assert parsed.style == parsed.style.strip()


def test_parse_lyrics_rejects_missing_sections() -> None:
    with pytest.raises(ValidationFailed, match="歌名"):
        parse_lyrics("## 歌词\nx\n## 歌曲风格\ny\n")

    with pytest.raises(ValidationFailed, match="歌词"):
        parse_lyrics("# 歌名：《夜色引擎》\n")


def test_parse_lyrics_rejects_short_content() -> None:
    text = sample_markdown()
    before, marker, rest = text.partition("## 歌词\n")
    _, style_marker, style_body = rest.partition("## 歌曲风格\n")
    text = before + marker + "短词\n[End]\n\n" + style_marker + style_body
    with pytest.raises(ValidationFailed, match="歌词长度"):
        parse_lyrics(text)

    text = sample_markdown()
    marker = "## 歌曲风格\n"
    prefix, _, _ = text.partition(marker)
    text = prefix + marker + "摇滚\n"
    with pytest.raises(ValidationFailed, match="风格描述长度"):
        parse_lyrics(text)


def test_list_lyric_files_reads_todays_project_date_folder(tmp_path: Path) -> None:
    root = tmp_path / "lyrics"
    expected_dir = root / "2026-09-17"
    other_dir = root / "2026-09-16"
    expected_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    (expected_dir / "02_second.md").write_text("b", encoding="utf-8")
    (expected_dir / "01_first.md").write_text("a", encoding="utf-8")
    (expected_dir / "ignored.txt").write_text("c", encoding="utf-8")
    (other_dir / "old.md").write_text("d", encoding="utf-8")

    files = list_lyric_files(root, day="2026-09-17")

    assert [path.name for path in files] == ["01_first.md", "02_second.md"]
