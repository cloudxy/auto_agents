"""接口时间类型（审计 BUG-43）：库存 UTC naive，出参带 +00:00，入参归一成 UTC naive

用法：出入参 schema 的时间字段一律写 ``UTCDateTime`` / ``Optional[UTCDateTime]``，
不要写裸 ``datetime``——裸 datetime 的 naive 值序列化后不带偏移，前端 ``new Date()``
会按浏览器本地时区解释，差 8 小时（``test_time_contract.py`` 扫描守门）。
"""
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer, WithJsonSchema

from platform_core.timeutil import to_utc_naive, utc_iso

UTCDateTime = Annotated[
    datetime,
    AfterValidator(to_utc_naive),
    PlainSerializer(utc_iso, return_type=str, when_used="json"),
    # 契约里仍是 date-time（序列化器返回 str 会把出参 schema 退化成裸 string）
    WithJsonSchema({"type": "string", "format": "date-time"}, mode="serialization"),
]

__all__ = ["UTCDateTime"]
