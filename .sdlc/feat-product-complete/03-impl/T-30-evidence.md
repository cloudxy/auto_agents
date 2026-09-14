# 实现证据 · T-30 LLM「激活」→「默认」文案与互斥呈现

> 票：contract §11 T-30（Wave A）｜FR 锚点：FR-97（GWT-97.1…97.4）｜角色：frontend admin｜日期：2026-09-11
> 口径：SHAPE-QA-03——经办既有供应商行 CRUD 写权**保持**；只有「设为默认」收权到负责人/公司管理员（GWT-97.1/97.2 主语）。后端 `is_active` 机制与 activate/deactivate 端点**不动**；纯前端文案/交互。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 动作用词「默认 / 设为默认」，全页无「激活」（GWT-97.1） | 页面 | `frontend/admin/src/pages/LlmProviders.tsx` | 列头「默认」/动作「设为默认」「取消默认」；`is_active` 内部字段名保留（edge-states 允许） |
| 说明句「未指定模型时，默认使用该模型，可按需更换。」（GWT-97.1 钉句） | 页面 | 同上 | 表格上方固定 Text（始终可见；测试断言原句在场） |
| 切换确认弹窗钉句「将“{B}”设为默认？…“{A}”不再默认。」+「设置中…」（GWT-97.2） | 页面 | 同上 | Modal：已有默认 A 时带后半句，无默认时只前半句（派生自钉句） |
| 互斥呈现：B 带「默认」、A 标记消失（GWT-97.2） | 页面 | 同上 | 后端互斥返回刷新后的行；前端只呈现（成功 toast「已将“{B}”设为默认。」） |
| 未设默认提示「还没有默认供应商。未指定模型的请求将使用平台公共模型。」（非横幅） | 页面 | 同上 | 表格上方一行 Text（黄 warning 色），替换旧黄色 Alert「尚未激活任何 LLM 供应商」 |
| 顶部横幅「当前激活供应商：X（model）」→「当前默认供应商：X（model）」 | 页面 | 同上 | 按票面只改文案；横幅**移除归 T-34**（packet forbidden 钉） |
| 筛选「全部激活位/已激活/未激活」→「全部/已设默认/未设默认」 | 页面 | 同上 | value 键 all/active/inactive 不变（代码标识符） |
| 默认模型金色 Tag + 说明「未指定模型时使用」 | 页面 | 同上 | 模型列金色 Tag 包 Tooltip |
| 「设为默认」失败内联「设置默认失败。{原因或检查网络后重试}。原默认保持不变。」弹窗不关 | 页面 | 同上 | Modal 内 Text(danger)，不关窗 |
| 离线「网络不可用，默认没有更改。」弹窗不关 | 页面 | 同上 | `navigator.onLine` 判定（RelayGroups 同法） |
| 空态「还没有模型供应商。」+ 有权者「添加供应商」（GWT-97.3 钉句） | 页面 | 同上 | 替换被 GWT-84.1 点名禁止的「暂无 LLM 供应商，点击…」 |
| 失败句「供应商列表加载失败。检查网络后重试。」+ 重试，不走空态（GWT-97.3/FR-84） | 页面 | 同上 | `listError` 态；旧行保留（刷新保留行）；空表时隐藏 Table 防止空态句顶替失败句 |
| 只读：无「设为默认」控件，默认标记可见（GWT-97.4） | 页面 | 同上 | 只读旁注沿用「当前账号不能管理供应商。需要经办或企业负责人权限。」 |
| 经办：CRUD 写权保持 + 无「设为默认」控件 + 旁注（SHAPE-QA-03） | 页面 | 同上 | 旁注「当前账号不能设置默认，请联系企业管理员」 |
| 设默认控件角色判据 `tenant_role ∈ {owner, admin}` ∪ `isPlatformAdmin` | 页面 | 同上 | useAuthStore user.tenant_role（与 relay `_ISSUER_ROLES` 同口径）；平台超管沿用平台行既有写面 |
| 调用后端既有 activate/deactivate 端点 | service | `frontend/admin/src/services/llm.ts` | **零行为改动**；仅注释更新（FR-97 词汇映射） |

