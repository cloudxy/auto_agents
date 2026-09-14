# ADR-0008: roles.permissions 维持 JSON 数组承载 RBAC 判定（暂不换关联表）

- 状态：已采纳（2026-09-05，工单 B3——dba P2 池 F-07 处置）
- 背景：体检（.sdlc/assessment-2026-09-05/dba/findings.md F-07）指出
  `roles.permissions` 用 JSON 数组承载 RBAC 判定数据，违背「JSON 只放不参与
  查询的弹性属性」的一般原则，建议评估 `role_permissions(role_id,
  permission_code)` 关联表。
- 关联：ADR-0005（SaaS 治理 DB 单源）；迁移 022（roles 表）/023（permissions
  注册表 + menus）；T7（API 层 ORM 直连收口后，权限读写单点为 RbacService）。
- 决策类型：保留现状（waived-with-reason），附触发重评条件。

## 语境与问题

RBAC 判定数据现状：

- `roles.permissions`：JSON 数组，元素为权限码字符串（`menu:*` / `btn:*`），
  全量提交语义（角色管理页保存时整组覆盖）。
- `permissions` 表（023）：权限码**注册表**（码值元数据），与 roles 表构成
  码值的单一事实源——RbacService 写入前用 `builtin_codes | db_permission_codes()`
  做未知码拒绝（rbac_service.py:61/106）。
- 判定路径（T7 收口后全部经 RbacService，无第二入口）：

```
auth.py get_permissions / _permissions_of
  → RbacService.get_role_permissions(role_key)      # select(Role.permissions)
  → Python 侧 set 判定（前端菜单过滤 / 按钮可见性）
```

## 决策依据（代码证据，2026-09-05 HEAD）

**换表的收益在当前访问模式下不存在**：

1. **判定路径无 SQL 层 JSON 查询**。`Role.permissions` 的全部访问点收敛在
   rbac_service.py 单文件 7 处，均为「整角色读出数组 → Python 侧 set 运算」；
   全库唯一一次 SQL 级 `JSON_CONTAINS` 在迁移 023 的种子 UPDATE（一次性）。
   关联表能提供的「按权限码反查角色」索引路径，没有调用方。
2. **基数无关性能**。roles 行数 = 角色数（内置 3 + 自建，个位数量级），
   权限码 22 个。整数组读出 + set 判定的成本在任何可预见规模下都不是瓶颈；
   换表反而把「一次主键读」变成「一次 JOIN/GROUP 聚合」。
3. **权限码集合已被结构化收口**。023 的 permissions 注册表 + RbacService
   未知码拒绝，已经解决了「码值无字典」的模型正确性问题——这是 F-07 建议
   换表的实质收益的一半，且已落地。

**换表的成本是确定的**：

1. expand-contract 双写过渡（新表回填 + roles.permissions 保留读投影 +
   收敛切换 + 删列四步），至少 3 个迁移 + 一次发布窗口。
2. RbacService 7 处访问点全路径改写；T12 刚收口的角色管理页「全量提交」
   契约要改差量（role → codes 的增删语义），前端联动回归。
3. 迁移风险与收益比：上面 1-3 证明无性能/正确性欠账，迁移是纯形状重构。

## 决策

**保留 JSON 数组**。`roles.permissions` 继续作为角色→权限码的读投影，
码值合法性由 permissions 注册表 + RbacService 校验保证（现状已闭环）。

同时固化两条边界（防漂移）：

- RBAC 判定的读写必须继续经 RbacService 单点——新增判定路径禁止绕过服务层
  直接 `select(Role.permissions)`（与 ADR-0007 事务归属、T1 直连收口同口径）。
- permissions 码值新增走 permissions 注册表（含 023 式种子或运营面），
  禁止在 roles.permissions 里出现未注册码。

## 触发重评条件（任一命中即重开换表评估）

1. **权限码细粒度扩张**：`api:*` / `res:*` 级权限码增长到 100+，或需要
   按权限维度做高频反查（如「哪些角色能调此接口」进入请求路径）。
2. **租户自定义角色**：roles 若加 tenant_id（租户自建角色），行数从个位数
   膨胀到 ∑租户×角色，整数组读的放大开始可感知。
3. **权限审计需求**：出现「权限变更历史 / 按权限反查角色的关系代数查询 /
   外部合规导出」类需求，JSON 遍历成本进入审计路径。
4. **数据库迁移**：整体迁往对 JSON 索引支持差异较大的引擎（如 PG 的 jsonb
   vs 关联表查询规划差异需重测）。

命中后的迁移草案（本票不动手，留独立票）：`role_permissions(role_id BIGINT,
permission_code VARCHAR(64), PRIMARY KEY(role_id, permission_code))`，
回填 `JSON_TABLE` 拆数组 → RbacService 判定路径切新表 → roles.permissions
降级为冗余读投影观察一个发布窗口 → 删列。三步各自可回滚。
