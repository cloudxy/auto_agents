# ADR-0021：后台侧栏单一真相 = `menuConfig` + 权限过滤；停用 `/auth/menus` 驱动 IA

> 状态：**accepted**（v2 修订：与 FR-95 和解，QA-02）
> 日期：2026-09-11｜决策者：architect 帽｜相关：spec v1.5 FR-82 / FR-95 / FR-96；X-IA；不重排五组；FR-91 本轮不冻结

## 背景

`AdminLayout` 优先渲染 `/auth/menus` 动态树，空/失败才回退 `frontend/admin/src/config/menuConfig.tsx`。两套树已经漂：静态树有「渠道组」「我的安装」；DB 种子（023）仍可能带 `/rbac` `/enterprise`、缺渠道组。租户公司管理员深链 `/rbac` `/enterprise` 因 `ProtectedRoute requireAdmin`（**租户** admin，不是超管）进得去。FR-82 要单一真相：找得到自己的叶，走不进组织页。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 负责人侧栏能找到渠道组与我的安装；找不到角色权限/企业管理 | GWT-82.1 |
| 权限未就绪显示「权限加载中」，不闪组织叶 | GWT-82.2 |
| 租户公司管理员直打组织页 = 页面不存在同形 | GWT-82.3 |
| 不重排五组；不把幽灵修成超管功能 | X-IA；spec §5 |
| 租户「能力市场」不得进七叶 **本轮不施工** | FR-91 移出冻结集 |

## 决策

1. **侧栏唯一输入 = `menuConfig` 经现网 `usePermission().filteredMenus`。** `AdminLayout` **停止**在 `dynamicMenus.length` 时改画 IA。`/auth/menus` 本波仍可 200（RBAC 页/旧客户端），**不得**再决定租户看见哪几片叶。
2. **幽灵路由 `/enterprise` `/rbac`：** 对租户（含公司管理员）渲染与后台 NotFound **同形**（不是「抱歉，您没有权限」）。**不**把这两页修成租户功能页。**【v2 修订，QA-02 和解】**「超管组织管理本波也不新开」按 spec v1.5 修正为：`/enterprise` **本就是既有超管页**——幽灵页问题是*租户走进去*，不是页不存在；FR-95 **增强该既有页**（改名/停用/再启用/平台租户显式化），**不新增第二处企业管理入口**（运营台既有停用/配额/续期保持，两处对同一状态同一真相）。租户侧栏与深链 404 同形语义**一字不变**（GWT-82.1…82.4 仍真，由 GWT-96.4 钉住；ADR-0022 只动挂载结构不动本句）。
3. **权限未就绪：** 保留现网「权限加载中」句；渠道组/我的安装不得因动态树 miss 永久消失（因为不再依赖动态树）。
4. **expand-contract：** 先停读（本 ADR）→ 下一特征再考虑删 `menus` 表或改成从 `menuConfig` 生成。本波 **不**删表、不改 023 种子当主路径。
5. **不代选 FR-91：** `/capabilities` 对租户仍可能是治理七叶——本 ADR 不管货架 vs 安装；只保证「我的安装」叶找得到。

## 备选与否决理由

### 备选 A：以 DB `menus` 为唯一真相，回填种子补渠道组/安装、删 rbac/enterprise

**否决理由：** 023 与 `menuConfig` 已经漂过一次。RBAC 菜单 CRUD 仍能再写下组织叶。单一真相若在可被运营改的表里，GWT-82.1 无法稳定。

### 备选 B：启动时用 `menuConfig` 覆盖写入 `menus` 表，侧栏仍读 DB

**否决理由：** 双写。本波「第二次出现再抽象」。先停读。

### 备选 C：维持双源回退（现网）

**否决理由：** FR-82 标题就是消灭双源。DB 非空时静态树上的渠道组根本不会出现——这是现网「找不到」的根因。

### 备选 D：修幽灵页给超管当系统管理

**否决理由：** spec §5 / X-IA 明文禁止。GWT-82.3 要的是租户 404 同形，不是功能页。

## 证据

```
spike：侧栏双源
问题：DB 树非空时租户能否看到 menuConfig 里的 /relay 与 /capabilities/installs
环境：读码 AdminLayout.tsx L31–47；menuConfig.tsx L47/L68；
      App.tsx L100–114 requireAdmin 包 /enterprise /rbac
结果：dynamicMenus.length>0 则完全不用 filteredMenus；
      requireAdmin = 租户公司管理员可进幽灵页
结论：停用动态树驱动；幽灵改 404 同形
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| `/auth/menus` 与侧栏短期不一致 | 文档：侧栏以 menuConfig 为准；RBAC 菜单编辑本波不驱动导航 |
| 运营不能热改菜单 | 本波本就冻结五组 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/frontend` | AdminLayout 只走 filteredMenus；深链 NotFound；Jest 82.1–82.3 |
| `/backend` | 本波可不改 `/auth/menus` 形状；不要为侧栏再加种子当完成态 |
| `/qa` | 动态树有脏数据时仍 82.1；直打无「抱歉您没有权限」 |

## 后续复审条件

若操作者要「运营可改菜单且不漂」再评估生成式同步。FR-91 关闭后再管「能力市场」落点。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-11 | proposed → accepted | 塑形第一 spawn |
| 2026-09-11 | accepted（v2 修订） | shape r1 QA-02：决策 2 与 FR-95 显式和解——/enterprise 是既有超管页，FR-95 增强它、不开第二入口；租户 404 同形语义不变；补 FR-96/ADR-0022 边界引用 |
