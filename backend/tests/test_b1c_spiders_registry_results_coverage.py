"""B1c 零 HTTP 覆盖路由清剿——爬虫注册表面（定义 CRUD/文件/节点/代理）+ 结果面（11 条）

覆盖路由清单：
定义子域（/api/v1/spiders/definitions*，写操作 require_admin）：
- POST   /api/v1/spiders/definitions            手动登记（source=manual）
- PATCH  /api/v1/spiders/definitions/{name}     启停代码爬虫
- PATCH  /api/v1/spiders/definitions/{name}/meta 编辑元信息（标题/描述）
- DELETE /api/v1/spiders/definitions/{name}     删除（历史任务引用时拒绝，m1 原子条件删）
注册表只读（require_login）：
- GET    /api/v1/spiders/files                  代码爬虫文件清单（关联启停状态）
- GET    /api/v1/spiders/nodes                  Worker 节点心跳列表（Redis 数据源）
代理健康（require_operator）：
- GET    /api/v1/spiders/proxy-health           代理评分排行
结果子域（读 require_login / 删 require_admin）：
- GET    /api/v1/spiders/results                跨任务分页查询（数据中心）
- GET    /api/v1/spiders/results/{task_id}      按任务查询
- GET    /api/v1/spiders/results/{task_id}/export 导出（csv/json 流式下载）
- DELETE /api/v1/spiders/results/{result_id}    删除单条采集结果

行为契约级口径：
- 写路径副作用直接断言 DB（spider_definitions / spider_results 行级变化）
- 删除引用保护：有历史任务的定义拒绝删除且行仍在（防统计断链）
- GET /api/v1/spiders/registry 已由既有测试覆盖（字面量命中），不在本文件
"""
import asyncio
import json

import pytest
from sqlalchemy import select

import backend.services.spider_registry_service as registry_mod
from factories import build_spider_definition, build_spider_task
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_result import SpiderResult
from platform_core.queues import (
    ACTIVE_TASK_KEY,
    PROXY_SCORES_KEY,
    PROXY_STATS_KEY,
    WORKER_HEARTBEAT_PREFIX,
)
from stubs import FakeRedis

DEFS_URL = "/api/v1/spiders/definitions"


def _seed(db_session, *rows):
    async def _go():
        async with db_session() as s:
            for row in rows:
                s.add(row)
            await s.commit()

    asyncio.run(_go())


