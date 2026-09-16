"""T-14 / FR-08：治理埋点收口——四事件字段逐项对 GWT-08.1–08.4。

口径：
- 事件必须能从 `/api/v1/product-events` 检索到（product_events 基建，AD-9），
  不是只写日志；
- props 字段逐项断言（字段名即契约，前端/看板按名取数）；
- 每个事件同时有同名 `logger.info` 结构化日志行（R10 + NFR-09 可检索）——
  用 caplog 抓 `market_events.emit_*` 行，避免只断言 DB 漏掉日志面。
"""
from __future__ import annotations

import json

import pytest

from backend.tests.fr33_support import fr33_asset, seed_rows
from conftest import make_platform_admin_headers

EVENTS = "/api/v1/product-events"
PUBLIC = "/api/v1/public/capabilities"
SYNC = "/api/v1/capabilities/sync-agents-hub"
TREE_CONFIRM = "/api/v1/capabilities/import/tree/confirm"

SKILL_MD = "---\nname: {name}\ndescription: {name} 的说明\n---\n\n正文\n"


class _RateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    fake = _RateRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


@pytest.fixture
def agents_root(tmp_path):
    """同步/导入都要落到临时根——绝不碰仓库真 .agents。"""
    from config import settings

    root = tmp_path / "hub" / ".agents"
    (root / "skills").mkdir(parents=True)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(root))
    yield root
    settings.set("SKILLS.AGENTS_ROOT", original)


@pytest.fixture
def loguru_sink():
    """把 loguru 记录接到 std logging，便于断言结构化日志行。"""
    from platform_core.logger import logger as loguru_logger

    lines: list[str] = []
    sink_id = loguru_logger.add(lines.append, level="INFO")
    yield lines
    loguru_logger.remove(sink_id)


def _rows(client, headers, name: str) -> list[dict]:
    resp = client.get(EVENTS, headers=headers, params={"event_name": name})
    assert resp.status_code == 200, resp.text
    return [r for r in resp.json()["data"]["items"] if r["event_name"] == name]


def _parts(mapping: dict[str, str]):
    return [("files", (rel, body.encode("utf-8"))) for rel, body in mapping.items()]


# ---------- GWT-08.3 sync_completed / sync_failed ----------

def test_gwt_08_3_sync_completed_fields(
    db_client, platform_admin_client, db_session, agents_root, loguru_sink,
):
    (agents_root / "skills" / "ev-one").mkdir(parents=True)
    (agents_root / "skills" / "ev-one" / "SKILL.md").write_text(
        SKILL_MD.format(name="ev-one"), encoding="utf-8",
    )
    assert platform_admin_client.post(SYNC).status_code == 200
    admin = make_platform_admin_headers(db_session)
    rows = _rows(db_client, admin, "sync_completed")
    assert rows, "sync_completed 未进 product_events"
    props = rows[0].get("props") or {}
    assert props.get("actor") == "manual"            # manual|startup
    for key in ("added", "updated", "unchanged"):
        assert key in props, f"sync_completed 缺字段 {key}"
    assert props["added"] >= 1
    assert any("emit_sync_completed" in ln for ln in loguru_sink)


def test_gwt_08_3_sync_failed_carries_error_type(
    db_client, platform_admin_client, db_session, agents_root, monkeypatch, loguru_sink,
):
    import backend.services.power_market.agents_hub as hub

    def _boom(_root):
        raise RuntimeError("磁盘不可读")

    monkeypatch.setattr(hub, "collect_agents_hub", _boom)
    # TestClient 默认 raise_server_exceptions=True：未处理异常原样冒泡到调用方，
    # 这正是「按原异常上抛」的契约（统一异常处理器在真实部署出 500）。
    with pytest.raises(RuntimeError, match="磁盘不可读"):
        platform_admin_client.post(SYNC)
    admin = make_platform_admin_headers(db_session)
    rows = _rows(db_client, admin, "sync_failed")
    assert rows, "sync_failed 未进 product_events"
    assert (rows[0].get("props") or {}).get("error_type") == "RuntimeError"
    assert any("emit_sync_failed" in ln for ln in loguru_sink)


# ---------- GWT-08.1 import_completed ----------

def test_gwt_08_1_import_completed_fields(
    db_client, platform_admin_client, db_session, agents_root, loguru_sink,
):
    files = {
        "up/ev-a/SKILL.md": SKILL_MD.format(name="ev-a"),
        "up/ev-b/SKILL.md": SKILL_MD.format(name="ev-b"),
        "up/ev-a/junk.exe": "MZ",
    }
    got = platform_admin_client.post(TREE_CONFIRM, files=_parts(files))
    assert got.status_code == 200, got.text
    # QA-10：contract §4 #4 要求响应带 batch_id（回执号不入库，只是关联令牌）
    resp_batch_id = got.json()["data"].get("batch_id")
    assert resp_batch_id, "confirm 响应缺 batch_id"
    admin = make_platform_admin_headers(db_session)
    rows = _rows(db_client, admin, "import_completed")
    assert rows, "import_completed 未进 product_events"
    props = rows[0].get("props") or {}
    for key in ("actor_role", "source", "files",
                "assets_created", "assets_updated", "assets_skipped", "batch_id"):
        assert key in props, f"import_completed 缺字段 {key}"
    assert props["source"] == "directory"
    assert props["files"] == len(files)
    assert props["assets_created"] == 2
    assert props["assets_skipped"] == 1      # 非白名单 .exe 进跳过清单
    assert props["batch_id"] == resp_batch_id  # 事件里的 batch_id 与响应一致，能对上号
    assert any("emit_import_completed" in ln for ln in loguru_sink)


