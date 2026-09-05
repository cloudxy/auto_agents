"""角色与部门管理 API（SaaS 化拓展：权限矩阵 / 组织树）

- 角色：列表 / 权限码集合编辑（DB 单源，/auth/permissions 即时生效）；
  全量权限码目录由菜单配置 + 按钮级常量派生
- 部门：租户内 CRUD（软删除）；平台超管可跨租户管理（platform 态）

T1 收口（R7）：本模块原有 2 处模块级 + 16 处函数内延迟 import 直连 ORM
（延迟 import 系规避循环依赖的绕道——依赖方向本应是 Router→Service）。
数据访问与业务校验已全部下沉 backend/services/rbac_service.py（RbacService），
本层只做请求校验、审计编排与响应组装。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin
from backend.app.responses import created, ok, updated
from backend.services.rbac_service import RbacService
from platform_core.db import get_async_db
from platform_core.logger import get_logger
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

_BUILTIN_CODES = {c["code"] for c in PERMISSION_CATALOG}


def _service(session: AsyncSession = Depends(get_async_db)) -> RbacService:
    return RbacService(session)


class RoleUpdateRequest(RequestBody):
    """角色编辑（显示名/说明/权限码集合）"""

    name: str = Field(None, max_length=64)
    description: str = Field(None, max_length=255)
    permissions: list[str] = Field(None)


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
async def list_roles(
    _user: CurrentUser = Depends(require_admin),
    service: RbacService = Depends(_service),
):
    """角色列表 + 权限码目录（DB 单源：roles/permissions 表；miss 回退内置）"""
    rows = await service.list_roles()
    if not rows:
        from backend.app.api.v1.auth import _ROLE_PERMISSIONS

        rows = [
            {"id": None, "role_key": k,
             "name": {"admin": "管理员", "operator": "操作员", "viewer": "只读"}.get(k, k),
             "description": "内置（DB 未初始化，回退视图）", "permissions": v, "is_builtin": True}
            for k, v in _ROLE_PERMISSIONS.items()
        ]
    # 权限目录：permissions 表优先（运营面可维护），回退内置常量
    try:
        catalog = await service.list_permission_catalog() or PERMISSION_CATALOG
    except Exception:  # noqa: BLE001 表未建（未跑迁移 023）
        catalog = PERMISSION_CATALOG
    return ok(data={"roles": rows, "catalog": catalog})


@router.post("/roles", status_code=201)
async def create_role(
    payload: RoleCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """新建自定义角色（role_key 唯一；权限码集合可后配）"""
    result = await service.create_role(payload.model_dump(), builtin_codes=_BUILTIN_CODES)
    await session.commit()
    await record_audit(session, user, "role.create", f"role:{result['role_key']}")
    return created(data=result)


@router.delete("/roles/{role_key}")
async def delete_role(
    role_key: str,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """删除角色（内置禁删；有用户在用禁删）"""
    await service.delete_role(role_key)
    await session.commit()
    await record_audit(session, user, "role.delete", f"role:{role_key}")
    return ok(data={"role_key": role_key, "deleted": True})


@router.put("/roles/{role_key}")
async def update_role(
    role_key: str,
    payload: RoleUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """编辑角色（权限分配：permissions 集合全量提交；/auth/permissions 即时生效）"""
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    result = await service.update_role(role_key, changes, builtin_codes=_BUILTIN_CODES)
    await session.commit()
    await record_audit(session, user, "role.update", f"role:{role_key}",
                       detail={"fields": sorted(changes.keys())})
    logger.info(f"角色更新 | role={role_key} perms={len(result['permissions'])}")
    return updated(data=result)


# ---------------- 部门（租户组织树） ----------------

@router.get("/departments")
async def list_departments(
    tenant_id: int,
    _user: CurrentUser = Depends(require_admin),
    service: RbacService = Depends(_service),
):
    """部门列表（按租户；软删行排除；含成员计数）"""
    return ok(data=await service.list_departments(tenant_id))


@router.post("/departments", status_code=201)
async def create_department(
    payload: DepartmentCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """创建部门（租户内名唯一）"""
    result = await service.create_department(payload.model_dump())
    await session.commit()
    await record_audit(session, user, "department.create", f"department#{result['id']}",
                       detail={"tenant_id": result["tenant_id"], "name": result["name"]})
    return created(data={"id": result["id"], "name": result["name"]})


@router.put("/departments/{department_id}")
async def update_department(
    department_id: int,
    payload: DepartmentUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """编辑部门（改名/说明；成员挂接走用户管理）"""
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    await service.update_department(department_id, changes)
    await session.commit()
    await record_audit(session, user, "department.update", f"department#{department_id}", detail=changes)
    return updated(data={"id": department_id, **changes})


@router.delete("/departments/{department_id}")
async def delete_department(
    department_id: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """软删除部门（成员 department_id 置空回退未分组）"""
    await service.delete_department(department_id)
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


@router.get("/menus/tree")
async def menu_tree(
    _user: CurrentUser = Depends(require_admin),
    service: RbacService = Depends(_service),
):
    """菜单管理树（管理视角：含隐藏项，运营面全量编辑）"""
    rows = await service.list_menus()
    nodes = {m["id"]: {**m, "children": []} for m in rows}
    tree = []
    for m in rows:
        node = nodes[m["id"]]
        if m["parent_id"] and m["parent_id"] in nodes:
            nodes[m["parent_id"]]["children"].append(node)
        else:
            tree.append(node)
    return ok(data=tree)


@router.post("/menus", status_code=201)
async def create_menu(
    payload: MenuCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    menu_id = await service.create_menu(payload.model_dump())
    await session.commit()
    await record_audit(session, user, "menu.create", f"menu#{menu_id}", detail={"name": payload.name})
    return created(data={"id": menu_id})


@router.put("/menus/{menu_id}")
async def update_menu(
    menu_id: int,
    payload: MenuUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    await service.update_menu(menu_id, changes)
    await session.commit()
    await record_audit(session, user, "menu.update", f"menu#{menu_id}", detail=changes)
    return updated(data={"id": menu_id, **changes})


@router.delete("/menus/{menu_id}")
async def delete_menu(
    menu_id: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    """删除菜单（级联删除子菜单；物理删——菜单无审计追溯需求，变更走操作审计）"""
    await service.delete_menu(menu_id)
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
    service: RbacService = Depends(_service),
):
    """权限资源清单（DB 单源；miss 回退内置目录）"""
    try:
        rows = await service.list_permissions()
        if rows:
            return ok(data=rows)
    except Exception:  # noqa: BLE001 未跑迁移 023
        pass
    return ok(data=PERMISSION_CATALOG)


@router.post("/permissions", status_code=201)
async def create_permission(
    payload: PermissionCreateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    result = await service.create_permission(payload.model_dump())
    await session.commit()
    await record_audit(session, user, "permission.create", result["code"])
    return created(data={"id": result["id"], "code": result["code"]})


@router.put("/permissions/{permission_id}")
async def update_permission(
    permission_id: int,
    payload: PermissionUpdateRequest,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    code = await service.update_permission(permission_id, changes)
    await session.commit()
    await record_audit(session, user, "permission.update", code, detail=changes)
    return updated(data={"id": permission_id, **changes})


@router.delete("/permissions/{permission_id}")
async def delete_permission(
    permission_id: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: RbacService = Depends(_service),
):
    code = await service.delete_permission(permission_id)
    await session.commit()
    await record_audit(session, user, "permission.delete", code)
    return ok(data={"id": permission_id, "deleted": True})
