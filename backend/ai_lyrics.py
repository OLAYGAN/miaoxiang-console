"""AI lyric generation with deterministic output validation."""

import json
import re
import time
from typing import Any, Callable

import httpx
from pydantic import BaseModel, Field

from backend.errors import ValidationFailed
from backend.models import (
    AI_MAX_TOKENS,
    AI_TEMPERATURE,
    AI_TIMEOUT_SECONDS,
    DEFAULT_AI_SYSTEM_PROMPT,
    ConsoleSettings,
    LyricData,
    LyricTemplateConfig,
)


SYSTEM_PROMPT = DEFAULT_AI_SYSTEM_PROMPT


class LyricGenerateRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=64)


class LyricSaveRequest(BaseModel):
    day: str | None = None
    songs: list[LyricData] = Field(min_length=1)


def build_lyric_payload(
    settings: ConsoleSettings,
    *,
    template: LyricTemplateConfig,
    count: int,
    stream: bool = False,
) -> dict[str, Any]:
    user_prompt = {
        "precedence": (
            "template_overrides_general_rules: 当模板中的歌词格调、歌曲风格、主题"
            "与通用规则冲突时，以模板为准；模板未覆盖的规则仍遵守通用规则"
        ),
        "descriptor_language": (
            "All bracketed section directives, parenthetical performance cues, "
            "and the complete style field must be written in English. Chinese is "
            "allowed only in song_name and the actual sung lyric lines; translate "
            "Chinese template ideas into professional English music descriptors."
        ),
        "template_name": template.name,
        "lyric_tone": template.lyric_tone,
        "song_style": template.song_style,
        "themes": template.themes,
        "count": count,
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
                + "\n\n# 本请求冲突处理\n当用户消息中的模板与通用规则冲突时，以模板为准；模板未覆盖的规则仍遵守通用规则。"
                + "\n\n# 输出语言硬规则\n所有方括号段落指令、圆括号演唱提示和完整 style 字段必须全部用英文；即使模板内容是中文，也要转译成专业英文音乐描述。中文只允许出现在 song_name 和实际唱出的歌词行。",
            },
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "temperature": AI_TEMPERATURE,
        "max_tokens": AI_MAX_TOKENS,
    }
    if stream:
        payload["stream"] = True
    return payload


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
        raise ValidationFailed(f"AI 返回格式错误，不是合法 JSON: {error}") from error

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
        try:
            lyric = LyricData.model_validate(
                {
                    "song_name": str(song.get("song_name") or "").strip(),
                    "lyrics": str(song.get("lyrics") or "").strip(),
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
    if not settings.ai_api_base_url or not settings.ai_model:
        raise ValidationFailed("请先在系统设置 → AI API 中完成配置")

    payload = build_lyric_payload(settings, template=template, count=count)
    headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
    url = f"{settings.ai_api_base_url.rstrip('/')}/chat/completions"

    async def default_post() -> dict:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code in {401, 403}:
            raise ValidationFailed("API Key 无效或没有权限")
        if response.status_code == 429:
            raise ValidationFailed("AI API 请求频率或额度限制，请稍后重试")
        try:
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, ValueError) as error:
            raise ValidationFailed(
                f"AI API 返回错误 {response.status_code}: {response.text[:300]}"
            ) from error

    last_error: Exception | None = None
    for _ in range(settings.ai_max_retries + 1):
        try:
            result = await post_json(url, payload) if post_json else await default_post()
            choices = result.get("choices") if isinstance(result, dict) else None
            content = choices[0].get("message", {}).get("content") if choices else None
            if not content:
                raise ValidationFailed("AI API 没有返回歌词内容")
            return parse_lyric_response(str(content), count)
        except ValidationFailed as error:
            last_error = error
            if "API Key 无效" in error.message or "频率或额度" in error.message:
                raise
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
    if not settings.ai_api_base_url or not settings.ai_model:
        raise ValidationFailed("请先在系统设置 → AI API 中完成配置")

    payload = build_lyric_payload(settings, template=template, count=count, stream=True)
    headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
    url = f"{settings.ai_api_base_url.rstrip('/')}/chat/completions"
    last_error: Exception | None = None

    for attempt in range(1, settings.ai_max_retries + 2):
        started_at = time.monotonic()
        content = ""
        reasoning = ""
        names: list[str] = []
        last_emit = 0.0

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
                            or (not content and reasoning)
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
            return parse_lyric_response(content, count)
        except ValidationFailed as error:
            last_error = error
            if "API Key 无效" in error.message or "频率或额度" in error.message:
                raise
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
