# LiteLLM Proxy Sidecar（L1 影子接入）

> 状态：**影子模式（L1）**——只读对比，不接任何生产流量；回滚 = 移除 compose 服务。
> 决策出处：`.scratch/p0-p1-2026-09/product-review.md` 任务二（new-api → LiteLLM 五票路线）。

## 1. L1 范围

| 交付物 | 位置 |
|---|---|
| compose 服务（默认不启动） | `docker-compose.yml` 的 `litellm` 服务（`profiles: ["litellm"]`） |
| 配置导出器 + CLI | `backend/services/litellm/exporter.py` + `backend/scripts/export_litellm_config.py` |
| 影子只读对比器 | `backend/services/litellm/shadow.py`（零外呼，不发真实 LLM 调用） |
| 镜像版本守卫红测 | `backend/tests/test_litellm_version_guard.py`（compose 变更时红） |
| 配置 | `config/default/litellm.yml`（`LITELLM.*`） |

**不在 L1 范围**：python SDK 嵌入主 venv（已决策暂缓）、LiteLLM DB/虚拟键（L3）、
new-api 任何改动（L5 才退役）、内部调用切流（L4）。

## 2. 镜像版本与查证记录（供应链红线）

- **pin**：`litellm/litellm-database:v1.99.1`
- **查证（2026-09-05，Docker Hub Registry API `hub.docker.com/v2/repositories/litellm/litellm-database/tags`）**：
  - `main-stable` digest = `sha256:e9842aba4cb42ca5502310217b41dbbfd7ddf1ff9c97a99382651bbd5d456220`，
    与 `v1.99.1` digest **完全一致**（同一推送 2026-09-02T03:11:40Z）→ 官方当前
    stable 指针即 1.99.1；
  - 最新 patch `v1.97.2`（2026-09-03）为稳定系列分支，非 main-stable 指向，未选；
  - **黑名单验证**：恶意版本 `1.82.7` / `1.82.8` tag 在 Docker Hub 已 404（下架痕迹），
    但下架 ≠ 防回归——守卫红测锁死黑名单；
- **守卫**：`test_litellm_version_guard.py` 解析 `docker-compose.yml`，断言精确语义
  版本 pin（拒 latest / main-stable / dev / 浮动前缀 / digest-only）且不在
  `{1.82.7, 1.82.8}`。**改 compose 里的 litellm 镜像 tag 前先过守卫。**

## 3. 开启方式

```bash
# ① 生成配置（读 llm_providers enabled 行 + models 子表 → 静态 config.yaml）
uv run python backend/scripts/export_litellm_config.py
#   无可用供应商时：生成空 model_list + 警告 + 退出码 1（失败可回退）
#   --redacted-sample 可输出脱敏样例（key 掩码）用于工单/日志留证

# ② 显式开启 profile 启动 sidecar（默认 up 不含它）
docker compose --profile litellm up -d litellm

# ③ 健康探测（liveliness = 进程存活浅探测，无需鉴权）
curl -s http://127.0.0.1:4000/health/liveliness
```

生成文件：`deploy/litellm/config.gen.yaml`（**含明文 API Key，已 gitignore，权限 0600**）。
刷新 = 重新跑 ①（覆盖写）；供应商增删/改 key/换模型后需重跑再 `docker compose
--profile litellm restart litellm`。

## 4. 影子只读对比器（零外呼）

`backend/services/litellm/shadow.py`：输入「自研候选链对某请求的供应商选择
（`capture_self_side_choice`：复用 `llm_common.resolve_runtime_config` +
`ai_planner._candidate_chain` + `_cooldown`）」与「导出的 config」，输出两侧
路由决策对照表（`model→provider` 映射差异、cooldown 状态差异）。**只读对比，
不发起任何真实 LLM 调用、不连接 proxy**。

## 5. 回滚

```bash
docker compose --profile litellm down litellm   # 停 sidecar
# 删除 docker-compose.yml 的 litellm 服务块（守卫红测随之转为「未接入」——
# 若需保留守卫请同步删 test_litellm_version_guard.py 的真实 compose 用例）
```

零生产流量变更：影子阶段不改任何现有请求路径，自研直连路径（ai_planner）原样。

## 6. 与 L2-L5 的衔接

| 票 | 衔接点 |
|---|---|
| L2 渠道配置面切换 | 导出器扩展为 Admin API 下发（治理层只走 Admin API，禁直连 LiteLLM 库）；`backend/services/litellm/` 子包是配置生成的事实源 |
| L3 虚拟键+计费对账 | sidecar 加 LiteLLM 专用 Postgres + virtual keys/budgets；本仓 MySQL 保持唯一业务事实源，spend → `llm_token_usage` 对账 |
| L4 内部调用切流 | `llm_common.runtime` 加 PROXY 路由开关（feature flag）；shadow.py 的对照表是 A/B 质量对比的基线工具 |
| L5 退役清理 | new-api 全残留删除（本票零 new-api 改动） |

## 7. 已知差异（L1 只记录不解决）

**cooldown 分层共存**：自研 cooldown（`ai_planner/_cooldown.py`，提交 292ca81）是
Redis 计数——跨进程共享、键 = provider+model、连通成功清零，作用于**内部直连路径**；
LiteLLM router 的 `allowed_fails`+`cooldown_time` 是 **proxy 进程内存态**（多副本不共享），
作用于**中转站路径**。两者分层共存；shadow.py 对照表对冷却态差异标
`known_layering=True`（记录维度，不算配置错误）。是否在 proxy 路径关自研冷却层是
L4 的 ADR 决策点。

其余已知边界：非 `openai_compatible` 协议（anthropic / google_gemini）的映射前缀
已生成但**影子验收范围仅 openai 兼容路径**；master key 未引入（sidecar 仅绑定
127.0.0.1，L2 接治理层时再加）。
