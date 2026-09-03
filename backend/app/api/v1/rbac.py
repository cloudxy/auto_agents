"""角色与部门管理 API（SaaS 化拓展：权限矩阵 / 组织树）

- 角色：列表 / 权限码集合编辑（DB 单源，/auth/permissions 即时生效）；
  全量权限码目录由菜单配置 + 按钮级常量派生
- 部门：租户内 CRUD（软删除）；平台超管可跨租户管理（platform 态）
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_admin
from backend.app.api._helpers import record_audit
from backend.app.responses import created, ok, updated
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException, NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.department import Department
from platform_core.models.role import Role
from platform_core.schemas.auth import RequestBody
from pydantic import Field

logger = get_logger("api.rbac")

router = APIRouter()

# 全量权限码目录（菜单项由前端 menuConfig 消费 menu:*；按钮级 btn:*）
PERMISSION_CATALOG: list[dict] = [
    {"code": "menu:dashboard", "group": "菜单", "label": "概览/仪表盘"},
    {"code": "menu:spiders", "group": "菜单", "label": "数据工厂（父组）"},
    {"code": "menu:spiders.tasks", "group": "菜单", "label": "采集任务"},
    {"code": "menu:spiders.logs", "group": "菜单", "label": "运行日志"},
    {"code": "menu:spiders.nodes", "group": "菜单", "label": "节点监控"},
    {"code": "menu:ai", "group": "菜单", "label": "AI 采集规划"},
    {"code": "menu:data", "group": "菜单", "label": "数据中心"},
    {"code": "menu:skills", "group": "菜单", "label": "能力资产"},
    {"code": "menu:members", "group": "菜单", "label": "成员管理（租户视角）"},
    {"code": "menu:usage", "group": "菜单", "label": "用量看板（租户视角）"},
    {"code": "menu:platform-ops", "group": "菜单", "label": "平台运营台"},
    {"code": "menu:logs", "group": "菜单", "label": "日志中心"},
    {"code": "menu:llm", "group": "菜单", "label": "LLM 配置"},
    {"code": "menu:newapi", "group": "菜单", "label": "中转站管控"},
    {"code": "menu:users", "group": "菜单", "label": "用户管理"},
    {"code": "menu:settings", "group": "菜单", "label": "系统设置"},
    {"code": "btn:create", "group": "按钮", "label": "创建任务/方案"},
    {"code": "btn:delete", "group": "按钮", "label": "删除操作"},
    {"code": "btn:schedule", "group": "按钮", "label": "定时调度"},
    {"code": "btn:skill:edit", "group": "按钮", "label": "技能矫正"},
    {"code": "btn:skill:admin", "group": "按钮", "label": "技能治理（扫描/评分）"},
]


class RoleUpdateRequest(RequestBody):
    """角色编辑（显示名/说明/权限码集合）"""

    name: str = Field(None, max_length=64)
    description: str = Field(None, max_length=255)
    permissions: list[str] = Field(None)


class DepartmentCreateRequest(RequestBody):
    tenant_id: int
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(None, max_length=255)


class DepartmentUpdateRequest(RequestBody):
    name: str = Field(None, min_length=1, max_length=64)
    description: str = Field(None, max_length=255)


@router.get("/roles")
async def list_roles(_user: CurrentUser = Depends(require_admin),
                     session: AsyncSession = Depends(get_async_db)):  # noqa: F811
    """角色列表 + 权限码目录（权限矩阵页一次拉齐；DB miss 回退内置映射）"""
    from backend.app.api.v1.auth import _ROLE_PERMISSIONS

    rows = (await session.execute(select(Role).order_by(Role.id))).scalars().all()
    if not rows:  # roles 表空（未跑迁移 022）：回退内置映射构造只读视图
        rows = [
            Role(role_key=k, name={"admin": "管理员", "operator": "操作员", "viewer": "只读"}.get(k, k),
                 description="内置（DB 未初始化，回退视图）", permissions=v, is_builtin=True)
            for k, v in _ROLE_PERMISSIONS.items()
        ]
    return ok(data={
        "roles": [
            {"id": getattr(r, "id", None), "role_key": r.role_key, "name": r.name,
             "description": r.description, "permissions": r.permissions or [],
             "is_builtin": bool(r.is_builtin)}
            for r in rows
        ],
        "catalog": PERMISSION_CATALOG,
    })


@router.put("/roles/{role_key}")
async def update_role(
    role_key: str,
    payload: RoleUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """编辑角色（权限分配：permissions 集合全量提交；/auth/permissions 即时生效）"""
    row = (await session.execute(select(Role).where(Role.role_key == role_key))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"角色 {role_key}")
    valid_codes = {c["code"] for c in PERMISSION_CATALOG}
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "permissions" in changes:
        unknown = set(changes["permissions"]) - valid_codes
        if unknown:
            raise ValidationException(message=f"未知权限码: {sorted(unknown)}", field="permissions")
        row.permissions = sorted(set(changes["permissions"]))
    if "name" in changes:
        row.name = changes["name"]
    if "description" in changes:
        row.description = changes["description"]
    # commit 会 expire ORM 对象：先固化返回值再提交（防同步 refresh IO）
    saved_perms = list(row.permissions or [])
    await session.commit()
    await record_audit(session, user, "role.update", f"role:{role_key}",
                       detail={"fields": sorted(changes.keys())})
    logger.info(f"角色更新 | role={role_key} perms={len(saved_perms)}")
    return updated(data={"role_key": role_key, "permissions": saved_perms})


# ---------------- 部门（租户组织树） ----------------

@router.get("/departments")
async def list_departments(
    tenant_id: int,
    _user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """部门列表（按租户；软删行排除；含成员计数）"""
    from sqlalchemy import func

    from platform_core.models.user import User

    rows = (await session.execute(
        select(Department, func.count(User.id))
        .outerjoin(User, (User.department_id == Department.id) & (User.deleted_at.is_(None)))
        .where(Department.tenant_id == tenant_id, Department.deleted_at.is_(None))
        .group_by(Department.id).order_by(Department.id)
    )).all()
    return ok(data=[
        {"id": d.id, "tenant_id": d.tenant_id, "name": d.name,
         "description": d.description, "member_count": int(cnt)}
        for d, cnt in rows
    ])


@router.post("/departments", status_code=201)
async def create_department(
    payload: DepartmentCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """创建部门（租户内名唯一）"""
    from platform_core.models.tenant import Tenant

    tenant = (await session.execute(select(Tenant).where(Tenant.id == payload.tenant_id))).scalar_one_or_none()
    if tenant is None:
        raise ValidationException(message=f"租户不存在: {payload.tenant_id}", field="tenant_id")
    dup = (await session.execute(
        select(Department).where(Department.tenant_id == payload.tenant_id,
                                 Department.name == payload.name,
                                 Department.deleted_at.is_(None))
    )).scalar_one_or_none()
    if dup is not None:
        raise BusinessException(f"部门已存在: {payload.name}")
    dept = Department(tenant_id=payload.tenant_id, name=payload.name,
                      description=payload.description)
    session.add(dept)
    await session.flush()
    dept_id, dept_name = int(dept.id), str(dept.name)
    await session.commit()
    await record_audit(session, user, "department.create", f"department#{dept_id}",
                       detail={"tenant_id": payload.tenant_id, "name": dept_name})
    return created(data={"id": dept_id, "name": dept_name})


@router.put("/departments/{department_id}")
async def update_department(
    department_id: int,
    payload: DepartmentUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """编辑部门（改名/说明；成员挂接走用户管理）"""
    dept = (await session.execute(
        select(Department).where(Department.id == department_id, Department.deleted_at.is_(None))
    )).scalar_one_or_none()
    if dept is None:
        raise NotFoundException(resource=f"部门 {department_id}")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        setattr(dept, k, v)
    await session.commit()
    await record_audit(session, user, "department.update", f"department#{department_id}", detail=changes)
    return updated(data={"id": department_id, **changes})


@router.delete("/departments/{department_id}")
async def delete_department(
    department_id: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """软删除部门（成员 department_id 置空回退未分组）"""
    from sqlalchemy import update as sa_update

    from platform_core.models.user import User

    dept = (await session.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if dept is None:
        raise NotFoundException(resource=f"部门 {department_id}")
    await session.execute(
        sa_update(User).where(User.department_id == department_id).values(department_id=None))
    from sqlalchemy import func

    dept.deleted_at = func.now()
    await session.commit()
    await record_audit(session, user, "department.delete", f"department#{department_id}")
    return ok(data={"id": department_id, "deleted": True})
