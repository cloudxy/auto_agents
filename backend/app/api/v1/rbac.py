"""角色与部门管理 API（SaaS 化拓展：权限矩阵 / 组织树）

- 角色：列表 / 权限码集合编辑（DB 单源，/auth/permissions 即时生效）；
  全量权限码目录由菜单配置 + 按钮级常量派生
- 部门：租户内 CRUD（软删除）；平台超管可跨租户管理（platform 态）
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
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


async def _valid_permission_codes(session) -> set[str]:
    """合法权限码集合：DB 注册表（含自定义）∪ 内置目录"""
    from platform_core.models.permission import Permission

    codes = {c["code"] for c in PERMISSION_CATALOG}
    try:
        rows = (await session.execute(select(Permission.code))).scalars().all()
        codes |= set(rows)
    except Exception:  # noqa: BLE001 表未建
        pass
    return codes


class RoleCreateRequest(RequestBody):
    """新建自定义角色"""

    role_key: str = Field(..., min_length=2, max_length=32, pattern="^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(None, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class DepartmentCreateRequest(RequestBody):
    tenant_id: int
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(None, max_length=255)


class DepartmentUpdateRequest(RequestBody):
    name: str = Field(None, min_length=1, max_length=64)
    description: str = Field(None, max_length=255)


@router.get("/roles")
async def list_roles(_user: CurrentUser = Depends(require_admin),
                     session: AsyncSession = Depends(get_async_db)):
    """角色列表 + 权限码目录（DB 单源：roles/permissions 表；miss 回退内置）"""
    from platform_core.models.permission import Permission

    rows = (await session.execute(select(Role).order_by(Role.id))).scalars().all()
    if not rows:
        from backend.app.api.v1.auth import _ROLE_PERMISSIONS

        rows = [
            Role(role_key=k, name={"admin": "管理员", "operator": "操作员", "viewer": "只读"}.get(k, k),
                 description="内置（DB 未初始化，回退视图）", permissions=v, is_builtin=True)
            for k, v in _ROLE_PERMISSIONS.items()
        ]
    # 权限目录：permissions 表优先（运营面可维护），回退内置常量
    try:
        perm_rows = (await session.execute(select(Permission).order_by(Permission.id))).scalars().all()
        catalog = [
            {"code": p.code, "group": p.group_name, "label": p.name, "ptype": p.ptype}
            for p in perm_rows
        ] or PERMISSION_CATALOG
    except Exception:  # noqa: BLE001 表未建（未跑迁移 023）
        catalog = PERMISSION_CATALOG
    return ok(data={
        "roles": [
            {"id": getattr(r, "id", None), "role_key": r.role_key, "name": r.name,
             "description": r.description, "permissions": r.permissions or [],
             "is_builtin": bool(r.is_builtin)}
            for r in rows
        ],
        "catalog": catalog,
    })


@router.post("/roles", status_code=201)
async def create_role(
    payload: RoleCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """新建自定义角色（role_key 唯一；权限码集合可后配）"""
    valid_codes = await _valid_permission_codes(session)
    unknown = set(payload.permissions or []) - valid_codes
    if unknown:
        raise ValidationException(message=f"未知权限码: {sorted(unknown)}", field="permissions")
    dup = (await session.execute(select(Role).where(Role.role_key == payload.role_key))).scalar_one_or_none()
    if dup is not None:
        raise BusinessException(f"角色标识已存在: {payload.role_key}")
    row = Role(role_key=payload.role_key, name=payload.name,
               description=payload.description,
               permissions=sorted(set(payload.permissions or [])), is_builtin=False)
    session.add(row)
    await session.commit()
    await record_audit(session, user, "role.create", f"role:{row.role_key}")
    return created(data={"role_key": row.role_key, "name": row.name})


@router.delete("/roles/{role_key}")
async def delete_role(
    role_key: str,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """删除角色（内置禁删；有用户在用禁删）"""
    from platform_core.models.user import User

    row = (await session.execute(select(Role).where(Role.role_key == role_key))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"角色 {role_key}")
    if row.is_builtin:
        raise BusinessException(f"内置角色禁删: {role_key}（权限可调）")
    in_use = (await session.execute(
        select(func.count()).select_from(User).where(User.role == role_key, User.deleted_at.is_(None))
    )).scalar_one()
    if int(in_use) > 0:
        raise BusinessException(f"角色仍在使用中（{in_use} 个用户），先改派再删")
    await session.delete(row)
    await session.commit()
    await record_audit(session, user, "role.delete", f"role:{role_key}")
    return ok(data={"role_key": role_key, "deleted": True})


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
    valid_codes = await _valid_permission_codes(session)
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


# ---------------- 菜单管理（menus 树 CRUD + 动态下发） ----------------

class MenuCreateRequest(RequestBody):
    parent_id: int = Field(None, description="父菜单（NULL=顶级）")
    name: str = Field(..., min_length=1, max_length=64)
    path: str = Field(None, max_length=128)
    icon: str = Field(None, max_length=64)
    permission: str = Field(None, max_length=64)
    sort_order: int = 100


class MenuUpdateRequest(RequestBody):
    name: str = Field(None, min_length=1, max_length=64)
    path: str = Field(None, max_length=128)
    icon: str = Field(None, max_length=64)
    permission: str = Field(None, max_length=64)
    sort_order: int = None
    visible: bool = None


def _menu_row(m) -> dict:
    return {
        "id": m.id, "parent_id": m.parent_id, "name": m.name, "path": m.path,
        "icon": m.icon, "permission": m.permission, "sort_order": m.sort_order,
        "visible": bool(m.visible),
    }


@router.get("/menus/tree")
async def menu_tree(
    _user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """菜单管理树（管理视角：含隐藏项，运营面全量编辑）"""
    from platform_core.models.menu import Menu

    rows = (await session.execute(
        select(Menu).order_by(Menu.sort_order.asc(), Menu.id.asc()))).scalars().all()
    nodes = {m.id: {**_menu_row(m), "children": []} for m in rows}
    tree = []
    for m in rows:
        node = nodes[m.id]
        if m.parent_id and m.parent_id in nodes:
            nodes[m.parent_id]["children"].append(node)
        else:
            tree.append(node)
    return ok(data=tree)


@router.post("/menus", status_code=201)
async def create_menu(
    payload: MenuCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    from platform_core.models.menu import Menu

    if payload.parent_id is not None:
        parent = (await session.execute(select(Menu).where(Menu.id == payload.parent_id))).scalar_one_or_none()
        if parent is None:
            raise ValidationException(message=f"父菜单不存在: {payload.parent_id}", field="parent_id")
    row = Menu(parent_id=payload.parent_id, name=payload.name, path=payload.path,
               icon=payload.icon, permission=payload.permission, sort_order=payload.sort_order)
    session.add(row)
    await session.flush()
    menu_id = int(row.id)
    await session.commit()
    await record_audit(session, user, "menu.create", f"menu#{menu_id}", detail={"name": payload.name})
    return created(data={"id": menu_id})


@router.put("/menus/{menu_id}")
async def update_menu(
    menu_id: int,
    payload: MenuUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    from platform_core.models.menu import Menu

    row = (await session.execute(select(Menu).where(Menu.id == menu_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"菜单 {menu_id}")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        setattr(row, k, v)
    await session.commit()
    await record_audit(session, user, "menu.update", f"menu#{menu_id}", detail=changes)
    return updated(data={"id": menu_id, **changes})


@router.delete("/menus/{menu_id}")
async def delete_menu(
    menu_id: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """删除菜单（级联删除子菜单；物理删——菜单无审计追溯需求，变更走操作审计）"""
    from platform_core.models.menu import Menu

    row = (await session.execute(select(Menu).where(Menu.id == menu_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"菜单 {menu_id}")
    children = (await session.execute(
        select(func.count()).select_from(Menu).where(Menu.parent_id == menu_id))).scalar_one()
    if int(children) > 0:
        raise BusinessException(f"存在 {children} 个子菜单，先删子级")
    await session.delete(row)
    await session.commit()
    await record_audit(session, user, "menu.delete", f"menu#{menu_id}")
    return ok(data={"id": menu_id, "deleted": True})


# ---------------- 权限资源管理（permissions CRUD） ----------------

class PermissionCreateRequest(RequestBody):
    code: str = Field(..., max_length=64, pattern="^(menu|btn|api):[a-z0-9_.:-]+$")
    name: str = Field(..., min_length=1, max_length=64)
    group_name: str = Field("自定义", max_length=32)
    ptype: str = Field("btn", pattern="^(menu|btn|api)$")
    description: str = Field(None, max_length=255)


class PermissionUpdateRequest(RequestBody):
    name: str = Field(None, min_length=1, max_length=64)
    group_name: str = Field(None, max_length=32)
    description: str = Field(None, max_length=255)


@router.get("/permissions")
async def list_permissions(
    _user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """权限资源清单（DB 单源；miss 回退内置目录）"""
    from platform_core.models.permission import Permission

    try:
        rows = (await session.execute(select(Permission).order_by(Permission.id))).scalars().all()
        if rows:
            return ok(data=[
                {"id": p.id, "code": p.code, "name": p.name, "group": p.group_name,
                 "ptype": p.ptype, "description": p.description} for p in rows
            ])
    except Exception:  # noqa: BLE001 未跑迁移 023
        pass
    return ok(data=PERMISSION_CATALOG)


@router.post("/permissions", status_code=201)
async def create_permission(
    payload: PermissionCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    from platform_core.models.permission import Permission

    dup = (await session.execute(
        select(Permission).where(Permission.code == payload.code))).scalar_one_or_none()
    if dup is not None:
        raise BusinessException(f"权限码已存在: {payload.code}")
    row = Permission(code=payload.code, name=payload.name, group_name=payload.group_name,
                     ptype=payload.ptype, description=payload.description)
    session.add(row)
    await session.flush()
    pid = int(row.id)
    await session.commit()
    await record_audit(session, user, "permission.create", payload.code)
    return created(data={"id": pid, "code": payload.code})


@router.put("/permissions/{permission_id}")
async def update_permission(
    permission_id: int,
    payload: PermissionUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    from platform_core.models.permission import Permission

    row = (await session.execute(
        select(Permission).where(Permission.id == permission_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"权限资源 {permission_id}")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        setattr(row, k, v)
    await session.commit()
    await record_audit(session, user, "permission.update", row.code, detail=changes)
    return updated(data={"id": permission_id, **changes})


@router.delete("/permissions/{permission_id}")
async def delete_permission(
    permission_id: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    from platform_core.models.permission import Permission

    row = (await session.execute(
        select(Permission).where(Permission.id == permission_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"权限资源 {permission_id}")
    # 引用检查：任一角色仍在使用则禁删
    used = (await session.execute(select(Role))).scalars().all()
    for r in used:
        if row.code in (r.permissions or []):
            raise BusinessException(f"权限码 {row.code} 仍被角色「{r.name}」引用，先解除再删")
    await session.delete(row)
    await session.commit()
    await record_audit(session, user, "permission.delete", row.code)
    return ok(data={"id": permission_id, "deleted": True})
