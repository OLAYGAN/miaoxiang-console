import json

import pytest

from backend.ai_lyrics import (
    _failed_song_indexes,
    build_lyric_payload,
    generate_lyrics,
    parse_lyric_response,
    render_lyric_markdown,
)
from backend.errors import ValidationFailed
from backend.lyrics import parse_lyrics, sanitize_lyrics_for_generation
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


def make_valid_generation_song(name: str = "第一首") -> LyricData:
    return LyricData(
        song_name=name,
        lyrics=(
            "[Verse 1]\n"
            "钥匙转进旧锁\n"
            "墙后安静得像空壳\n"
            "你的名字停在桌\n"
            "茶杯凉了半截\n\n"
            "[Pre-Chorus]\n"
            "别问我是否还等着\n"
            "呼吸先乱了节拍\n\n"
            "[Chorus]\n"
            "钥匙还你锁也空着\n"
            "钥匙还你心别拉扯\n"
            "旧账翻篇别再重播\n"
            "这次路我自己走过\n\n"
            "[Verse 2]\n"
            "我把照片折成纸鹤\n"
            "放进抽屉最深的格\n"
            "闹钟响到第七回合\n"
            "我仍站在原地沉默\n\n"
            "[Chorus]\n"
            "钥匙还你锁也空着\n"
            "钥匙还你心别拉扯\n"
            "旧账翻篇别再重播\n"
            "这次路我自己走过\n\n"
            "[Bridge]\n"
            "如果转身算认输\n"
            "我也认这一场错"
        ),
        style=(
            "[alternative pop rock][signature: dry piano hit and kick enter in the first second]"
            "[2-4 key instruments][no intro]\n"
            "BPM 88 | Key A minor | Vocals: female lead\n"
            "Arrangement: cold open -> intimate verse -> rising pre-chorus -> "
            "expansive chorus -> stripped bridge -> final chorus lift"
        ),
    )


def test_parse_lyric_response_validates_count_and_fields() -> None:
    song = make_song()
    payload = f'{{"songs":[{song.model_dump_json()}]}}'

    result = parse_lyric_response(payload, 1)

    assert result[0].lyrics == (
        "[Verse 1]\n"
        "夜色 像 一台 缓慢 转动 的 引擎\n\n"
        "[Pre-Chorus]\n"
        "穿过 城市 也 穿过 我 的 呼吸\n\n"
        "[Chorus]\n"
        "旧 灯光 写 下 未完成 的 旋律\n\n"
        "[Verse 2]\n"
        "街灯 把 影子 拉成 回声\n\n"
        "[Chorus]\n"
        "我 要 往 有 光 的 地方 走\n\n"
        "[Bridge]\n"
        "夜 会 亮 起来"
    )
    assert result[0].style == song.style


async def test_generate_lyrics_declares_template_precedence() -> None:
    song = make_valid_generation_song("模板")
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
    assert "本请求冲突处理" in messages[0]["content"]
    assert "字段分离硬规则" in messages[0]["content"]
    assert "lyrics 字段只保留英文方括号结构标签" in messages[0]["content"]
    assert "template_overrides_general_rules" in messages[1]["content"]
    assert "lyrics_contract" in messages[1]["content"]
    assert "opening_five_seconds" in messages[1]["content"]
    assert "song_design" in messages[1]["content"]
    assert "rhyme_contract" in messages[1]["content"]
    assert "prosody_and_singability" in messages[1]["content"]
    assert "style_contract" in messages[1]["content"]
    assert "motif_diversity" in messages[1]["content"]
    assert "batch_diversity_contract" in messages[1]["content"]
    assert "naturalness_contract" in messages[1]["content"]
    assert "efficiency_contract" in messages[1]["content"]
    assert "song_assignments" in messages[1]["content"]
    assert "two [Chorus] sections" in messages[1]["content"]
    assert "first three sung lines" in messages[1]["content"]
    assert "first 1-2 seconds" in messages[1]["content"]
    assert "Chorus is the highest emotional point" in messages[1]["content"]
    assert "Rhyme is mandatory" in messages[1]["content"]
    assert "风, 灯, 光, 窗, 月, 夜, 雨, 影子, 街, 门, 伞, 站台, 车票" in messages[1]["content"]
    assert "no more than 15 percent of the songs" in messages[1]["content"]


