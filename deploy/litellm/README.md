# LiteLLM Proxy · 独立数据面编排（auto_agents）

> 镜像 **`ghcr.io/berriai/litellm:v1.100.0`**（**本票钉死**，勿用浮动 latest / main-latest / main-stable）。
> 查阅：GitHub Release [v1.100.0](https://github.com/BerriAI/litellm/releases/tag/v1.100.0)（2026-09-06）；
> Docker Hub [`litellm/litellm:v1.100.0`](https://hub.docker.com/r/litellm/litellm/tags) 于 2026-09-09 确认 tag_status=active
> （docker.io manifest `sha256:c8756e7b9a61fe45df2ccb5b781d388c3b2f3a21ef9e4956630caef20f9f03aa`）。
>
> **本目录定位**：LiteLLM Proxy 作为**独立隔离部署**的平台 LLM 数据面——独立目录
> `deploy/litellm/`、独立网络 `litellm-net`、自有 Postgres，不并入根
> `docker-compose.yml` 的 services 表、不进 uv workspace、不进 app Alembic。
> **渠道调度器与渠道真伪探针不由本目录承载**，由本项目 backend 内置服务
> 经 HTTP 调用本 Proxy（见 §5）。backend **只**持 `LITELLM.BASE_URL` /
> `LITELLM.MASTER_KEY` / `LITELLM.TIMEOUT`，**禁止** `LITELLM.DB_DSN`。

---

## 一、简介与架构

### 1.1 架构图（文本版）

```
 auto_agents backend（平台路径 llm_chat → T-16；值班/探针 → T-18/T-19）
        │  HTTP only：LITELLM.BASE_URL + LITELLM.MASTER_KEY
        │  禁止 DSN / 禁止打本目录 Postgres / 禁止租户浏览器直连 :4000
        ▼
 ┌────────────────────────────────────────────────────────┐
 │  LiteLLM Proxy  ghcr.io/berriai/litellm:v1.100.0       │
 │  （对外仅 4000；默认绑 127.0.0.1）                      │
 │  · 虚拟 Key / spend / 模型行 —— 自有 Postgres           │
 │  · 上游 Key 只活在网关密钥面（env 或 DB+SALT）           │
 │  · Admin UI = 操作者面，不是租户产品                     │
 └───────────────────────────┬────────────────────────────┘
                             │ 上游官方 / 已授权渠道
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
      上游 A              上游 B              上游 C
```

单副本**不启 Redis**。多副本（限流 / 路由状态跨实例）才需要自有 Redis；
本 compose 不声明 redis 服务。见 ADR-0014 与诊断 §2.1。

### 1.2 职责边界（重要）

| 关注点 | 承载方 | 说明 |
| --- | --- | --- |
| 虚拟 Key / spend / 模型配置 | LiteLLM Proxy + 本目录 Postgres | 本目录部署运维 |
| 上游明文 Key | 网关 env（`os.environ/<NAME>`）或 Proxy DB（`LITELLM_SALT_KEY`） | 不进 git、不进 backend yml |
| 渠道用量调度 / 真伪探针 | **本项目 backend 内置服务** | HTTP 打 Proxy；不持网关 DSN |
| 平台路径 chat | backend `llm_chat`（T-16，不在本票） | `POST {LITELLM.BASE_URL}/v1/chat/completions` |
| Admin UI | 操作者本机 / 反代 | **不是**租户产品；租户不得直连网关端口 |
| 主站探活 `/health/deep` | 根 compose backend（MySQL + Redis） | **不**绑网关 liveness |

---

## 二、部署步骤

### 2.1 准备

```bash
cd deploy/litellm
cp .env.example .env
openssl rand -hex 32   # → LITELLM_MASTER_KEY（建议 sk- 前缀）
openssl rand -hex 32   # → LITELLM_SALT_KEY（设一次；见 §4 SALT）
# 可选：cp config.yaml.example config.gen.yaml
#      并在 .env 设 LITELLM_CONFIG=./config.gen.yaml
#      yaml 里只写 os.environ/<NAME>，不要写明文 Key
```

`config.gen.yaml` 已 gitignore（T-11）。本票只做运行时注入，不把生成配置拉回跟踪树。

### 2.2 启动

```bash
docker compose -f deploy/litellm/docker-compose.yml up -d
```

独立网络名 **`litellm-net`**（compose `networks.default.name`）。根编排若先于本栈启动，须先：

```bash
docker network create litellm-net
```

根 `docker-compose.yml` 只声明该网为 `external: true`，**禁止**声明 litellm 服务。
「compose 起来了」≠ 平台路径已切（Then 在 T-16 / T-20）。

### 2.3 运维速查

| 操作 | 命令/方式 |
| --- | --- |
| 看日志 | `docker compose -f deploy/litellm/docker-compose.yml logs -f litellm` |
| 升级版本 | 先备份 `./postgres-data` → 改 compose 中 **钉死 tag** → `pull && up -d` |
| 备份 | 备份 `./postgres-data/` 与 `.env`（离线）；**不要**把 `.env` 提交 git |
| 4000 连不上 | `docker compose ps`（healthcheck）与 `LITELLM_BIND` |
| 语法校验（不启动） | `docker compose -f deploy/litellm/docker-compose.yml config -q` |

---

## 三、操作者面（不是租户产品）

LiteLLM Admin UI（`/ui`）与虚拟 Key 管理是**平台操作者**工具。

- **不要**把 Admin UI 做成租户菜单、租户「我的渠道组」、租户虚拟令牌产品（Q-RELAY 未关；本票不代选）。
- 租户浏览器禁止直连网关端口。
- 租户直打值班页走 **GWT-07.3**（与未登录打一个不存在页同形；页上无密钥）。
  **禁止**用「打开渠道页见掩码」当 Then（GWT-75.3 与 GWT-14.3 同一句；产品句在 T-05）。

超管值班页上若出现密钥相关字段：仅掩码或无完整上游 Key（GWT-75.2，与 T-18 同一句）。本票保证注入侧不把完整 Key 写进可跟踪文件。

---

## 四、安全加固清单

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | 改 placeholder 密钥 | `.env` 中 `LITELLM_MASTER_KEY` / `LITELLM_SALT_KEY` / `POSTGRES_PASSWORD` 必改 |
| 2 | **SALT 不可当普通回滚** | 更换 `LITELLM_SALT_KEY` 前先导出模型；否则 DB 内上游凭据无法解密 |
| 3 | 4000 不暴露公网 | 默认 `LITELLM_BIND=127.0.0.1`；外部走反代；租户不直连 |
| 4 | 密钥管理 | `.env` / `config.gen.yaml` 严禁提交 git（本目录 `.gitignore` 已忽略） |
| 5 | Postgres 不出网 | 容器**未发布**宿主端口，仅 `litellm-net` 内部互通；勿额外加 `ports` |
| 6 | 上游 Key 只走 env | yaml 使用 `os.environ/<NAME>`；跟踪树样例禁止 `api_key: sk-…` |
| 7 | 主站探活隔离 | backend `/health/deep` **不**因网关挂变红 |

**Caddy 示例**（操作者反代；Caddy 需加入 `litellm-net`）：

```caddyfile
llm-gateway.example.com {
    reverse_proxy litellm:4000
}
```

**Nginx 示例**（SSE/流式必需项已标注）：

```nginx
server {
    server_name llm-gateway.example.com;
    listen 443 ssl;

    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

---

## 五、与本项目（auto_agents）集成

### 5.1 平台路径接入（出口不在本票）

平台路径 chat 由 T-16 改 `llm_chat`，本票不改该出口。完成后 backend 使用：

- `LITELLM.BASE_URL` → 同机 `http://127.0.0.1:4000`；容器加入 `litellm-net` 后 `http://litellm:4000`
- `LITELLM.MASTER_KEY` → 与本目录 `.env` 的 master key 对应（虚拟 Key 也可，由操作者签发）
- `LITELLM.TIMEOUT`

切换旗标 `LLM.DATA_PLANE` 与 new-api 退役完成态在 T-20。短双跑只作 expand 回滚件，不是本票完成态。

### 5.2 渠道调度器与真伪探针（本项目 backend 内置服务）

- **不在本目录部署任何调度脚本**。参考材料与 new-api 时代外部脚本仅作设计参考；
  用量巡检 / 冷却恢复 / 真伪探针由 backend 服务经 **LiteLLM 管理 HTTP** 重写（T-18 / T-19），
  并继续规避 DSN 误连、类型比较、非原子状态、单渠道中断整轮等缺陷。
- **配置**：backend 只持 HTTP 连接键 `LITELLM.BASE_URL` / `LITELLM.MASTER_KEY` /
  `LITELLM.TIMEOUT`（Dynaconf；键落地 T-15）。敏感 master key 走
  `config/<env>/.env` 或环境变量覆盖（`AUTO_AGENTS_LITELLM__MASTER_KEY`），不落跟踪 yml。
  **禁止** `LITELLM.DB_DSN`。网关 Postgres 的 `DATABASE_URL` 只给 **网关进程**。
- **网络**：backend 与 LiteLLM Proxy 若同机，`LITELLM.BASE_URL=http://127.0.0.1:4000`；
  若 backend 也容器化，加入 `litellm-net` 后用服务名 `http://litellm:4000`。
  禁止容器内 `localhost:4000` 当生产默认。根文件只声明外部网络，不声明 litellm 服务。

---

## 六、部署前验证清单

1. **Compose 语法校验**（不启动）：

   ```bash
   docker compose -f deploy/litellm/docker-compose.yml config -q
   ```

2. **跟踪树**：`git ls-files deploy/litellm/config.gen.yaml` 必须为空。
3. **镜像 tag**：compose 与本 README 均为 `v1.100.0`；对浮动 latest 的 grep 闸只允许命中 compose 注释。
4. **健康检查**（启动后）：`docker compose ps` 两服务 `healthy`；
   `curl -sS http://127.0.0.1:4000/health/liveliness` 正常。此探活 **不**接入 backend `/health/deep`。
5. **根编排**：根 `docker-compose.yml` 的 `services` 无 `litellm`；仅 `networks.litellm-net.external`。
6. **Alembic**：本目录 Postgres **不**出现在 `backend/alembic`。

---

## 七、合规与风险提醒

- 本 compose 使用 LiteLLM **OSS** 镜像能力（Key / team / spend）。Enterprise Org / SSO 不在本票。
- 上游授权：只聚合调用**自己合法持有**的上游 API。
- 保密：`LITELLM_MASTER_KEY` / `LITELLM_SALT_KEY` / `.env` / `config.gen.yaml` 不提交 git、不贴工单。
- 对外收费故事不在本票（不代选 Q-AGPL / Q-BILL / Q-PRICE / Q-RELAY）。

---

## 八、密钥轮换（清单项，不写密钥）

交付清单（后续 `06-deliver/checklist.md`，本票不写该文件）必须含：

1. 轮换曾出现在已跟踪生成配置里的上游凭据（操作者机外；证据只记「已轮换」）。
2. `LITELLM_SALT_KEY` 生成一次进 secret manager；runbook 写「先导出模型再动 SALT」。
3. 之后生成配置只走 ignore + 运行时 env 注入。

---

## 九、文件说明

| 文件 | 用途 |
| --- | --- |
| `docker-compose.yml` | Proxy `v1.100.0` + Postgres `16.10-alpine`；网络 `litellm-net`；无 Redis |
| `.env.example` | 环境变量模板（占位符；无真实上游 Key） |
| `config.yaml.example` | 跟踪样例；`api_key: os.environ/OPENAI_API_KEY` |
| `config.gen.yaml` | 生成配置；**不跟踪** |
| `.gitignore` | `.env` / `*.gen.yaml` / `postgres-data/` |
| `../../docker-compose.yml` | 根编排：只 `external: litellm-net`，无 litellm 服务 |

### 版本锁定一览

| 镜像 | 锁定 tag | 依据（查阅 2026-09-09） |
| --- | --- | --- |
| `ghcr.io/berriai/litellm` | `v1.100.0` | GitHub Release v1.100.0（2026-09-06）；Docker Hub `litellm/litellm:v1.100.0` active |
| `postgres` | `16.10-alpine` | Docker Hub `library/postgres` tag_status=active |

本 compose **无** Redis 服务。多副本时再加，并在 runbook 写明跨副本限流依赖。

---

## 十、L1 影子对照（不改生产路径）

L1 交付的是**影子对照与配置导出**，不是根 `docker-compose.yml` 里的 sidecar。
生产流量默认仍走自研直连；治理层走 HTTP Admin API（`LITELLM.ADMIN.ENABLED`）。

| 交付物 | 位置 |
|---|---|
| 独立 compose（本目录） | `deploy/litellm/docker-compose.yml`（pin `ghcr.io/berriai/litellm:v1.100.0`） |
| 配置导出器 + CLI | `backend/services/litellm/exporter.py` + `backend/scripts/export_litellm_config.py` |
| 影子只读对比器 | `backend/services/litellm/shadow.py`（零外呼，不发真实 LLM 调用） |
| 镜像版本守卫 | `backend/tests/test_litellm_version_guard.py` + `backend/services/litellm/guard.py` |
| 配置 | `config/default/litellm.yml`（`LITELLM.*`） |

```bash
# 生成配置（读 llm_providers enabled 行 + models 子表 → 静态 yaml）
uv run python backend/scripts/export_litellm_config.py
# 生成文件：deploy/litellm/config.gen.yaml（明文 Key，已 gitignore；FR-14 不进跟踪树）
# --redacted-sample 可输出脱敏样例（key 掩码）用于工单/日志留证

docker compose -f deploy/litellm/docker-compose.yml up -d
curl -sS http://127.0.0.1:4000/health/liveliness
```

`shadow.py`：输入「自研候选链对某请求的供应商选择」与「导出的 config」，输出两侧
路由决策对照表（`model→provider` 映射差异、cooldown 状态差异）。**只读对比，
不发起任何真实 LLM 调用、不连接 proxy**。

**cooldown 分层共存**：自研 cooldown（`ai_planner/_cooldown.py`）是 Redis 计数——
跨进程共享、键 = provider+model、连通成功清零，作用于**内部直连路径**；
LiteLLM router 的 `allowed_fails`+`cooldown_time` 是 **proxy 进程内存态**
（多副本不共享），作用于**中转站路径**。两者分层共存；shadow 对照表对冷却态
差异标 `known_layering=True`（记录维度，不算配置错误）。

| 票 | 衔接点 |
|---|---|
| L2 渠道配置面 | `backend/services/litellm/admin_client.py` + `/api/v1/litellm/*`（平台超管）；禁直连 LiteLLM 库 |
| L3 虚拟键+计费 | 注册 `attach_free_plan` → `ensure_tenant_key`（Admin 未启用则跳过） |
| L4 内部调用切流 | `llm_common.runtime` PROXY 路由开关；shadow 对照表是 A/B 基线 |
| L5 退役清理 | new-api 残留删除（本目录不承载 new-api） |
