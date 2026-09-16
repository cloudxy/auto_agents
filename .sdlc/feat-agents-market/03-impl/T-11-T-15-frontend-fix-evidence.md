# 实现证据 · T-11 / T-15 前端用例修红（接手上一会话半成品）

> 票：contract §7 T-11 + T-15｜日期：2026-09-15｜接手背景：上一会话在 quota 中断时，
> `CatalogTab.test.tsx` 刚写完尚未跑过，11 个用例全红。

## 1. 三个红因（都在测试侧/可及性侧，组件逻辑无误）

| # | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | 11/11 报 `No QueryClient set` | `CatalogTab` 内嵌 `AssetDetailDrawer`（`useQuery` 读公开详情），用例直接 `render(<CatalogTab />)` 没有 Provider | 加 `renderTab()` 包 `QueryClientProvider`（`retry:false`，与 `AssetDetailDrawer.test.tsx` 同款） |
| 2 | 找不到 name 为「示例」「清理失源资产」的按钮 | ① antd 对**两字中文**按钮自动插空格 →「示 例」；② 带 `DeleteOutlined` 的按钮，图标 `<span role="img" aria-label="delete">` 参与可及名 →「delete 清理失源资产」 | ① `renderTab()` 补 `ConfigProvider button={{ autoInsertSpace: false }}`——**与生产一致**（`Capabilities.tsx:80/91` 就是这么包的，`Capabilities.import.test.tsx:217` 早有同款注释）；② 给清理按钮补 `aria-label="清理失源资产"`（顺带修掉读屏会念出「delete」的可及性问题） |
| 3 | 示例弹窗用例断言不可达 | 写废的三元 `getByLabelText('示例 2') ? 保存 : 保存`——两支相同，且左侧在元素不存在时直接抛 | 改为直接点「保存」 |

## 2. 自测证据

```
$ node node_modules/.bin/jest --maxWorkers=2 src/pages/market/CatalogTab.test.tsx
Tests: 11 passed, 11 total

$ node node_modules/.bin/jest --maxWorkers=2 src/pages/market/{AssetVisual,MarkdownBody}.test.tsx
9 passed        （T-09 / T-10）
$ node node_modules/.bin/jest --maxWorkers=2 src/pages/market/AssetDetailDrawer.test.tsx
7 passed        （T-10，含 <script> 载荷不执行）
$ node node_modules/.bin/jest --maxWorkers=2 src/pages/market/{TenantShelf,PowerMarketSwitch,TeamLeafTab}.test.tsx
26 passed       （T-08 / T-13）
$ node node_modules/.bin/jest --maxWorkers=2 src/pages/Capabilities.{import,governance,command,subscribe}.test.tsx
28 passed       （T-12 旧向导面 + 治理壳）
```

## 3. 遗留（QA-16 更新：已由 T-12 补齐，原"仍未写"记录已过时）

- ~~T-12 的 GWT-07.x 前端用例仍未写~~——本文件写下此记录时后端 T-07 尚未
  落地；T-07 落地后 T-12 已补齐目录导入前端用例（`ImportTreePicker.test.tsx`，
  非票面原写的 `Capabilities.import.test.tsx`，理由见
  `03-impl/T-12-evidence.md` §1），10 passed，见该证据文件 §2。
  `state.yaml.implement_progress.done` 含 T-12 与此一致，本条遗留已关闭。
