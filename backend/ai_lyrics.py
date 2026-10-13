"""AI lyric generation with deterministic output validation."""

import json
import math
import re
import time
from typing import Any, Callable

import httpx
from pydantic import BaseModel, Field

from backend.errors import ValidationFailed
from backend.lyric_quality import (
    FATIGUE_TERMS,
    validate_lyric_batch,
    validate_title_assignments,
)
from backend.lyrics import sanitize_lyrics_for_generation
from backend.models import (
    AI_MAX_TOKENS,
    AI_MAX_TOKENS_PER_SONG,
    AI_MIN_REQUEST_MAX_TOKENS,
    AI_TEMPERATURE,
    AI_TIMEOUT_SECONDS,
    DEFAULT_AI_SYSTEM_PROMPT,
    ConsoleSettings,
    LyricData,
    LyricTemplateConfig,
)


SYSTEM_PROMPT = DEFAULT_AI_SYSTEM_PROMPT
MAX_AI_LYRIC_BATCH_SIZE = 5
_TITLE_LENGTH_SEQUENCE = (2, 3, 4, 5, 3, 4, 2, 5, 4, 3, 5, 2)
_OPENING_STRATEGIES = (
    "动作突入",
    "直接对白",
    "后果反噬",
    "矛盾反转",
    "具体判决",
    "质问",
    "命令",
    "物件失控",
    "倒叙揭示",
    "声音切入",
)
_EMOTIONAL_ANGLES = (
    "失去",
    "守护",
    "反击",
    "和解",
    "逃离",
    "归来",
    "愧疚",
    "清醒",
    "自嘲",
    "重新开始",
)
_HAN_CHAR = re.compile(r"[\u3400-\u9fff]")
_LENIENT_SONG_OBJECT = re.compile(
    r"\{\s*\"song_name\"\s*:\s*\"(?P<song_name>.*?)\"\s*,?\s*"
    r"\"lyrics\"\s*:\s*\"(?P<lyrics>.*?)\"\s*,?\s*"
    r"\"style\"\s*:\s*\"(?P<style>.*?)\"\s*\}",
    re.DOTALL,
)


class LyricGenerateRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=64)


class LyricSaveRequest(BaseModel):
    day: str | None = None
    songs: list[LyricData] = Field(min_length=1)


def _request_max_tokens(count: int) -> int:
    requested = max(AI_MIN_REQUEST_MAX_TOKENS, count * AI_MAX_TOKENS_PER_SONG)
    return min(AI_MAX_TOKENS, requested)


def _is_deepseek_endpoint(settings: ConsoleSettings) -> bool:
    base_url = settings.ai_api_base_url.lower()
    model = settings.ai_model.lower()
    return "deepseek" in base_url and "deepseek" in model


