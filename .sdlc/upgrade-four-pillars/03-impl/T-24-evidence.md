# 实现证据 · T-24 通知入口、密钥不进镜像、通道失败可观测

> 票：`02-shape/contract.md` §10 T-24｜FR 锚点：FR-U31 FR-U38 NFR-U03｜角色：/sre｜日期：2026-09-12
> 上游：T-15 凭据加密｜T-17 无 JWT notify 验真｜T-16/T-19 未配置空态｜T-22 事件查询
> 下游：`06-deliver/checklist.md` **N3 段**（N1 段保留）
> 本票 **不改业务代码**、不改 schema、不跑支付宝/微信 live 沙箱、不写「亲爱的用户」

合入闸 = pytest 夹具 + 架构/迁移 + 密钥扫描。**live 沙箱不是合入闸。**

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /api/v1/billing/notify/alipay` 无 JWT | Router（已有，T-17） | `backend/app/api/v1/billing.py` `channel_notify` | 无 `Depends(get_current_user)`；通道 IP 不带 Bearer |
| `POST /api/v1/billing/notify/wechat` 无 JWT | 同上 `{channel}` | 闭集 `OnlinePayChannel` | 静态段先于 `/orders/{id}`（PIT-1） |
| 通道 IP 可达 | 反代笔记，非应用 | `06-deliver/checklist.md` §N3-8 | 根 compose 钉 `127.0.0.1:9111`，实验室通道 IP 打不进；生产精确 location、禁止 `auth_request` |
| 商户密钥仅 DB 密文 | 表 046 + 超管 PUT | `payment_channel_credentials.secrets_encrypted` | 不进 compose / Dockerfile / git / `.env.example` |
| vault 主密钥 | 运行时环境 | `LLM_ENCRYPTION_KEY` | 与 LLM 保险库同一把；**不是**商户明文 |
| 未配置 / 失败可观测 | 日志 + 事件 | `service.payment_notify` / `payment_failed` | 不记密钥/`sign`；失败 HTTP 200 |
| 单通道挂、另一通道可选 | 结账 preview | T-16/T-19 | 「该通道未开通」；两通道空态「收款通道未开通」非 5xx |
| live 沙箱 | ➖ 排除 | — | FR-U38 不选算法/回调形态；夹具四要素即合入证据 |

**分层依赖核对**：☑ 本票未改 Router/ORM/Schema ☑ 未新增 yml 商户键 ☑ 未把 notify 挂进 `deploy/litellm` 或 `deploy/newapi` nginx 示例

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `.sdlc/upgrade-four-pillars/06-deliver/checklist.md` | 修改 | **追加 N3 段**；N1 正文不动 |
| `.sdlc/upgrade-four-pillars/03-impl/T-24-evidence.md` | 新增 | 本文件 |
| `.sdlc/upgrade-four-pillars/memory/sre.md` | 修改 | N3 事实 |

**与票里「会改哪些文件」一致**：☑ 是（sre 交付物 = checklist + 证据；compose/nginx **笔记**写在 checklist §N3-8，仓库无根 nginx 可改）

**未触碰「不许改的文件」**：☑ 确认（未改 GWT / 046 / billing.py / 凭据服务；未加 `ALIPAY_*` env；未写用户公告）

## 3. 关键实现决策

本票核对既有入口，不新写履约。通知验真/开通仍是 T-17；凭据加密仍是 T-15。

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 本票无新写路径 | ➖ N/A | 运维核对 |

**事务提交后的操作失败怎么办**：➖ N/A

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 既有 `order_no`（T-17 CAS） |
| 保证方式 | 本票不改 |
| 重复 notify | 已 fulfilled 不叠加；HTTP 仍 200 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无本票条件更新 | — | T-17 CAS 已处理 |

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 支付宝/微信 live | ➖ 不接 | 通道重投由我方 200 + CAS | 未配置/验真失败人话或 200 不开通，不是 5xx | 我方按订单号开通一次 |
| 根 compose 反代 | 无 nginx 服务 | — | 实验室只绑 127.0.0.1 | — |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM / 迁移 / schema.dbml。046 由 T-14 落地。

结构核对输出：

```
$ bash tools/check/db_migrations.sh
迁移破坏性变更检测（strong_migrations 语义）
==============================================
✓ 迁移破坏性变更检测通过
db_migrations_exit:0
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `api.billing`「通道通知 \| channel= order_no=」；`service.payment_notify` 验真/缺字段/无凭据/非真通知/商户金额订单号不符/迟到 |
| 业务指标 | 超管 `GET /api/v1/product-events?event_name=payment_succeeded\|payment_failed`（T-22）；`reason` 闭集 |
| 失败探针 | **不能**用 notify 5xx：验真失败合同是 200。5xx/401 才是入口事故 |
| 脱敏 | 日志不打印密钥/`sign`/PEM；事件 props 仅 channel/product/tenant_id/reason；GET 凭据掩码 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无商户密钥全文 ☑ 无完整 PEM

