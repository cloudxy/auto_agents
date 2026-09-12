# 实现证据 · T-32 总览三问驾驶舱 + 问题渠道置顶 + 事件跳转

> 票：contract §11 T-32｜FR 锚点：FR-98（GWT-98.2 / 98.3 / 98.5 / 98.6）｜角色：/frontend（admin）｜日期：2026-09-11
> 依赖：T-31（PageHeaderTabs + `overview-3q` 预留容器）；与 T-33 同文件串行（先 T-32 后 T-33）。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 三问同屏（GWT-98.2） | 组件分区 | `frontend/admin/src/components/newapi/Overview3q.tsx` | 复用 T-31 预留 `data-testid="overview-3q{,-health,-channels,-events}"`，三区自上而下 |
| Q1 能不能用（健康灯+模型数+部署摘要） | 同上 | 同上 | 数据 = `/newapi/overview`（react-query）；健康灯文字+颜色双通道（Tag 可用/不可用 + 图标） |
| Q2 真不真/稳不稳（判定/延迟/24h 事件/窗口用量/既有配置动作） | 组件 | `frontend/admin/src/components/newapi/OverviewChannels.tsx` | 行 = channels ∪ 本地探针行合并；spoofed/offline 置顶（GWT-98.3） |
| Q3 刚才发生了什么（Top 10 + 跳转） | 组件 | `Overview3q.tsx` | 行点击（含键盘 Enter）→ `onTabChange('events')`；EventsList 新增可选 `highlightId` 行高亮（GWT-98.5） |
| 三区独立失败（GWT-98.4 边界句） | 组件 | `Overview3q.tsx` | overview/channels/probes/events 四查询独立；失败句走 `LoadState`（FR-84 族，edge-states 已冻句） |
| 网关不可达（GWT-98.6） | 组件 | `Overview3q.tsx` | 健康灯=不可用 + 已冻 71.3 句；本地探针行继续显示；71.2 空态保持已冻两句，无第三套 |
| 句式/映射常量 | 共享 | `frontend/admin/src/components/newapi/newapiShared.ts` | 区失败/空态句单一来源；`channelIdFromRef`（数值引用镜像） |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/newapi/Overview3q.tsx` | 新增 | 驾驶舱容器（四查询 + 行装配 + 跳转/探测编排），323 行 |
| `frontend/admin/src/components/newapi/OverviewChannels.tsx` | 新增 | Q2 渠道表（置顶排序导出 `sortChannelRows`），202 行 |
| `frontend/admin/src/components/newapi/eventsList.css` | 新增 | 跳转目标行高亮（`var(--ant-color-primary-bg)` + 兜底，与 marketTabs.css 同款） |
| `frontend/admin/src/components/newapi/newapiShared.ts` | 修改 | 新增区级句常量 + `channelIdFromRef` |
| `frontend/admin/src/pages/NewApiOps.tsx` | 修改 | 总览 tab 换装 `Overview3q`；总览数据面 react-query 化（页面 315→167 行）；窗口配置 Modal/探针/事件 pane 不动 |
| `frontend/admin/src/components/newapi/EventsList.tsx` | 修改 | 仅增可选 `highlightId`（既有列表/筛选/分页零改动） |
| `frontend/admin/src/pages/NewApiOps.test.tsx` | 修改 | mock 扩展 + 渲染包 QueryClientProvider + 新增 6 用例 |

与票表一致：仅 NewApiOps.tsx 呈现层 + 子件；未动探针/事件 pane 既有列表；未动 T-34 页头规范（PageHeaderTabs 结构沿用）。未触碰「不许改的文件」：确认（未改 menuConfig/filteredMenus/AdminLayout/App.tsx）。

## 3. 关键实现决策

- **数据面 react-query 化（T-17 同款）**：overview / channels / probe-latest(100) / events-slice(100) 四查询独立挂载，三区独立 loading/error/refetch；离线时缓存数据保留 + 「网络不可用，以下为已加载的本地数据。」提示行（edge-states 离线节）。
- **Q2 行合并**：channels 行按 `model_name` 关联最新探针行（探针行自带 `channel_id`，事件计数/用量按 channel_id 直连）；无探针记录的渠道仅数值 `gateway_ref` 可镜像出 channel_id（`newapi_api._channel_id_from_ref` 数字分支），否则该行 24h 事件/用量列「—」——sha256 分支依赖 BigInt，构建 target=es5 不可用，**不在前端镜像**（缺口 §8）。
- **置顶排序（GWT-98.3）**：`spoofed/offline` 组在前（组内判定时间倒序，时间相同按模型名稳定排序），`original`/未探测在后。
- **Q3 Top N**：事件切片前 10 条；空切片 = 已冻句「最近 24 小时还没有事件。」；行点击/Enter 跳事件 tab，目标行 `events-row-highlight` 高亮（首页可见）。
- **跳转受控**：复用 T-31 的 `activeTab/onTabChange` 受控（`onJumpToEvent` → `onTabChange('events')` + `highlightEventId`），pane 常挂载语义不变。
- **离线渠道延迟「—」**（不显示 0ms）；预算窗未配置额度「—」+ tooltip「未配置预算窗口」，不显示 0/0。

## 4. 数据契约核对

未改任何 API 契约 / ORM / schema / token。无新 hex 色值（高亮走 antd CSS 变量 + 既有兜底同款）。`npx tsc --noEmit` 退出 0。

## 5. 自测证据（命令 + 退出码原样）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 25 passed, 25 total
Tests:       149 passed, 149 total
Snapshots:   0 total
Time:        420.012 s
Ran all test suites.
exit: 0   （TEST_EXIT=0，定向 NewApiOps 套件 11/11 先行通过）

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.        # 警告仅存量五文件（LogDrawer/EnterpriseManagement/Rbac/SpiderLogs/auth），本次新增文件零警告
File sizes after gzip: …
exit: 0   （BUILD_EXIT=0）

$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0   （FRONTEND_SH_EXIT=0）
```