def build_lyric_payload(
    settings: ConsoleSettings,
    *,
    template: LyricTemplateConfig,
    count: int,
    stream: bool = False,
    song_assignments: list[dict[str, Any]] | None = None,
    previous_context: dict[str, Any] | None = None,
    retry_feedback: str | None = None,
) -> dict[str, Any]:
    context = previous_context or {}
    total_requested_count = int(context.get("requested_total_count") or count)
    fatigue_limit = max(1, math.ceil(total_requested_count * 0.15))
    fatigue_usage = {
        str(term): int(used_count)
        for term, used_count in (context.get("used_fatigue_term_counts") or {}).items()
        if str(term).strip()
    }
    motif_diversity = (
        "The default fatigue list is: 风, 灯, 光, 窗, 月, 夜, 雨, 影子, 街, "
        "门, 伞, 站台, 车票. When count is greater than one, each fatigue term may "
        "appear in no more than 15 percent of the songs in the entire generation "
        "run, rounded up, counted by distinct songs. These terms are not forbidden: "
        "one occurrence in one song may be natural, but repeated use across songs "
        "is fatigue. Assign every song a different anchor object from a different "
        "everyday domain, then check the whole batch before output."
    )
    if fatigue_usage:
        usage_text = ", ".join(
            (
                f"{term}: used {used_count}/{fatigue_limit}, "
                f"at most {max(0, fatigue_limit - used_count)} more song(s) in this batch"
            )
            for term, used_count in fatigue_usage.items()
        )
        motif_diversity += (
            f" CROSS-BATCH USAGE LIMIT: the complete requested run is "
            f"{total_requested_count} songs, so any one of these terms may appear "
            f"in at most {fatigue_limit} distinct songs. Earlier usage is {usage_text}. "
            "Prefer unused anchor objects; if a term has no remaining slot, do not "
            "use it in this batch."
        )
    user_prompt = {
        "precedence": (
            "template_overrides_general_rules: 当模板中的歌词格调、歌曲风格、主题"
            "与通用创作偏好冲突时，以模板为准；JSON 结构、歌词与风格分离规则"
            "属于硬性输出约束，任何模板都不能覆盖"
        ),
        "retry_feedback": (
            "上一版输出未通过确定性校验，本次必须修正该问题："
            f"{retry_feedback}。若错误提到某个字词重复过多，应优先换成未使用的"
            "具体物象；若错误提到押韵，必须重写整个问题段落，不能只改一行。其余"
            "硬性要求保持不变。"
            if retry_feedback
            else ""
        ),
        "lyrics_contract": (
            "The lyrics field must contain only standalone section tags in English "
            "and natural Chinese lyric lines. Every song must include two [Chorus] "
            "sections; the first two lines of both choruses must be identical. Use "
            "[Verse 1], [Pre-Chorus], [Chorus], [Verse 2], [Chorus], and optional "
            "[Bridge] by default. Every Verse and Chorus must contain exactly four "
            "sung lines, and Pre-Chorus and Bridge must contain exactly two, unless "
            "the template explicitly requires a different section length. The first "
            "three sung lines are a hard opening hook. "
            "Do not add bars, BPM, instruments, vocal roles, arrangement notes, "
            "performance cues, or a second bracketed description to any section tag."
        ),
        "opening_five_seconds": (
            "This is a hard constraint: the song must cold open and win attention in "
            "the first five seconds. If the template requires chorus-first, the first "
            "three chorus lines are the opening hook. Otherwise, the first three "
            "Verse 1 lines must work as one continuous hook: line 1 breaks the calm "
            "with a concrete action, contradiction, direct line of dialogue, conflict, "
            "or suspenseful claim; line 2 immediately increases pressure through a "
            "consequence, reversal, unanswered question, or hidden fact; line 3 reveals "
            "what is at stake or lands the memorable hook phrase. Each line should fit "
            "one natural breath and use active verbs and concrete nouns. Never open "
            "with weather, time of day, scenery, location description, generic "
            "loneliness, nostalgia, or an explanation of mood. Read the first three "
            "lines alone; if they do not create conflict, curiosity, surprise, cost, or "
            "a strong image, rewrite them before output."
        ),
        "song_design": (
            "Before writing, design each song internally: one-sentence premise, "
            "surface emotion versus hidden emotion, one recurring anchor object, "
            "and the intended emotional change. Verse 1 establishes specific people, "
            "place, relationship, and conflict. Pre-Chorus tightens the tension and "
            "must not resolve it. Chorus is the highest emotional point and contains "
            "the main hook and likely title, written in direct, repeatable language "
            "without new plot details. Verse 2 adds consequences or new information. "
            "Bridge creates a turn, confession, reversal, or quieter revelation that "
            "makes the second chorus feel renewed."
        ),
        "rhyme_contract": (
            "Rhyme is mandatory. Match the final syllable of lyric lines. In every "
            "Verse and Chorus, use one consistent four-line rhyme scheme: AAAA, AABB, "
            "or ABAB. Matching letters must share the same or a close rhyme family; "
            "prefer AAAA for Chorus hooks. Do not leave an unpaired or unmatched "
            "line, and do not alternate unrelated endings. Both choruses must keep "
            "the same rhyme pattern and hook. Do not use 的, 了, 着 or other neutral "
            "particles as the rhyme landing. Changing rhyme between sections is "
            "allowed, but unrhymed prose-like lyrics are not. Before output, "
            "mechanically label the final Chinese character of every Verse and "
            "Chorus line as A/B in working memory and rewrite any section that is "
            "not AAAA, AABB, or ABAB."
        ),
        "prosody_and_singability": (
            "Write singable, conversational Chinese with one natural breath per line. "
            "Vary line length, place key words near strong beats or line endings, and "
            "avoid tongue-twisting word order. The chorus hook must be easy to open "
            "the mouth and sing, and the emotional intensity must rise from verse to "
            "pre-chorus to chorus, then turn in the bridge before the final chorus."
        ),
        "style_contract": (
            "Put one coherent song-level direction in the style field: one primary "
            "genre, mood, a consistent vocal identity, 2-4 key instruments, dynamics, "
            "production, BPM, and key. The arrangement line must describe the full "
            "emotional arc, such as cold open -> intimate verse -> rising pre-chorus "
            "-> expansive chorus -> stripped bridge -> final chorus lift. The first "
            "line must include a signature motif audible in the first 1-2 seconds, and "
            "there must be no long intro. Use English and keep all arrangement choices "
            "out of the lyrics field. The style string must contain exactly three "
            "non-empty lines separated by newline characters: line 1 genre/mood/"
            "vocals/instruments/signature, line 2 BPM/Key/Vocals, line 3 Arrangement."
        ),
        "motif_diversity": motif_diversity,
        "batch_diversity_contract": (
            "Treat the whole requested batch as one release. This request contains "
            "at most five songs; at most 20 percent may begin with the same Chinese "
            "character and at most two may begin with the same two-character "
            "construction. Rotate genuinely different opening strategies: action "
            "collision, direct dialogue, consequence, contradiction, verdict, "
            "question, command, object out of control, delayed reveal, or sound-first "
            "scene. Do not use the same pronoun-led template repeatedly. Rotate "
            "emotional angles too: loss, protection, counterattack, reconciliation, "
            "escape, return, guilt, clarity, self-mockery, and renewal must not "
            "collapse into repeated motivational slogans. Each song must have a "
            "different one-sentence premise and a different way the ending changes. "
            "Interleave song-name lengths from 2 to 6 Chinese characters; a single "
            "length may not exceed 40 percent of the batch and must not produce a run "
            "of identical title shapes. If song_assignments is present, follow every "
            "assigned title length, opening strategy, and emotional angle exactly. "
            "If previous_batch_context is present, also avoid every listed song name, "
            "opening two-character construction, title length pattern, fatigue term, "
            "and chorus hook."
        ),
        "naturalness_contract": (
            "Every line must sound like something a person can naturally sing in one "
            "breath. Keep a clear speaker and referent; do not introduce 她 or 他 for "
            "the first time in the Bridge when the preceding song used 我 and 你. Do "
            "not use inverted or invented wording merely to force a rhyme, including "
            "锁藏, 省了没教, or a sentence such as 不充电就能留住. Ban motivational "
            "slogans such as 才是我的主场, 替我下结论, 站起来才, 逆风翻盘, 相信自己, "
            "别怕, and 不认输. Replace each slogan with a concrete action and visible "
            "cost."
        ),
        "efficiency_contract": (
            "Do one concise internal plan, then write the final lyrics directly. "
            "Do not produce alternatives, compare multiple drafts, or repeatedly "
            "rewrite already valid sections. Run one final contract check and return "
            "the JSON as soon as every song passes."
        ),
        "template_name": template.name,
        "lyric_tone": template.lyric_tone,
        "song_style": template.song_style,
        "themes": template.themes,
        "count": count,
        "song_assignments": song_assignments or [],
        "previous_batch_context": previous_context or {},
        "output_schema": {
            "songs": [{"song_name": "string", "lyrics": "string", "style": "string"}]
        },
    }
    payload: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    settings.ai_system_prompt
                    or SYSTEM_PROMPT
                )
                + "\n\n# 本请求冲突处理\n当模板中的题材、情绪、曲风、人声等创作选择与通用偏好冲突时，以模板为准；但 JSON 结构以及 lyrics / style 字段分离属于硬性格式，模板不得覆盖。"
                + "\n\n# 字段分离硬规则\n模板只决定题材、情绪、曲风、人声等创作选择，不能覆盖 JSON 结构和字段分工。lyrics 字段只保留英文方括号结构标签和实际唱出的中文歌词行，不得出现 bars、BPM、乐器、人声分工、编曲说明、圆括号演唱提示或第二组方括号描述；全部歌曲级风格与编曲信息只能写入英文 style 字段。",
            },
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "temperature": AI_TEMPERATURE,
        "max_tokens": _request_max_tokens(count),
    }
    if _is_deepseek_endpoint(settings):
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "low"
        payload["response_format"] = {"type": "json_object"}
    if stream:
        payload["stream"] = True
    return payload