def _fetch(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return (await s.execute(stmt)).scalars().all()

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# POST /api/v1/spiders/definitions
# ---------------------------------------------------------------------------

CREATE_BODY = {"name": "b1c-spider", "title": "B1c 演示爬虫", "type": "api"}


def test_definition_create_admin_ok(db_client, admin_client, db_engine, db_session):
    resp = admin_client.post(DEFS_URL, json=CREATE_BODY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    data = body["data"]
    assert data["name"] == "b1c-spider"
    assert data["source"] == "manual"   # 手动登记来源标记
    assert data["enabled"] is True      # 新登记默认启用

    rows = _fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider"))
    assert len(rows) == 1 and rows[0].source == "manual"  # 副作用：落库


def test_definition_create_duplicate_400(db_client, admin_client, db_engine, db_session):
    _seed(db_session, build_spider_definition(name="b1c-spider", title="占位"))
    resp = admin_client.post(DEFS_URL, json=CREATE_BODY)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "BUSINESS_ERROR"
    assert "已存在" in body["message"]
    # 副作用：重名拒绝后仍只有一行
    assert len(_fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider"))) == 1


@pytest.mark.parametrize("payload,field", [
    ({"title": "t", "type": "web"}, "name"),                       # 缺 name
    ({"name": "x" * 51, "title": "t", "type": "web"}, "name"),     # 超长（max=50 界外）
    ({"name": "ok", "title": "", "type": "web"}, "title"),         # 空标题（min_length 界外）
    ({"name": "ok", "title": "t", "type": "bogus"}, "type"),       # 非法类型枚举
])
def test_definition_create_validation_422(db_client, admin_client, db_engine, db_session, payload, field):
    resp = admin_client.post(DEFS_URL, json=payload)
    assert resp.status_code == 422, resp.text
    assert field in resp.text
    assert _fetch(db_session, select(SpiderDefinition)) == []  # 校验失败零落库


def test_definition_create_anonymous_401(client):
    assert client.post(DEFS_URL, json=CREATE_BODY).status_code == 401


def test_definition_create_operator_403(operator_client):
    assert operator_client.post(DEFS_URL, json=CREATE_BODY).status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/v1/spiders/definitions/{name}（启停）
# ---------------------------------------------------------------------------

def test_definition_patch_enabled(db_client, admin_client, db_engine, db_session):
    _seed(db_session, build_spider_definition(name="b1c-spider", title="t", enabled=True))
    resp = admin_client.patch(f"{DEFS_URL}/b1c-spider", json={"enabled": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "UPDATED"
    assert body["data"]["enabled"] is False
    # 副作用：DB 启停位翻转
    rows = _fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider"))
    assert rows[0].enabled is False


def test_definition_patch_404(db_client, admin_client):
    resp = admin_client.patch(f"{DEFS_URL}/ghost", json={"enabled": False})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_definition_patch_anonymous_401(client):
    assert client.patch(f"{DEFS_URL}/b1c-spider", json={"enabled": False}).status_code == 401


def test_definition_patch_operator_403(operator_client):
    assert operator_client.patch(f"{DEFS_URL}/b1c-spider", json={"enabled": False}).status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/v1/spiders/definitions/{name}/meta（元信息）
# ---------------------------------------------------------------------------

def test_definition_patch_meta(db_client, admin_client, db_engine, db_session):
    _seed(db_session, build_spider_definition(
        name="b1c-spider", title="旧标题", description="旧描述"))
    resp = admin_client.patch(f"{DEFS_URL}/b1c-spider/meta",
                              json={"title": "新标题", "description": "新描述"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "UPDATED"
    rows = _fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider"))
    assert rows[0].title == "新标题"      # 副作用：元信息落库
    assert rows[0].description == "新描述"


def test_definition_patch_meta_empty_body_noop(db_client, admin_client, db_engine, db_session):
    """空变更集：幂等成功，值不变"""
    _seed(db_session, build_spider_definition(name="b1c-spider", title="不变标题"))
    resp = admin_client.patch(f"{DEFS_URL}/b1c-spider/meta", json={})
    assert resp.status_code == 200
    rows = _fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider"))
    assert rows[0].title == "不变标题"


def test_definition_patch_meta_404(db_client, admin_client):
    assert admin_client.patch(f"{DEFS_URL}/ghost/meta", json={"title": "x"}).status_code == 404


def test_definition_patch_meta_anonymous_401(client):
    assert client.patch(f"{DEFS_URL}/b1c-spider/meta", json={"title": "x"}).status_code == 401


def test_definition_patch_meta_operator_403(operator_client):
    assert operator_client.patch(f"{DEFS_URL}/b1c-spider/meta", json={"title": "x"}).status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/spiders/definitions/{name}
# ---------------------------------------------------------------------------

def test_definition_delete_unreferenced_ok(db_client, admin_client, db_engine, db_session):
    _seed(db_session, build_spider_definition(name="b1c-spider", title="t"))
    resp = admin_client.delete(f"{DEFS_URL}/b1c-spider")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "DELETED"
    assert body["data"] == {"name": "b1c-spider", "deleted": True}
    # 副作用：行已删除
    assert _fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider")) == []


def test_definition_delete_referenced_rejected(db_client, admin_client, db_engine, db_session):
    """有历史任务引用 → 400 拒绝，且定义行仍在（m1：防统计断链）"""
    _seed(db_session,
          build_spider_definition(name="b1c-spider", title="t"),
          build_spider_task(spider_name="b1c-spider"))
    resp = admin_client.delete(f"{DEFS_URL}/b1c-spider")
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "BUSINESS_ERROR"
    assert "历史任务" in body["message"]
    assert len(_fetch(db_session, select(SpiderDefinition).where(
        SpiderDefinition.name == "b1c-spider"))) == 1  # 拒绝路径零删除


def test_definition_delete_404(db_client, admin_client):
    assert admin_client.delete(f"{DEFS_URL}/ghost").status_code == 404


def test_definition_delete_anonymous_401(client):
    assert client.delete(f"{DEFS_URL}/b1c-spider").status_code == 401


def test_definition_delete_operator_403(operator_client):
    assert operator_client.delete(f"{DEFS_URL}/b1c-spider").status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/files（require_login）
# ---------------------------------------------------------------------------

def test_spider_files_ok(db_client, viewer_client, db_engine, db_session, tmp_path, monkeypatch):
    """文件清单：仅 *.py（排除 __init__.py），关联定义启停状态；viewer 可读"""
    spiders_dir = tmp_path / "spiders"
    spiders_dir.mkdir()
    (spiders_dir / "alpha.py").write_text("# alpha\n")
    (spiders_dir / "beta.py").write_text("# beta\n")
    (spiders_dir / "__init__.py").write_text("")
    monkeypatch.setattr(registry_mod, "_SPIDERS_DIR", str(spiders_dir))
    _seed(db_session, build_spider_definition(name="alpha", title="已登记", enabled=True))

    resp = db_client.get("/api/v1/spiders/files")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    by_name = {i["name"]: i for i in items}
    assert set(by_name) == {"alpha", "beta"}          # __init__.py 不入清单
    assert by_name["alpha"]["registered"] is True
    assert by_name["alpha"]["enabled"] is True
    assert by_name["beta"]["registered"] is False
    assert by_name["beta"]["enabled"] is None         # 未登记无启停态
    assert by_name["alpha"]["file"] == "scrapy/spiders/alpha.py"


def test_spider_files_anonymous_401(client):
    assert client.get("/api/v1/spiders/files").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/nodes（require_login；Redis 心跳数据源）
# ---------------------------------------------------------------------------

class _NodesRedis(FakeRedis):
    """FakeRedis + smembers + count 兼容 scan_iter（stubs 未收录，域内局部桩）"""

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def scan_iter(self, match=None, count=None):  # noqa: ARG002 count 仅兼容签名
        import fnmatch

        all_keys = list(self.strings) + list(self.hashes) + list(self.sets)
        for key in sorted(all_keys):
            if match is None or fnmatch.fnmatch(key, match):
                yield key


def _wire_nodes_redis(monkeypatch, redis):
    monkeypatch.setattr(registry_mod, "get_async_redis", lambda: redis)
    return redis


def test_nodes_with_heartbeat(db_client, viewer_client, db_engine, db_session, monkeypatch):
    """心跳键 → 节点在线（pid 解析 / 爬虫清单 / 无活跃任务占位）；viewer 可读"""
    redis = _wire_nodes_redis(monkeypatch, _NodesRedis())
    redis.hashes[f"{WORKER_HEARTBEAT_PREFIX}worker-1"] = {
        "pid": "4242", "spiders": "alpha,beta",
        "started_at": "2026-09-05 10:00:00", "respawn_count": "2",
    }
    redis.sets[ACTIVE_TASK_KEY.format(spider_name="alpha")] = set()  # 无活跃任务

    resp = db_client.get("/api/v1/spiders/nodes")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    node = data["items"][0]
    assert node["worker_id"] == "worker-1"
    assert node["pid"] == 4242
    assert node["online"] is True
    assert node["spiders"] == ["alpha", "beta"]
    # 无活跃任务的爬虫以 task_id=None 占位（前端渲染该爬虫空闲）
    assert node["active_tasks"] == [
        {"spider_name": "alpha", "task_id": None, "status": None},
        {"spider_name": "beta", "task_id": None, "status": None},
    ]


def test_nodes_redis_down_fail_open(db_client, viewer_client, monkeypatch):
    """Redis 故障：降级空列表（读路径 fail-open，不 5xx）"""

    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(registry_mod, "get_async_redis", _boom)
    resp = db_client.get("/api/v1/spiders/nodes")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"total": 0, "items": []}


def test_nodes_anonymous_401(client):
    assert client.get("/api/v1/spiders/nodes").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/proxy-health（require_operator）
# ---------------------------------------------------------------------------

def test_proxy_health_operator_ok(operator_client, monkeypatch):
    """评分排行：合并 scores/stats 两 hash，按评分降序"""
    import backend.services.proxy_health_service as proxy_mod

    redis = FakeRedis()
    redis.hashes[PROXY_SCORES_KEY] = {"http://p-fast": "0.9", "http://p-slow": "0.1"}
    redis.hashes[PROXY_STATS_KEY] = {
        "http://p-fast": json.dumps(
            {"success": 120, "fail": 5, "avg_latency": 1.23, "last_check": "2026-09-05"}),
    }
    monkeypatch.setattr(proxy_mod, "get_async_redis", lambda: redis)

    resp = operator_client.get("/api/v1/spiders/proxy-health")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [row["proxy"] for row in data] == ["http://p-fast", "http://p-slow"]  # 降序
    fast = data[0]
    assert fast["score"] == 0.9
    assert fast["success"] == 120
    assert fast["avg_latency"] == 1.23
    slow = data[1]
    assert slow["success"] == 0   # 无 stats 的代理计数归零


def test_proxy_health_viewer_403(viewer_client):
    """viewer 直调（require_operator 端点）→ 403"""
    assert viewer_client.get("/api/v1/spiders/proxy-health").status_code == 403


def test_proxy_health_anonymous_401(client):
    assert client.get("/api/v1/spiders/proxy-health").status_code == 401


# ---------------------------------------------------------------------------
# 结果面：种子构造（任务 + 结果行）
# ---------------------------------------------------------------------------


def _seed_results(db_session):
    """任务 1（spider-a，2 条结果）+ 任务 2（spider-b，1 条结果）"""

    async def _go():
        async with db_session() as s:
            t1 = build_spider_task(spider_name="spider-a", status="completed")
            t2 = build_spider_task(spider_name="spider-b", status="completed")
            s.add_all([t1, t2])
            await s.flush()
            s.add_all([
                SpiderResult(task_id=t1.id, spider_name="spider-a",
                             url="https://a.example.com/1", title="目标词甲", content="c1"),
                SpiderResult(task_id=t1.id, spider_name="spider-a",
                             url="https://a.example.com/2", title="乙", content="c2"),
                SpiderResult(task_id=t2.id, spider_name="spider-b",
                             url="https://b.example.com/1", title="其他", content="c3"),
            ])
            await s.commit()
            return t1.id, t2.id

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/results（跨任务查询，require_login）
# ---------------------------------------------------------------------------

def test_search_results_filter_and_pagination(db_client, viewer_client, db_engine, db_session):
    task1, _ = _seed_results(db_session)

    resp = db_client.get("/api/v1/spiders/results", params={"spider_name": "spider-a"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2
    assert {i["spider_name"] for i in data["items"]} == {"spider-a"}

    # 关键词（title/url/content 模糊）
    kw = db_client.get("/api/v1/spiders/results", params={"keyword": "目标词"})
    assert kw.json()["data"]["total"] == 1
    assert kw.json()["data"]["items"][0]["title"] == "目标词甲"

    # 分页：page_size=1 → 首页 1 条，total 仍为真实计数
    page = db_client.get("/api/v1/spiders/results",
                         params={"spider_name": "spider-a", "page": 1, "page_size": 1})
    pdata = page.json()["data"]
    assert len(pdata["items"]) == 1 and pdata["total"] == 2


def test_search_results_anonymous_401(client):
    assert client.get("/api/v1/spiders/results").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/results/{task_id}（require_login）
# ---------------------------------------------------------------------------

def test_task_results_ok(db_client, viewer_client, db_engine, db_session):
    task1, _ = _seed_results(db_session)
    resp = db_client.get(f"/api/v1/spiders/results/{task1}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2
    assert all(i["task_id"] == task1 for i in data["items"])

    # skip/limit 分页（offset 型契约：page 由 skip//limit+1 换算）
    paged = db_client.get(f"/api/v1/spiders/results/{task1}",
                          params={"skip": 1, "limit": 1})
    pdata = paged.json()["data"]
    assert len(pdata["items"]) == 1
    assert pdata["page"] == 2 and pdata["page_size"] == 1


def test_task_results_404(db_client, viewer_client, db_engine, db_session):
    _seed_results(db_session)
    resp = db_client.get("/api/v1/spiders/results/99999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_task_results_anonymous_401(client):
    assert client.get("/api/v1/spiders/results/1").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/results/{task_id}/export（require_login；流式下载）
# ---------------------------------------------------------------------------

def test_export_csv(db_client, viewer_client, db_engine, db_session):
    task1, _ = _seed_results(db_session)
    resp = db_client.get(f"/api/v1/spiders/results/{task1}/export", params={"format": "csv"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == (
        f'attachment; filename="task_{task1}_results.csv"')
    body = resp.content.decode("utf-8")
    assert "spider_name" in body           # 表头列
    assert "https://a.example.com/1" in body  # 数据行


def test_export_json(db_client, viewer_client, db_engine, db_session):
    task1, _ = _seed_results(db_session)
    resp = db_client.get(f"/api/v1/spiders/results/{task1}/export", params={"format": "json"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    rows = json.loads(resp.content.decode("utf-8"))
    assert len(rows) == 2
    assert {r["spider_name"] for r in rows} == {"spider-a"}


def test_export_unknown_task_404(db_client, viewer_client, db_engine, db_session):
    resp = db_client.get("/api/v1/spiders/results/99999999/export")
    assert resp.status_code == 404


def test_export_invalid_format_422(db_client, viewer_client, db_engine, db_session):
    """format 枚举界外（csv|json）→ 422"""
    task1, _ = _seed_results(db_session)
    resp = db_client.get(f"/api/v1/spiders/results/{task1}/export",
                         params={"format": "xml"})
    assert resp.status_code == 422


def test_export_anonymous_401(client):
    assert client.get("/api/v1/spiders/results/1/export").status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/spiders/results/{result_id}（require_admin）
# ---------------------------------------------------------------------------

def test_delete_result_admin_ok(db_client, admin_client, db_engine, db_session):
    task1, _ = _seed_results(db_session)
    rows = _fetch(db_session, select(SpiderResult).where(SpiderResult.task_id == task1))
    target = rows[0].id

    resp = admin_client.delete(f"/api/v1/spiders/results/{target}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "DELETED"
    assert body["data"] == {"id": target, "deleted": True}
    # 副作用：行已删，同任务其余结果保留
    left = _fetch(db_session, select(SpiderResult).where(SpiderResult.task_id == task1))
    assert len(left) == 1


def test_delete_result_404(db_client, admin_client):
    assert admin_client.delete("/api/v1/spiders/results/99999999").status_code == 404


def test_delete_result_anonymous_401(client):
    assert client.delete("/api/v1/spiders/results/1").status_code == 401


def test_delete_result_viewer_403(viewer_client):
    assert viewer_client.delete("/api/v1/spiders/results/1").status_code == 403
