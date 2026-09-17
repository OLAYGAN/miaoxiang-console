"""Data models shared by the API, task engine, and persistence layer."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AccountConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    account_name: str = Field(min_length=1, max_length=64)
    chrome_profile_dir: str
    chrome_debug_port: int = Field(default=9222, ge=1024, le=65535)
    lyric_dir: str
    output_dir: str
    download_dir: str
    model_name: str = "Sway v5.5"
    singer_name: str = "老岩"
    max_retries: int = Field(default=3, ge=1, le=10)
    song_interval_seconds: float = Field(default=5, ge=0, le=600)
    generation_batch_size: int = Field(default=2, ge=1, le=2)
    create_url: str = "https://music.douyin.com/studio/create"
    assets_url: str = "https://music.douyin.com/studio/assets"

    @field_validator(
        "chrome_profile_dir",
        "lyric_dir",
        "output_dir",
        "download_dir",
        mode="before",
    )
    @classmethod
    def normalize_path(cls, value: object) -> str:
        if isinstance(value, Path):
            path = value
        elif isinstance(value, str) and value.strip():
            path = Path(value.strip())
        else:
            raise ValueError("路径不能为空")
        return str(path.expanduser().resolve())


class ConsoleSettings(BaseModel):
    page_load_timeout_seconds: int = Field(default=30, ge=1, le=300)
    generation_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    editor_import_wait_seconds: int = Field(default=8, ge=1, le=120)
    export_timeout_seconds: int = Field(default=60, ge=1, le=600)
    download_timeout_seconds: int = Field(default=30, ge=1, le=600)
    log_history_limit: int = Field(default=1000, ge=100, le=10000)


class LyricData(BaseModel):
    song_name: str
    lyrics: str
    style: str


class GeneratedCandidate(BaseModel):
    song_name: str
    generated_title: str
    card_index: int


class BatchSongResult(BaseModel):
    song_name: str
    status: str = "generation_failed"
    output_path: str | None = None
    error: str | None = None


class SongRecord(BaseModel):
    file_name: str
    status: str
    current_step: str = "pending"
    attempts: int = 0
    error: str | None = None
    screenshot_path: str | None = None
    output_path: str | None = None
    updated_at: datetime = Field(default_factory=datetime.now)


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    level: str = "info"
    step: str = "system"
    song: str | None = None
    message: str
    screenshot_path: str | None = None


class SongProgress(BaseModel):
    file_name: str
    song_name: str | None = None
    status: str = "pending"
    current_step: str = "pending"
    attempts: int = 0
    error: str | None = None
    screenshot_path: str | None = None


class TaskSnapshot(BaseModel):
    run_id: str
    account_id: str
    account_name: str
    status: str = "running"
    current_file: str | None = None
    current_step: str = "starting"
    songs: list[SongProgress] = Field(default_factory=list)
    success_count: int = 0
    skipped_count: int = 0
    failure_count: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None
    error: str | None = None