def _chunk_sizes(count: int) -> list[int]:
    if count <= 0:
        raise ValidationFailed("歌词生成数量必须大于 0")
    result: list[int] = []
    remaining = count
    while remaining:
        size = min(MAX_AI_LYRIC_BATCH_SIZE, remaining)
        result.append(size)
        remaining -= size
    return result


def _song_assignments(count: int, start_index: int) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for offset in range(count):
        index = start_index + offset
        assignments.append({
            "batch_position": offset + 1,
            "required_title_length": _TITLE_LENGTH_SEQUENCE[
                index % len(_TITLE_LENGTH_SEQUENCE)
            ],
            "opening_strategy": _OPENING_STRATEGIES[index % len(_OPENING_STRATEGIES)],
            "emotional_angle": _EMOTIONAL_ANGLES[index % len(_EMOTIONAL_ANGLES)],
        })
    return assignments


def _opening_signature(song: LyricData) -> str:
    for line in song.lyrics.splitlines():
        value = line.strip()
        if not value or value.startswith("["):
            continue
        return "".join(_HAN_CHAR.findall(value))[:2]
    return ""


def _previous_batch_context(
    songs: list[LyricData], total_requested_count: int
) -> dict[str, Any]:
    used_fatigue_terms = [
        term
        for term in FATIGUE_TERMS
        if any(term in song.lyrics for song in songs)
    ]
    used_fatigue_term_counts = {
        term: sum(term in song.lyrics for song in songs)
        for term in used_fatigue_terms
    }
    used_chorus_hooks: list[str] = []
    for song in songs:
        lines = [line.strip() for line in song.lyrics.splitlines() if line.strip()]
        chorus_index = next(
            (
                index
                for index, line in enumerate(lines)
                if line.lower().startswith("[chorus")
            ),
            None,
        )
        if chorus_index is None:
            continue
        hook = " / ".join(lines[chorus_index + 1 : chorus_index + 3])
        if hook and hook not in used_chorus_hooks:
            used_chorus_hooks.append(hook)
    return {
        "used_song_names": [song.song_name for song in songs],
        "used_opening_two_chars": [
            _opening_signature(song) for song in songs if _opening_signature(song)
        ],
        "used_title_lengths": [len(_HAN_CHAR.findall(song.song_name)) for song in songs],
        "requested_total_count": total_requested_count,
        "used_fatigue_terms": used_fatigue_terms,
        "used_fatigue_term_counts": used_fatigue_term_counts,
        "used_chorus_hooks": used_chorus_hooks,
    }


