# 实现证据 · T-06 出站拉数钥匙页（FR-51）

> 票：T-06（contract §7.3 / tickets 表）｜FR 锚点：FR-51（GWT-51.1 UI / 51.2 / 51.5 / 51.8 / 51.9 呈现面）｜角色：/frontend｜日期：2026-09-12
> 骨架先行（防饿死）；自测证据随施工回填。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 页面/路由 `/outbound-keys` | 路由 + 页 | `frontend/admin/src/App.tsx` + `src/pages/OutboundKeys.tsx` | 数据工厂组内加叶、紧挨数据中心（sitemap §2） |
| 菜单叶（tenantOnly，五组不重排） | 菜单 | `frontend/admin/src/config/menuConfig.tsx` | 加一行；可见性矩阵：租户三角色都显示、超管无企业隐藏 |
| GET/POST/DELETE 服务层 | Service | `frontend/admin/src/services/outboundKeys.ts` | 既有 unwrap 模式；空态句走信封 message 单源（T-04 §8） |
| GWT-51.2 空态句 | 页（渲染信封 message） | `OutboundKeys.tsx` | 冻结句「还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。」 |
| GWT-51.1/51.8 明文只一次 | 页（签发结果弹窗） | `OutboundKeys.tsx` | 明文只在签发响应弹窗出现一次+复制；列表只有前缀/状态 |
| GWT-51.5/51.9 角色显隐（控件隐藏单支） | 页 | `OutboundKeys.tsx` | canManage=owner/admin/operator（与后端 `_ISSUER_ROLES` 同口径）；只读无签发/吊销控件+「请联系企业管理员」 |
| 超管无企业 | 页 | `TenantSpaceOnly`（既有组件） | 「出站拉数属于企业空间」，不是空表 |
| 吊销确认（不可逆提示中文） | 页（确认弹窗） | `OutboundKeys.tsx` | 票面要求确认弹窗（edge-states「不要求」=不强求，非禁止） |
| 失败句 FR-84 族 | 页 | `OutboundKeys.tsx` | 列表失败=失败句+重试（≠空表）；签发失败内联弹窗不关；吊销失败内联 |

**分层依赖核对**：☑ UI 只经 services 调 API（不裸 axios）☑ 未定义 token/未改 GWT/未动 RelayGroups

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/OutboundKeys.tsx` | 新增 | 页面（≤400 行） |
| `frontend/admin/src/pages/OutboundKeys.test.tsx` | 新增 | 组件测试：空态/明文一次/角色显隐/吊销确认/失败句/企业空间 |
| `frontend/admin/src/services/outboundKeys.ts` | 新增 | 服务层（列表+签发+吊销，信封 message 透传） |
| `frontend/admin/src/config/menuConfig.tsx` | 修改 | 数据工厂组加叶（一行） |
| `frontend/admin/src/App.tsx` | 修改 | lazy + 路由一行 |

**与票里「会改哪些文件」一致**：☑ 是（票面只钉 menuConfig 加一行 + 新页 + services 新建；路由注册是 lazy 页落地的必要一行）

**未触碰「不许改的文件」**：☑ 确认（RelayGroups.tsx / relay.ts / 渠道组页零改动；backend / shared 零改动）

## 3. 关键实现决策（UI）

- **菜单不加权限码（tenantOnly 单控）**：sitemap 可见性矩阵钉「经办/只读/admin 都显示、超管无企业隐藏」——`tenantOnly` 一层即精确表达；若新增 `menu:outbound-keys` 码，须动 auth.py `_ROLE_PERMISSIONS` + roles 表迁移（032/040 先例），否则已部署 DB 角色无此码 → 叶被滤光 → 违反「出站拉数钥匙不得永久消失」（edge-states）。票面也只要求「menuConfig.tsx 加一行」。写权限在页内按角色藏控件，后端 `OUTBOUND_KEY_ROLE_NOT_ALLOWED` 是最终防线。
- **空态句单一来源**：GET 列表 200 且 data=[] 时信封 message 即冻结句（T-04 已落）；页直接渲染，本地字面仅作缺省兜底。
- **明文一次**：签发成功 → 结果弹窗 `data-testid="issued-plaintext"` + copyable（toast「已复制出站拉数钥匙」）+ 警示「明文仅显示一次，请妥善保存。关闭后无法再查看明文。」；关闭即从内存清除（invalidate 后列表只有 key_prefix+status）。
- **产品名纪律（X-KEY）**：页 h1/卡片/按钮全部「出站拉数钥匙」；「渠道组令牌」四字只出现在互斥说明句一处。

## 4. 自测证据

> TDD（companion tdd）：先测试红轮（模块未建即红）、后实现绿轮，两轮输出都保留。

```
$ cd frontend/admin && CI=true npx jest src/pages/OutboundKeys --maxWorkers=2   # 红轮（先写测试）
Test suite failed to run
Cannot find module '../services/outboundKeys' from 'src/pages/OutboundKeys.test.tsx'
Test Suites: 1 failed, 1 total
Tests:       0 total
exit: 1

