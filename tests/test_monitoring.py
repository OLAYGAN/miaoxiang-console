from datetime import datetime

from backend.models import AccountConfig, MonitoringDailyRecord, MonitoringSnapshot
from backend.monitoring import (
    parse_settlement_available_balance,
    parse_statistics_trends,
    parse_statistics_update_date,
)
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
        "4": {"baseResp": {"errorCode": 0}, "data": {"points": [
            {"date": "20261016", "totalValue": "7"},
            {"date": "20261017", "totalValue": "0"},
        ]}},
    }

    records = parse_statistics_trends(payload, account())

    assert [record.date for record in records] == ["2026-10-17", "2026-10-16"]
    assert records[0].qishui_heat_index == 1234
    assert records[0].qishui_play_count == 20
    assert records[0].qishui_paid_user_play_index == 3
    assert records[0].qishui_search_play_index == 0


def test_parse_statistics_update_date_uses_platform_date() -> None:
    assert parse_statistics_update_date("数据中心\n数据更新至2026/10/19\n近1天") == "2026-10-19"
    assert parse_statistics_update_date("数据更新至2026/10/32") is None


def test_parse_settlement_available_balance_handles_platform_text() -> None:
    page_text = "我的收入\n收支明细\n可用余额\n15.01\u00a0元\n提现指引"

    assert parse_settlement_available_balance(page_text) == 15.01
    assert parse_settlement_available_balance("可用余额 1,234.50 元") == 1234.5
    assert parse_settlement_available_balance("可用余额") is None


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


def test_monitoring_records_are_unique_for_account_and_date(tmp_path) -> None:
    repository = MonitoringRepository(tmp_path / "monitoring.json")
    current = account()
    first_time = datetime(2026, 10, 21, 10, 0, 0)
    second_time = datetime(2026, 10, 21, 11, 0, 0)

    def snapshot(collected_at: datetime, heat: int) -> MonitoringSnapshot:
        return MonitoringSnapshot(
            trigger="manual",
            period="last_1_day",
            account_id=current.id,
            account_name=current.account_name,
            collected_at=collected_at,
            records=[MonitoringDailyRecord(
                date="2026-10-19",
                account_id=current.id,
                account_name=current.account_name,
                qishui_heat_index=heat,
                qishui_play_count=heat,
                qishui_paid_user_play_index=heat,
                qishui_search_play_index=heat,
            )],
        )

    repository.save(snapshot(first_time, 1))
    repository.save(snapshot(second_time, 2))

    records = repository.list_records()

    assert len(records) == 1
    assert records[0]["date"] == "2026-10-19"
    assert records[0]["collected_at"] == second_time
    assert records[0]["qishui_heat_index"] == 2