def test_payload_uses_small_budget_and_low_deepseek_reasoning() -> None:
    template = LyricTemplateConfig(account_id="account-1", name="性能测试", themes=["成长"])
    regular_payload = build_lyric_payload(
        ConsoleSettings(), template=template, count=5
    )
    deepseek_payload = build_lyric_payload(
        ConsoleSettings(
            ai_api_base_url="https://api.deepseek.com",
            ai_model="deepseek-flash",
        ),
        template=template,
        count=5,
    )
    single_payload = build_lyric_payload(
        ConsoleSettings(
            ai_api_base_url="https://api.deepseek.com",
            ai_model="deepseek-flash",
        ),
        template=template,
        count=1,
    )

    assert regular_payload["max_tokens"] == 5 * 4_096
    assert "thinking" not in regular_payload
    assert deepseek_payload["thinking"] == {"type": "enabled"}
    assert deepseek_payload["reasoning_effort"] == "low"
    assert deepseek_payload["response_format"] == {"type": "json_object"}
    assert deepseek_payload["max_tokens"] == 5 * 4_096
    assert single_payload["thinking"] == {"type": "enabled"}
    assert single_payload["reasoning_effort"] == "low"
    assert single_payload["response_format"] == {"type": "json_object"}
    assert single_payload["max_tokens"] == 16_384


def test_payload_reports_remaining_cross_batch_fatigue_budget() -> None:
    settings = ConsoleSettings()
    template = LyricTemplateConfig(account_id="account-1", name="跨批测试", themes=["失去"])

    payload = build_lyric_payload(
        settings,
        template=template,
        count=5,
        previous_context={
            "requested_total_count": 20,
            "used_fatigue_term_counts": {"夜": 2, "灯": 1},
        },
    )
    user_prompt = json.loads(payload["messages"][1]["content"])

    assert "CROSS-BATCH USAGE LIMIT" in user_prompt["motif_diversity"]
    assert "at most 3 distinct songs" in user_prompt["motif_diversity"]
    assert "夜: used 2/3, at most 1 more song(s)" in user_prompt["motif_diversity"]
    assert "灯: used 1/3, at most 2 more song(s)" in user_prompt["motif_diversity"]


def test_failed_song_indexes_locates_fatigue_overuse() -> None:
    songs = [
        make_valid_generation_song("第一首").model_copy(
            update={"lyrics": make_valid_generation_song("第一首").lyrics + "\n夜"}
        ),
        make_valid_generation_song("第二首").model_copy(
            update={"lyrics": make_valid_generation_song("第二首").lyrics + "\n夜"}
        ),
        make_valid_generation_song("第三首").model_copy(
            update={"lyrics": make_valid_generation_song("第三首").lyrics + "\n夜"}
        ),
    ]

    indexes = _failed_song_indexes(
        songs,
        ValidationFailed("疲劳意象频率过高：夜 3 首，当前最多允许 1 首"),
    )

    assert indexes == [1, 2]


async def test_generate_lyrics_splits_large_batch_and_passes_prior_context() -> None:
    requests: list[dict[str, object]] = []
    opening_prefixes = tuple("甲乙丙丁戊己庚辛壬癸子丑寅卯辰")

    async def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        messages = payload["messages"]
        user_prompt = json.loads(messages[1]["content"])
        requests.append(user_prompt)
        songs: list[LyricData] = []
        for offset, assignment in enumerate(user_prompt["song_assignments"]):
            index = len(requests) * 5 + offset
            prefix = opening_prefixes[index % len(opening_prefixes)]
            title_length = assignment["required_title_length"]
            title = (prefix + "测" * title_length)[:title_length]
            song = make_valid_generation_song(title).model_copy(
                update={
                    "lyrics": make_valid_generation_song(title).lyrics.replace(
                        "钥匙", prefix
                    )
                }
            )
            songs.append(song)
        return {
            "choices": [
                {"message": {"content": json.dumps({"songs": [item.model_dump() for item in songs]}, ensure_ascii=False)}}
            ]
        }

    settings = ConsoleSettings(ai_api_base_url="https://api.example.com/v1", ai_model="test-model")
    template = LyricTemplateConfig(
        account_id="account-1",
        name="批量测试",
        themes=["失去"],
        generation_count=10,
    )

    songs = await generate_lyrics(settings, template=template, count=20, post_json=post_json)

    assert len(songs) == 20
    assert [len(request["song_assignments"]) for request in requests] == [5, 5, 5, 5]
    assert requests[0]["previous_batch_context"]["used_song_names"] == []
    assert requests[1]["previous_batch_context"]["used_song_names"] == [
        song.song_name for song in songs[:5]
    ]
    assert requests[1]["previous_batch_context"]["used_title_lengths"] == [
        len(song.song_name) for song in songs[:5]
    ]
    assert "used_fatigue_terms" in requests[1]["previous_batch_context"]
    assert "used_fatigue_term_counts" in requests[1]["previous_batch_context"]
    assert requests[1]["previous_batch_context"]["requested_total_count"] == 20
    assert "used_chorus_hooks" in requests[1]["previous_batch_context"]
    assert {len(song.song_name) for song in songs} == {2, 3, 4, 5}


