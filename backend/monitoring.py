"""Parsing helpers for Douyin Music disclosure statistics."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from backend.errors import BrowserFlowError
from backend.models import AccountConfig, MonitoringDailyRecord


STATISTICS_URL = "https://music.douyin.com/console/statistics?enter_from=menu_data_center"
SETTLEMENT_URL = "https://music.douyin.com/console/settlement/index"
STATISTICS_PERIOD_LAST_1_DAY = 1
STATISTICS_PERIOD_LAST_7_DAYS = 2
STATISTICS_METRIC_TYPES = {
    "qishui_heat_index": 1,
    "qishui_play_count": 2,
    "qishui_paid_user_play_index": 3,
    "qishui_search_play_index": 4,
}


def _metric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_statistics_trends(
    payload: dict[str, Any],
    account: AccountConfig,
) -> list[MonitoringDailyRecord]:
    trends: dict[str, dict[str, float | None]] = {}
    for field, metric_type in STATISTICS_METRIC_TYPES.items():
        response = payload.get(str(metric_type))
        if not isinstance(response, dict):
            raise BrowserFlowError(f"统计接口未返回指标 {metric_type}")
        base = response.get("baseResp") or {}
        if int(base.get("errorCode") or 0) != 0:
            raise BrowserFlowError(f"统计接口返回错误 {metric_type}: {base.get('errorMsg') or base.get('errorCode')}")
        data = response.get("data") or {}
        points = data.get("points")
        if not isinstance(points, list) or not points:
            raise BrowserFlowError(f"统计接口未返回指标 {metric_type} 的每日数据")
        values: dict[str, float | None] = {}
        for point in points:
            if not isinstance(point, dict):
                continue
            raw_date = str(point.get("date") or "")
            try:
                iso_date = datetime.strptime(raw_date, "%Y%m%d").date().isoformat()
            except ValueError as error:
                raise BrowserFlowError(f"统计接口日期格式错误: {raw_date}") from error
            values[iso_date] = _metric_value(point.get("totalValue"))
        if not values:
            raise BrowserFlowError(f"统计接口指标 {metric_type} 没有有效日期")
        trends[field] = values

    dates = set(trends["qishui_heat_index"])
    for values in trends.values():
        dates &= set(values)
    if not dates:
        raise BrowserFlowError("统计指标的日期没有交集")

    return [
        MonitoringDailyRecord(
            date=iso_date,
            account_id=account.id,
            account_name=account.account_name,
            qishui_heat_index=trends["qishui_heat_index"][iso_date],
            qishui_play_count=trends["qishui_play_count"][iso_date],
            qishui_paid_user_play_index=trends["qishui_paid_user_play_index"][iso_date],
            qishui_search_play_index=trends["qishui_search_play_index"][iso_date],
        )
        for iso_date in sorted(dates, reverse=True)
    ]


def parse_statistics_update_date(page_text: str) -> str | None:
    match = re.search(r"数据更新至\s*(\d{4})/(\d{1,2})/(\d{1,2})", page_text)
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ).date().isoformat()
    except ValueError:
        return None


def parse_settlement_available_balance(page_text: str) -> float | None:
    match = re.search(
        r"可用余额\s*(?:￥|¥)?\s*([0-9][0-9,.\u00a0 ]*?)\s*元",
        page_text,
    )
    if not match:
        return None
    value = _metric_value(match.group(1))
    return value if value is not None and value >= 0 else None
