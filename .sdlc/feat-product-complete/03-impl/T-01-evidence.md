# 实现证据 · T-01 扩线下订单写规则：在线零单、单 pending、角色找管理员

> 票：contract §11 Wave C 首行（T-01）｜FR 锚点：FR-50（GWT-50.2/50.5/50.7/50.8/50.14/50.15）+ spec §3.1 线下升级申请流转与非法流转表｜角色：/backend｜日期：2026-09-11｜lane: api

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /billing/orders` 路径/方法/201 | Router | `backend/app/api/v1/billing.py` | 协议转换；201 信封 message 带「等待管理员确认收款」（GWT-50.2 提示） |
| 字段校验（plan_id/channel 枚举） | Schema | `platform_core/schemas/billing.py` | `OrderCreate` 已有 Literal 枚举，本票零改动 |
| 角色判定（谁能下单） | **Service** | `backend/services/billing_service.py::_assert_order_allowed` | 业务规则（GWT-50.7/50.8 的 Then 是业务拒绝句，不是 403），Router 依赖从 `require_tenant_manager` 换 `get_current_user`，把 `user.tenant_role` 传入 Service |
| 在线通道零新行 | Service | 同上 | alipay/wechat 在任何写库前抛业务拒绝；`payment_provider.UnconfiguredOnlineProvider` 类保持不动（contract §1 约束「保持」） |
| 单 pending 判重 | Service + 唯一约束 | `create_order` + 迁移 040 `orders.idempotency_key UNIQUE` | 业务键 `pending:{tenant_id}` 写入该列，靠唯一约束兜底，**非先查后插**；确认 pending→paid 时释放为 `paid:{order_id}`（「同一时刻最多一张」语义） |
| 错误码映射 | 统一异常处理器 | `platform_core/exceptions/handlers.py`（未改） | 全部走 `BusinessException` → 稳定 code + 中文 message |
| 幂等 | Service + 唯一约束 | 约束 `orders.idempotency_key`（040 已有，**无新迁移**） | 重复请求 → 400 `ORDER_PENDING_EXISTS` |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象（返回 `OrderOut`）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/billing_service.py` | 修改 | `create_order` 加 role 参数 + 角色拒绝 + 在线通道拒绝 + `idempotency_key=pending:{tid}` + IntegrityError→`ORDER_PENDING_EXISTS`；`confirm_paid` 在 pending→paid 时释放占位键；新增 `_assert_order_allowed` 辅助（保单函数 ≤40 行） |
| `backend/app/api/v1/billing.py` | 修改 | `create_order` 依赖换 `get_current_user`、传 `user.tenant_role`；201 message 带「等待管理员确认收款」；移除 `require_tenant_manager` import |
| `backend/tests/test_billing_orders_write_rules.py` | 新增 | 9 测：GWT-50.2/50.5×2/50.7/50.8/50.14/50.15 + §3.1 免费档 + 确认后释放占位键 |
| `backend/tests/test_billing_relay.py` | 修改 | PIT-2 改守卫同 PR 改金标：alipay 断言从 `code==PAYMENT_NOT_CONFIGURED` 改为零新行+中文句+无该内码；viewer 下单从 403 改为找管理员句+无单 |

**与票里「会改哪些文件」一致**：☑ 是（billing 写规则 + 既有金标测试；`payment_provider.py`、`_apply_plan`、relay、outbound、market、auth 均未动）

