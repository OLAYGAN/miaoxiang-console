"""Daily publish quota tracking for each platform account."""

import json
from pathlib import Path

from backend.errors import ValidationFailed
from backend.models import AccountConfig


MAX_DAILY_UPLOADS = 10


def _day_directory(account: AccountConfig, day: str) -> Path:
    return Path(account.output_dir) / day


def _manifest_paths(account: AccountConfig, day: str) -> set[str]:
    path = _day_directory(account, day) / ".uploaded.json"
    if not path.is_file():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(item) for item in value} if isinstance(value, list) else set()


def _history_paths(account: AccountConfig, day: str) -> set[str]:
    path = _day_directory(account, day) / ".upload-history.json"
    if not path.is_file():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(item) for item in value} if isinstance(value, list) else set()


def _write_history(account: AccountConfig, day: str, paths: set[str]) -> None:
    directory = _day_directory(account, day)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".upload-history.json").write_text(
        json.dumps(sorted(paths), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def seed_upload_history(account: AccountConfig, day: str) -> None:
    """Preserve the daily count when local uploaded markers are reset."""
    manifest = _manifest_paths(account, day)
    history = _history_paths(account, day)
    missing = manifest - history
    if missing:
        _write_history(account, day, history | manifest)


def daily_upload_used(account: AccountConfig, day: str) -> int:
    return min(
        MAX_DAILY_UPLOADS,
        max(
            len(_manifest_paths(account, day)),
            len(_history_paths(account, day)),
        ),
    )


def daily_upload_remaining(account: AccountConfig, day: str) -> int:
    return max(0, MAX_DAILY_UPLOADS - daily_upload_used(account, day))


def ensure_daily_upload_capacity(
    account: AccountConfig,
    day: str,
    selected_count: int | None = None,
) -> int:
    remaining = daily_upload_remaining(account, day)
    used = daily_upload_used(account, day)
    if remaining == 0:
        raise ValidationFailed(
            f"{account.account_name} {day} 已发布 {used}/{MAX_DAILY_UPLOADS} 首，"
            "平台每日上传上限已用完"
        )
    if selected_count is not None and selected_count > remaining:
        raise ValidationFailed(
            f"{account.account_name} {day} 最多还能发布 {remaining} 首，"
            f"本次选择了 {selected_count} 首"
        )
    return remaining


def record_daily_uploads(
    account: AccountConfig,
    day: str,
    uploaded_paths: list[str],
) -> int:
    seed_upload_history(account, day)
    history = _history_paths(account, day)
    history.update(str(path) for path in uploaded_paths)
    _write_history(account, day, history)
    return min(len(history), MAX_DAILY_UPLOADS)