compose/nginx 笔记（全文）：`06-deliver/checklist.md` §N3-8。摘要：

- 根 compose `backend.environment` 无 `ALIPAY_*` / `WECHAT_*`；Dockerfile `ENV` 只有 `APP_ENV` 与 `AUTO_AGENTS_API__HOST`。
- 生产反代 `location = /api/v1/billing/notify/alipay` 与 `.../wechat`：无 JWT、建议 `limit_req`、可选 CIDR（CIDR **不是**合入闸）。
- `deploy/litellm` / `deploy/newapi` 的 nginx 示例是网关 SSE，**不要**拿来挂 billing。

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

### 6.1 无 JWT 通知 vs 结账匿名 401；未配置空态；密钥不进 yml

`post_notify`（`backend/tests/payment_notify_support.py`）不设 `Authorization`。`channel_notify` 形参无 `user`。

```
$ uv run python - <<'PY'
from inspect import signature
from backend.app.api.v1.billing import channel_notify, create_checkout, preview_checkout
for fn in (channel_notify, create_checkout, preview_checkout):
    print(fn.__name__, [p.name for p in signature(fn).parameters.values()])
print('channel_notify_has_user', 'user' in signature(channel_notify).parameters)
PY
channel_notify: ['channel', 'payload', 'service']
create_checkout: ['payload', 'user', 'session', 'service']
preview_checkout: ['product', 'user', 'service']
channel_notify_has_user False
```

```
$ uv run pytest -v --tb=no \
    backend/tests/test_fr_u33_notify.py::test_gwt_u33_1_plan_pro_opens_pro_not_relay \
    backend/tests/test_fr_u33_notify.py::test_gwt_u38_3_missing_sign_stays_pending \
    backend/tests/test_fr_u31_payment_credentials.py::test_gwt_u31_4_secret_not_in_config_or_git \
    backend/tests/test_fr_u30_checkout.py::test_gwt_u32_1_unconfigured_channel_pending_then_unpaid \
    backend/tests/test_fr_u30_checkout.py::test_gwt_u32_2_get_both_unconfigured_200_empty_no_order \
    backend/tests/test_fr_u30_checkout.py::test_one_channel_unconfigured_other_selectable \
    backend/tests/test_fr_u30_checkout.py::test_gwt_u36_3_anonymous_no_order

backend/tests/test_fr_u33_notify.py::test_gwt_u33_1_plan_pro_opens_pro_not_relay PASSED
backend/tests/test_fr_u33_notify.py::test_gwt_u38_3_missing_sign_stays_pending PASSED
backend/tests/test_fr_u31_payment_credentials.py::test_gwt_u31_4_secret_not_in_config_or_git PASSED
backend/tests/test_fr_u30_checkout.py::test_gwt_u32_1_unconfigured_channel_pending_then_unpaid PASSED
backend/tests/test_fr_u30_checkout.py::test_gwt_u32_2_get_both_unconfigured_200_empty_no_order PASSED
backend/tests/test_fr_u30_checkout.py::test_one_channel_unconfigured_other_selectable PASSED
backend/tests/test_fr_u30_checkout.py::test_gwt_u36_3_anonymous_no_order PASSED

============================== 7 passed in 2.12s ===============================
exit: 0
```

### 6.2 deploy/ 与镜像 env 商户密钥扫描（无命中 = rg exit 1）