**未触碰「不许改的文件」**：☑ 确认（`_apply_plan` 原样；`UnconfiguredOnlineProvider` 原样；无 tickets/*.md；git status 里其余改动属并行批他票）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 订单插入 + 占位键 | 是（单行单事务，flush→commit） | 单表写；IntegrityError 在 flush 即暴露，rollback 后抛业务异常 |
| 确认（状态+释放键+`_apply_plan`） | 是（沿用既有 confirm 事务） | 本票只追加「释放键」一行，不改事务形状 |

**事务提交后的操作失败怎么办**：无新增外部调用；`OfflinePaymentProvider.collect` 只是日志 + 返回（沿骨架现状）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键「同一企业同一时刻最多一张 pending」→ `idempotency_key = "pending:{tenant_id}"`（040 已有列与 UNIQUE 约束，零迁移） |
| 保证方式 | 唯一约束 `orders.idempotency_key` + 捕获 `IntegrityError`（flush 即检）→ rollback → `ORDER_PENDING_EXISTS` |
| 重复请求返回 | 400 `ORDER_PENDING_EXISTS` +「已有待确认的升级申请」（GWT-50.15：不产生第二张、原单保持） |
| 释放 | 确认 pending→paid 时改写为 `paid:{order_id}`——「同时最多一张」不是「史上最多一张」；T-02 重写确认时不得回退该语义（变异 4 证明该行为负载） |

☑ 未使用「先查后插」（判重完全靠约束；约束前的角色/通道/档位拒绝都在写库前）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 并发双提交（两请求同企业同时建 pending） | 唯一约束互斥，后到者 flush 抛 IntegrityError | 捕获 → rollback → 400 `ORDER_PENDING_EXISTS`（即 GWT-50.15 文案） |

☑ 所有条件更新的返回行数都有处理（本票无条件更新语句；确认走状态早退，T-02 范围）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新增外部依赖（offline provider 仅日志） | ➖ | ➖ | ➖ | ➖ |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 本票 **零模型/零迁移改动**，只复用 040 已有 `orders.idempotency_key String(64) NULL UNIQUE`。

结构核对输出（无迁移，以约束在测试库真实生效为准——`test_gwt_50_15` 的 IntegrityError 路径即证明）：

```
$ grep -n "idempotency_key" backend/alembic/versions/040_billing_and_relay_sku.py
60:        sa.Column("idempotency_key", sa.String(length=64), nullable=True, comment="防重复下单"),
64:        sa.UniqueConstraint("idempotency_key"),
exit: 0
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `create_order` 记 `tenant/role/plan/channel`（R10，role 无敏感信息）；`confirm_paid` 原有 `order=` 保留 |
| trace_id | 既有异常处理器 `request_id`（未改） |
| 错误日志上下文 | 拒绝路径经 `app_exception_handler` 记 `code/message`（4xx 级 warning） |
| 慢操作耗时 | 无慢路径（单表写） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无卡号（日志仅 tenant_id/plan_id/channel/role）

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

### TDD 红（对改动前代码跑新测试文件；用 `git stash push -- <两个产品文件>` 后复跑，复现与首跑同失败集）

```
$ uv run pytest -q backend/tests/test_billing_orders_write_rules.py
FAILED backend/tests/test_billing_orders_write_rules.py::test_gwt_50_2_owner_offline_pro_creates_single_pending
FAILED backend/tests/test_billing_orders_write_rules.py::test_gwt_50_5_online_channel_creates_no_order
FAILED backend/tests/test_billing_orders_write_rules.py::test_gwt_50_7_viewer_cannot_order_sees_contact_admin
FAILED backend/tests/test_billing_orders_write_rules.py::test_gwt_50_8_operator_cannot_order_sees_contact_admin
FAILED backend/tests/test_billing_orders_write_rules.py::test_gwt_50_15_second_pending_rejected
FAILED backend/tests/test_billing_orders_write_rules.py::test_pending_slot_released_after_confirm
6 failed, 3 passed in 6.74s
exit: 1
```

失败原因逐条（红=对正确 oracle 的断言失败，非导入/夹具错误）：
- 50.2：`assert "等待管理员确认收款" in message`（旧 message=「创建成功」）+ `rows[0]["key"] == f"pending:{tid}"`（旧为 None）
- 50.5a：`assert body["code"] != "PAYMENT_NOT_CONFIGURED"`（旧即抛该码）
- 50.7/50.8：`assert body["code"] not in _FORBIDDEN_CODES`（旧 403 FORBIDDEN）+ 找管理员句缺失
- 50.15：`assert resp.status_code == 400`（旧二次提交 201、产生第二张）
- 释放：`assert rows[1]["key"] == f"pending:{tid}"`（旧不写键）

### TDD 绿

```
$ uv run pytest -q backend/tests/test_billing_orders_write_rules.py backend/tests/test_billing_relay.py
.............                                                          [100%]
13 passed in 8.53s
exit: 0
```

### 变异红（3 个「生而绿」测试 + 释放机制，各一次「拆守卫→红→复原→绿」）

```
$ # MUTATION-1：禁用在线通道拒绝（_assert_order_allowed 中 if False and channel in ...）
$ uv run pytest -q ...::test_gwt_50_5_online_channel_creates_no_order ...::test_gwt_50_5_online_keeps_existing_pending
>       assert resp.status_code == 400
E       assert 201 == 400
E       AssertionError: assert '在线支付尚未开通' in '已有待确认的升级申请'
2 failed in 5.41s
exit: 1
（复原后绿）

$ # MUTATION-2：放行非公开档（if plan is None or (not plan.is_public and False)）
$ uv run pytest -q ...::test_gwt_50_14_enterprise_no_sku_no_order
E       assert 201 == 404        # 企业档（is_public=0）被下单成功 = 假装第三档
1 failed in 3.27s
exit: 1
（复原后绿）

$ # MUTATION-3：禁用免费档拒绝（price<=0 and False）
$ uv run pytest -q ...::test_free_plan_order_rejected
E       assert 201 == 400        # 免费档被下单成功
1 failed in 2.13s
exit: 1
（复原后绿）

$ # MUTATION-4：确认后不释放 pending 占位键（pass 替代 key 改写）
$ uv run pytest -q ...::test_pending_slot_released_after_confirm
E       AssertionError: {"success":false,"code":"ORDER_PENDING_EXISTS","message":"已有待确认的升级申请",...}
E       assert 400 == 201        # 已确认企业被永久锁死，无法再申请
1 failed in 4.83s
exit: 1
（复原后绿）
```

### 全量回归 + 架构 + lint

```
$ uv run pytest -x -q backend/tests
1365 passed, 36 skipped, 7 warnings in 276.36s
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend/services/billing_service.py backend/app/api/v1/billing.py backend/tests/test_billing_orders_write_rules.py backend/tests/test_billing_relay.py
All checks passed!
exit: 0
```

注：本批为并行票共享工作树。全量首跑曾两次被**他票在途文件**打断（`test_db_fixtures.py` 允许清单被 T-04 并发编辑；`test_outbound_migration_041.py` 缺 fidelity skip 守卫），均非本票回归——T-04 侧补齐后同命令即 exit 0（上行粘贴为终态）。`--ignore` 该文件的中跑为 `1374 passed, 35 skipped, exit 0`。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-50.2 正常·token 满申请 | `test_gwt_50_2_owner_offline_pro_creates_single_pending` | ✅（pending 单、档位=pro、channel=offline、提示等待确认、无已支付单、配额不变） |
| GWT-50.5 边界·在线通道 | `test_gwt_50_5_online_channel_creates_no_order` + `test_gwt_50_5_online_keeps_existing_pending` | ✅（零新行含零 pending；原 pending 保持；中文句；无 `PAYMENT_NOT_CONFIGURED`） |
| GWT-50.7 越权·只读 | `test_gwt_50_7_viewer_cannot_order_sees_contact_admin` | ✅（零单、找管理员句、无 FORBIDDEN/QUOTA_EXCEEDED/QUOTA_PLAN_LOCKED/裸 429、套餐不变） |
| GWT-50.8 越权·经办下单 | `test_gwt_50_8_operator_cannot_order_sees_contact_admin` | ✅（同上） |
| GWT-50.14 边界·企业档无 SKU | `test_gwt_50_14_enterprise_no_sku_no_order` | ✅（公开价目仅 free/pro；企业档/幽灵 id 提交零申请） |
| GWT-50.15 边界·第二张 pending | `test_gwt_50_15_second_pending_rejected` | ✅（`ORDER_PENDING_EXISTS`、单张、原单 pending、配额不变） |
| §3.1 非法流转·免费档 | `test_free_plan_order_rejected` | ✅（`ORDER_FREE_PLAN` + 零申请） |
| §3.1「同一时刻」语义 | `test_pending_slot_released_after_confirm` | ✅（确认释放键后可再申请；GWT-50.16 夹具前置机制） |

既有 `test_billing_relay.py` 四测：**不勾 FR-50 完成**——已按新口径改写其中两条断言（在线通道/只读），确认收款与 `_apply_plan` 断言保留为骨架回归，FR-50 完成线在 T-02/T-03（「我的订单能看见已确认」）。

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | `test_gwt_50_15_second_pending_rejected`（IntegrityError→rollback→无残留行） | ✅ |
| 幂等 | `test_gwt_50_15_second_pending_rejected`（约束判重，非先查后插） | ✅ |
| 并发写 | ➖ N/A：判重由数据库唯一约束串行化，两并发提交必然后到者撞约束（等价于 50.15 路径）；异步双事件循环夹具下真并发注入本仓无既有模式，不为验收新造 |
| 外部依赖失败 | ➖ N/A：本票无外部依赖（offline provider 仅日志） |

## 7. NFR 验证

票内无 NFR 条目。➖

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① SQLite 测试库验证；MySQL 方言下 `idempotency_key` 多 NULL 共存语义需保真通道复核（夹具直插行 key=NULL 不受约束影响，GWT-50.16 两张夹具 pending 不受本票阻塞）。② 018c369 骨架期的存量 pending 行（key=NULL）**不**会被判重——预发若有此类行需人工核对（产品未 GA，预期无存量）。③ GWT-50.7 断言集含 `QUOTA_PLAN_LOCKED`，本票已覆盖下单面。 |
| `/frontend`（T-03） | 新稳定 code：`ORDER_ROLE_NOT_ALLOWED`（请联系企业管理员）、`ORDER_ONLINE_UNAVAILABLE`（在线支付尚未开通，请改用线下对公。）、`ORDER_PENDING_EXISTS`（已有待确认的升级申请）。**禁止渲染任何 code 字面**，渲染 message。下单成功 201 的 message=「升级申请已提交，等待管理员确认收款」可直接用作 GWT-50.2 提示。 |
| `/architect` | ① §7.1 未给「经办/只读下单」与「在线通道」的**替换 code**（只钉了禁用 FORBIDDEN/QUOTA_EXCEEDED/PAYMENT_NOT_CONFIGURED）；本票引入 `ORDER_ROLE_NOT_ALLOWED`/`ORDER_ONLINE_UNAVAILABLE` 两个稳定 code，请追认进契约。② GWT-50.7 的「任何改套餐入口」字面含 `PATCH /tenant/usage/quota`（现 `require_tenant_manager`→403 FORBIDDEN；任何角色命中都抛 `QUOTA_PLAN_LOCKED`）——本票只改了 `POST /billing/orders`，quota 端点是否也要改找管理员句请裁决（T-03 UI 可先行兜住渲染）。③ 确认释放占位键（`paid:{id}`）是 T-02 重写确认时的不可回退语义。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（全量 1365 passed / arch 0 / ruff 0）
- [x] 契约落位表已核对，分层无违规（Router 无 ORM；角色判定在 Service）
- [x] ORM 与 DBML 一致，未自行加字段（零迁移，复用 040）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（无 redis 调用；commit 后经 `refresh` 再读，P-BE-01 口径）
- [x] 无 `except: pass`（IntegrityError 捕获后 rollback+抛业务异常，`from None` 显式断链）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（N/A：无条件更新）
- [x] 外部依赖四件套（N/A：无外部依赖）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8：code 追认、PATCH /quota 口径、存量 key=NULL 行），未自行绕过
- [x] 票状态：本票完成（状态更新归管理窗，本帽不写 state.yaml）