$ cd frontend/admin && CI=true npx jest src/pages/OutboundKeys --maxWorkers=2   # 绿轮（实现后）
PASS src/pages/OutboundKeys.test.tsx
  ✓ gwt_51_2: empty sentence from envelope with issue entry for entitled role, not a relay page (1046 ms)
  ✓ gwt_51_5_51_9: viewer sees list with no issue/revoke controls (591 ms)
  ✓ gwt_51_1_51_8: issue shows plaintext once, revisit shows prefix and status only (22167 ms)
  ✓ revoke confirm modal shows irreversible copy, then key becomes revoked (14772 ms)
  ✓ gwt_84: load failure shows retry sentence, not an empty table (1765 ms)
  ✓ issue failure stays inline, modal open, no fake success plaintext (8771 ms)
  ✓ issue offline shows offline sentence and no plaintext (8653 ms)
  ✓ revoke failure stays inline in modal: key still usable (14833 ms)
  ✓ platform admin without tenant sees tenant-space note and sends no list request (9 ms)
Tests: 9 passed, 9 total
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（警告均为存量文件：LogDrawer.tsx 未用 import、RbacManagement.tsx；本票文件零警告）
File sizes after gzip: …（build/static/js 按 chunk 分包正常输出）
exit: 0

$ bash /Users/xuyun/auto_agents/tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0

$ cd frontend/admin && CI=true npx jest --maxWorkers=2   # 回归（动了共享 menuConfig/App，全量跑）
Test Suites: 35 passed, 35 total
Tests:       221 passed, 221 total
exit: 0
```

绿轮途中两处测试侧修正（非产品码缺陷）：① antd v6 两字按钮自动插空格（可访问名「吊 销」）→ 断言改 `/吊\s*销/`（票面 `/签\s*发/` 形态即为此）；② react-query v5 mutationFn 第二参带 context → 断言 `toHaveBeenCalledWith(7, expect.anything())`。

### 验收项逐条对应

| GWT（呈现面） | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-51.2 空态句+有权签发入口、非渠道组页冒充 | `gwt_51_2: empty sentence from envelope with issue entry for entitled role, not a relay page` | ✅ |
| GWT-51.5/51.9 只读：无控件+「请联系企业管理员」，列表可见 | `gwt_51_5_51_9: viewer sees list with note, no issue/revoke controls` | ✅ |
| GWT-51.1 签发明文一次+可复制+警示 / GWT-51.8 再进页只见前缀+状态 | `gwt_51_1_51_8: issue shows plaintext once, revisit shows prefix and status only` | ✅ |
| 吊销确认弹窗（不可逆提示）→ 已吊销 | `revoke confirm modal shows irreversible copy, then key becomes revoked` | ✅ |
| FR-84 族列表失败≠空表 | `gwt_84: load failure shows retry sentence, not an empty table` | ✅ |
| 签发失败内联、弹窗不关、无假成功 | `issue failure stays inline, modal open, no fake success plaintext` | ✅ |
| 离线签发：无明文、弹窗不关 | `issue offline shows offline sentence and no plaintext` | ✅ |
| 吊销失败内联「钥匙仍可使用」 | `revoke failure stays inline in modal: key still usable` | ✅ |
| 超管无企业=企业空间句、不发空表请求 | `platform admin without tenant sees tenant-space note and sends no list request` | ✅ |

### 四类易漏测试（UI 口径）

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端票，无多步写） |
| 幂等 | ➖ N/A（签发每次=新钥匙行，后端 T-04 已测） |
| 并发写 | ➖ N/A（无前端并发写路径） |
| 外部依赖失败 | `issue failure / issue offline / revoke failure / gwt_84` 四例 | ✅ |

## 5. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 服务层全 mock（信封语义）；真库联调时重验角色拒绝码 `OUTBOUND_KEY_ROLE_NOT_ALLOWED` 与企业空间 403 语义；菜单叶无权限码（tenantOnly 单控）需在侧栏可见性一并验 |
| `/architect` | 无契约歧义；GWT-51.3/4/6/7/10（拉数执法）归 T-05 后端，本票只做呈现面 |

## 6. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 定向 jest 绿（9/9 exit 0）+ admin build 绿（exit 0）+ 全量回归绿（221/221 exit 0）+ frontend.sh 门禁绿（exit 0）
- [x] .tsx ≤400 行（OutboundKeys.tsx 212 行）；无硬编码色值/裸 setInterval；读模型走 react-query
- [x] 未改 GWT/token/schema；未动 RelayGroups 与 backend/shared
- [x] 产品名纪律：除互斥说明句（MUTEX_NOTE 一处）外全页无「渠道组令牌」字样（测试断言 `还没有令牌` 不在页上）
- [x] 发现的上游问题已回报（见 §5；无阻塞项）