（后端侧门禁属 T-33 改动，见 T-33-evidence §5：全量 pytest 1473 passed / arch 0。）

## 6. 验收项逐条对应

| GWT | 覆盖的测试（`src/pages/NewApiOps.test.tsx`） | 结果 |
|---|---|---|
| GWT-98.2 三问同屏 | `GWT-98.2 three questions on one screen…`（健康灯/模型数/部署、判定+延迟+24h 事件+窗口用量已用额度、Top 事件） | ✅ |
| GWT-98.3 问题渠道置顶 | `GWT-98.3 spoofed and offline channels are pinned before original ones`（伪装→不可用→正品 行序断言） | ✅ |
| GWT-98.4 边界（任一接口挂不拖垮全区） | `GWT-98.4 edge: one region failing does not take down other regions`（事件区失败句+重试，健康/渠道区不受影响） | ✅ |
| GWT-98.5 事件跳转 | `GWT-98.5 clicking a top event row switches to the events tab and highlights the row`（tab 切换 + 行可见 + 高亮类） | ✅ |
| GWT-98.6 网关不可达 | `GWT-98.6 unreachable gateway…`（不可用灯 + 71.3 句 + 本地探针行继续显示 + 无 71.2/「暂无渠道」）＋ 既有 `GWT-71.3` 用例 | ✅ |
| 既有冻结验收不回退 | `GWT-71.2` / `GWT-71.3` / `GWT-71.1` / `GWT-98.1`（×2） | ✅ |

## 7. 9 维自检（lane 规定）

间距 16 节奏同库内既有；颜色全 antd token（Tag success/error/default、CSS 变量高亮）；字体 Typography 同款；圆角/阴影 antd 默认；图标全 @ant-design/icons；交互态（loading/disabled/tooltip/行键盘可达 tabIndex+Enter）；六态全覆盖（骨架/已冻空态句/三区失败+重试/离线行/越权=页面级 404 同形既有/边界「—」）；响应式（表格 scroll-x + Space wrap，未起 dev server 实测 375/768——单路串行禁 watch，留 qa 浏览器抽检）；a11y（健康灯文字+颜色双通道、判定非仅色、事件行键盘可达）。

## 8. 给下游的信息（后端缺口清单，未编数据）

| 给谁 | 内容 |
|---|---|
| /backend | 缺口 1：无 per-channel 24h 事件数聚合端点——前端取最近 100 条事件切片客户端计数，>100 条/24h 时该列可能少计（夹具量级准确）。建议 events 按渠道聚合列。 |
| /backend | 缺口 2：窗口用量「已用」无读 API（调度器把 `last_usage` 写在 Redis state 未暴露 HTTP）——前端以「最近一次事件记录的 usage」为最近真值信号（tooltip 注明来源），无事件显示「—」。建议 channels 响应携带窗口已用。 |
| /backend | 缺口 3：`gateway_ref → channel_id`（sha256）只在后端 `_channel_id_from_ref`；前端 target=es5 无法镜像非数值引用 → 无探针记录且引用非数字的渠道行事件/用量列「—」。建议 channels/probe-results 响应直接带 `channel_id`。 |
| /qa | Q2 行按 `model_name` 关联探针行——同名模型多渠道会并到一行（指纹引擎以模型为对象，现网无双同名场景）；GWT-98.2 夹具请给渠道配探针行，事件计数才非「—」。 |
| /designer | 三区视觉用 Card size=small + antd 默认 token，未新增视觉体系；视觉细节可在后续票替换不动结构位（data-testid 三区容器已钉）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（admin 全量 25 套件/149 测 = 基线 25/143 + 6 新增）
- [x] 契约落位表已核对（纯 UI 票：无 Router/Service/Repository 分层问题）
- [x] 未自行加字段/改类型/改 token
- [x] 无硬编码连接串/密钥/端口；无手写轮询（react-query refetchInterval）
- [x] 发现的上游问题已回报（§8 缺口清单），未自行绕过、未编数据
- [x] .tsx ≤ 400 行（最大 323）；未 git commit（按 packet 禁令）
