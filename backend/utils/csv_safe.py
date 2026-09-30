"""CSV 公式注入防护（审计 BUG-20）

采集结果是不可信的外部内容。以 = + - @ 或制表 / 回车开头的单元格会被 Excel / WPS
当作公式执行（如 =HYPERLINK(...) 外带数据、=cmd|' /C calc'!A0）。导出时给这类值加单引号前缀，
纯数字（如 -1.5）不处理。
"""
from __future__ import annotations

import re
from typing import Any

_DANGEROUS_PREFIX = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")


def neutralize_csv_value(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(_DANGEROUS_PREFIX) and not _PLAIN_NUMBER.match(value):
        return "'" + value
    return value


def safe_csv_row(row: dict) -> dict:
    return {k: neutralize_csv_value(v) for k, v in row.items()}
