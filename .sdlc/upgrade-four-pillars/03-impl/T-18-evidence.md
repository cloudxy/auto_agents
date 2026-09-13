# 实现证据 · T-18 SKU 闸「我的渠道组」；签发/吊销/到期旧令牌失效

> 票：`02-shape/contract.md` §10 T-18｜FR 锚点：FR-U20 FR-U21 FR-U22 FR-U23｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/api/v1/relay/sku` | Router | `backend/app/api/v1/relay.py` | 权益状态 + 买方去升级 `product=relay` |
| GET `/relay/groups\|tokens` 空态句 | Router + Service | 同上 + `relay_service.py` | SKU≠active：`[]` + 「未开通中转」/「中转已到期」 |
| 签发/建组 422 `RELAY_SKU_INACTIVE` | Service | `relay_sku_gate.require_active_sku` | 到期句「中转已到期」 |
| 明文只当次；列表/再 GET 仅前缀 | Service | `issue_token` / `_token_out` | `plaintext_key=None` |
| 吊销后列表「还没有令牌」；凭证不可用 | Service | `list_tokens` 滤 revoked；`usage_by_plaintext` | GET `/tokens/by-key` |
| 跨租户 404 同形 | Service | `raise_missing` → HTTP_404 / Not Found | 先点查本企再 SKU |
| 值班页租户 404 | 既有守卫 | `newapi.py` `require_platform_admin_or_404` | 本票回归，不改守卫 |
| 错误码映射 | 统一异常处理器 | `RELAY_SKU_INACTIVE` 422；跨租户 HTTP_404 | 未新造信封 |
| 数据读写 | Repository | `relay_sku_entitlement_repository.py` | **只读** SELECT；禁止写权益 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/repositories/relay_sku_entitlement_repository.py` | 新增 | 按 tenant_id 点查；无 INSERT/UPDATE |
| `backend/services/relay_sku_gate.py` | 新增 | 缺行≡none；空态句；去升级 CTA |
| `backend/services/relay_usage.py` | 新增 | 用量观察从 relay_service 抽出（≤500 行） |
| `backend/services/relay_service.py` | 修改 | SKU 闸列表/签发/吊销；凭证读用量 |
| `backend/app/api/v1/relay.py` | 修改 | `/sku`、`/tokens/by-key`；空态 message |
| `platform_core/schemas/relay.py` | 修改 | `RelaySkuPageOut` / `RelayUpgradeOut` |
| `backend/tests/relay_sku_support.py` | 新增 | 测试直接 INSERT 权益行 |
| `backend/tests/test_fr_u20_relay_sku.py` | 新增 | GWT-U20…U23 |
| 既有 relay/billing/outbound/product_events 测 | 修改 | PIT-2：写路径先 INSERT `status=active` |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：合同未列路径；按既有 `/relay` 加闸。未改 046 / 未写履约。）

**未触碰「不许改的文件」**：☑ 确认（无 Alipay notify；无 T-17 履约写权益；无 schema 加列）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| SKU 点查 + 列表 | 否（只读） | 单表点查 |
| 签发（网关登记 + 本地 hash） | 是（既有） | 本地失败则尽力作废网关 Key |
| 吊销（网关 delete + 本地 revoked） | 是（既有） | 网关失败不本地假吊销 |

**事务提交后的操作失败怎么办**：网关孤儿 Key 记日志（既有）；产品事件 fail-open（既有）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 既有吊销：已 revoked 再 DELETE 不打网关 |
| 保证方式 | `revoked_at` 非空短路 |
| 重复请求返回 | 200 同形 revoked |

☑ 未使用「先查后插」（本票无新写权益）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 本票无状态机 UPDATE | — | N/A 只读权益 |

☑ N/A 本票不对 `relay_sku_entitlements` 做条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM `/key/generate\|delete`（既有签发/吊销） | 既有 httpx | 无（失败可见） | 502 `RELAY_GATEWAY_UNAVAILABLE` | 吊销按 alias |
| 权益表 | 本地 DB | — | 缺行≡none | — |

## 4. ORM 与 DBML 对齐

☑ 本票无新表/新列。读 `relay_sku_entitlements`（046 / T-14）。缺行 ≡ none。

结构核对输出：