**分层核对**：☐ N/A（纯前端票，无 Router/Service/Repository 层）——未动任何后端文件。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/LlmProviders.tsx` | 修改 | 激活→默认全文案 + 确认弹窗 + 角色显隐 + 空态/失败句；387 行（≤400，F-7） |
| `frontend/admin/src/pages/LlmProviders.test.tsx` | 修改 | 4→15 例：文案扫描/弹窗钉句/互斥/失败/离线/空态/失败句/只读/经办 + 既有 GWT-06.5/73.4 回归 |
| `frontend/admin/src/services/llm.ts` | 修改 | 仅 3 处注释（is_active/activate/deactivate 的 FR-97 词汇说明），零行为 |

**与票里「会改哪些文件」一致**：☐ 有偏差——`services/llm.ts` 注释为顺手澄清（票面允许内部字段名保留，注释非用户可见面）；后端零文件。

**未触碰「不许改的文件」**：☐ 确认——后端选路、页头结构大改（横幅移除归 T-34）、menuConfig、ProviderWizardModal/ModelSetDrawer、RelayGroups、Users*（并行在制文件）均零 diff。

## 3. 关键实现决策

### 事务边界 / 幂等 / 并发 / 外部依赖

☐ N/A（纯前端文案/交互票，无多步写、无幂等键、无并发写、无新外部依赖；既有 activate/deactivate 单调用保持）。

### 角色显隐（SHAPE-QA-03 口径）

| 角色 | 判据 | 供应商行 CRUD | 「设为默认/取消默认」 | 旁注 |
|---|---|---|---|---|
| 负责人/公司管理员 | `tenant_role ∈ {owner, admin}` | 有（既有） | **有**（GWT-97.1/97.2 主语） | 无 |
| 经办 | `tenant_role === 'operator'` | **有（保持）** | **无** | 「当前账号不能设置默认，请联系企业管理员」 |
| 只读 | 其余 | 无 | 无 | 沿用「当前账号不能管理供应商…」 |
| 平台超管 | `is_platform_admin` | 平台行既有写面保持 | 平台行有（沿用既有写面，未扩权） | 无 |

说明：票面写「权限数据既有 usePermission」，但 usePermission 不暴露 tenant_role；仓库既有同口径判据在 RelayGroups（useAuthStore user.tenant_role，与后端 `_ISSUER_ROLES` 对齐，memory 钉「勿用平台 role」），故沿用后者。强提交仍会被后端 require_operator 拒（票面：后端不动）。

## 4. ORM 与 DBML 对齐

☐ N/A（无数据契约改动）。

## 5. 可观测性

☐ N/A（无新日志面；无敏感数据展示——api_key_masked 既有脱敏保持）。

## 6. 自测证据（命令与退出码原样粘贴）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/LlmProviders.test.tsx --maxWorkers=2
Test Suites: 1 passed, 1 total
Tests:       15 passed, 15 total
Snapshots:   0 total
exit: 0

$ npm run build --prefix /Users/xuyun/auto_agents/frontend/admin
Compiled with warnings.   # 警告全部位于并行在制/存量文件（LogDrawer/EnterpriseManagement/Nodes/Rbac/SpiderLogs/auth）——LlmProviders* 零警告
The build folder is ready to be deployed.
exit: 0

$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest --watchAll=false --maxWorkers=2 --testPathIgnorePatterns "Users.test.tsx|App.menu.test.tsx"
Test Suites: 22 passed, 22 total
Tests:       115 passed, 115 total
exit: 0
```

