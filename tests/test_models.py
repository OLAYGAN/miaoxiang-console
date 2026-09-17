from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import AccountConfig, ConsoleSettings


def test_account_config_applies_stable_defaults() -> None:
    account = AccountConfig(
        account_name="账号01",
        chrome_profile_dir="chrome/accounts/account-01",
        lyric_dir="lyrics",
        output_dir="output",
        download_dir="downloads",
    )

    assert account.model_name == "Sway v5.5"
    assert account.singer_name == "老岩"
    assert account.max_retries == 3
    assert account.song_interval_seconds == 5
    assert account.chrome_debug_port == 9222
    assert account.create_url == "https://music.douyin.com/studio/create"
    assert account.generation_batch_size == 2


def test_account_config_normalizes_paths() -> None:
    account = AccountConfig(
        account_name="账号01",
        chrome_profile_dir="chrome/accounts/../accounts/账号01",
        lyric_dir="lyrics/账号01",
        output_dir="output/账号01",
        download_dir="downloads/账号01",
    )

    assert account.chrome_profile_dir == str(
        (Path.cwd() / "chrome/accounts/账号01").resolve()
    )
    assert ".." not in account.lyric_dir
    assert Path(account.output_dir).is_absolute()
    assert Path(account.download_dir).is_absolute()


def test_account_config_rejects_invalid_retry_and_port() -> None:
    with pytest.raises(ValidationError):
        AccountConfig(
            account_name="账号01",
            chrome_profile_dir="chrome/账号01",
            lyric_dir="lyrics/账号01",
            output_dir="output/账号01",
            download_dir="downloads/账号01",
            max_retries=0,
        )

    with pytest.raises(ValidationError):
        AccountConfig(
            account_name="账号01",
            chrome_profile_dir="chrome/账号01",
            lyric_dir="lyrics/账号01",
            output_dir="output/账号01",
            download_dir="downloads/账号01",
            chrome_debug_port=70000,
        )


def test_console_settings_validate_wait_bounds() -> None:
    settings = ConsoleSettings()

    assert settings.generation_timeout_seconds == 300
    assert settings.editor_import_wait_seconds == 8
    assert settings.export_timeout_seconds == 60
    assert settings.download_timeout_seconds == 30

    with pytest.raises(ValidationError):
        ConsoleSettings(generation_timeout_seconds=0)

    with pytest.raises(ValidationError):
        AccountConfig(
            account_name="账号01",
            chrome_profile_dir="chrome/账号01",
            lyric_dir="lyrics/账号01",
            output_dir="output/账号01",
            download_dir="downloads/账号01",
            generation_batch_size=3,
        )
