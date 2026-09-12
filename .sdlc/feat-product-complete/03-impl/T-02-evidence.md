# 实现证据 · T-02 扩我的订单读模型 + 超管确认不可逆 + 提交/确认事件

> 票：contract §11 T-02（§7.2）｜FR 锚点：FR-50（GWT-50.3/4/9/10/11/16）+ FR-92（GWT-92.1/92.2）｜角色：/backend｜日期：2026-09-11
> 依赖：T-01 已落（idempotency 键 `pending:{tenant_id}`、确认释放为 `paid:{id}` —— 本票未回退该冻结语义）

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `GET /billing/orders` 本企业单 + 元金额 + 档位名 | Service 读模型 | `backend/services/billing_service.py` | join Plan；只读也能看（读面无角色门槛） |
| `amount_yuan`（元，与定价页同一数字） | Schema 计算字段 | `platform_core/schemas/billing.py` | `amount_cents/100`；Pricing.tsx 印 ¥299/月 == 299.0 |
| `GET /billing/admin/orders` 企业名 + 金额元 | Service 读模型 | 同上 | join Plan+Tenant；仅 `require_platform_admin` |
| 确认不可逆（pending→paid 单向）+ 再确认 no-op | Service | 同上 | 状态早退；无任何回退端点；释放键语义保持 T-01 |
| 租户确认拒绝（GWT-50.9） | Router 守卫 | `backend/app/api/v1/billing.py` | 既有 `require_platform_admin`（403，SEC-5），未改 |
| `offline_order_submitted` / `offline_order_confirmed` | Service 事务后置 | `billing_service.py` | 既有 `emit_product_event` 通道（独立短会话、fail-open、`strip_secret_props`） |
| 空态（GWT-50.4） | API 返回空列表 | — | 句「还没有升级申请。」由 T-03 前端承接 |
| 事件含 tenant_id、档位名；不含明文/密钥 | Service props | 同上 | props=`{order_id, plan_name}`；tenant_id 走事件列 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象（返回 `OrderOut` DTO）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（schema 用 `computed_field` 派生，无 ORM 引用）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/schemas/billing.py` | 修改 | `OrderOut` 增 `plan_name`/`tenant_name`/`amount_yuan`（computed_field） |
| `backend/services/billing_service.py` | 修改 | 读模型 join；`create_order`/`confirm_paid` 增 `actor_user_id` 透传 + 事件上报；commit 前快照（P-BE-01） |
| `backend/app/api/v1/billing.py` | 修改 | 两处透传 `actor_user_id=user.id`（守卫与协议面未动） |
| `backend/tests/test_billing_orders_read_model.py` | 新增 | T-02 全部 GWT 红→绿（tdd：先红后实现） |

**与票里「会改哪些文件」一致**：☑ 是（billing 扩，未重写 040 骨架；未动 T-01 写规则测试）

**未触碰「不许改的文件」**：☑ 确认（未动 `test_billing_orders_write_rules.py`、未动 relay/outbound/UI、未做 T-22 查询面）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 确认：status/paid_at/释放占位键 + `_apply_plan`（骨架副作用保持） | 是 | 单写事务，与 T-01 相同 |
| 事件上报 `offline_order_submitted`/`confirmed` | 否（commit 后） | 既有 product_events 通道本身独立短会话；失败不挡主路径（GWT-92.6 验收在 T-22） |

**事务提交后的操作失败怎么办**：`emit_product_event` 内部 try/except + warning 日志（至少一次语义容忍；事件不可丢诉求由独立短会话保证不被主路径 rollback 带走）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | T-01 既定：`pending:{tenant_id}` → 确认后释放为 `paid:{order_id}` |
| 保证方式 | `orders.idempotency_key` 唯一约束（迁移 040）+ flush 捕获 IntegrityError |
| 重复请求返回 | 下单重复 → 400 `ORDER_PENDING_EXISTS`；重复确认 → 200 保持 paid（no-op，无新副作用、无重复事件） |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 确认流转 | 状态早退（`status == "paid"` 直接返回） | N/A——无并发确认叠加副作用路径；早退分支不重放 `_apply_plan` |

☑ 所有条件更新的返回行数都有处理（本票无新增条件 UPDATE）

### P-BE-01 防 MissingGreenlet

`create_order`/`confirm_paid` 在 **commit 之前**快照 `order.id`/`tenant_id`/`plan.name`，事件与响应只用快照 + 显式 `refresh(order)`。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| product_events（同库，独立短会话） | N/A | N/A | 失败 warning 不挡主路径 | 追加语义天然幂等容忍 |

## 4. ORM 与 DBML 对齐

☑ 本票**零 ORM/迁移改动**（读模型与事件只复用既有 orders/plans/tenants/product_events）——无需结构核对输出；`_apply_plan` 副作用原样保留（contract §1 技术债行：不删不改口径）。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `create_order`/`list_orders`/`list_pending_orders`/`confirm_paid` 入口 `logger.info`（R10）；确认日志增 actor |
| 事件失败 | `emit_product_event` warning（不挡主路径） |
| 脱敏 | props 仅 `order_id`/`plan_name`；无密码/token/密钥（`strip_secret_props` 兜底） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无卡号（金额为档位标价，非支付凭证）

## 6. 自测证据

> 命令与退出码原样粘贴。

```
$ uv run pytest -q backend/tests/test_billing_orders_read_model.py backend/tests/test_billing_orders_write_rules.py backend/tests/test_billing_relay.py
22 passed in 12.93s
exit: 0

