# ADR-001：管理端 v1 API 统一响应契约（ApiResponse 信封）

- 状态：已采纳（Accepted）
- 日期：2026-08-30
- 影响范围：`backend/app/api/v1/*`、`frontend/admin/src/services/*`、`backend/tests/*`
- 冻结范围：`backend/app/external_api/v1/*`（第三轨）、`backend/app/api/v2/*`（第二轨）保持现状不动

## 1. 背景与问题

管理端 v1 内部响应契约三轨并存，前端被迫按模块写不同解包逻辑：

| 轨道 | 现状 | 代表模块 |
|------|------|----------|
| ① 信封 | `ApiResponse`（`ok()` 快捷构造） | `auth.py`、`admin.py` |
| ② 裸直出 | Pydantic 模型 / dict / 数组直接返回 | `spiders.py`、`llm_providers.py`、`newapi.py`、`ai.py`、`configs.py` |
| ③ 外部 API | 独立契约（对第三方集成方承诺） | `external_api/v1/*` |

前端后果（`frontend/admin/src/services/llm.ts` 头注释自证）：

- `llm.ts` / `newapi.ts` / `spiders.ts` / `ai.ts` 期待裸结构；`auth.ts` 期待信封；
- 页面层解包方式分裂：`Users.tsx` / `LogCenter.tsx` / `Dashboard.tsx` 按 `res.data` 解包
  （其中 Dashboard 调用的 `/spiders/tasks` 实际是裸结构，`res.data` 恒为 undefined，
  属于信封化前预适配的隐性 bug）；`Nodes.tsx` / `Settings.tsx` 又按裸结构解包。

## 2. 决策

### 2.1 统一信封

管理端 v1 所有成功响应统一使用 `backend/app/responses/` 既有设施：

- 单对象 / 字典 / 数组：`ApiResponse`（`ok()/created()/updated()/deleted()` 快捷构造），
  载荷置于 `data` 字段；
- 分页端点（请求参数含 `skip/limit` 或 `page/page_size`）：`PaginatedResponse`，
  `data` 为 `PaginatedData{items, total, page, page_size, total_pages}`。
  `items/total` 命名与前端既有消费约定（`{total, items}`）对齐，前端仅多解一层 `data`；
  offset 分页端点由 helper `paginated_from_offset` 统一换算 `page = skip // limit + 1`。

约束：

- 信封只管成功响应；错误路径维持 `HTTPException` + 统一异常处理器现状（4xx/5xx 结构不变）；
- 路由、权限（`require_login/operator/admin`）、审计（`record_audit`）逻辑一律不动；
- OpenAPI schema 变化属预期内，不做兼容层（前后端同仓同发）。

### 2.2 白名单（探测类 / 二进制端点，保持裸结构）

以下端点强行包装无业务意义，列入白名单并说明理由：

| 端点 | 理由 |
|------|------|
| `GET /`（root） | 进程探活端点，返回 `{"message": ...}` 供启动脚本/网关探测，无业务消费方 |
| `GET /health`、`/health/db`、`/health/storage`、`/health/redis` | 基础设施探活契约：docker-compose healthcheck / 运维监控直接消费 `status` 字段，且 unhealthy 分支（200 + `status=unhealthy`）依赖裸结构语义，包装后语义被信封 `success=true` 稀释 |
| `GET /spiders/results/{task_id}/export` | 二进制流下载（CSV/JSON 附件），非 JSON 响应，无法信封化 |

刻意**不**白名单的"探测类"端点：

- `POST /llm/providers/{id}/test`：连通性测试结果（`{ok, latency_ms, model, error}`）
  照常包装为 `ApiResponse`，`data.ok`（探测结论）与信封 `success`（请求成功）语义正交，
  前端同步解包成本一行，保持"尽量少白名单"。

例外记录（2026-08-30 终验评审）：health 端点虽整体白名单，其 `error` 字段从完整异常串
`str(e)` 收窄为异常类型名 `type(e).__name__`——探活契约只暴露故障类别、不暴露内部实现细节，
异常完整信息走日志（细节走日志原则）；消费方仅依赖 `status` 字段判定健康态，不受影响。

### 2.3 各模块目标形态

| 模块 | 目标 |
|------|------|
| `auth.py` / `admin.py` | 已信封，不动 |
| `configs.py` | GET → `ok(data=dict)`；PUT → `ok(message=...)` |
| `newapi.py` | overview → `ApiResponse`；events / probe-results → `PaginatedResponse` |
| `llm_providers.py` | 全部 7 端点 → `ApiResponse`（列表 `data=[...]`） |
| `spiders.py` | 分页 3 端点 → `PaginatedResponse`；列表端点 → `ApiResponse`（`data={total, items}` 或数组）；单对象/dict 端点 → `ApiResponse`；export 白名单 |
| `ai.py` | plans 列表 → `PaginatedResponse`；其余 → `ApiResponse` |

## 3. 迁移顺序与影响面

严格按序执行，每步后端→前端→测试同步闭环：

1. **newapi.py**（3 端点，面最小）→ `newapi.ts` 解包 + `NewApiOps.tsx`（经 service 层，无需改）
2. **llm_providers.py**（7 端点）→ `llm.ts` 解包（页面 `LlmProviders.tsx` 经 service 层，无需改）
3. **spiders.py**（33 端点，只动返回包装，不改路由/权限/审计）→ `spiders.ts` 解包
   + 直接 axios 的 `Nodes.tsx`（`res.items` → `res.data.items`）
4. **ai.py**（7 端点）→ `ai.ts` 解包
5. **configs.py**（2 端点）→ 直接 axios 的 `Settings.tsx` 解包
6. **测试同步**：断言从裸结构改为 `body["data"]...` / `body["data"]["items"]`

前端解包策略：**service 层统一解信封（`envelope.data`），对外返回类型保持不变**，
页面组件经 service 层消费零改动；仅两个绕过 service 直接 axios 的页面
（`Nodes.tsx`、`Settings.tsx`）同步解包。`Dashboard.tsx` 的预适配解包
（`res.data?.items`）在本次迁移后从隐性 bug 变为正确行为。

## 4. 后果

- 正面：前端解包逻辑单一化（信封 → data）；`request_id` 贯通追踪；OpenAPI 契约一致；
- 负面 / 风险：破坏性变更（同仓同发可接受）；外部消费方若直连 v1 裸结构需同步
  （external_api 契约不受影响）；
- 后续：v2 与 external_api 是否跟进信封化，另立 ADR。
