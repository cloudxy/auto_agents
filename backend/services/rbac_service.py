"""RBAC 服务（角色/部门/菜单/权限资源）——SaaS 化权限矩阵的数据与业务收口

T1 收口（R7）：backend/app/api/v1/rbac.py 与 auth.py 此前在路由层直连 ORM
（含 16 处函数内延迟 import 规避），依赖方向错误。本服务承接全部 ORM 访问，
对上只暴露 dict 快照（不泄漏 ORM 实例，不触发 commit 后过期属性的惰性加载）。

事务约定（与 MemberService/SkillService 同口径）：
- 写操作只 add/flush 并回传快照，commit 由调用方（路由层）统一执行后写审计。
"""
from typing import Optional

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import BusinessException, NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.department import Department
from platform_core.models.menu import Menu
from platform_core.models.permission import Permission
from platform_core.models.role import Role
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

logger = get_logger("service.rbac")


class RbacService:
    """RBAC 编排（session 注入；调用方保证 admin 权限）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------------- 角色 ----------------

    async def list_roles(self) -> list[dict]:
        """角色列表（按 id 升序；空表返回 []，内置回退视图由调用方拼装）"""
        logger.info("查询角色列表")
        rows = (await self.session.execute(select(Role).order_by(Role.id))).scalars().all()
        return [
            {"id": r.id, "role_key": r.role_key, "name": r.name,
             "description": r.description, "permissions": r.permissions or [],
             "is_builtin": bool(r.is_builtin)}
            for r in rows
        ]

    async def db_permission_codes(self) -> set[str]:
        """permissions 表已注册的权限码集合（表未建吞异常返回空集——未跑迁移 023 场景）"""
        logger.info("查询 DB 权限码集合")
        try:
            rows = (await self.session.execute(select(Permission.code))).scalars().all()
            return set(rows)
        except Exception as e:  # noqa: BLE001 表未建
            logger.warning(f"permissions 表读取失败（按空集处理）: {e}")
            return set()

    async def create_role(self, payload: dict, builtin_codes: set[str]) -> dict:
        """新建自定义角色（role_key 唯一；权限码须在 DB 注册表 ∪ 内置目录内）"""
        logger.info(f"创建角色 | role_key={payload.get('role_key')}")
        unknown = set(payload["permissions"] or []) - (builtin_codes | await self.db_permission_codes())
        if unknown:
            raise ValidationException(message=f"未知权限码: {sorted(unknown)}", field="permissions")
        dup = (await self.session.execute(
            select(Role).where(Role.role_key == payload["role_key"])
        )).scalar_one_or_none()
        if dup is not None:
            raise BusinessException(f"角色标识已存在: {payload['role_key']}")
        row = Role(role_key=payload["role_key"], name=payload["name"],
                   description=payload["description"],
                   permissions=sorted(set(payload["permissions"] or [])), is_builtin=False)
        self.session.add(row)
        await self.session.flush()
        return {"role_key": row.role_key, "name": row.name}

    async def delete_role(self, role_key: str) -> None:
        """删除角色（内置禁删；有用户在用禁删）；commit 由调用方执行"""
        logger.info(f"删除角色 | role_key={role_key}")
        row = (await self.session.execute(
            select(Role).where(Role.role_key == role_key)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"角色 {role_key}")
        if row.is_builtin:
            raise BusinessException(f"内置角色禁删: {role_key}（权限可调）")
        in_use = (await self.session.execute(
            select(func.count()).select_from(User).where(
                User.role == role_key, User.deleted_at.is_(None))
        )).scalar_one()
        if int(in_use) > 0:
            raise BusinessException(f"角色仍在使用中（{in_use} 个用户），先改派再删")
        await self.session.delete(row)

    async def update_role(self, role_key: str, changes: dict, builtin_codes: set[str]) -> dict:
        """编辑角色（permissions 全量提交；name/description 可选）；返回保存后快照"""
        logger.info(f"更新角色 | role_key={role_key} fields={sorted(changes.keys())}")
        row = (await self.session.execute(
            select(Role).where(Role.role_key == role_key)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"角色 {role_key}")
        if "permissions" in changes:
            unknown = set(changes["permissions"]) - (builtin_codes | await self.db_permission_codes())
            if unknown:
                raise ValidationException(message=f"未知权限码: {sorted(unknown)}", field="permissions")
            row.permissions = sorted(set(changes["permissions"]))
        if "name" in changes:
            row.name = changes["name"]
        if "description" in changes:
            row.description = changes["description"]
        await self.session.flush()
        # commit 会 expire ORM 对象：先固化返回值再由调用方提交（防同步 refresh IO）
        return {"role_key": role_key, "permissions": list(row.permissions or [])}

    async def get_role_permissions(self, role_key: str) -> Optional[list[str]]:
        """角色权限码（roles 表单源；miss 返回 None——内置映射回退由调用方决定）"""
        logger.info(f"查询角色权限 | role_key={role_key}")
        row = (await self.session.execute(
            select(Role.permissions).where(Role.role_key == role_key)
        )).scalar_one_or_none()
        return list(row) if row else None

    # ---------------- 部门（租户组织树） ----------------

    async def list_departments(self, tenant_id: int) -> list[dict]:
        """部门列表（按租户；软删行排除；含成员计数）"""
        logger.info(f"查询部门列表 | tenant={tenant_id}")
        rows = (await self.session.execute(
            select(Department, func.count(User.id))
            .outerjoin(User, (User.department_id == Department.id) & (User.deleted_at.is_(None)))
            .where(Department.tenant_id == tenant_id, Department.deleted_at.is_(None))
            .group_by(Department.id).order_by(Department.id)
        )).all()
        return [
            {"id": d.id, "tenant_id": d.tenant_id, "name": d.name,
             "description": d.description, "member_count": int(cnt)}
            for d, cnt in rows
        ]

    async def create_department(self, payload: dict) -> dict:
        """创建部门（租户须存在；租户内名唯一）"""
        logger.info(f"创建部门 | tenant={payload.get('tenant_id')} name={payload.get('name')}")
        tenant = (await self.session.execute(
            select(Tenant).where(Tenant.id == payload["tenant_id"])
        )).scalar_one_or_none()
        if tenant is None:
            raise ValidationException(message=f"租户不存在: {payload['tenant_id']}", field="tenant_id")
        dup = (await self.session.execute(
            select(Department).where(Department.tenant_id == payload["tenant_id"],
                                     Department.name == payload["name"],
                                     Department.deleted_at.is_(None))
        )).scalar_one_or_none()
        if dup is not None:
            raise BusinessException(f"部门已存在: {payload['name']}")
        dept = Department(tenant_id=payload["tenant_id"], name=payload["name"],
                          description=payload["description"])
        self.session.add(dept)
        await self.session.flush()
        return {"id": int(dept.id), "name": str(dept.name), "tenant_id": payload["tenant_id"]}

    async def update_department(self, department_id: int, changes: dict) -> None:
        """编辑部门（改名/说明）"""
        logger.info(f"更新部门 | department={department_id} fields={sorted(changes.keys())}")
        dept = (await self.session.execute(
            select(Department).where(Department.id == department_id, Department.deleted_at.is_(None))
        )).scalar_one_or_none()
        if dept is None:
            raise NotFoundException(resource=f"部门 {department_id}")
        for k, v in changes.items():
            setattr(dept, k, v)

    async def delete_department(self, department_id: int) -> None:
        """软删除部门（成员 department_id 置空回退未分组）"""
        logger.info(f"删除部门 | department={department_id}")
        dept = (await self.session.execute(
            select(Department).where(Department.id == department_id)
        )).scalar_one_or_none()
        if dept is None:
            raise NotFoundException(resource=f"部门 {department_id}")
        await self.session.execute(
            sa_update(User).where(User.department_id == department_id).values(department_id=None))
        dept.deleted_at = func.now()

    # ---------------- 菜单管理 ----------------

    async def list_menus(self) -> list[dict]:
        """菜单全量（管理视角：含隐藏项，运营面全量编辑）"""
        logger.info("查询菜单全量")
        rows = (await self.session.execute(
            select(Menu).order_by(Menu.sort_order.asc(), Menu.id.asc()))).scalars().all()
        return [self._menu_row(m) for m in rows]

    @staticmethod
    def _menu_row(m) -> dict:
        return {
            "id": m.id, "parent_id": m.parent_id, "name": m.name, "path": m.path,
            "icon": m.icon, "permission": m.permission, "sort_order": m.sort_order,
            "visible": bool(m.visible),
        }

    async def list_visible_menus(self) -> list[dict]:
        """可见菜单（动态菜单下发：visible=True，按 sort_order/id 升序）"""
        logger.info("查询可见菜单")
        rows = (await self.session.execute(
            select(Menu).where(Menu.visible == True)  # noqa: E712
            .order_by(Menu.sort_order.asc(), Menu.id.asc())
        )).scalars().all()
        return [self._menu_row(m) for m in rows]

    async def create_menu(self, payload: dict) -> int:
        """创建菜单（父菜单须存在）；返回新菜单 id"""
        logger.info(f"创建菜单 | name={payload.get('name')} parent={payload.get('parent_id')}")
        if payload["parent_id"] is not None:
            parent = (await self.session.execute(
                select(Menu).where(Menu.id == payload["parent_id"]))).scalar_one_or_none()
            if parent is None:
                raise ValidationException(
                    message=f"父菜单不存在: {payload['parent_id']}", field="parent_id")
        row = Menu(parent_id=payload["parent_id"], name=payload["name"], path=payload["path"],
                   icon=payload["icon"], permission=payload["permission"],
                   sort_order=payload["sort_order"])
        self.session.add(row)
        await self.session.flush()
        return int(row.id)

    async def update_menu(self, menu_id: int, changes: dict) -> None:
        """编辑菜单"""
        logger.info(f"更新菜单 | menu={menu_id} fields={sorted(changes.keys())}")
        row = (await self.session.execute(
            select(Menu).where(Menu.id == menu_id))).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"菜单 {menu_id}")
        for k, v in changes.items():
            setattr(row, k, v)

    async def delete_menu(self, menu_id: int) -> None:
        """删除菜单（存在子菜单禁删；物理删——变更走操作审计）"""
        logger.info(f"删除菜单 | menu={menu_id}")
        row = (await self.session.execute(
            select(Menu).where(Menu.id == menu_id))).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"菜单 {menu_id}")
        children = (await self.session.execute(
            select(func.count()).select_from(Menu).where(Menu.parent_id == menu_id))).scalar_one()
        if int(children) > 0:
            raise BusinessException(f"存在 {children} 个子菜单，先删子级")
        await self.session.delete(row)

    # ---------------- 权限资源管理 ----------------

    async def list_permissions(self) -> list[dict]:
        """权限资源清单（按 id 升序；空表由调用方回退内置目录）"""
        logger.info("查询权限资源清单")
        rows = (await self.session.execute(
            select(Permission).order_by(Permission.id))).scalars().all()
        return [
            {"id": p.id, "code": p.code, "name": p.name, "group": p.group_name,
             "ptype": p.ptype, "description": p.description}
            for p in rows
        ]

    async def list_permission_catalog(self) -> list[dict]:
        """权限码目录（/roles 的 catalog 视图：code/group/label/ptype，不含 id/description）"""
        logger.info("查询权限码目录")
        rows = (await self.session.execute(
            select(Permission).order_by(Permission.id))).scalars().all()
        return [
            {"code": p.code, "group": p.group_name, "label": p.name, "ptype": p.ptype}
            for p in rows
        ]

    async def create_permission(self, payload: dict) -> dict:
        """注册权限码（code 唯一）"""
        logger.info(f"注册权限码 | code={payload.get('code')}")
        dup = (await self.session.execute(
            select(Permission).where(Permission.code == payload["code"]))).scalar_one_or_none()
        if dup is not None:
            raise BusinessException(f"权限码已存在: {payload['code']}")
        row = Permission(code=payload["code"], name=payload["name"],
                         group_name=payload["group_name"], ptype=payload["ptype"],
                         description=payload["description"])
        self.session.add(row)
        await self.session.flush()
        return {"id": int(row.id), "code": payload["code"]}

    async def update_permission(self, permission_id: int, changes: dict) -> str:
        """编辑权限资源；返回权限码（供审计）"""
        logger.info(f"更新权限资源 | permission={permission_id} fields={sorted(changes.keys())}")
        row = (await self.session.execute(
            select(Permission).where(Permission.id == permission_id))).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"权限资源 {permission_id}")
        code = row.code
        for k, v in changes.items():
            setattr(row, k, v)
        return code

    async def delete_permission(self, permission_id: int) -> str:
        """删除权限资源（任一角色仍在引用则禁删）；返回权限码（供审计）"""
        logger.info(f"删除权限资源 | permission={permission_id}")
        row = (await self.session.execute(
            select(Permission).where(Permission.id == permission_id))).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"权限资源 {permission_id}")
        code = row.code
        # 引用检查：任一角色仍在使用则禁删
        used = (await self.session.execute(select(Role))).scalars().all()
        for r in used:
            if code in (r.permissions or []):
                raise BusinessException(f"权限码 {code} 仍被角色「{r.name}」引用，先解除再删")
        await self.session.delete(row)
        return code