$ uv run pytest -q backend/tests
1449 passed, 37 skipped, 7 warnings in 248.54s (0:04:08)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

tdd 红（实现前）：`test_gwt_50_3_my_orders_show_plan_status_amount_yuan` FAILED（读模型缺 `plan_name`/`amount_yuan`）→ 实现后同文件 9 测全绿。

共享工作树注记：期间一次全量出现 1 failed（并发泳道同刻落盘），随后连续两次全量 1449 passed/37 skipped 复核绿——失败非本票文件（本票三文件 22 passed 稳定）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-50.3 我的订单（档位名/状态/金额元/不见他企业） | `test_gwt_50_3_my_orders_show_plan_status_amount_yuan` | ✅ |
| GWT-50.4 空态（后端半：空列表 200） | `test_gwt_50_4_backend_half_empty_orders_returns_empty_list` | ✅（句由 T-03 承接） |
| 50.3 读半：只读成员也能看列表 | `test_viewer_can_read_order_list` | ✅ |
| GWT-50.9 租户确认→拒绝仍 pending 配额不变 | `test_gwt_50_9_tenant_confirm_rejected_stays_pending` | ✅（owner+viewer 双拒） |
| GWT-50.10 超管确认→租户读到已确认（完成线） | `test_gwt_50_10_admin_confirm_tenant_reads_paid` | ✅（**不断言 quota**——Then 不含履约） |
| GWT-50.11 再确认 no-op 不叠副作用 | `test_gwt_50_11_reconfirm_no_new_row_no_stacked_side_effect` | ✅（quota/expires_at/period_end/事件数四不变） |
| GWT-50.16 两张夹具 pending 都 paid 不叠档 | `test_gwt_50_16_two_fixture_pendings_both_paid_no_quota_stack` | ✅（task_concurrency=20 非 40） |
| GWT-92.1 submitted 事件 + 查询面可查 | `test_gwt_92_1_submitted_event_with_tenant_and_plan` | ✅（DB 行 + `/api/v1/product-events`） |
| GWT-92.2 confirmed 事件 | `test_gwt_92_2_confirmed_event_with_tenant_and_plan` | ✅（重复确认不重复上报在 50.11 钉住） |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无多步新事务；确认沿 T-01 单事务；事件独立会话不受主回滚影响） |
| 幂等 | `test_gwt_50_11_reconfirm_no_new_row_no_stacked_side_effect`（+ T-01 既有 `test_pending_slot_released_after_confirm`） | ✅ |
| 并发写 | ➖ N/A（重复确认早退无副作用窗口；单 pending 唯一约束在 T-01 已验） |
| 外部依赖失败 | ➖ N/A（无新增外部依赖；事件 fail-open 验收归 T-22/GWT-92.6） |

## 7. NFR 验证

本票无 NFR 行（NFR-08 事件仅超管可查沿既有查询面守卫，未改动）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/frontend`（T-03） | ① `GET /billing/orders` 现回 `plan_name`（档位名）、`status`（pending/paid）、`amount_yuan`（元，专业档=299，与定价页同一数字）、`amount_cents`（兼容保留）。② 空态后端回空列表，句「还没有升级申请。」在前端渲染。③ `GET /billing/admin/orders` 增回 `tenant_name`（运营台看企业名）。④ 确认成功响应 `data.status=="paid"`、`paid_at` 非空；重复确认也回 200 paid（幂等）。 |
| `/qa` | ① 50.10 验收**不得**断言配额三数字（Q-PRICE）；`_apply_plan` 副作用仍在跑（骨架保留），但不在 Then 内。② 事件 props=`{order_id, plan_name}`，tenant_id 在事件列（查询面按 `event_name`+`tenant_id` 过滤）。③ 重复确认（跨请求）只产生一条 `offline_order_confirmed`。④ SQLite 测试库验证；MySQL 方言复核通道同 T-01 注记。 |
| `/architect` | 无新契约歧义。`OrderOut` 增 `plan_name`/`tenant_name`/`amount_yuan` 三字段是 §7.2「金额元 + 档位名称 + 运营台企业名」的直接落位，请追认进契约 API 面。 |
| `/backend`（T-22） | 两事件已挂（提交/确认路径）；T-22 只需验 fail-open 与查询面 404 同形，勿重复挂事件。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（本票 22 passed；全量 1449 passed/37 skipped）
- [x] 契约落位表已核对，分层无违规（arch.sh exit 0）
- [x] ORM 与 DBML 一致，未自行加字段（零 ORM 改动）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（事件通道异步；无 redis）
- [x] 无 `except: pass`（吞异常仅在既有 emit fail-open，带 warning 日志）
- [x] 日志已脱敏
- [x] 事务里无外部调用（事件在 commit 后）
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（本票无新增条件 UPDATE）
- [x] 外部依赖四件套（同库通道，降级=不挡主路径；其余 N/A 已注）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8）
- [x] T-01 冻结语义（释放占位键）未回退；50.10 Then 未写入配额履约
