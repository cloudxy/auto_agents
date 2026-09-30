"""平台超管迁回 platform 租户（审计 R1-3 / B1-1 / P0-11a）

Revision ID: 051
Revises: 050a
Create Date: 2026-09-28

024 只回填了 tenant_id 为 NULL 的平台超管；早于 024 已挂到 default 等业务租户的
超管行（dev 库 admin → default #1）未被迁移。超管挂在业务租户会：
- 让该租户的 admin 经成员接口触达超管（B1-1，服务层已另行封堵）；
- 在该租户被停用时连带锁死平台超管；
- 让超管出现在租户的成员列表与用量归属里。
本迁移把 is_platform_admin=1 且不在 platform 租户的行迁回 platform 租户，tenant_role 置空。

撞名：platform 租户里已有同名**存活**账号时，该超管原地不动并打印告警（不中断整条迁移链），
由 `scripts/db/platform_admin_tenant.py inventory` 列出、人工改名后 `apply --yes` 收尾。
软删的同名行不算撞名（042 / 050a 的 alive_flag 唯一键已放行）。

downgrade 为 no-op：原归属不可还原（也不应还原到有风险的状态）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# SM-EXEMPT: 纯数据迁移、无 schema 变更；downgrade 刻意不还原归属（原值不可知，且不应回到
# 超管挂业务租户的风险态），回滚到 050 照常成功——满足「可回滚」的本意（审计 10.2-G）

revision: str = "051"
down_revision: Union[str, Sequence[str], None] = "050a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 024 已保证 platform 租户存在；此处再做一次幂等补种，防止手工删除
    op.execute(
        "INSERT INTO tenants (slug, name, status, quota, created_at, updated_at) "
        "SELECT 'platform', '平台租户', 'active', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'platform')"
    )
    bind = op.get_bind()
    platform_id = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'platform'")).scalar_one()
    rows = bind.execute(sa.text(
        "SELECT u.id, u.username, u.deleted_at IS NULL AS alive, "
        "EXISTS (SELECT 1 FROM users p WHERE p.tenant_id = :p AND p.username = u.username "
        "AND p.deleted_at IS NULL AND p.id <> u.id) AS clash "
        "FROM users u WHERE u.is_platform_admin = 1 AND (u.tenant_id IS NULL OR u.tenant_id <> :p) "
        "ORDER BY u.id"
    ), {"p": platform_id}).fetchall()
    # 已软删的超管不参与唯一判重，照常迁；存活且撞名（platform 已有同名，或本批里
    # 先迁的同名超管）的留原地
    movable: list[int] = []
    claimed: set[str] = set()
    for r in rows:
        if r.alive and (r.clash or r.username in claimed):
            print(f"[051] 跳过平台超管 #{r.id} {r.username}：platform 租户已有同名存活账号，"
                  "请改名后执行 scripts/db/platform_admin_tenant.py apply --yes")
            continue
        if r.alive:
            claimed.add(r.username)
        movable.append(r.id)
    if movable:
        bind.execute(sa.text(
            "UPDATE users SET tenant_id = :p, tenant_role = NULL WHERE id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True)), {"p": platform_id, "ids": movable})


def downgrade() -> None:
    # 无 schema 变更可撤；数据归属不回滚（见文件头 SM-EXEMPT 说明）
    return None
