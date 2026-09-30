---
name: playwright-admin-e2e
description: admin 浏览器冒烟（登录→仪表盘→用量→成员）：构建、端口、NO_PROXY、接口拦截
metadata:
  type: playbook
  origin: 2026-09-07 feat/litellm-l1
  status: active
---

# admin Playwright 冒烟

## 怎么跑

```bash
CI= npm run build -w admin
npm run e2e -w admin
```

脚本已带 `NO_PROXY=127.0.0.1,localhost,::1`。本机 HTTP 代理会把 Playwright 的 webServer 探测打成 **502**，表现为卡在 `Timed out waiting from config.webServer`。

## 约定

- 静态服端口 **46112**（不要用 `PORT`，会和 admin 9112 抢）。
- `serve -l <port>`，不要 `tcp://127.0.0.1:...`（serve 14 会忽略并换随机端口）。
- 接口全部 `page.route('**/api/v1/**')` 拦截，不启 MySQL/Redis。
- 登录勾「记住我」，否则 `page.goto('/usage')` 整页刷新后 zustand 不持久化，会掉回登录页。
- 侧栏 antd Menu 的 `menuitem` 不稳定；登录后用 `page.goto('/usage')` / `/members`。
- 窄屏用例（375）：断言 `document.documentElement.scrollWidth <= 375`；抽屉用 `getByRole('dialog')`，antd 6 的 drawer 内部类名变了。
- 全页截图前先逐屏滚动到底：官网区块是 `whileInView` 动画，不滚动截出来是空白。

## 相关

- [[frontend-query-testing]]
- `frontend/admin/e2e/smoke.spec.ts`
- `frontend/admin/playwright.config.ts`
