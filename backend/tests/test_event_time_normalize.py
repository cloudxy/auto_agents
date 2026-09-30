"""事件时刻归一（审计 BUG-43 / F3 QA-6 第 4 点回归）"""
from datetime import datetime, timedelta, timezone

from backend.services.product_event_service import normalize_occurred_at

NOW = datetime(2026, 9, 28, 4, 0, 0)  # UTC naive


def test_none_uses_server_time():
    assert normalize_occurred_at(None, NOW) == NOW


def test_offset_aware_value_converted_to_utc():
    """+08:00 的 12:01 = UTC 04:01：原先按墙钟 12:01 落库，偏 8 小时"""
    shanghai = datetime(2026, 9, 28, 12, 1, 0, tzinfo=timezone(timedelta(hours=8)))
    assert normalize_occurred_at(shanghai, NOW) == datetime(2026, 9, 28, 4, 1, 0)


def test_forged_past_or_future_replaced_by_server_time():
    assert normalize_occurred_at(NOW - timedelta(days=30), NOW) == NOW
    assert normalize_occurred_at(NOW + timedelta(hours=2), NOW) == NOW


def test_small_skew_kept():
    value = NOW - timedelta(seconds=90)
    assert normalize_occurred_at(value, NOW) == value
