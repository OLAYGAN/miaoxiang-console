import json
from pathlib import Path

import pytest

from backend.errors import ValidationFailed
from backend.models import AccountConfig
from backend.upload_limit import (
    MAX_DAILY_UPLOADS,
    daily_upload_remaining,
    daily_upload_used,
    ensure_daily_upload_capacity,
    record_daily_uploads,
    seed_upload_history,
)


def make_account(tmp_path: Path) -> AccountConfig:
    return AccountConfig(
        account_name="账号01",
        chrome_profile_dir=tmp_path / "chrome",
        chrome_debug_port=9222,
        lyric_dir=tmp_path / "lyrics",
        output_dir=tmp_path / "output",
        download_dir=tmp_path / "downloads",
        max_retries=1,
        song_interval_seconds=0,
    )


def write_manifest(account: AccountConfig, day: str, count: int) -> list[str]:
    directory = Path(account.output_dir) / day
    directory.mkdir(parents=True, exist_ok=True)
    paths = [str((directory / f"{index:02d}.mp3").resolve()) for index in range(count)]
    (directory / ".uploaded.json").write_text(
        json.dumps(paths, ensure_ascii=False),
        encoding="utf-8",
    )
    return paths


def test_daily_limit_allows_only_remaining_slots(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    day = "2026-10-03"
    write_manifest(account, day, MAX_DAILY_UPLOADS - 1)

    assert daily_upload_used(account, day) == MAX_DAILY_UPLOADS - 1
    assert daily_upload_remaining(account, day) == 1
    assert ensure_daily_upload_capacity(account, day, 1) == 1

    with pytest.raises(ValidationFailed, match="最多还能发布 1 首"):
        ensure_daily_upload_capacity(account, day, 2)


def test_daily_limit_rejects_upload_when_ten_have_been_published(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    day = "2026-10-03"
    write_manifest(account, day, MAX_DAILY_UPLOADS)

    assert daily_upload_used(account, day) == MAX_DAILY_UPLOADS
    assert daily_upload_remaining(account, day) == 0
    with pytest.raises(ValidationFailed, match="上限已用完"):
        ensure_daily_upload_capacity(account, day)


def test_resetting_uploaded_markers_does_not_restore_quota(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    day = "2026-10-03"
    paths = write_manifest(account, day, MAX_DAILY_UPLOADS)

    seed_upload_history(account, day)
    (Path(account.output_dir) / day / ".uploaded.json").write_text(
        "[]",
        encoding="utf-8",
    )

    assert daily_upload_used(account, day) == MAX_DAILY_UPLOADS
    history = json.loads(
        (Path(account.output_dir) / day / ".upload-history.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(history) == set(paths)


def test_daily_limit_resets_on_the_next_day(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    write_manifest(account, "2026-10-03", MAX_DAILY_UPLOADS)

    assert daily_upload_remaining(account, "2026-10-03") == 0
    assert daily_upload_remaining(account, "2026-10-04") == MAX_DAILY_UPLOADS


def test_recorded_uploads_accumulate_across_resets(tmp_path: Path) -> None:
    account = make_account(tmp_path)
    day = "2026-10-03"
    directory = Path(account.output_dir) / day
    first = str((directory / "01.mp3").resolve())
    second = str((directory / "02.mp3").resolve())

    assert record_daily_uploads(account, day, [first]) == 1
    assert record_daily_uploads(account, day, [first, second]) == 2
    assert daily_upload_used(account, day) == 2