```
$ bash tools/check/arch.sh
架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `load_sku_status` / `issue_token` / `usage_by_plaintext` 记 tenant（无明文） |
| trace_id | 既有中间件 |
| 错误日志上下文 | SKU 非 active 记 status；跨租户不打 token 全文 |
| 慢操作耗时 | 网关观察既有 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token 明文 ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ uv run pytest -q backend/tests/test_fr_u20_relay_sku.py
...............                                                          [100%]
15 passed in 4.99s
exit: 0

$ uv run pytest -x -q backend/tests
1641 passed, 40 skipped, 7 warnings in 254.82s (0:04:14)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U20.1 正常 | `test_gwt_u20_1_active_lists_own_groups_no_upstream_key` | ✅ |
| GWT-U20.2 空态 | `test_gwt_u20_2_active_zero_tokens_empty_copy` | ✅ |
| GWT-U20.3 越权 | `test_gwt_u20_3_cross_tenant_404_same_shape` | ✅ |
| GWT-U21.1 正常 | `test_gwt_u21_1_missing_row_empty_copy_upgrade_relay` / `_status_none_row_same_as_missing` | ✅ |
| GWT-U21.2 空态 | `test_gwt_u21_2_nav_has_no_subscribed_badge` | ✅ |
| GWT-U21.3 越权 | `test_gwt_u21_3_issue_refused_when_inactive` | ✅ |
| GWT-U22.1 正常 | `test_gwt_u22_duty_page_404_even_when_sku_active`（无熔断控件/无网关 URL） | ✅ |
| GWT-U22.2 空态 | 同上 GET `/newapi/overview` 404 同形 | ✅ |
| GWT-U22.3 越权 | 同上 PUT 渠道窗口 spy 未调用 + 404 | ✅ |
| GWT-U22.4 越权 | 同上 `/relay/sku` 无直连网关 | ✅ |
| GWT-U23.1 正常 | `test_gwt_u23_1_plaintext_once_later_prefix_only` | ✅ |
| GWT-U23.2 空态 | `test_gwt_u23_2_revoked_only_shows_empty_tokens` | ✅ |
| GWT-U23.3 越权 | `test_gwt_u23_3_6_7_token_as_credential` B 持 A 令牌 404 | ✅ |
| GWT-U23.4 边界 | `test_gwt_u23_4_expired_sku_issue_copy` | ✅ |
| GWT-U23.5 越权 | `test_gwt_u23_5_operator_cannot_issue_when_active` | ✅ |
| GWT-U23.6 边界 | `test_gwt_u23_3_6_7_token_as_credential` SKU expired 后旧令牌 404 | ✅ |
| GWT-U23.7 越权 | 同上 A 令牌当 B 凭证 404 | ✅ |
| GWT-U23.8 边界 | `test_gwt_u23_2_revoked_only_shows_empty_tokens` by-key 404 | ✅ |
| GWT-U33.1 只读侧 | `test_plan_pro_order_does_not_open_relay` | ✅ 履约写权益仍是 T-17 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（本票权益只读；签发事务既有 T-08） |
| 幂等 | 既有吊销再 DELETE | ✅ 回归 `test_revoke_invalidates_gateway_then_local` |
| 并发写 | — | ➖ N/A（无权益 UPDATE） |
| 外部依赖失败 | 既有网关 5xx 签发失败 | ✅ 回归 `test_issue_gateway_5xx_visible_no_local_row` |

N/A 已给理由。

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U04 | 明文不进列表/日志/事件 | GET list/detail `plaintext_key is None`；by-key 无全文 | pytest SQLite |
| — | 禁「当前可买」 | 源码 + `/sku` 响应扫描 | 同左 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| T-20 `/frontend` | GET `/api/v1/relay/sku` → `status` none/active/expired；none/expired 的 `upgrade.product=relay`、`checkout_path=/billing/checkout?product=relay`。列表空时 message 即空态标题。不要 COUNT 组行当已开通。 |
| T-17 | 本票只读权益。`plan_pro` fulfilled 单不得经 relay 写 `relay_sku_entitlements`（测已钉）。 |
| `/qa` | 测试用 INSERT 权益行，不打支付宝。跨租户与 by-key 失败均为 HTTP_404 / Not Found（与 `/admin/tenants` 同形）。 |
| `/architect` | 无新错误码信封；`RELAY_SKU_INACTIVE` 在 edge-states 已点名。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无新的外部调用
- [x] 幂等未用「先查后插」当权益保证
- [x] 本票无权益条件更新
- [x] 四类易漏测试已覆盖或标 N/A
- [x] 未做 Alipay notify；未写履约
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