```
$ rg -n -i --hidden --glob '!**/postgres-data/**' \
    'ALIPAY_|WECHAT_PAY|WECHAT_MCH|alipay_private_key|alipay_app_secret|wechat_mch_key|wechat_api_v3_key|wxpay_key|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
    deploy docker-compose.yml Dockerfile .env.example config
(no matches)
rg_exit:1
```

```
$ git grep -n -i -E 'alipay_private_key|alipay_app_secret|wechat_mch_key|wechat_api_v3_key|wxpay_key|ALIPAY_|WECHAT_PAY|WECHAT_MCH' \
    -- '*.yml' '*.yaml' '*.env' '*.example' 'docker-compose.yml' 'Dockerfile'
git_grep:no_hits
```

根 compose 实际注入的键（无商户）：`AUTO_AGENTS_API__HOST/PORT`、`MYSQL/REDIS` 主机与密码、`JWT__SECRET_KEY`、`WEBHOOK__SECRET_KEY`。Dockerfile `ENV APP_ENV=prod AUTO_AGENTS_API__HOST=0.0.0.0`。

### 6.3 迁移门禁

见 §4。046 抛开库 up-down-up：T-14 `udup_exit:0`。

### 验收项逐条对应

| GWT / NFR | 覆盖 | 结果 |
|---|---|---|
| FR-U31.4 密钥不进 git/默认配置/镜像 env | U31.4 + deploy/compose rg | ✅ |
| FR-U38 未验真不开通 | U38.3 无 JWT 缺签 200、不开通 | ✅ |
| 通知入口无 JWT、通道可打 | `channel_notify` 无 user；U33.1 无 Bearer 200 | ✅ 实验室 127.0.0.1；生产反代笔记 §N3-8 |
| NFR-U03 单通道未配 | U32.1 + `test_one_channel_unconfigured_other_selectable` | ✅ 另一通道仍可选；非 5xx |
| NFR-U03 两通道空态 | U32.2 GET 200「收款通道未开通」 | ✅ |
| 失败可观测、不泄密 | T-17 日志字段；T-22 `payment_failed.reason` | ✅ |
| live 沙箱 | — | ➖ **故意不跑、不合入闸** |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 本票无新写；U38.3 零履约 | ➖ N/A（运维票）/ ✅ 既有 |
| 幂等 | T-17 U33.6 | ✅ 引用 |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | live 沙箱不接；未配置/缺签降级 200 或人话 | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U03 | 单通道「该通道未开通」、另一可选；两通道「收款通道未开通」非错误页 | U32.1/U32.2/one_channel；T-19 UI | pytest / Jest（T-19） |
| NFR-U04 / FR-U31 | 密文落库、不进 git/compose | rg 无命中；U31.4 | 源码 + git |
| NFR-U04 / FR-U38 | 四要素否则不开通 | U38.3 无 JWT | pytest |
| NFR-U08 | 失败可查、无 succeeded | T-22 U37.6 | pytest |
| — | 合入不要求 live 沙箱 | 本清单显式 ➖ | 发布清单 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 覆盖矩阵 N3 行勿再标「未实现豁免」时，用 T-15/T-16/T-17/T-22 + 本票扫描。**不要**加 live 沙箱 job。无 JWT 针：`POST /api/v1/billing/notify/alipay` 无 `Authorization` 不得 401。 |
| `/qc` | 检查清单 N3 段；放行仍由 qc。阻塞项只有冻结 SHA 四闸（沿 N1），不是沙箱。 |
| `/ops` | 本帽无用户公告。空态句已在产品里，不要另写「亲爱的用户」。 |
| `/backend` | [SEC-7] 应用层仍无 notify `RateLimitPolicy`；本票把限流放在反代笔记，未改 `rate_limiter.py`。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（七条 + 扫描无命中 + db_migrations 0）
- [x] 契约落位表已核对；本票未改分层代码
- [x] ORM 与 DBML 未动
- [x] 无硬编码商户密钥/端口进 compose
- [x] 日志脱敏（引用 T-17，本票扫描 env）
- [x] 四类易漏已覆盖或标 N/A
- [x] 发现的限流残差已回报，未自行改业务代码
- [x] 无 `tickets/T-24.md`；checklist N3 + 本证据即交票物
- [x] 未要求 live 沙箱合入
- [x] 未写「亲爱的用户」
