import pytest

from backend.ai_lyrics import generate_lyrics, parse_lyric_response, render_lyric_markdown
from backend.errors import ValidationFailed
from backend.lyrics import parse_lyrics
from backend.models import ConsoleSettings, LyricData, LyricTemplateConfig


def make_song(name: str = "第一首") -> LyricData:
    return LyricData(
        song_name=name,
        lyrics=(
            "[主歌1][成人独唱，温暖中低音男声rap，木吉他+鼓点轻压，叙事，3 bars]\n"
            "夜色 像 一台 缓慢 转动 的 引擎\n(轻声，带一点气声)\n"
            "[预副歌][成人独唱，弦乐渐入，渐强，2 bars]\n"
            "穿过 城市 也 穿过 我 的 呼吸\n(情绪渐强)\n"
            "[副歌1][成人男声主唱，鼓全开，弦乐铺层，释放，4 bars]\n"
            "旧 灯光 写 下 未完成 的 旋律\n(明亮，情绪到顶)\n"
            "[主歌2][成人独唱，电吉他+贝斯，节奏收紧，3 bars]\n"
            "街灯 把 影子 拉成 回声\n(更坚定)\n"
            "[副歌2][成人男声主唱，和声加厚，饱满到顶，4 bars]\n"
            "我 要 往 有 光 的 地方 走\n(情绪到顶)\n"
            "[桥段][成人独白，只留木吉他，近乎耳语，2 bars]\n"
            "夜 会 亮 起来\n(独白感，近乎清唱)"
        ),
        style=(
            "[都市夜行][都市流行，木吉他+鼓+弦乐，温暖中低音男声，夜晚推进感，限时80-90秒，no EDM，no autotune]\n"
            "BPM 82　调性 C大调　全曲 24 bars≈80秒\n"
            "段落人声：主歌/预副歌/桥段=成人独唱；副歌=成人男声主唱"
        ),
    )


def test_parse_lyric_response_validates_count_and_fields() -> None:
    song = make_song()
    payload = f'{{"songs":[{song.model_dump_json()}]}}'

    result = parse_lyric_response(payload, 1)

    assert result[0].lyrics.strip() == song.lyrics.strip()
    assert result[0].style == song.style


async def test_generate_lyrics_declares_template_precedence() -> None:
    song = make_song("模板优先")
    captured_payload: dict[str, object] = {}

    async def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        captured_payload.update(payload)
        return {
            "choices": [
                {"message": {"content": f'{{"songs":[{song.model_dump_json()}]}}'}}
            ]
        }

    settings = ConsoleSettings(ai_api_base_url="https://api.example.com/v1", ai_model="test-model")
    template = LyricTemplateConfig(
        account_id="account-1",
        name="自定义模板",
        lyric_tone="温暖叙事，有具体画面和成长痕迹",
        song_style="pop ballad, total duration 300 seconds",
        themes=["成长"],
    )

    await generate_lyrics(settings, template=template, count=1, post_json=post_json)

    messages = captured_payload["messages"]
    assert "以模板为准" in messages[0]["content"]
    assert "输出语言硬规则" in messages[0]["content"]
    assert "style 字段必须全部用英文" in messages[0]["content"]
    assert "template_overrides_general_rules" in messages[1]["content"]
    assert "complete style field must be written in English" in messages[1]["content"]


def test_parse_lyric_response_rejects_short_style() -> None:
    song = make_song().model_copy(update={"style": "太短"})

    with pytest.raises(ValidationFailed) as error:
        parse_lyric_response(f'{{"songs":[{song.model_dump_json()}]}}', 1)

    assert "曲风描述长度不足" in error.value.message


def test_parse_lyric_response_accepts_plain_text_lyrics_for_field_mapping() -> None:
    song = make_song().model_copy(
        update={"lyrics": "夜色像一台缓慢转动的引擎\n穿过城市也穿过我的呼吸\n" + "旧灯光写下未完成的旋律\n" * 20}
    )

    result = parse_lyric_response(f'{{"songs":[{song.model_dump_json()}]}}', 1)

    assert result[0].lyrics.strip() == song.lyrics.strip()
    assert result[0].style == song.style


def test_parse_lyric_response_accepts_variant_style_text_for_field_mapping() -> None:
    song = make_song()
    song = song.model_copy(update={"style": "都市流行，中速，木吉他和鼓点作为基础，副歌加入弦乐并稍微开阔，温暖男声从低音叙事推进到明亮释放，整体有夜晚步行感。"})

    result = parse_lyric_response(f'{{"songs":[{song.model_dump_json()}]}}', 1)

    assert result[0].style == song.style


def test_rendered_ai_lyric_uses_console_format() -> None:
    song = make_song("AI测试歌")

    markdown = render_lyric_markdown(song)
    parsed = parse_lyrics(markdown)

    assert parsed.song_name == song.song_name
    assert parsed.lyrics == f"歌名：《{song.song_name}》\n\n{song.lyrics}\n[End]"
    assert parsed.style == song.style
    assert "## 歌词" in markdown
    assert "## 歌曲风格" in markdown
