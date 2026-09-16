import json
from pathlib import Path

import pytest

from backend.errors import ConflictError, NotFoundError
from backend.events import EventBus
from backend.models import AccountConfig, LogEntry, SongRecord
from backend.storage import AccountRepository, JsonStore, RunStateRepository


def make_account(name: str = "账号01", port: int = 9222) -> AccountConfig:
    return AccountConfig(
        account_name=name,
        chrome_profile_dir=f"chrome/{name}",
        chrome_debug_port=port,
        lyric_dir=f"lyrics/{name}",
        output_dir=f"output/{name}",
        download_dir=f"downloads/{name}",
    )


def test_json_store_writes_atomically_and_backs_up_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    store = JsonStore(path, default={"value": 1})

    assert store.read() == {"value": 1}
    backups = list(tmp_path.glob("state.*.corrupt.json"))
    assert len(backups) == 1

    store.write({"value": 2})
    assert json.loads(path.read_text(encoding="utf-8"))["value"] == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_account_repository_crud_and_conflicts(tmp_path: Path) -> None:
    repository = AccountRepository(tmp_path / "accounts.json")
    account = repository.create(make_account())

    assert repository.list() == [account]
    assert repository.get(account.id) == account

    with pytest.raises(ConflictError, match="端口"):
        repository.create(make_account(name="账号02", port=9222))
    with pytest.raises(ConflictError, match="名称"):
        repository.create(make_account(name="账号01", port=9223))

    changed = account.model_copy(update={"account_name": "主账号", "chrome_debug_port": 9230})
    updated = repository.update(account.id, changed)
    assert updated.account_name == "主账号"

    copied = repository.copy(account.id, "备用账号")
    assert copied.id != account.id
    assert copied.account_name == "备用账号"
    assert copied.chrome_debug_port != 9230

    repository.delete(account.id)
    with pytest.raises(NotFoundError):
        repository.get(account.id)


def test_run_state_is_isolated_by_date_account_and_song(tmp_path: Path) -> None:
    repository = RunStateRepository(tmp_path / "run_state.json")
    record = SongRecord(file_name="01_song.md", status="成功")

    repository.mark("2026-09-17", "账号01", record)
    repository.mark(
        "2026-09-17",
        "账号02",
        SongRecord(file_name="01_song.md", status="失败"),
    )

    assert repository.get("2026-09-17", "账号01", "01_song.md").status == "成功"
    assert repository.get("2026-09-17", "账号02", "01_song.md").status == "失败"
    assert repository.get("2026-09-16", "账号01", "01_song.md") is None
    assert repository.list("2026-09-17", "账号01") == [record]


@pytest.mark.asyncio
async def test_event_bus_publishes_and_keeps_recent_history() -> None:
    bus = EventBus(history_limit=2)
    received: list[dict] = []

    def subscriber(event: dict) -> None:
        received.append(event)

    unsubscribe = bus.subscribe(subscriber)
    await bus.publish({"type": "log", "data": LogEntry(message="first").model_dump(mode="json")})
    await bus.publish({"type": "log", "data": LogEntry(message="second").model_dump(mode="json")})
    await bus.publish({"type": "log", "data": LogEntry(message="third").model_dump(mode="json")})

    assert [event["data"]["message"] for event in received] == ["first", "second", "third"]
    assert [event["data"]["message"] for event in bus.recent()] == ["second", "third"]

    unsubscribe()
    await bus.publish({"type": "log", "data": LogEntry(message="fourth").model_dump(mode="json")})
    assert received[-1]["data"]["message"] == "third"