# ---------- GWT-08.2 import_failed ----------

def test_gwt_08_2_import_failed_carries_error_type(
    db_client, platform_admin_client, db_session, agents_root, loguru_sink,
):
    got = platform_admin_client.post(
        TREE_CONFIRM, files=_parts({"up/notes/README.md": "# 无可判型资产\n"}),
    )
    assert got.status_code == 422, got.text
    admin = make_platform_admin_headers(db_session)
    rows = _rows(db_client, admin, "import_failed")
    assert rows, "import_failed 未进 product_events"
    props = rows[0].get("props") or {}
    assert props.get("actor_role")
    assert props.get("error_type") == "ValidationException"
    assert any("emit_import_failed" in ln for ln in loguru_sink)


def test_qa7_import_failed_survives_dirty_session_rollback(
    db_client, platform_admin_client, db_session, agents_root, monkeypatch,
):
    """QA-7 回归：confirm_tree_import 在会话已经写脏（至少一个 item 真实
    upsert 成功）之后再失败——之前的代码在 capabilities_gov 的 except 里
    直接拿脏会话发 emit_import_failed，SQLite 单写库下独立会话撞写锁、
    250ms 认输的兜底 add+flush 落在已失败事务上抛 PendingRollbackError，
    被外层宽 except 吞掉、事件永久丢失。修复后 except 先 rollback 再发事件，
    这里必须仍能查到 import_failed。
    """
    import backend.services.power_market.hub_import as hub_import_mod
    from platform_core.exceptions import BusinessException
    from platform_core.models.capability import CapabilityAsset

    async def _dirty_then_raise(session, parts, *, agents_root):
        # 模拟"部分 item 真实成功"：直接写脏当前主会话（与线上收尾 flush
        # 抛错前、已有若干 upsert 成功落在同一事务里的状态等价）
        session.add(CapabilityAsset(
            asset_type="skill", name="qa7-dirty-row", category="cat",
            status="stable", listing_state="unlisted", license="MIT",
            source_type="self_built", sync_state="ok",
        ))
        await session.flush()
        raise BusinessException(message="qa7 boom：模拟收尾 flush 在脏会话上失败")

    monkeypatch.setattr(hub_import_mod, "confirm_tree_import", _dirty_then_raise)

    got = platform_admin_client.post(
        TREE_CONFIRM, files=_parts({"up/qa7-skill/SKILL.md": SKILL_MD.format(name="qa7-skill")}),
    )
    assert got.status_code >= 400

    admin = make_platform_admin_headers(db_session)
    rows = _rows(db_client, admin, "import_failed")
    assert rows, "import_failed 未进 product_events（QA-7：脏会话回滚缺失会导致这里丢事件）"


# ---------- GWT-08.4 detail_opened ----------

def test_gwt_08_4_detail_opened_on_normal_and_preview(
    db_client, db_session, loguru_sink,
):
    admin = make_platform_admin_headers(db_session)
    seed_rows(db_session, [fr33_asset(name="ev-detail")])

    assert db_client.get(f"{PUBLIC}/skill/ev-detail").status_code == 200
    rows = _rows(db_client, admin, "detail_opened")
    assert rows, "正式通道未发 detail_opened"
    props = rows[0].get("props") or {}
    for key in ("actor_role", "asset_type", "asset_name"):
        assert key in props, f"detail_opened 缺字段 {key}"
    assert props["asset_type"] == "skill"
    assert props["asset_name"] == "ev-detail"

    before = len(rows)
    assert db_client.get(
        f"{PUBLIC}/skill/ev-detail", params={"preview": "true"}, headers=admin,
    ).status_code == 200
    after = _rows(db_client, admin, "detail_opened")
    assert len(after) == before + 1          # 预览通道同样发（AD-5e）
    assert any(
        (r.get("props") or {}).get("actor_role") == "platform_admin" for r in after
    )
    assert any("emit_detail_opened" in ln for ln in loguru_sink)


def test_detail_viewed_event_still_emitted_alongside(db_client, db_session):
    """既有 MARKET_DETAIL_VIEWED 不得被 detail_opened 顶替（AD-5e 明示并存）。"""
    admin = make_platform_admin_headers(db_session)
    seed_rows(db_session, [fr33_asset(name="ev-both")])
    assert db_client.get(f"{PUBLIC}/skill/ev-both").status_code == 200
    assert _rows(db_client, admin, "market_detail_viewed")


def test_event_props_are_json_serializable(db_client, db_session, agents_root):
    """看板直接吃 props——不得混入不可序列化对象。"""
    admin = make_platform_admin_headers(db_session)
    seed_rows(db_session, [fr33_asset(name="ev-json")])
    db_client.get(f"{PUBLIC}/skill/ev-json")
    for row in _rows(db_client, admin, "detail_opened"):
        json.dumps(row.get("props") or {}, ensure_ascii=False)

