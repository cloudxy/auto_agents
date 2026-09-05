"""T5-1 约束契约测试：users.tenant_id NOT NULL + (tenant_id, username) 唯一键

对应迁移 024（users 租户收紧）：模型列 nullable=False 与复合唯一约束在
create_all（SQLite/MySQL 同构）下可机械验证——NULL 租户重复名的绕过通道
（MySQL NULL≠NULL，体检发现 2）从列约束层消灭。真库 up→down→up 演练见
T5.md 证据记录（024 已在本机真库演练通过， MYSQL_FIDELITY 全链归 T9）。
"""
import pytest
from sqlalchemy.exc import IntegrityError

from platform_core.models.tenant import Tenant
from platform_core.models.user import User


def _user(username: str, tenant_id, email: str) -> User:
    return User(username=username, email=email, password_hash="x",
                role="viewer", tenant_id=tenant_id, tenant_role="viewer")


@pytest.mark.asyncio
async def test_null_tenant_user_rejected(db_session):
    """NULL tenant_id 用户行不可再产生（024 契约：NOT NULL 列约束拦截）"""
    async with db_session() as s:
        s.add(_user("null-row", None, "null-row@x.local"))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_same_tenant_duplicate_username_rejected(db_session):
    """同租户同名：唯一键拦截（含活行间冲突；软删行占位口径见 T4 套件）"""
    async with db_session() as s:
        t = Tenant(slug="ct-1", name="约束租户一")
        s.add(t)
        await s.flush()
        s.add(_user("same-name", t.id, "s1@x.local"))
        await s.flush()
        s.add(_user("same-name", t.id, "s2@x.local"))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_cross_tenant_same_username_allowed(db_session):
    """跨租户同名合法（产品既定能力：各企业各建"张三"）"""
    async with db_session() as s:
        t1 = Tenant(slug="ct-a", name="甲")
        t2 = Tenant(slug="ct-b", name="乙")
        s.add_all([t1, t2])
        await s.flush()
        s.add_all([
            _user("zhang-san", t1.id, "zs-a@x.local"),
            _user("zhang-san", t2.id, "zs-b@x.local"),
        ])
        await s.commit()  # 不抛即通过
