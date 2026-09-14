# 实现证据 · T-22 payment_succeeded/payment_failed 超管可查

> 票：`02-shape/contract.md` §10 T-22｜FR 锚点：FR-U37｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/product-events` | Router | `backend/app/api/v1/product_events.py` | 既有超管查询；本票不新开路径 |
| event_name / tenant_id / 发生时间 | Service | `ProductEventService.query` | 按 occurred_at 倒序 |
| 权限（仅超管；租户 404 同形） | Router 守卫 | `require_platform_admin_or_404` | GWT-U37.3 = GWT-U03.3 同一句 |
| props：channel/product；失败 reason | Service 写入 | T-17 `emit_product_event` | 禁止密钥/口令 |
| 数据读写 | Repository | `product_event_repository` | 至少一次；失败不挡 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/tests/test_fr_u37_payment_events.py` | 新增 | GWT-U37.1…U37.8 |
| `backend/tests/payment_notify_support.py` | 新增 | 与 T-17 共用夹具 |
| T-17 履约/emit | 依赖 | 本票查询面不改守卫 |

**与票里「会改哪些文件」一致**：☑ 查询面沿用既有叶；本票钉支付事件可查与脱敏。

**未触碰「不许改的文件」**：☑ 确认（未改 GWT；未加密钥列；无「当前可买」。）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 支付事件写入 | 否（独立短会话） | 既有 emit；GWT-U37.7 在开通 commit 前即可查 |
| 超管查询 | 只读 | 无写 |

**事务提交后的操作失败怎么办**：事件 fail-open（既有）。查询不到开通失败用单据对账，不挡主路径。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 产品事件表仍至少一次（ADR-0016） |
| 保证方式 | 开通精确一次在 T-17 CAS；事件允许至少一次 |
| 重复查询 | 只读，无副作用 |

☑ 查询未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 本票只读 | — | N/A |

☑ 无本票条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无 | — | — | 租户直打 404 同形，不泄事件 | N/A |

## 4. ORM 与 DBML 对齐

☑ 未加列。`product_events.props` JSON 含 `channel`/`product`/`tenant_id`/`reason`；`strip_secret_props` 仍剥 token/password。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 既有 `query_product_events` 记 name；T-17 emit 记事件名+tenant |
| 脱敏 | 断言响应无商户密钥、无 `secrets_encrypted`、无算法名 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无密钥全文 ☑ 租户 404 零事实泄露

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_fr_u37_payment_events.py
........                                                                 [100%]
8 passed in 2.81s
T22_EXIT:0
```

```
$ uv run pytest -x -q backend/tests
1669 passed, 40 skipped, 7 warnings in 166.58s (0:02:46)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
ARCH_EXIT:0
```

```
$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
LAYER_EXIT:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U37.1 正常 | `test_gwt_u37_1_succeeded_queryable_with_channel_product` | ✅ tenant_id + channel + product |
| GWT-U37.2 取消 | `test_gwt_u37_2_cancel_failed_no_succeeded` | ✅ reason=cancel；无 succeeded |
| GWT-U37.3 越权 | `test_gwt_u37_3_tenant_404_same_shape` | ✅ HTTP_404 / Not Found；非抱歉 403 |
| GWT-U37.4 超时 | `test_gwt_u37_4_timeout_failed_event` | ✅ reason=timeout |
| GWT-U37.5 通道失败 | `test_gwt_u37_5_channel_error_failed_plan_unchanged` | ✅ reason=channel_error；档位未开 |
| GWT-U37.6 未配置 | `test_gwt_u37_6_unconfigured_failed_no_succeeded` | ✅ reason=unconfigured；unpaid |
| GWT-U37.7 开通前可查 | `test_gwt_u37_7_succeeded_visible_before_fulfill` | ✅ paid_pending 时已有 succeeded |
| GWT-U37.8 仅打开结账 | `test_gwt_u37_8_open_checkout_no_payment_events` | ✅ 无新支付事件、无单据 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 未配/伪造不产生 succeeded | ✅ T-17 + U37.6 |
| 幂等 | 查询只读 | ➖ N/A（无写） |
| 并发写 | — | ➖ N/A（查询面） |
| 外部依赖失败 | — | ➖ N/A（无 SDK） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U08 | 仅超管按发生时间可查；未验真无 succeeded | U37.1/3/7 + U38.3 | pytest |
| FR-U24 | 无「当前可买」 | 事件 JSON 断言 | pytest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | `GET /api/v1/product-events?event_name=payment_succeeded\|payment_failed&tenant_id=`。props.channel ∈ alipay/wechat；product ∈ plan_pro/plan_enterprise/relay；failed.reason 闭集。租户直打与 `/api/v1/admin/tenants` 同形 404。 |
| `/frontend` | 租户无支付事实查询面。超管用既有产品事件页即可，无需新路由。 |
| `/analyst` | 支付成功是驱动；U37.7 开通完成不是该事件前置。 |
| `/architect` | 未新增查询过滤字段（channel/product 在 props 内）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口
- [x] props 无密钥
- [x] 租户 404 同形
- [x] 未写「当前可买」
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
