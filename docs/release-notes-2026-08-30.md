# 发布公告 · 2026-08-30（feature/project-structure 基线固化）

> 本次发布为「四阶段交付（LLM 供应商管理 + new-api 中转站 + 体检修复 + 数据闭环）」的基线固化版本。
> 发布前请完整阅读以下破坏性变更与上线顺序要求。

## 一、破坏性变更（Breaking Changes）

### 1. `/data/sync` 桩端点已删除
- 旧版根路径下的 `/data/sync` 占位（stub）端点已移除，调用方将收到 **404**。
- 如有外部脚本仍在轮询该端点，请改用外部 API 正式数据接口（见下条鉴权要求）。

### 2. 外部 API 鉴权统一为 401
- 所有外部 API 公开端点（Webhook 之外）启用统一的 `X-API-Key` 鉴权：
  - **未携带 `X-API-Key`，或携带的 Key 不在 `EXTERNAL_API.API_KEYS` 列表内 → 一律 401**；
  - 配置方式见 `.env.example`（`AUTO_AGENTS_EXTERNAL_API__API_KEYS`，JSON 数组字符串）；
  - 默认空列表 = 全部拒绝（fail-closed）。
- 旧单 Key（`EXTERNAL_API.API_KEY`）仅作过渡期兼容（非空时并入有效密钥列表），**下个版本移除**，请尽快迁移到列表配置。
- Webhook 回调仍走 `X-Signature`（HMAC-SHA256）签名校验，密钥为 `WEBHOOK.SECRET_KEY`，与 API Key 体系相互独立。

## 二、上线顺序要求（必须遵守）

### 1. 数据库迁移 010/011 必须先于代码上线
- 本次交付包含两个新迁移：
  - `010` 新增 `llm_providers` 表（LLM 供应商管理）；
  - `011` 新增 `channel_events` / `channel_probe_results` 表（渠道事件与探针结果）。
- **执行顺序：先 `alembic upgrade head`（到 011），再发布新版后端代码**。
  新代码启动即访问 `llm_providers` 等表，先代码后迁移会导致启动失败。
- 迁移已在演练库完成 `upgrade head → downgrade -2 → upgrade head` 全流程验证（纯建表/删表，无损，不触碰既有数据）。

### 2. downgrade 仅限发布初期窗口
- `alembic downgrade -2`（回退 010/011）仅删除上述三张表，**会丢失已写入的供应商配置、渠道事件与探针结果数据**。
- 仅允许在发布初期（确认新表尚无生产数据写入前）作为回滚手段；一旦新功能开始产生数据，回滚必须走数据保留方案（备份表），禁止直接 downgrade。

## 三、安全配置要求（生产环境必查）

以下项的默认值/空值仅限本地开发，生产沿用将视为配置事故：

| 配置项 | 风险 | 生成/配置方式 |
|---|---|---|
| `AUTO_AGENTS_JWT__SECRET_KEY` | 默认 `change-me-in-production`，令牌可被伪造 | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `AUTO_AGENTS_WEBHOOK__SECRET_KEY` | 同上，采集回调可被伪造 | 同上（Backend 与 Scrapy 必须一致） |
| `AUTO_AGENTS_EXTERNAL_API__API_KEYS` | 空列表 = 外部 API 全 401 | 按调用方分发 Key 并登记列表 |
| `LLM_ENCRYPTION_KEY` | 未配置则供应商 API Key 拒绝保存（fail-closed） | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AUTO_AGENTS_NEWAPI__ACCESS_TOKEN` / `DB_DSN` / `PROBE_API_KEY` | 中转站对接凭据 | `.env` 注入，禁入 yml |

完整键位说明见仓库根目录 `.env.example`（本次已扩充为全键注释化占位版）。

## 四、本次交付概览

- **LLM 供应商管理**：多供应商 CRUD + Fernet 密钥加密入库 + 激活/连通性测试（`/api/v1/llm-providers`）。
- **new-api 中转站集成**：渠道调度器（用量上限→下线→冷却→自动上线）+ 渠道真伪探针 + 用量总览（`/api/v1/newapi`）；独立部署编排见 `deploy/newapi/`。
- **外部 API 鉴权统一**：`X-API-Key` 校验收敛至单一入口，未配置一律 401。
- **前端**：admin 后台新增供应商/中转站/告警/统计等模块；official 官网入口更新（gitlink 转普通目录纳入主仓管理）。
- **基线质量**：`419 passed` / `check-arch 0 违规` / `ruff 0 违规`。

## 五、已知遗留项

- Alembic 迁移链无法从空库引导至 head（003 假定 `spider_tasks` 已由 create_all 预建）——新环境初始化仍需 `init-db` + stamp 流程，基线修复另行排期。
- `EXTERNAL_API.API_KEY`（单 Key）过渡期兼容，下个版本移除。
