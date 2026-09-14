"""T-24 软删用户：可筛「已删除」+ 恢复 + 占用判定/释放 + user_restored（FR-93 / GWT-92.8）

Seam：/admin/users 列表筛选与恢复端点（db_client 平台超管 Bearer 真链路 + SQLite 真库）。

口径（contract §7.9 / db-spec §16.1）：
- 默认列表不含已删（GWT-93.2 既有保持）；status=deleted 只含已删且带标记（93.1）
- 恢复仅平台超管，租户直打 404 同形（93.6）
- 占用判定：username 同租户在册 / email 全局在册，任一冲突→中文句拒绝（93.4/93.8）
- 释放：新建查重在册行，已删行不阻塞 username（93.5）/email（93.7）
- 重复恢复 no-op、不重复事件（93.9）；恢复成功上报 user_restored（92.8）
"""
import asyncio

import pytest
from sqlalchemy import func, select

from conftest import make_platform_admin_headers, make_tenant_owner_headers

USERS_URL = "/api/v1/admin/users"
CONFLICT_MSG = "用户名或邮箱已被现有用户占用"


async def _soft_delete(db_session, user_id: int) -> None:
    """直改库造已删行（F-02 同款：deleted_at 非空 + is_active=False）"""
    from platform_core.models.user import User

    async with db_session() as s:
        row = await s.get(User, user_id)
        row.deleted_at = func.now()
        row.is_active = False
        await s.commit()


def _get(db_client, headers, status: str | None = None):
    url = USERS_URL if status is None else f"{USERS_URL}?status={status}"
    resp = db_client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _restore_events(db_session, user_id: int) -> list:
    """该用户的 user_restored 事件行"""
    from platform_core.models.product_event import ProductEvent

    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(ProductEvent).where(ProductEvent.event_name == "user_restored")
            )).scalars().all()
            return [r for r in rows if (r.props or {}).get("restored_user_id") == user_id]

    return asyncio.run(_go())


def _add_alive_user(db_session, tenant_id: int, *, username: str, email: str) -> None:
    from platform_core.models.user import User

    async def _go():
        async with db_session() as s:
            s.add(User(username=username, email=email, password_hash="x",
                       role="viewer", tenant_id=tenant_id, tenant_role="viewer"))
            await s.commit()

    asyncio.run(_go())


@pytest.fixture
def seed(db_session):
    """平台超管 Bearer + co-a 租户（act-op 在册 / gone-op 待删）"""
    state: dict = {}

    async def _do():
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User

        async with db_session() as s:
            co_a = Tenant(slug="co-a", name="甲公司")
            s.add(co_a)
            await s.flush()
            state["tenant_id"] = int(co_a.id)
            act = User(username="act-op", email="act-op@t24.local", password_hash="x",
                       role="viewer", tenant_id=co_a.id, tenant_role="viewer")
            gone = User(username="gone-op", email="gone-op@t24.local", password_hash="x",
                        role="viewer", tenant_id=co_a.id, tenant_role="viewer")
            s.add_all([act, gone])
            await s.flush()
            state["act_id"] = int(act.id)
            state["gone_id"] = int(gone.id)
            await s.commit()

    asyncio.run(_do())
    state["headers"] = make_platform_admin_headers(db_session)
    yield state


# ---------------- GWT-93.1 / 93.2：筛选与默认视图 ----------------


def test_deleted_filter_lists_only_deleted_with_marker(db_client, db_session, seed):
    """已删筛选：空态无已删行；软删后只出现已删用户且带标记（93.1）"""
    empty = _get(db_client, seed["headers"], status="deleted")
    assert empty["items"] == []  # 尚未删：已删筛选为空（边界）

    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    data = _get(db_client, seed["headers"], status="deleted")
    usernames = [u["username"] for u in data["items"]]
    assert usernames == ["gone-op"]  # 已删行出现
    assert data["items"][0]["deleted_at"] is not None  # 带已删除标记
    assert "act-op" not in usernames  # 活跃用户不出现在该筛选
    assert data["total"] == 1