async def test_generate_lyrics_feeds_validation_error_into_retry() -> None:
    captured: list[dict] = []
    song = make_valid_generation_song("模板")

    async def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        captured.append(json.loads(payload["messages"][1]["content"]))
        if len(captured) == 1:
            return {"choices": [{"message": {"content": '{"songs":[]}'}}]}
        return {
            "choices": [
                {"message": {"content": f'{{"songs":[{song.model_dump_json()}]}}'}}
            ]
        }

    settings = ConsoleSettings(
        ai_api_base_url="https://api.example.com/v1",
        ai_model="test-model",
        ai_max_retries=2,
    )
    template = LyricTemplateConfig(account_id="account-1", name="重试测试", themes=["成长"])

    songs = await generate_lyrics(settings, template=template, count=1, post_json=post_json)

    assert len(songs) == 1
    assert captured[0]["retry_feedback"] == ""
    assert "上一版输出未通过确定性校验" in captured[1]["retry_feedback"]


async def test_generate_lyrics_repairs_only_the_failed_song() -> None:
    requests: list[dict[str, object]] = []
    valid_song = make_valid_generation_song("钥匙")
    invalid_song = make_valid_generation_song("旧锁门").model_copy(
        update={
            "lyrics": make_valid_generation_song("旧锁门").lyrics.replace(
                "我把照片折成纸鹤\n"
                "放进抽屉最深的格\n"
                "闹钟响到第七回合\n"
                "我仍站在原地沉默",
                "钥匙还你门会空\n"
                "旧账翻篇你先走\n"
                "灯灭之后房还空\n"
                "天色一亮我回来",
            )
        }
    )
    invalid_replacement = make_valid_generation_song("新锁门").model_copy(
        update={"lyrics": invalid_song.lyrics.replace("旧锁门", "新锁门")}
    )
    replacement_song = make_valid_generation_song("新锁门")

    async def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        user_prompt = json.loads(payload["messages"][1]["content"])
        requests.append(user_prompt)
        if len(requests) == 1:
            songs = [valid_song, invalid_song]
        elif len(requests) == 2:
            songs = [invalid_replacement]
        else:
            songs = [replacement_song]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"songs": [song.model_dump() for song in songs]},
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    settings = ConsoleSettings(
        ai_api_base_url="https://api.example.com/v1",
        ai_model="test-model",
        ai_max_retries=2,
    )
    template = LyricTemplateConfig(
        account_id="account-1",
        name="单曲修复测试",
        themes=["失去"],
    )

    songs = await generate_lyrics(settings, template=template, count=2, post_json=post_json)

    assert [song.song_name for song in songs] == ["钥匙", "新锁门"]
    assert [len(request["song_assignments"]) for request in requests] == [2, 1, 1]
    assert "《旧锁门》" in requests[1]["retry_feedback"]
    assert "旧锁门" in requests[1]["previous_batch_context"]["used_song_names"]


def test_parse_lyric_response_rejects_short_style() -> None:
    song = make_song().model_copy(update={"style": "太短"})

    with pytest.raises(ValidationFailed) as error:
        parse_lyric_response(f'{{"songs":[{song.model_dump_json()}]}}', 1)

    assert "曲风描述长度不足" in error.value.message


def test_parse_lyric_response_recovers_missing_comma_between_fields() -> None:
    song = make_valid_generation_song("模板")
    malformed = song.model_dump_json().replace(
        '"song_name":"模板","lyrics"',
        '"song_name":"模板" "lyrics"',
        1,
    )

    result = parse_lyric_response(f'{{"songs":[{malformed}]}}', 1)

    assert result[0].song_name == "模板"
    assert result[0].lyrics == song.lyrics


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
    assert parsed.lyrics == sanitize_lyrics_for_generation(song.lyrics)
    assert parsed.style == song.style
    assert "## 歌词" in markdown
    assert "## 歌曲风格" in markdown
