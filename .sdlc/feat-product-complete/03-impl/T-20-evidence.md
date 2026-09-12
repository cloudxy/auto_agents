# 实现证据 · T-20 只读成员页隐藏写控件（FR-89）

> 票：T-20（contract §11｜spec FR-89 GWT-89.1..89.3）｜角色：/frontend（sdlc-workflow:frontend）｜lane：L4/ui｜日期：2026-09-11
> 状态：**已完成**（定向 jest 10/10 绿 + admin build 绿 + 后端守卫 17/17 绿，退出码均 0）

## 1. 契约落位表（前端 UI 半）

| 契约元素 | 落位 | 文件 | 备注 |
|---|---|---|---|
| 写守卫=owner/admin（只读/经办不渲染写控件） | 页面组件 | `frontend/admin/src/pages/Members.tsx` | `useAuthStore((s) => s.user)` + `MEMBER_WRITER_ROLES=['owner','admin']` 数组判断——RelayGroups（`canIssue`）/FileTab（`META_EDITOR_ROLES`）同款写法；「经办本波不开放成员写」（票边界）→ operator 同 viewer 不渲染 |
| GWT-89.1 四控件不渲染（添加成员/角色下拉/重置密码/删除） | 工具栏 + 表格三列 | 同上 | 条件渲染（非 disabled）；角色列降级为 Tag（与 owner 行同形）、操作列只读视角显示「—」 |
| 顺带：启用/停用 Switch 同属写控件（patchMember is_active） | 状态列 | 同上 | 非写者降级为 Tag「启用/停用」（FR-89 标题「写控件」口径，页面注释 owner/admin 可操作） |
| GWT-89.2 单人企业：负责人自见 | 列表渲染 | 同上 + `Members.test.tsx` | 列表=接口返回原样渲染，无空表顶掉问题；测试钉 `mockMembers=[OWNER_ROW]` 双视角 |
| GWT-89.3 强提交拒绝 | 后端既有守卫（未改） | `backend/tests/test_saas_members.py` | `test_viewer_cannot_manage`（POST /members → 403）/ `test_viewer_cannot_delete_member`（DELETE → 403 + 名单不变）；前端职责=无入口（queryByRole 全 null + 写 API 零调用断言） |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Members.tsx` | 修改 | 229 → 237 行：useAuthStore 守卫；工具栏「添加成员」、角色列 Select、状态列 Switch、操作列 重置密码/删除 条件渲染（非写者降级为 Tag/「—」） |
| `frontend/admin/src/pages/Members.test.tsx` | 修改 | 134 → 227 行：api mock 改容器式（`mockMembers` 可切单人企业）；新增 `useAuthStore` mock（RelayGroups 同款 `mockUserState` 容器）；GWT-89.1/89.2×2/89.3 + admin 写侧不回归共 5 测 |

**与票「会改哪些文件」一致**：☑ 是（票列的正是这两个文件）。
**未触碰「不许改的文件」**：☑ 确认（`backend/services/member_service.py` 零改动——强提交拒绝守卫已存在；`Settings.tsx` 未动）。未改 GWT、未改成员 API 角色模型、无设计 token 涉及。

## 3. 关键实现决策

- **守卫口径 = owner/admin**：页头注释「租户 owner/admin 自助管理子账号」与页上 Alert「owner/admin 可操作」同口径；票边界明言「经办本波不开放成员写」→ operator 与 viewer 一并走只读分支（写法=FileTab 的角色数组 `includes`，而非逐处 `=== 'viewer'` 反向判断——新增写角色不会漏放行）。
- **「点了再失败不算藏」→ 条件渲染而非 disabled**：非写者分支不渲染 Button/Select/Switch DOM（测试用 `queryByRole(...)).not.toBeInTheDocument()` 控件级断言），后端 403 仍是最终防线。
- **降级形态而非空白**：角色列降级为与 owner 行同形的 `Tag`（role 色不变）、状态列降级为 Tag「启用/停用」、操作列显示「—」——只读视角仍是完整可读名单（GWT-89.1「能看见成员名单」）。
- **测试夹具容器化**：`mockUserState`/`mockMembers` 均容器式（babel-jest mock* 前缀豁免，工厂懒读取无 TDZ，RelayGroups.test 同款）；`beforeEach` 重置为 owner+两行默认值——既有 5 测零改动保持绿；写 API mockClear 保证 GWT-89.3「零调用」断言不受前序用例污染。
- **两字按钮 `/删\s*除/` 形态断言**（沿用仓库约定）；「添加成员」「重置密码」四字按字面断言。

## 4. 自测证据（命令与退出码原样）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Members --maxWorkers=2
PASS src/pages/Members.test.tsx (143.754 s)
  ✓ renders member list with owner row visible (420 ms)
  ✓ delete confirm copy matches backend semantics (audit preserved) (12453 ms)
  ✓ create 422 (soft-deleted name conflict): toast with actionable copy, form kept (F-02) (17395 ms)
  ✓ create 422 (email taken): mapped copy shown, form kept (F-02) (20144 ms)
  ✓ reset password failure: backend message shown, modal kept (F-02 顺带) (22764 ms)
  T-20 FR-89 只读成员页隐藏写控件
    ✓ GWT-89.1 viewer：添加成员/角色下拉/重置密码/删除不渲染，名单可见 (10621 ms)
    ✓ GWT-89.2 单人企业（接口成功）：负责人能看见自己 (6602 ms)
    ✓ GWT-89.2 只读打开同一企业：仍满足 89.1（名单可见+四控件不渲染） (10549 ms)
    ✓ GWT-89.3 viewer 无入口：写 API（POST/PATCH/DELETE）全程未被调用 (1133 ms)
    ✓ 写侧不回归：admin 视角四控件仍渲染（守卫只藏只读，不误伤管理者） (37982 ms)

Test Suites: 1 passed, 1 total
Tests:       10 passed, 10 total
Snapshots:   0 total
Time:        144.229 s
Ran all test suites matching /src\/pages\/Members/i.
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.   ← 全部为存量文件（LogDrawer/RbacManagement/SpiderLogs/auth.ts 未触碰文件）的 no-unused-vars；触碰文件零告警
File sizes after gzip:
  251.31 kB (-1 B)  build/static/js/main.a8905a74.js
exit: 0

$ cd /Users/xuyun/auto_agents && uv run pytest -x -q backend/tests/test_saas_members.py   ← GWT-89.3 后端守卫核对（票自测命令；只读引用，零改动）
.................                                                        [100%]
17 passed in 11.37s
exit: 0
```

