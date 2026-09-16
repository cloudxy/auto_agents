# 实现证据 · T-12 目录导入向导（前端）

> 票：contract §7 T-12｜FR 锚点：FR-07 UI 面 + NFR-08｜lane：ui｜日期：2026-09-15

## 1. 交付面

| 文件 | 性质 | 说明 |
|---|---|---|
| `src/pages/market/ImportTreePicker.test.tsx` | 新增 | 10 用例（本轮补齐；组件本体在上一会话已落地） |

**与票表的偏差**：票写「ImportWizard 测试扩展（`Capabilities.import.test.tsx`）」，实际落在
组件同名测试文件 `ImportTreePicker.test.tsx`。理由：`Capabilities.import.test.tsx` 覆盖的是
**旧向导（GWT-100.x）**的页面级流转，而 T-12 是嵌套子向导的独立交互面，与 T-09/T-10/T-11
的同名测试文件惯例一致；页面级集成不回退，`Capabilities.import.test.tsx` 原 9 用例保持全绿。

## 2. GWT × 用例对照

| GWT | 用例 | 断言要点 |
|---|---|---|
| 07.1 正常 | 三步流转 | 已选择回显、类型计数句、新建/更新标注、bundled 子项缩进展示、结果汇总 |
| 07.2 取消 | 预览步骤取消 | **`confirmTreeImport` 零调用** + 零写入 toast + `onCancel(false)` |
| 07.3 upsert | 同上「更新」标注 | 预览 action=update → 「更新」Tag |
| 07.4 空态 | 无可判型资产 | 空态句 +「确认导入 0 项」禁用 |
| 07.5 部分失败 | 结果清单 | 逐条失败原因 + 成功计数不受影响 |
| 07.6 超限 | 两条路径 | ① 前端预检：>500 时「开始解析」禁用且**零请求**；② 服务端 422：逐字文案 +「使用服务器路径」出口 |
| 07.8 能力不回退 | 同上 ② | `onUseServerPath` 被调用（回父向导高级项） |
| 07.9 白名单 + QA-8 | 跳过清单 | 非白名单扩展名与非法路径各自带原因逐字显示 |
| AD-4a 上传形态 | 单列用例 | **part filename 必须等于 `webkitRelativePath`**——这条错了后端判型全盘失效，故单钉 |
| 六态 · Error | 网络失败 | 中性句 + 重试，重试成功保留所选进入预览 |

jsdom 不会自己填只读的 `webkitRelativePath`，用例用 `Object.defineProperty` 造带该属性的
`File`，并直接 `defineProperty(input, 'files')` 触发 change——与真实目录选择同形。
渲染统一包 `ConfigProvider button={{ autoInsertSpace: false }}`（与生产 `Capabilities.tsx` 一致）。

## 3. 自测证据

```
$ node node_modules/.bin/jest --maxWorkers=2 src/pages/market/ImportTreePicker.test.tsx
Tests: 10 passed, 10 total

$ node node_modules/.bin/jest --maxWorkers=2 src/pages/Capabilities.import.test.tsx \
      src/pages/market/CatalogTab.test.tsx
Tests: 20 passed, 20 total        ← 页面级集成与治理目录面不回退
```

前端全量（52 个 suite）：**369 passed**，无红。
