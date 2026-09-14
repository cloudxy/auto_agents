# ADR-0005: SaaS 治理 DB 单源——roles/menus/permissions/departments

日期：2026-09-03 · 状态：已实施（迁移 022/023，系统管理四模块上线）

## 决策

1. **角色权限 DB 化**（roles 表，内置三角色种子）：`/auth/permissions` 实时读 DB，
   角色管理改动刷新即生效；DB miss/异常回退 auth.py 内置映射（登录链路永不断）。
2. **菜单结构 DB 化**（menus 自引用树，22 节点种子）：`/auth/menus` 按登录用户权限
   动态下发（空分组剔除/租户视角过滤/DB 故障回退前端静态 menuConfig）——
   菜单从代码配置变为运营面数据。
3. **权限资源注册表**（permissions 表，23 码种子）：自定义权限码可注册（menu/btn/api
   三型）；角色授权校验 = DB ∪ 内置目录并集；被角色引用禁删。
4. **组织树**：tenants（公司）→ departments（部门）→ users.department_id；
   部门须属于用户所在公司（update 校验）；资源分配粒度链路挂点（中转站/虚拟 Key）。
5. **防自锁守卫**（用户管理）：不可降级/停用/删除自己、不可删最后一个平台超管。

## 后果

- 前端 usePermission 静态 menuConfig 降级为回退配置（非删除）
- 角色硬编码 _ROLE_PERMISSIONS 降级为兜底映射（非删除）
- 自定义角色/权限码/菜单进入运行态，升级脚本不得再覆盖用户改动（种子仅 INSERT IF NOT EXISTS 语义）