## 5. 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-89.1 只读打开成员页：四控件不渲染 + 名单可见 | `GWT-89.1 viewer：添加成员/角色下拉/重置密码/删除不渲染，名单可见`（queryByRole×4 全 null + 名单两行可见 + Switch 顺带藏） | ✅ |
| GWT-89.2 单人企业：负责人自见；只读同企业仍满足 89.1 | `GWT-89.2 单人企业（接口成功）：负责人能看见自己`（自见 + 所有者 Tag + 添加成员仍在）；`GWT-89.2 只读打开同一企业：仍满足 89.1` | ✅ |
| GWT-89.3 只读强提交 → 拒绝、名单不变 | 前端：`GWT-89.3 viewer 无入口`（POST/PATCH/DELETE 零调用 + 按钮不存在的控件级断言）；后端：`test_viewer_cannot_manage`（403）、`test_viewer_cannot_delete_member`（403 + 断言成员仍在名单）——§4 第三条 17 passed 引用 | ✅ |
| 写侧不误伤（owner/admin 行为不回归） | `写侧不回归：admin 视角四控件仍渲染` + 既有 5 测（默认 owner 视角跑，零改动全绿） | ✅ |

### 四类易漏测试（前端票）

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端 UI 票，无事务） |
| 幂等 | ➖ N/A（无重复提交语义变更） |
| 并发写 | ➖ N/A（无并发面） |
| 外部依赖失败 | ➖ N/A（API mock 既有失败路径用例保留：422×2 + 404×1） |

## 6. F-7 行数核对

- `Members.tsx` 237 行（≤400）☑｜`Members.test.tsx` 227 行（≤400）☑

## 7. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 只读视角=**控件不渲染**（DOM 不存在），不是 disabled——验收请用元素缺席断言；操作列只读视角显示「—」、角色列显示 Tag 属预期形态；Switch（启用/停用）顺带隐藏属 FR-89「写控件」口径而非新需求 |
| `/architect` | 无契约歧义。后端 403 守卫已存在且测试齐全（17 passed），本票零后端改动 |

## 8. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（jest 10/10、build exit 0、后端守卫 17/17）
- [x] 契约落位表已核对；未改 GWT/后端守卫/成员 API 角色模型/设计 token
- [x] 无硬编码密钥/端口；.tsx ≤ 400 行（F-7）
