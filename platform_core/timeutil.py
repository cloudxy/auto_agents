"""统一时间基准（审计 BUG-43 / F3 QA-6 / R3 QA-5）

约定（单一事实源）：
- **库里存 UTC naive**。MySQL 会话固定 ``time_zone='+00:00'``（:data:`MYSQL_UTC_CONNECT_ARGS`），
  ``NOW()`` / ``CURRENT_TIMESTAMP`` / ``ON UPDATE`` 与 Python 写入同一时钟。
- **应用只用** :func:`utcnow`，不用宿主本地 ``datetime.now()``（宿主时区随部署而变）。
- **业务日按 Asia/Shanghai 切**：配额窗口、按日分桶、月度计量都用 :data:`BUSINESS_TZ`。
- **API 输出带偏移**：naive 值一律按 UTC 标注（:func:`utc_iso`），前端按本地时区渲染。

Asia/Shanghai 自 1991 年起无夏令时，SQL 侧按固定 +8 小时切日（:class:`business_date`）
与 zoneinfo 结果一致。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import Date

BUSINESS_TZ_NAME = "Asia/Shanghai"
BUSINESS_TZ = ZoneInfo(BUSINESS_TZ_NAME)
_BUSINESS_OFFSET_HOURS = 8

# pymysql / aiomysql 都认 init_command：每条物理连接建立时执行一次
MYSQL_UTC_CONNECT_ARGS: dict[str, Any] = {"init_command": "SET time_zone = '+00:00'"}


def utcnow() -> datetime:
    """当前 UTC 时刻（naive，与库内存储口径一致）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    """入库前归一：带偏移的换算成 UTC 再去掉 tzinfo；naive 视为已是 UTC"""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def business_now() -> datetime:
    """业务时区当前时刻（带 tzinfo）"""
    return datetime.now(BUSINESS_TZ)


def business_today() -> date:
    """业务日（Asia/Shanghai）"""
    return business_now().date()


def business_date_of(value: datetime) -> date:
    """某个时刻所属的业务日；naive 按 UTC 解释"""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(BUSINESS_TZ).date()


def business_day_start_utc(day: date) -> datetime:
    """业务日零点对应的 UTC naive 时刻（窗口下界）"""
    local = datetime.combine(day, datetime.min.time(), tzinfo=BUSINESS_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def utc_iso(value: Any) -> Any:
    """API 输出：datetime → 带 +00:00 的 ISO 串（naive 按 UTC 标注）；其他类型原样返回"""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def business_iso(value: Any) -> Any:
    """导出文件用：datetime → 北京时间且带 +08:00 的 ISO 串（人读友好、仍自描述）；其他原样返回"""
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(BUSINESS_TZ).isoformat()
    return value


class business_date(FunctionElement):
    """SQL 表达式：UTC 列 → 业务日（Asia/Shanghai）的 DATE。

    替代 ``func.date(col)``（那是按 UTC 切日，上海 0–8 点的数据会落到前一天）。
    """

    type = Date()
    inherit_cache = True
    name = "business_date"


@compiles(business_date, "mysql")
def _business_date_mysql(element, compiler, **kw):
    col = compiler.process(list(element.clauses)[0], **kw)
    return f"DATE(DATE_ADD({col}, INTERVAL {_BUSINESS_OFFSET_HOURS} HOUR))"


@compiles(business_date, "sqlite")
def _business_date_sqlite(element, compiler, **kw):
    col = compiler.process(list(element.clauses)[0], **kw)
    return f"DATE({col}, '+{_BUSINESS_OFFSET_HOURS} hours')"


@compiles(business_date)
def _business_date_default(element, compiler, **kw):
    col = compiler.process(list(element.clauses)[0], **kw)
    return f"CAST(({col} + INTERVAL '{_BUSINESS_OFFSET_HOURS} hours') AS DATE)"


__all__ = [
    "BUSINESS_TZ",
    "BUSINESS_TZ_NAME",
    "MYSQL_UTC_CONNECT_ARGS",
    "business_date",
    "business_date_of",
    "business_iso",
    "business_day_start_utc",
    "business_now",
    "business_today",
    "to_utc_naive",
    "utc_iso",
    "utcnow",
]
