"""统一时间基准（审计 BUG-43 / F3 QA-6 / R3 QA-5 回归）

- 库存 UTC naive；MySQL 会话固定 +00:00
- 应用不用宿主本地时钟（datetime.now() / date.today() / utcnow() 静态扫描守门）
- 按日分桶按 Asia/Shanghai 切日
- 接口出参带 +00:00：schema 不留裸 datetime；dict 出参走 jsonable_encoder 也带偏移
- 定时计划的 cron 按业务时区解释
"""
import ast
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

from platform_core.schemas.time_types import UTCDateTime
from platform_core.timeutil import (
    MYSQL_UTC_CONNECT_ARGS,
    business_date_of,
    business_day_start_utc,
    to_utc_naive,
    utc_iso,
    utcnow,
)

REPO = Path(__file__).resolve().parents[2]


def test_utcnow_is_naive_utc():
    now = utcnow()
    assert now.tzinfo is None
    assert abs((datetime.now(timezone.utc).replace(tzinfo=None) - now).total_seconds()) < 5


def test_to_utc_naive_converts_offsets():
    shanghai = datetime(2026, 9, 28, 12, 1, tzinfo=timezone(timedelta(hours=8)))
    assert to_utc_naive(shanghai) == datetime(2026, 9, 28, 4, 1)
    assert to_utc_naive(datetime(2026, 9, 28, 4, 1)) == datetime(2026, 9, 28, 4, 1)
    assert to_utc_naive(None) is None


def test_business_day_helpers():
    # UTC 09-26 17:00 = 上海 09-27 01:00
    assert business_date_of(datetime(2026, 9, 26, 17, 0)) == date(2026, 9, 27)
    assert business_day_start_utc(date(2026, 9, 27)) == datetime(2026, 9, 26, 16, 0)
    assert utc_iso(datetime(2026, 9, 14, 1, 3, 3)) == "2026-09-14T01:03:03+00:00"


def test_utc_datetime_type_serializes_with_offset_and_normalizes_input():
    class Out(BaseModel):
        at: UTCDateTime
        maybe: UTCDateTime | None = None

    out = Out(at=datetime(2026, 9, 14, 1, 3, 3))
    assert out.model_dump(mode="json") == {"at": "2026-09-14T01:03:03+00:00", "maybe": None}
    # 前端 dayjs().toISOString() / 带 +08:00 的入参 → 库内 UTC naive
    inp = Out(at="2026-10-01T00:00:00+08:00")
    assert inp.at == datetime(2026, 9, 30, 16, 0)


def test_mysql_connect_args_pin_session_utc():
    assert MYSQL_UTC_CONNECT_ARGS["init_command"].replace(" ", "") == "SETtime_zone='+00:00'"