def test_default_list_excludes_deleted(db_client, db_session, seed):
    """默认视图：已删用户不出现（93.2 既有行为保持）"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    data = _get(db_client, seed["headers"])
    usernames = [u["username"] for u in data["items"]]
    assert "gone-op" not in usernames
    assert "act-op" in usernames


def test_deleted_filter_rejects_unknown_status(db_client, seed):
    """筛选参数白名单：status 只认 active|deleted"""
    resp = db_client.get(f"{USERS_URL}?status=zzz", headers=seed["headers"])
    assert resp.status_code == 422


# ---------------- GWT-93.3 / 92.8：恢复成功 + 事件 ----------------


def test_restore_success_returns_to_default_list_and_emits_event(db_client, db_session, seed):
    """恢复成功：回默认列表、状态=启用、已删筛选不再出现；上报 user_restored"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))

    resp = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=seed["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["is_active"] is True and data["deleted_at"] is None

    default = _get(db_client, seed["headers"])
    assert "gone-op" in [u["username"] for u in default["items"]]  # 回默认列表
    deleted = _get(db_client, seed["headers"], status="deleted")
    assert "gone-op" not in [u["username"] for u in deleted["items"]]

    events = _restore_events(db_session, seed["gone_id"])
    assert len(events) == 1
    ev = events[0]
    assert ev.tenant_id == seed["tenant_id"]  # 该用户归属租户
    assert ev.actor_user_id is not None  # 操作超管
    assert (ev.props or {}).get("restored_user_id") == seed["gone_id"]
    assert "password" not in str(ev.props or {}).lower()  # 不含敏感字段


# ---------------- GWT-93.4 / 93.8：占用冲突拒绝 ----------------


def test_restore_conflict_by_username_keeps_both_intact(db_client, db_session, seed):
    """username 被同租户在册行占用 → 同句拒绝；双方不变（93.4）"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    _add_alive_user(db_session, seed["tenant_id"],
                    username="gone-op", email="occ-un@t24.local")

    resp = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=seed["headers"])
    assert resp.status_code == 400
    assert resp.json()["message"] == CONFLICT_MSG

    deleted = _get(db_client, seed["headers"], status="deleted")
    assert "gone-op" in [u["username"] for u in deleted["items"]]  # U 保持已删除
    assert _restore_events(db_session, seed["gone_id"]) == []  # 无事件


def test_restore_conflict_by_email(db_client, db_session, seed):
    """email 被在册行占用（全局口径）→ 同句拒绝（93.4 拆格）"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    _add_alive_user(db_session, seed["tenant_id"],
                    username="occ-em", email="gone-op@t24.local")

    resp = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=seed["headers"])
    assert resp.status_code == 400
    assert resp.json()["message"] == CONFLICT_MSG


def test_re_restore_after_release_conflicts_with_same_sentence(db_client, db_session, seed):
    """释放后被新建用户占用 → 再恢复同句拒绝（93.8）"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    # 释放：同租户用同一 username 新建成功（93.5 前置）
    created = db_client.post(USERS_URL, headers=seed["headers"], json={
        "username": "gone-op", "email": "rebuilt@t24.local", "password": "Passw0rd!",
        "role": "viewer", "tenant_id": seed["tenant_id"],
    })
    assert created.status_code == 201

    resp = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=seed["headers"])
    assert resp.status_code == 400
    assert resp.json()["message"] == CONFLICT_MSG


# ---------------- GWT-93.5 / 93.7：标识可释放 ----------------


def test_create_reuses_released_username_in_same_tenant(db_client, db_session, seed):
    """已删行不阻塞同租户新建同 username（93.5）；U 仍留在已删筛选"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    resp = db_client.post(USERS_URL, headers=seed["headers"], json={
        "username": "gone-op", "email": "fresh@t24.local", "password": "Passw0rd!",
        "role": "viewer", "tenant_id": seed["tenant_id"],
    })
    assert resp.status_code == 201, resp.text
    deleted = _get(db_client, seed["headers"], status="deleted")
    assert "gone-op" in [u["username"] for u in deleted["items"]]  # U 仍在已删筛选


