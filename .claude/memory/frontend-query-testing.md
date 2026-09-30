---
name: frontend-query-testing
description: admin 页 useQuery 后的测试/构建坑：QueryClient、queryFn 可选参数、antd 6 Alert/message
metadata:
  type: troubleshooting
  origin: 2026-09-06 feat/litellm-l1
  status: active
---

# admin react-query 测试与构建

## QueryClient

页面改 `useQuery` 后，Jest 必须包 `withQuery()`（`frontend/admin/src/testUtils.tsx`）。不要每个测试手写 `QueryClientProvider`。

## queryFn 不能直接传「首参可选」的函数

`useQuery({ queryFn: listMemberAudit })` 在 `CI=` 生产构建会 TS2769：react-query 把 QueryFunction context 当成那个可选 `limit`。写成 `queryFn: () => listMemberAudit()`。同类：`listDeadItems`。

## antd 6

- `Alert` 用 `title`，不要 `message`（deprecated）。
- `message.error` 在 jsdom 里会拖死 `findByText`。断言 toast 文案用 `jest.spyOn(message, 'error')`，不要等 DOM。
- 只读页不要常驻挂 `Drawer`/`Modal`（卸载时 React 19 `AggregateError`）。
- 两个汉字的按钮，antd 会在字间插空格（「禁 用」）：`getByRole('button', { name: '禁用' })` 找不到；**否定断言会静默通过**。一律写 `/^禁\s*用$/`。
- 生产构建剥掉 antd 弃用告警：查弃用写法靠静态扫（`valueStyle` / `Alert message` / `Drawer width`），不靠浏览器控制台。
- `Badge.Ribbon` 的 `style` 作用在角标上，要撑满外层用 `rootClassName`。
- 表格里任一列 `ellipsis` 会让整表走固定布局，不定宽的列在窄屏被挤成 0 宽——给关键列定宽。

## 相关

- [[playwright-admin-e2e]]
- `frontend/admin/src/testUtils.tsx`
