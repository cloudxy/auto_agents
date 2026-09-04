"""SaaS 化深化：菜单树 DB 化 + 权限资源注册表（menus / permissions + 种子）

Revision ID: 023
Revises: 022
Create Date: 2026-09-03

- menus 自引用树（结构与前端 menuConfig 五组一致——DB 为新真相源，前端静态配置降级为回退）
- permissions 权限码注册表（种子迁自 rbac.py PERMISSION_CATALOG）
- roles 表追加菜单管理/企业管理权限码种子（menu:enterprise / menu:rbac 已含于 menu:users 语义，独立化）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: Union[str, Sequence[str], None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 菜单种子：(parent_key, name, path, permission, sort) —— key 用于父子定位
_MENUS = [
    ("overview", "概览", None, None, 10),
    ("overview.dashboard", "仪表盘", "/dashboard", "menu:dashboard", 10),
    ("overview.usage", "用量看板", "/usage", "menu:usage", 20),
    ("factory", "数据工厂", None, None, 20),
    ("factory.tasks", "采集任务", "/spiders/tasks", "menu:spiders.tasks", 10),
    ("factory.logs", "运行日志", "/spiders/logs", "menu:spiders.logs", 20),
    ("factory.nodes", "节点监控", "/spiders/nodes", "menu:spiders.nodes", 30),
    ("factory.ai", "AI 采集规划", "/ai", "menu:ai", 40),
    ("factory.data", "数据中心", "/data", "menu:data", 50),
    ("assets", "能力资产", None, None, 30),
    ("assets.catalog", "资产目录", "/capabilities", "menu:skills", 10),
    ("ops", "运营管理", None, None, 40),
    ("ops.members", "成员管理", "/members", "menu:members", 10),
    ("ops.platform", "平台运营台", "/platform-ops", "menu:platform-ops", 20),
    ("ops.logs", "日志中心", "/logs", "menu:logs", 30),
    ("system", "系统管理", None, None, 50),
    ("system.users", "用户管理", "/users", "menu:users", 10),
    ("system.rbac", "角色权限菜单", "/rbac", "menu:rbac", 20),
    ("system.enterprise", "企业管理", "/enterprise", "menu:enterprise", 30),
    ("system.llm", "LLM 配置", "/llm", "menu:llm", 40),
    ("system.newapi", "中转站管控", "/newapi", "menu:newapi", 50),
    ("system.settings", "系统设置", "/settings", "menu:settings", 60),
]

# 权限资源种子（迁自 rbac.py PERMISSION_CATALOG + 新增 menu:rbac/menu:enterprise）
_PERMS = [
    ("menu:dashboard", "概览/仪表盘", "菜单"), ("menu:spiders", "数据工厂（父组）", "菜单"),
    ("menu:spiders.tasks", "采集任务", "菜单"), ("menu:spiders.logs", "运行日志", "菜单"),
    ("menu:spiders.nodes", "节点监控", "菜单"), ("menu:ai", "AI 采集规划", "菜单"),
    ("menu:data", "数据中心", "菜单"), ("menu:skills", "能力资产", "菜单"),
    ("menu:members", "成员管理（租户视角）", "菜单"), ("menu:usage", "用量看板（租户视角）", "菜单"),
    ("menu:platform-ops", "平台运营台", "菜单"), ("menu:logs", "日志中心", "菜单"),
    ("menu:llm", "LLM 配置", "菜单"), ("menu:newapi", "中转站管控", "菜单"),
    ("menu:users", "用户管理", "菜单"), ("menu:settings", "系统设置", "菜单"),
    ("menu:rbac", "角色权限菜单管理", "菜单"), ("menu:enterprise", "企业管理", "菜单"),
    ("btn:create", "创建任务/方案", "按钮"), ("btn:delete", "删除操作", "按钮"),
    ("btn:schedule", "定时调度", "按钮"), ("btn:skill:edit", "技能矫正", "按钮"),
    ("btn:skill:admin", "技能治理（扫描/评分）", "按钮"),
]


def upgrade() -> None:

    op.create_table(
        "menus",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=128), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("permission", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_menus_parent_id"), "menus", ["parent_id"])

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("group_name", sa.String(length=32), nullable=False, server_default="其他"),
        sa.Column("ptype", sa.String(length=16), nullable=False, server_default="btn"),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    # ── 种子（数据回填 backfill：migration data）──
    for code, name, group in _PERMS:
        ptype = "menu" if code.startswith("menu:") else "btn"
        op.execute(sa.text(
            f"INSERT INTO permissions (code, name, group_name, ptype) "
            f"VALUES ('{code}', '{name}', '{group}', '{ptype}')"
        ))

    # 菜单树播种：先顶级后子级（key 映射 id）
    inserted = {}

    def sow(key, name, path, perm, sort):
        parent_key = key.rsplit(".", 1)[0] if "." in key else None
        parent_id = inserted.get(parent_key)
        icon = {"overview": "DashboardOutlined", "factory": "BugOutlined", "assets": "AppstoreOutlined",
                "ops": "TeamOutlined", "system": "ToolOutlined"}.get(key)
        path_v = f"'{path}'" if path else "NULL"
        icon_v = f"'{icon}'" if icon else "NULL"
        perm_v = f"'{perm}'" if perm else "NULL"
        op.execute(sa.text(
            f"INSERT INTO menus (parent_id, name, path, icon, permission, sort_order) "
            f"VALUES ({parent_id or 'NULL'}, '{name}', {path_v}, {icon_v}, {perm_v}, {sort})"
        ))
        row = op.get_bind().execute(sa.text("SELECT LAST_INSERT_ID()")).scalar()
        inserted[key] = int(row)

    for item in _MENUS:
        if "." not in item[0]:
            sow(*item)
    for item in _MENUS:
        if "." in item[0]:
            sow(*item)

    # admin 角色追加两个新权限码（保持全量）
    op.execute(sa.text(
        "UPDATE roles SET permissions = JSON_ARRAY_APPEND(permissions, '$', 'menu:rbac') "
        "WHERE role_key='admin' AND NOT JSON_CONTAINS(permissions, '\"menu:rbac\"')"
    ))
    op.execute(sa.text(
        "UPDATE roles SET permissions = JSON_ARRAY_APPEND(permissions, '$', 'menu:enterprise') "
        "WHERE role_key='admin' AND NOT JSON_CONTAINS(permissions, '\"menu:enterprise\"')"
    ))


def downgrade() -> None:
    op.drop_table("menus")
    op.drop_table("permissions")