def test_create_reuses_released_email_globally(db_client, db_session, seed):
    """已删行不阻塞新建同 email（93.7，全局口径）"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    resp = db_client.post(USERS_URL, headers=seed["headers"], json={
        "username": "fresh-name", "email": "gone-op@t24.local", "password": "Passw0rd!",
        "role": "viewer", "tenant_id": seed["tenant_id"],
    })
    assert resp.status_code == 201, resp.text


# ---------------- GWT-93.6：越权 404 同形 ----------------


def test_tenant_direct_restore_is_404_shape(db_client, db_session, seed):
    """租户负责人直打恢复动作 → 页面不存在同形；已删用户保持已删除"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    owner_headers, _tid = make_tenant_owner_headers(db_session, slug="co-owner")

    resp = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=owner_headers)
    assert resp.status_code == 404
    assert resp.json()["message"] == "Not Found"  # 与页面不存在同形，不是 403 信封

    deleted = _get(db_client, seed["headers"], status="deleted")
    assert "gone-op" in [u["username"] for u in deleted["items"]]


# ---------------- GWT-93.9：重复恢复 no-op ----------------


def test_repeat_restore_is_noop_without_second_event(db_client, db_session, seed):
    """重复恢复：状态保持启用、不重复上报、无新副作用（93.9）"""
    asyncio.run(_soft_delete(db_session, seed["gone_id"]))
    first = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=seed["headers"])
    assert first.status_code == 200

    again = db_client.post(f"{USERS_URL}/{seed['gone_id']}/restore", headers=seed["headers"])
    assert again.status_code == 200
    data = again.json()["data"]
    assert data["is_active"] is True and data["deleted_at"] is None

    assert len(_restore_events(db_session, seed["gone_id"])) == 1  # 不重复上报


def test_restore_missing_user_400(db_client, seed):
    """恢复不存在的用户 → 400（与 delete_user 缺行同口径）"""
    resp = db_client.post(f"{USERS_URL}/99999/restore", headers=seed["headers"])
    assert resp.status_code == 400


# ---------------- DB 兜底：并发占名竞态由唯一键拦截 ----------------


@pytest.mark.asyncio
async def test_restore_db_constraint_fallback_same_sentence(db_session, monkeypatch):
    """预检被绕过（并发窗口）→ UPDATE 撞唯一键 → 回滚 + 同句（db-spec §16.1 兜底）"""
    from unittest.mock import AsyncMock

    from platform_core.exceptions import BusinessException
    from platform_core.models.tenant import Tenant
    from platform_core.models.user import User
    from backend.services.user_service import UserService

    async with db_session() as s:
        t = Tenant(slug="t24-race", name="竞态租户")
        s.add(t)
        await s.flush()
        s.add(User(username="race-name", email="race-occ@t24.local", password_hash="x",
                   role="viewer", tenant_id=t.id, tenant_role="viewer"))
        gone = User(username="race-name", email="race-gone@t24.local", password_hash="x",
                    role="viewer", tenant_id=t.id, tenant_role="viewer",
                    deleted_at=func.now(), is_active=False)
        s.add(gone)
        await s.commit()
        gone_id = int(gone.id)

    async with db_session() as s:
        svc = UserService(s)
        # 模拟「判定通过后、UPDATE 落库前」并发新建占名：预检全放行
        monkeypatch.setattr(svc.repo, "exists_username_in_tenant", AsyncMock(return_value=False))
        monkeypatch.setattr(svc.repo, "exists_by_email", AsyncMock(return_value=False))
        with pytest.raises(BusinessException) as exc:
            await svc.restore_user(gone_id, actor_id=1)
        assert exc.value.message == CONFLICT_MSG

    async with db_session() as s:  # 回滚后双方行不变（占位者不被触碰）
        rows = (await s.execute(
            select(User).where(User.username == "race-name").order_by(User.id)
        )).scalars().all()
        alive = [r for r in rows if r.deleted_at is None]
        dead = [r for r in rows if r.deleted_at is not None]
        assert len(alive) == 1 and len(dead) == 1
        assert alive[0].email == "race-occ@t24.local"
        assert dead[0].email == "race-gone@t24.local"
