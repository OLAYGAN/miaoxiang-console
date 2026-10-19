from datetime import datetime

from backend.models import AccountConfig, MonitoringDailyRecord, MonitoringSnapshot
from backend.monitoring import parse_statistics_trends
from backend.storage import MonitoringRepository


def account() -> AccountConfig:
    return AccountConfig(
        account_name="账号01",
        chrome_profile_dir="chrome",
        lyric_dir="lyrics",
        output_dir="output",
        download_dir="downloads",
    )


def test_parse_statistics_trends_maps_metric_types_to_daily_fields() -> None:
    payload = {
        "1": {"baseResp": {"errorCode": 0}, "data": {"points": [
            {"date": "20261016", "totalValue": "18"},
            {"date": "20261017", "totalValue": "1,234"},
        ]}},
        "2": {"baseResp": {"errorCode": 0}, "data": {"points": [
            {"date": "20261016", "totalValue": "1"},
            {"date": "20261017", "totalValue": "20"},
        ]}},
        "3": {"baseResp": {"errorCode": 0}, "data": {"points": [
            {"date": "20261016", "totalValue": "0"},
            {"date": "20261017", "totalValue": "3"},
        ]}},
    }

    records = parse_statistics_trends(payload, account())

    assert [record.date for record in records] == ["2026-10-17", "2026-10-16"]
    assert records[0].qishui_heat_index == 1234
    assert records[0].qishui_play_count == 20
    assert records[0].qishui_paid_user_play_index == 3


def test_monitoring_repository_keeps_every_snapshot_with_platform_end_date(tmp_path) -> None:
    repository = MonitoringRepository(tmp_path / "monitoring.json")
    current = account()
    old_time = datetime(2026, 10, 17, 10, 0, 0)
    new_time = datetime(2026, 10, 17, 11, 0, 0)
    repository.save(MonitoringSnapshot(
        account_id=current.id,
        account_name=current.account_name,
        collected_at=old_time,
        records=[MonitoringDailyRecord(
            date="2026-10-16",
            account_id=current.id,
            account_name=current.account_name,
            qishui_heat_index=1,
            qishui_play_count=1,
            qishui_paid_user_play_index=1,
        )],
    ))
    repository.save(MonitoringSnapshot(
        account_id=current.id,
        account_name=current.account_name,
        collected_at=new_time,
        records=[MonitoringDailyRecord(
            date="2026-10-17",
            account_id=current.id,
            account_name=current.account_name,
            qishui_heat_index=2,
            qishui_play_count=2,
            qishui_paid_user_play_index=2,
        )],
    ))

    records = repository.list_records()

    assert len(records) == 2
    assert records[0]["date"] == "2026-10-17"
    assert records[0]["data_end_date"] == "2026-10-17"
    assert records[0]["qishui_heat_index"] == 2
    assert records[1]["date"] == "2026-10-16"
    assert records[1]["data_end_date"] == "2026-10-16"
    assert records[1]["qishui_heat_index"] == 1
    assert records[0]["snapshot_id"] != records[1]["snapshot_id"]
