# ADR-0003: 前端 npm workspaces + shared 编译产物模式

日期：2026-09-02 · 状态：已实施（工单 64-68，批次 1）

## 背景

admin 与 official 两应用零共享基建：axios client 核心逻辑逐字重复、`ApiEnvelope`
3 份漂移实现（request_id 已丢失）、`TIER_COLORS` 4 处定义。后端协议变更需改两处，
漂移已实际发生。

## 决策

1. **根 package.json 声明 workspaces `frontend/*`**；lockfile 从 per-app 收敛到根
   （必须 npm@10 生成——CI Node 20，npm 11/10 lockfile 曾出兼容问题）。
2. **shared 包（@auto-agents/frontend-shared）采用编译产物模式**：`tsc` 编出
   `dist/`，`main` 指向 `dist/index.js`，**禁止 `main: src/index.ts` 源码直引**。
   原因：CRA 5 的 babel-loader 限定 `include: appSrc` 且 ModuleScopePlugin 拒绝
   src 外文件，workspace symlink 解析后真实路径在 `frontend/shared/`，源码直引
   直接解析失败；编译产物零新依赖、CRA 无感。
3. **共享 client 是工厂非单例**：`createApiClient({baseURL, getAuthToken?,
   onUnauthorized?})`——admin 注入 zustand token + 401 导航（navigate 保留
   `state.from`），official 无鉴权只传 baseURL。
4. **jest 转译例外**：`transformIgnorePatterns` 放行 `@ant-design|antd|rc-*|
   @rc-component`（antd v6 依赖链 ESM，jest 默认忽略 node_modules 会炸）。

## 后果

- CI `npm ci` 移到根 + `cache-dependency-path: package-lock.json` + app 构建
  前先 `npm run build -w @auto-agents/frontend-shared`。
- `run_frontend.py` 启动序：根安装 → build shared → start。
- 新增 `scripts/check-frontend.sh` 门禁（首批 F-5 应用互引禁令 / F-6 Envelope
  单源），挂 pre-commit + CI。
- 批次 3（工单 81）OpenAPI codegen 类型将落在 `shared/src/api/schema.d.ts`，
  届时手工类型 `shared/src/types/skills.ts` 退役。
