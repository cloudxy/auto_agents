# official —— AutoAgents 官网

React 19 + TypeScript + Ant Design 6 + Framer Motion，服务端状态用 TanStack Query。
构建用 Vite，测试用 Jest（jsdom），lint 用 ESLint flat config（`eslint.config.mjs`）。
跨应用共享代码在 `@auto-agents/frontend-shared`（经 `frontend/shared/dist` 消费）。

## 前置

Node.js ≥ 22.13（推荐 24 LTS，见仓库根 `.nvmrc`）。依赖在仓库根统一安装：

```bash
npm ci                 # 仓库根执行（npm workspaces）
npm run build:shared   # 先构建 shared 的 dist
```

## 常用命令（仓库根执行，或在本目录去掉 `-w official`）

| 命令 | 作用 |
|------|------|
| `npm start -w official` | Vite 开发服务器：`http://127.0.0.1:9113`（端口取 `PORT`，被占直接失败） |
| `npm run build -w official` | `tsc --noEmit` 类型检查 + `vite build`，产物在 `build/` |
| `npm run preview -w official` | 本地预览 `build/` |
| `npm run lint -w official` | ESLint（只有 error 让退出码非零） |
| `npm test -w official` | Jest 单测 |

一般用 `uv run python run.py start official` 启动：会注入端口，并把 `/api` 反代目标对齐 `config` 的 `API.HOST/PORT`。

## 开发代理与环境变量

- 开发态请求走同源 `/api/v1`，由 `vite.config.mts` 的 `server.proxy` 转给后端（只匹配 `/api` 路径段，`/api-keys` 之类前端路由不转发）：
  目标取 `API_PROXY_TARGET`，缺省 `http://127.0.0.1:9111`。
- 源码读 `process.env.REACT_APP_*`（沿用 CRA 约定），构建期静态替换。文件优先级（高 → 低）：
  进程环境变量 > `.env.[mode].local` > `.env.[mode]` > `.env.local` > `.env`（`npm start` 为 development，
  `build` 为 production）。**与 CRA 不同**：`.env.local` 压不过已提交的 `.env.development`，
  本地开发覆盖请写 `.env.development.local`。键说明见 `.env.example`。
- 只监听 `127.0.0.1`；需要局域网访问时临时用 `npm start -w official -- --host 0.0.0.0`。
