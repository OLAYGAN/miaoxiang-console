"""Persistence helpers for songs rejected by the publishing platform."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.models import AccountConfig


def rejected_manifest_path(account: AccountConfig, day: str) -> Path:
    return Path(account.output_dir) / day / ".rejected.json"


def read_rejected(account: AccountConfig, day: str) -> list[dict[str, Any]]:
    path = rejected_manifest_path(account, day)
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and item.get("title")]


def write_rejected(
    account: AccountConfig,
    day: str,
    items: list[dict[str, Any]],
) -> None:
    path = rejected_manifest_path(account, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not items:
        if path.exists():
            path.unlink()
        return
    normalized = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        normalized.append({
            "title": title,
            "file_name": str(item.get("file_name") or Path(str(item.get("path") or "")).name),
            "path": str(item.get("path") or ""),
            "error": str(item.get("error") or "平台判定不及格"),
        })
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def clear_rejected_titles(account: AccountConfig, day: str, titles: set[str]) -> None:
    remaining = [
        item for item in read_rejected(account, day)
        if str(item.get("title") or "") not in titles
    ]
    write_rejected(account, day, remaining)