**全量含在制文件的干扰定界（2026-09-11 T-30 时点）：**

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 2 failed, 22 passed, 24 total
Tests:       7 failed, 124 passed, 131 total
exit: 1
```

7 例失败全部落在 `src/pages/Users.test.tsx`（6 例，GWT-93.x「恢复」按钮 + 「重试/取消」按钮名）与 `src/App.menu.test.tsx`（1 例，「新建渠道组」）。两文件均为 **git 未跟踪的在制文件**（T-25/T-29 并行工单），不 import LlmProviders/services/llm（grep 证实零依赖）；排除后其余 22 套 115 例全绿。失败机理与 T-25 作者的按钮名断言写法相关（antd 两字按钮渲染带空格），见 §8 转交。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-97.1 文案（无「激活」+说明句） | `owner surface uses 默认/设为默认 only — no 激活 anywhere`（含 `document.body.textContent` 全扫 + 说明句/横幅/筛选断言）；`default model tag keeps gold tag and 未指定模型时使用 hint` | ✅ |
| GWT-97.2 互斥呈现（确认弹窗钉句+同域至多一个默认） | `set default confirm modal uses pinned sentence, then mutual exclusion`；`set default failure keeps modal open with inline sentence`；`set default offline keeps modal open with offline sentence` | ✅ |
| GWT-97.3 空态（钉句；失败句不走空态） | `empty state pins 还没有模型供应商 with 添加供应商 for authorized`；`readonly empty state shows sentence without 添加供应商`；`list failure shows failure sentence, not empty state` | ✅ |
| GWT-97.4 越权（只读无控件、标记可见、无内码） | `readonly member sees default mark, no set-default controls`；`operator keeps CRUD write but no set-default control`（SHAPE-QA-03） | ✅ |
| 取消默认（既有 deactivate 面） | `cancel default calls deactivate and shows no-default hint after` | ✅ |
| 既有回归 GWT-06.5 / GWT-73.4 | `renders provider list with protocol display name and readonly guard`；`tenant admin sees own-row write…`；`operator sees save and 测试连接…`；`operator click 测试连接 probes own-row id…` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端，无多步写） | |
| 幂等 | ➖ N/A（无新写路径；activate 单调用既有语义） | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | `set default failure keeps modal open…`（API 拒绝）+ `set default offline…`（离线）+ `list failure…`（列表失败句） | ✅ |

## 7. NFR 验证

☐ N/A（票无 NFR 指派；.tsx ≤400 行 = 387 行已核）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 互斥呈现依赖后端 activate 互斥返回 + 前端刷新（mock 双段验证）；「设置中…」在 okText 上随 `setting` 切换。真环境需重验：activate 拒绝时后端信封 message 进内联句 |
| T-25 作者 | Users.test 挂例是 antd 两字按钮空格坑：「恢复/重试/取消」需 `getByRole('button', { name: /恢\s*复/ })` 形态（本票测试同坑已用此法） |
| T-34 作者 | 移除本页绿色横幅/标题卡时：保留「默认」列、说明句行与未设默认提示行（edge-states §LLM 配置钉其承担横幅信息）；`LlmProviders.tsx` 本票已动过，合并施工只动一次 |
| `/architect` | 票面「权限数据既有 usePermission」与 usePermission 实际不暴露 tenant_role 的偏差已按仓库既有口径（useAuthStore tenant_role）落位，如需统一入口请开票 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测绿（本票套件 15/15；全量排除在制未跟踪文件后 115/115）
- [x] 契约落位表已核对；无后端/数据面改动
- [x] 无自行加字段/改类型/改 token（颜色沿用 antd 语义色 gold/warning，无硬编码 hex）
- [x] 无「激活」残留于用户可见面（`document.body.textContent` 全扫断言）
- [x] 数据获取沿用页面既有模式（本票为文案票，不重构为 react-query——归后续结构票）
- [x] 发现的上游/并行问题已回报（T-25 按钮名坑、usePermission 偏差），未自行绕过