def test_db_manager_engines_use_utc_session(monkeypatch):
    """DBManager 建的同步 / 异步引擎都带 time_zone=+00:00 的 init_command"""
    import platform_core.db as db
    from config import settings

    captured: list[dict] = []

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *_a, **_k):
            return None

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    def fake_create_engine(url, **kw):
        captured.append({"kind": "sync", **kw})
        return _FakeEngine()

    def fake_create_async_engine(url, **kw):
        captured.append({"kind": "async", **kw})
        return object()

    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    monkeypatch.setattr(db, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(db.DBManager, "_arm_mysql_rw_on_checkout", lambda self, eng: None)
    original = settings.get("MYSQL.DEFAULT.DB_NAME")
    settings.set("MYSQL.DEFAULT.DB_NAME", "test_auto_agents_tz")
    try:
        db.DBManager()._init_mysql_all()
    finally:
        settings.set("MYSQL.DEFAULT.DB_NAME", original)
    assert {c["kind"] for c in captured} == {"sync", "async"}
    for c in captured:
        assert c.get("connect_args", {}).get("init_command") == MYSQL_UTC_CONNECT_ARGS["init_command"]


def test_jsonable_encoder_emits_offset_for_dict_responses():
    import backend.app  # noqa: F401  create_app 模块导入即装配编码器
    from fastapi.encoders import jsonable_encoder

    assert jsonable_encoder({"t": datetime(2026, 9, 14, 1, 3, 3)}) == {"t": "2026-09-14T01:03:03+00:00"}


def test_next_fire_time_interprets_cron_in_business_tz():
    from backend.services.schedule_service import next_fire_time

    # 上海 08:30（UTC 00:30）→ 下一次「每天 9 点」是上海 09:00 = UTC 01:00
    assert next_fire_time("0 9 * * *", datetime(2026, 9, 27, 0, 30)) == datetime(2026, 9, 27, 1, 0)


@pytest.mark.asyncio
async def test_daily_counts_bucket_by_shanghai_day(db_session):
    from platform_core.models.spider_result import SpiderResult
    from platform_core.models.spider_task import SpiderTask
    from backend.repositories.spider_result_repository import SpiderResultRepository
    from backend.repositories.spider_task_repository import SpiderTaskRepository

    # UTC 09-26 17:00 = 上海 09-27 01:00：原 DATE(created_at) 分到 09-26
    at = datetime(2026, 9, 26, 17, 0)
    async with db_session() as s:
        task = SpiderTask(spider_name="tz", tenant_id=1, status="completed", params="{}", created_at=at)
        s.add(task)
        await s.flush()
        s.add(SpiderResult(task_id=task.id, tenant_id=1, spider_name="tz", url="u", created_at=at))
        await s.commit()
    since = business_day_start_utc(date(2026, 9, 21))
    async with db_session() as s:
        assert await SpiderTaskRepository(s).daily_task_counts(since) == [("2026-09-27", 1)]
        assert await SpiderResultRepository(s).daily_result_counts(since) == [("2026-09-27", 1)]


# ---- 静态守门 ----------------------------------------------------------------

_LOCAL_CLOCK = re.compile(r"datetime\.now\(\s*\)|datetime\.utcnow\(|date\.today\(\)")
# 宿主本地时钟的合法用法：日志文件按本机日期滚动；timeutil 自身的文档串点名了禁用写法
_LOCAL_CLOCK_ALLOW = {"platform_core/logger.py", "platform_core/timeutil.py"}


def _py_sources():
    for root in ("backend", "platform_core", "scrapy"):
        for path in (REPO / root).rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in rel or rel.startswith("backend/alembic/") or "/.venv/" in rel:
                continue
            yield rel, path


def test_no_host_local_clock_in_app_code():
    hits = []
    for rel, path in _py_sources():
        if rel in _LOCAL_CLOCK_ALLOW:
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _LOCAL_CLOCK.search(line.split("#", 1)[0]):
                hits.append(f"{rel}:{no}: {line.strip()}")
    assert not hits, "改用 platform_core.timeutil.utcnow()/business_today()：\n" + "\n".join(hits)


def _is_bare_datetime(node: ast.AST) -> bool:
    """注解里直接出现 datetime（含 Optional[datetime] / datetime | None / List[datetime]）"""
    if isinstance(node, ast.Name):
        return node.id == "datetime"
    if isinstance(node, ast.Attribute):
        return node.attr == "datetime"
    if isinstance(node, ast.Subscript):
        return _is_bare_datetime(node.slice)
    if isinstance(node, ast.Tuple):
        return any(_is_bare_datetime(e) for e in node.elts)
    if isinstance(node, ast.BinOp):
        return _is_bare_datetime(node.left) or _is_bare_datetime(node.right)
    return False


def test_pydantic_models_do_not_use_bare_datetime():
    """出入参模型的时间字段必须用 UTCDateTime（裸 datetime 出参不带偏移，前端差 8 小时）"""
    hits = []
    for rel, path in _py_sources():
        if rel.startswith("platform_core/models/"):
            continue  # ORM 模型不是接口契约
        source = path.read_text(encoding="utf-8")
        if "BaseModel" not in source and "RequestBody" not in source and "QueryParams" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and _is_bare_datetime(stmt.annotation):
                    hits.append(f"{rel}:{stmt.lineno}: {node.name}.{ast.unparse(stmt.target)}")
    assert not hits, "改用 platform_core.schemas.time_types.UTCDateTime：\n" + "\n".join(hits)


def test_relay_usage_day_is_business_day():
    """网关 spend 行按业务日归属：月度中转配额按上海月求和，日事实按 UTC 日会跨月错位"""
    from backend.services.relay_usage import _entry_date

    # UTC 09-30 20:00 = 上海 10-01 04:00 → 计入 10 月
    assert _entry_date({"startTime": "2026-09-30T20:00:00Z"}) == date(2026, 10, 1)


def test_tenant_expiry_input_with_offset_stored_as_utc(db_client, db_engine, db_session):
    """PATCH /admin/tenants 的 expires_at 带 +08:00：落库为 UTC naive，出参带 +00:00"""
    import asyncio

    from sqlalchemy import select

    from platform_core.models.tenant import Tenant
    from test_r5_r7_fixes import _platform_admin_token

    token = _platform_admin_token(db_session)

    async def _seed():
        async with db_session() as s:
            s.add(Tenant(slug="tz-exp", name="X", status="active"))
            await s.commit()
            return (await s.execute(select(Tenant.id).where(Tenant.slug == "tz-exp"))).scalar_one()

    tid = asyncio.run(_seed())
    resp = db_client.patch(f"/api/v1/admin/tenants/{tid}", json={"expires_at": "2026-10-01T00:00:00+08:00"},
                           headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    async def _read():
        async with db_session() as s:
            return (await s.execute(select(Tenant.expires_at).where(Tenant.id == tid))).scalar_one()

    assert asyncio.run(_read()) == datetime(2026, 9, 30, 16, 0)