def discovered_song_names(content: str) -> list[str]:
    names: list[str] = []
    for value in re.findall(r'"song_name"\s*:\s*"([^"]+)"', content):
        try:
            name = json.loads(f'"{value}"')
        except json.JSONDecodeError:
            name = value
        if name and name not in names:
            names.append(name)
    return names


def compact_excerpt(text: str, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", text).strip()[-limit:]


def _decode_json_fragment(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return (
            value.replace("\\r", "\r")
            .replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )


def _parse_lenient_song_objects(text: str) -> list[dict[str, str]] | None:
    songs = [
        {
            "song_name": _decode_json_fragment(match.group("song_name")),
            "lyrics": _decode_json_fragment(match.group("lyrics")),
            "style": _decode_json_fragment(match.group("style")),
        }
        for match in _LENIENT_SONG_OBJECT.finditer(text)
    ]
    return songs or None


def parse_lyric_response(content: str, expected_count: int) -> list[LyricData]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as error:
        songs = _parse_lenient_song_objects(text)
        if songs is None:
            raise ValidationFailed(f"AI 返回格式错误，不是合法 JSON: {error}") from error
    else:
        songs = payload.get("songs") if isinstance(payload, dict) else None
    if not isinstance(songs, list):
        raise ValidationFailed("AI 返回格式错误：缺少 songs 数组")
    if len(songs) != expected_count:
        raise ValidationFailed(f"AI 返回数量错误：期望 {expected_count} 首，实际 {len(songs)} 首")

    result: list[LyricData] = []
    names: set[str] = set()
    for index, song in enumerate(songs, start=1):
        if not isinstance(song, dict):
            raise ValidationFailed(f"第 {index} 首歌词格式错误")
        raw_lyrics = str(song.get("lyrics") or "").strip()
        lyrics = sanitize_lyrics_for_generation(raw_lyrics)
        try:
            lyric = LyricData.model_validate(
                {
                    "song_name": str(song.get("song_name") or "").strip(),
                    "lyrics": lyrics,
                    "style": str(song.get("style") or "").strip(),
                }
            )
        except Exception as error:
            raise ValidationFailed(f"第 {index} 首歌词字段不完整: {error}") from error
        if len(lyric.lyrics) <= 100:
            raise ValidationFailed(f"第 {index} 首歌词长度不足：当前 {len(lyric.lyrics)} 字符")
        if len(lyric.style) <= 50:
            raise ValidationFailed(f"第 {index} 首曲风描述长度不足：当前 {len(lyric.style)} 字符")
        if lyric.song_name in names:
            raise ValidationFailed(f"AI 返回了重复歌名: {lyric.song_name}")
        names.add(lyric.song_name)
        result.append(lyric)
    return result


async def _post_lyric_completion(
    settings: ConsoleSettings,
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    expected_count: int,
    post_json: Callable[[str, dict], Any] | None = None,
) -> list[LyricData]:
    if post_json is not None:
        result = await post_json(url, payload)
    else:
        try:
            async with httpx.AsyncClient(
                timeout=AI_TIMEOUT_SECONDS, follow_redirects=True
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.RequestError as error:
            message = (
                f"AI API 请求超时（本次允许 {AI_TIMEOUT_SECONDS} 秒）"
                if isinstance(error, httpx.TimeoutException)
                else f"AI API 请求失败: {type(error).__name__}: {error}"
            )
            raise ValidationFailed(message) from error
        if response.status_code in {401, 403}:
            raise ValidationFailed("API Key 无效或没有权限")
        if response.status_code == 429:
            raise ValidationFailed("AI API 请求频率或额度限制，请稍后重试")
        try:
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPStatusError, ValueError) as error:
            raise ValidationFailed(
                f"AI API 返回错误 {response.status_code}: {response.text[:300]}"
            ) from error

    choices = result.get("choices") if isinstance(result, dict) else None
    content = choices[0].get("message", {}).get("content") if choices else None
    if not content:
        raise ValidationFailed("AI API 没有返回歌词内容")
    return parse_lyric_response(str(content), expected_count)


def _failed_song_indexes(songs: list[LyricData], error: ValidationFailed) -> list[int]:
    indexes = [
        index
        for index, song in enumerate(songs)
        if f"《{song.song_name}》" in error.message
    ]
    if indexes:
        return indexes

    fatigue_match = re.search(
        r"疲劳意象频率过高：(.+?)，当前最多允许\s*(\d+)\s*首",
        error.message,
    )
    if not fatigue_match:
        return []
    maximum_songs = int(fatigue_match.group(2))
    for term in re.findall(r"([^、\s]+)\s+\d+\s*首", fatigue_match.group(1)):
        matches = [
            index
            for index, song in enumerate(songs)
            if term in song.lyrics or term in song.song_name
        ]
        indexes.extend(matches[maximum_songs:])
    return sorted(set(indexes))


async def _repair_invalid_songs(
    settings: ConsoleSettings,
    *,
    url: str,
    headers: dict[str, str],
    template: LyricTemplateConfig,
    songs: list[LyricData],
    failed_indexes: list[int],
    song_assignments: list[dict[str, Any]] | None,
    previous_context: dict[str, Any] | None,
    prior_songs: list[LyricData] | None,
    original_error: ValidationFailed,
    post_json: Callable[[str, dict], Any] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> list[LyricData]:
    repaired = list(songs)
    pending = list(dict.fromkeys(failed_indexes))
    last_error = original_error
    total_requested_count = int(
        (previous_context or {}).get("requested_total_count")
        or len(prior_songs or []) + len(songs)
    )

    for _ in range(settings.ai_max_retries + 1):
        if not pending:
            break
        next_pending: list[int] = []
        for index in pending:
            if index < 0 or index >= len(repaired):
                continue
            assignment = (
                dict(song_assignments[index])
                if song_assignments and index < len(song_assignments)
                else {}
            )
            assignment["batch_position"] = 1
            old_name = repaired[index].song_name
            context_songs = [
                *(prior_songs or []),
                *[
                    song
                    for position, song in enumerate(repaired)
                    if position != index
                ],
            ]
            replacement_context = _previous_batch_context(
                context_songs, total_requested_count
            )
            used_names = replacement_context.setdefault("used_song_names", [])
            if old_name and old_name not in used_names:
                used_names.append(old_name)
            if on_progress:
                on_progress({
                    "stage": "repairing",
                    "message": f"仅重写未通过歌曲《{old_name}》",
                })
            try:
                payload = build_lyric_payload(
                    settings,
                    template=template,
                    count=1,
                    song_assignments=[assignment],
                    previous_context=replacement_context,
                    retry_feedback=(
                        f"{last_error.message}。只重写这一首；每个 Verse 和 Chorus "
                        "必须明确采用 AAAA、AABB 或 ABAB 韵式，先标出句尾韵母，"
                        "再确认 style 恰好三行，然后立即输出最终 JSON。"
                    ),
                )
                replacement = await _post_lyric_completion(
                    settings,
                    url=url,
                    headers=headers,
                    payload=payload,
                    expected_count=1,
                    post_json=post_json,
                )
                validate_lyric_batch(replacement)
                validate_title_assignments(replacement, [assignment])
                candidate = list(repaired)
                candidate[index] = replacement[0]
                repaired = candidate
            except ValidationFailed as error:
                last_error = error
                next_pending.append(index)

        try:
            validate_lyric_batch([*(prior_songs or []), *repaired])
            validate_title_assignments(repaired, song_assignments)
            return repaired
        except ValidationFailed as error:
            last_error = error
            pending = list(dict.fromkeys([*next_pending, *_failed_song_indexes(repaired, error)]))
            if not pending:
                raise

    raise last_error


def render_lyric_markdown(song: LyricData) -> str:
    return (
        f"# 歌名：《{song.song_name}》\n\n"
        f"## 歌词\n歌名：《{song.song_name}》\n\n{song.lyrics}\n[End]\n\n"
        f"## 歌曲风格\n{song.style}\n"
    )


async def generate_lyrics(
    settings: ConsoleSettings,
    *,
    template: LyricTemplateConfig,
    count: int,
    post_json: Callable[[str, dict], Any] | None = None,
) -> list[LyricData]:
    """Generate a full request in small independent batches.

    A single large request tends to reuse one title shape, one opening
    construction, and one emotional arc. The outer request is therefore divided
    into batches of at most five songs, with explicit assignments and context
    from all earlier batches.
    """

    sizes = _chunk_sizes(count)
    songs: list[LyricData] = []
    start_index = 0
    for size in sizes:
        batch = await _generate_lyrics_request(
            settings,
            template=template,
            count=size,
            post_json=post_json,
            song_assignments=_song_assignments(size, start_index),
            previous_context=_previous_batch_context(songs, count),
            prior_songs=songs,
        )
        songs.extend(batch)
        start_index += size
    validate_lyric_batch(songs)
    validate_title_assignments(songs, _song_assignments(count, 0))
    return songs


async def _generate_lyrics_request(
    settings: ConsoleSettings,
    *,
    template: LyricTemplateConfig,
    count: int,
    post_json: Callable[[str, dict], Any] | None = None,
    song_assignments: list[dict[str, Any]] | None = None,
    previous_context: dict[str, Any] | None = None,
    prior_songs: list[LyricData] | None = None,
) -> list[LyricData]:
    if not settings.ai_api_base_url or not settings.ai_model:
        raise ValidationFailed("请先在系统设置 → AI API 中完成配置")

    headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
    url = f"{settings.ai_api_base_url.rstrip('/')}/chat/completions"

    last_error: Exception | None = None
    for _ in range(settings.ai_max_retries + 1):
        parsed_songs: list[LyricData] | None = None
        payload = build_lyric_payload(
            settings,
            template=template,
            count=count,
            song_assignments=song_assignments,
            previous_context=previous_context,
            retry_feedback=last_error.message if last_error else None,
        )
        try:
            parsed_songs = await _post_lyric_completion(
                settings,
                url=url,
                headers=headers,
                payload=payload,
                expected_count=count,
                post_json=post_json,
            )
            validate_lyric_batch([*(prior_songs or []), *parsed_songs])
            validate_title_assignments(parsed_songs, song_assignments)
            return parsed_songs
        except ValidationFailed as error:
            last_error = error
            if "API Key 无效" in error.message or "频率或额度" in error.message:
                raise
            if parsed_songs:
                failed_indexes = _failed_song_indexes(parsed_songs, error)
                if failed_indexes and len(failed_indexes) < len(parsed_songs):
                    try:
                        return await _repair_invalid_songs(
                            settings,
                            url=url,
                            headers=headers,
                            template=template,
                            songs=parsed_songs,
                            failed_indexes=failed_indexes,
                            song_assignments=song_assignments,
                            previous_context=previous_context,
                            prior_songs=prior_songs,
                            original_error=error,
                            post_json=post_json,
                        )
                    except ValidationFailed as repair_error:
                        last_error = repair_error
        except (httpx.RequestError, IndexError, KeyError, TypeError) as error:
            timeout_message = (
                f"AI API 请求超时（本次允许 {AI_TIMEOUT_SECONDS} 秒）；"
                "生成数量越多耗时越长，请稍后重试或减少单次生成数量"
                if isinstance(error, httpx.TimeoutException)
                else f"AI API 请求失败: {type(error).__name__}: {error}"
            )
            last_error = ValidationFailed(timeout_message)
    raise last_error or ValidationFailed("AI 作词失败")


async def stream_generate_lyrics(
    settings: ConsoleSettings,
    *,
    template: LyricTemplateConfig,
    count: int,
    on_progress: Callable[[dict[str, Any]], None],
) -> list[LyricData]:
    sizes = _chunk_sizes(count)
    songs: list[LyricData] = []
    start_index = 0
    batch_count = len(sizes)
    for batch_index, size in enumerate(sizes, start=1):
        def forward_progress(progress: dict[str, Any]) -> None:
            on_progress({
                **progress,
                "expected_count": count,
                "batch_index": batch_index,
                "batch_count": batch_count,
                "batch_size": size,
                "completed_song_count": len(songs),
            })

        batch = await _stream_generate_lyrics_request(
            settings,
            template=template,
            count=size,
            on_progress=forward_progress,
            song_assignments=_song_assignments(size, start_index),
            previous_context=_previous_batch_context(songs, count),
            prior_songs=songs,
        )
        songs.extend(batch)
        start_index += size
    validate_lyric_batch(songs)
    validate_title_assignments(songs, _song_assignments(count, 0))
    return songs


async def _stream_generate_lyrics_request(
    settings: ConsoleSettings,
    *,
    template: LyricTemplateConfig,
    count: int,
    on_progress: Callable[[dict[str, Any]], None],
    song_assignments: list[dict[str, Any]] | None = None,
    previous_context: dict[str, Any] | None = None,
    prior_songs: list[LyricData] | None = None,
) -> list[LyricData]:
    if not settings.ai_api_base_url or not settings.ai_model:
        raise ValidationFailed("请先在系统设置 → AI API 中完成配置")

    headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
    url = f"{settings.ai_api_base_url.rstrip('/')}/chat/completions"
    last_error: Exception | None = None

    for attempt in range(1, settings.ai_max_retries + 2):
        started_at = time.monotonic()
        content = ""
        reasoning = ""
        names: list[str] = []
        last_emit = 0.0
        parsed_songs: list[LyricData] | None = None

        def emit(stage: str, **extra: Any) -> None:
            nonlocal last_emit
            last_emit = time.monotonic()
            on_progress({
                "stage": stage,
                "attempt": attempt,
                "elapsed_seconds": round(last_emit - started_at, 1),
                "expected_count": count,
                "content_chars": len(content),
                "reasoning_chars": len(reasoning),
                "reasoning_available": bool(reasoning),
                "reasoning_excerpt": compact_excerpt(reasoning) if reasoning else "",
                "song_names": names,
                **extra,
            })

        emit("connecting", message="正在连接 AI API")
        payload = build_lyric_payload(
            settings,
            template=template,
            count=count,
            stream=True,
            song_assignments=song_assignments,
            previous_context=previous_context,
            retry_feedback=last_error.message if last_error else None,
        )
        try:
            async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS, follow_redirects=True) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code in {401, 403}:
                        raise ValidationFailed("API Key 无效或没有权限")
                    if response.status_code == 429:
                        raise ValidationFailed("AI API 请求频率或额度限制，请稍后重试")
                    if response.status_code >= 400:
                        error_text = (await response.aread()).decode("utf-8", errors="replace")
                        raise ValidationFailed(f"AI API 返回错误 {response.status_code}: {error_text[:300]}")

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") if isinstance(chunk, dict) else None
                        delta = choices[0].get("delta", {}) if choices else {}
                        if not isinstance(delta, dict):
                            continue
                        reasoning += str(delta.get("reasoning_content") or "")
                        content += str(delta.get("content") or "")
                        current_names = discovered_song_names(content)
                        now = time.monotonic()
                        should_emit = (
                            current_names != names
                            or now - last_emit >= 0.5
                        )
                        if should_emit:
                            names = current_names
                            if reasoning and not content:
                                emit("thinking", message="AI 正在整理创作思路")
                            elif content:
                                emit(
                                    "generating",
                                    message=f"正在输出歌词，已接收 {len(content)} 字符",
                                )

            names = discovered_song_names(content)
            if not content:
                raise ValidationFailed("AI API 没有返回歌词内容")
            emit("parsing", message="输出完成，正在校验 JSON 和歌词字段")
            parsed_songs = parse_lyric_response(content, count)
            validate_lyric_batch([*(prior_songs or []), *parsed_songs])
            validate_title_assignments(parsed_songs, song_assignments)
            return parsed_songs
        except ValidationFailed as error:
            last_error = error
            if "API Key 无效" in error.message or "频率或额度" in error.message:
                raise
            if parsed_songs:
                failed_indexes = _failed_song_indexes(parsed_songs, error)
                if failed_indexes and len(failed_indexes) < len(parsed_songs):
                    def repair_progress(progress: dict[str, Any]) -> None:
                        on_progress({
                            **progress,
                            "attempt": attempt,
                            "elapsed_seconds": round(
                                time.monotonic() - started_at, 1
                            ),
                            "expected_count": count,
                            "content_chars": len(content),
                            "reasoning_chars": len(reasoning),
                            "reasoning_available": bool(reasoning),
                            "reasoning_excerpt": "",
                            "song_names": names,
                        })

                    try:
                        return await _repair_invalid_songs(
                            settings,
                            url=url,
                            headers=headers,
                            template=template,
                            songs=parsed_songs,
                            failed_indexes=failed_indexes,
                            song_assignments=song_assignments,
                            previous_context=previous_context,
                            prior_songs=prior_songs,
                            original_error=error,
                            on_progress=repair_progress,
                        )
                    except ValidationFailed as repair_error:
                        last_error = repair_error
            on_progress({
                "stage": "retrying",
                "attempt": attempt,
                "elapsed_seconds": round(time.monotonic() - started_at, 1),
                "expected_count": count,
                "content_chars": len(content),
                "reasoning_chars": len(reasoning),
                "reasoning_available": bool(reasoning),
                "reasoning_excerpt": "",
                "song_names": names,
                "message": last_error.message,
            })
        except (httpx.RequestError, IndexError, KeyError, TypeError) as error:
            message = (
                f"AI API 请求超时（本次允许 {AI_TIMEOUT_SECONDS} 秒）"
                if isinstance(error, httpx.TimeoutException)
                else f"AI API 请求失败: {type(error).__name__}: {error}"
            )
            last_error = ValidationFailed(message)
            on_progress({
                "stage": "retrying",
                "attempt": attempt,
                "elapsed_seconds": round(time.monotonic() - started_at, 1),
                "expected_count": count,
                "content_chars": len(content),
                "reasoning_chars": len(reasoning),
                "reasoning_available": bool(reasoning),
                "reasoning_excerpt": "",
                "song_names": names,
                "message": message,
            })

        if attempt <= settings.ai_max_retries:
            on_progress({
                "stage": "retrying",
                "attempt": attempt + 1,
                "elapsed_seconds": 0,
                "expected_count": count,
                "content_chars": 0,
                "reasoning_chars": 0,
                "reasoning_available": False,
                "reasoning_excerpt": "",
                "song_names": [],
                "message": "准备重试 AI 作词请求",
            })

    raise last_error or ValidationFailed("AI 作词失败")
