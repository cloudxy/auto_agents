# 实现证据 · T-14 LiteLLM 独立 compose + 密钥注入 + 禁浮动 latest

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-14.md`｜FR 锚点：FR-75｜角色：/sre｜日期：2026-09-09
> 泳道：L4
> 闸：`git ls-files deploy/litellm/config.gen.yaml`；`git grep -n ':latest' deploy/litellm || true`；`bash tools/check/arch.sh`
> 本文件不含任何上游 Key / master / salt 明文。

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 独立故障域 | 编排 | `deploy/litellm/docker-compose.yml` | Proxy + 自有 Postgres；网络名 `litellm-net` |
| 根编排只挂网 | 编排 | `docker-compose.yml` | `networks.litellm-net.external: true`；services 仍 mysql/redis/backend |
| 镜像钉死 | 编排 + 文档 | compose + README | `ghcr.io/berriai/litellm:v1.100.0`；`postgres:16.10-alpine` |
| 密钥注入 | env 模板 | `deploy/litellm/.env.example` | 占位符；`.env` gitignore |
| 生成配置离树 | ignore | `deploy/litellm/.gitignore` + 根 `.gitignore` | `config.gen.yaml` / `*.gen.yaml` |
| 样例无明文 Key | 样例 yaml | `deploy/litellm/config.yaml.example` | `api_key: os.environ/OPENAI_API_KEY` |
| 网络契约 §5.2 | 文档 | `deploy/litellm/README.md` | 同构 `deploy/newapi/README.md` §5.2；对象=LiteLLM Proxy；backend 只 HTTP；无 DSN |
| 值班越权 Then | 文档边界 | README §3 | 租户直打值班页走 GWT-07.3；禁止「打开渠道页见掩码」 |

**分层依赖核对**：N/A（本票无 Router/ORM/Schema 业务改动）☑ 未改 `llm_chat` ☑ 未 resume `services/litellm/` pyc ☑ 未给 backend `LITELLM.DB_DSN` ☑ 未把 LiteLLM PG 写入 Alembic ☑ 未把 `/health/deep` 绑网关 liveness ☑ 未把 Admin UI 当租户产品

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `deploy/litellm/docker-compose.yml` | 新增 | Proxy `v1.100.0` + Postgres `16.10-alpine`；无 Redis |
| `deploy/litellm/.env.example` | 新增 | 占位密钥/口令；无真实上游 Key |
| `deploy/litellm/README.md` | 新增 | 部署 + §5.2 网络契约 |
| `deploy/litellm/.gitignore` | 修改 | 补 `postgres-data/` |
| `deploy/litellm/config.yaml.example` | 修改 | `store_model_in_db`；仍 `os.environ/*` |
| `docker-compose.yml` | 修改 | 仅加 `networks.litellm-net.external`；无 litellm 服务 |

**与票里「会改哪些文件」一致**：☑ 是

**未触碰「不许改的文件」**：☑ 确认（未改 `llm_chat`；未 resume pyc；未把 Admin UI 当租户产品；未绑 `/health/deep`；未把网关 PG 进 Alembic；未给 backend DSN；未代选六问）

## 3. 关键实现决策

### 镜像 tag（查阅，非发明）

| 镜像 | 钉死 tag | 查阅 |
|---|---|---|
| `ghcr.io/berriai/litellm` | `v1.100.0` | GitHub Release v1.100.0（2026-09-06）；Docker Hub `litellm/litellm:v1.100.0` 于 2026-09-09 tag_status=active（docker.io manifest `sha256:c8756e7b9a61fe45df2ccb5b781d388c3b2f3a21ef9e4956630caef20f9f03aa`）。compose **按 tag 钉死**，未把 docker.io digest 套到 ghcr 名上。 |
| `postgres` | `16.10-alpine` | Docker Hub `library/postgres` 于 2026-09-09 tag_status=active |

未使用浮动 latest / main-latest / main-stable。未发明未查阅的 digest。

### Redis

本 compose **无** redis 服务。单副本；限流/路由状态不需要跨实例。多副本时再加自有 Redis（README §1.1 / ADR-0014）。

### 根网络

根文件 `services` = mysql / redis / backend。backend **尚未** `networks: [default, litellm-net]`（「later」）。若根栈先于网关 compose 启动：`docker network create litellm-net`。

### 事务 / 幂等 / 并发 / ORM

全部 N/A（无 OLTP 业务写；网关 Prisma 表不进 `platform_core/models`）。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM `/health/liveliness` | 3s（compose healthcheck） | retries 5 / start_period 90s | 网关挂 ≠ 主站 `/health/deep` | N/A |
| Postgres `pg_isready` | 5s | retries 20 | Proxy `depends_on: service_healthy` | N/A |

## 4. 闸输出（原样）

```
$ git ls-files deploy/litellm/config.gen.yaml

exit: 0
```

（空：0 行）

```
$ git grep -n ':latest' deploy/litellm || true
deploy/litellm/docker-compose.yml:18:#     Forbidden: :latest, main-latest, main-stable (moving tags).
```

`:latest` **1 命中，仅注释**。无镜像 tag 使用浮动 latest。

```
$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 3 条边界）
======================================
✓ R1: 硬编码连接串
✓ R2: 明文 password
✓ R3: scrapy → backend 反向依赖
✓ R4: scrapy 使用 SQLAlchemy
✓ R5: DOWNLOAD_DELAY 已配置
✓ R6: USER_AGENT 配置存在
✓ R7: API 层 import models
✓ R8: models 反向 import schemas
✓ R9: 无循环 import
✓ R10: service 方法入口缺 logger
✓ R11: backend 同步 redis_client() 直调（阻塞事件循环）
✓ R12: spider_service 门面白名单外 import（应直接依赖子 Service）
✓ R13: 租户过滤收口（安装点/裸语句/豁免清单同步）

--- 核心代码边界 ---
✓ B1: platform_core → backend/scrapy 反向依赖
✓ B2: backend → scrapy 直接依赖
✓ B3: config → 业务模块反向依赖

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 3 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

```
$ docker compose -f deploy/litellm/docker-compose.yml config -q
exit: 0
```

根 `docker compose -f docker-compose.yml config -q` 亦 exit 0。渲染后根 services = mysql / redis / backend（无 litellm）。LiteLLM 渲染镜像 = `ghcr.io/berriai/litellm:v1.100.0` + `postgres:16.10-alpine`；网络名 `litellm-net`；无 redis 服务。

跟踪树现含：`.env.example` / `.gitignore` / `README.md` / `config.yaml.example` / `docker-compose.yml`。`config.gen.yaml` 不在 `git ls-files`。

## 5. GWT

| GWT | Then（不得改写成短句） | 本票证据 |
|---|---|---|
| 75.1 | Wave L 完成后的发布物与仓库跟踪文件无 LiteLLM/上游明文 Key；网关生成配置不在跟踪树内（轮换证据在交付清单，不在本 GWT 写密钥） | ignore + 样例 `os.environ/*` + `.env.example` 占位；FR-14 两行 ✓；本票先钉运行时注入。T-20 退役后仍须保持。 |
| 75.2 | 超管打开值班页且其中有密钥相关字段 → 仅掩码或无完整上游 Key（与 T-18 同一句） | 本票保证注入侧不把完整 Key 写进可跟踪文件。页实现在 T-18。 |
| 75.3 | 租户直打值班页走 GWT-07.3，页上无密钥（与 GWT-14.3 同一句） | **T-05 / GWT-07.3**。禁止用「打开渠道页见掩码」当 Then。本票不改渠道/值班页。 |

**SH-01**：根 compose 无 litellm 服务；未把「compose 起来了」写成平台路径已切；无 DSN 抄到 backend；镜像非浮动 latest。

## 6. 可观测性 / 回滚

| 项 | 实现 |
|---|---|
| 网关探活 | 容器 healthcheck → `/health/liveliness` |
| 主站探活 | 根 backend `/health/deep` **不**依赖网关 |
| 日志 | json-file 50m × 5；密钥不入 README/证据 |
| 回滚 | `docker compose -f deploy/litellm/docker-compose.yml down` 停网关故障域；SALT **不可**当普通回滚。平台路径切换回滚在 T-20（`LLM.DATA_PLANE`）。本票未演练生产切流。 |

**日志脱敏核对**：☑ 跟踪文件无上游明文 Key ☑ 证据无 master/salt/DSN 明文

## 7. 四类易漏

| 类型 | 结果 |
|---|---|
| 事务回滚 | ➖ N/A（无多步 OLTP 写） |
| 幂等 | ➖ N/A（编排幂等 = compose up 已运行则重建策略由操作者 `up -d`） |
| 并发写 | ➖ N/A |
| 外部依赖失败 | ☑ Postgres 未 healthy 则 Proxy 不起；网关挂不红 `/health/deep` |

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/backend` T-15 | 只 HTTP：`LITELLM.BASE_URL` / `LITELLM.MASTER_KEY` / `LITELLM.TIMEOUT`。同机 `http://127.0.0.1:4000`；容器加入 `litellm-net` 后 `http://litellm:4000`。禁止 `LITELLM.DB_DSN`。 |
| `/qa` | 本票不勾 70.x 产品格。75.3 Then = GWT-07.3，不是渠道页掩码。 |
| T-16 / T-20 | 禁止把本票 compose 起来写成平台路径完成态。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] `config.gen.yaml` 不在跟踪树
- [x] `:latest` 仅注释
- [x] `tools/check/arch.sh` exit 0
- [x] `docker compose … config -q` exit 0
- [x] 根 services 无 litellm
- [x] 无硬编码真实密钥
- [x] 未代选 Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL
- [x] 票状态 **done**
