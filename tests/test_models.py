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

    assert account.model_name == "自动"
    assert account.singer_name == "老岩"
    assert account.max_retries == 3
    assert account.song_interval_seconds == 5
    assert account.chrome_debug_port == 9222
    assert account.create_url == "https://music.douyin.com/studio/create"
    assert account.generation_batch_size == 2
    assert account.upload_batch_size == 10
    assert account.upload_artist_name == "白日逐梦"
    assert account.upload_real_name == "龙英"


def test_account_config_accepts_platform_models() -> None:
    base = {
        "account_name": "账号01",
        "chrome_profile_dir": "chrome/accounts/account-01",
        "lyric_dir": "lyrics",
        "output_dir": "output",
        "download_dir": "downloads",
    }
    expected_models = {
        "自动",
        "Sodance v2.0",
        "MiniMax v2.6",
        "TemPolor v4.1a",
        "音潮 v3.0",
        "SeedMusic v1.0 preview",
        "TemPolor v4.0",
        "Sway v5.5",
    }

    models = {
        AccountConfig(**base, model_name=model).model_name
        for model in expected_models
    }

    assert models == expected_models


def test_account_config_rejects_unknown_platform_model() -> None:
    with pytest.raises(ValidationError, match="model_name"):
        AccountConfig(
            account_name="账号01",
            chrome_profile_dir="chrome/accounts/account-01",
            lyric_dir="lyrics",
            output_dir="output",
            download_dir="downloads",
            model_name="Unknown model",
        )


def test_account_config_allows_empty_real_name() -> None:
    account = AccountConfig(
        account_name="账号01",
        chrome_profile_dir="chrome/accounts/account-01",
        lyric_dir="lyrics",
        output_dir="output",
        download_dir="downloads",
        upload_real_name="",
    )

    assert account.upload_real_name == ""


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

    with pytest.raises(ValidationError):
        AccountConfig(
            account_name="账号01",
            chrome_profile_dir="chrome/账号01",
            lyric_dir="lyrics/账号01",
            output_dir="output/账号01",
            download_dir="downloads/账号01",
            upload_batch_size=11,
        )
