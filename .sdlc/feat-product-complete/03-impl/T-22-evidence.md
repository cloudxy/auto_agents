# 实现证据 · T-22 产品事实：fail-open + 租户无查询面

> 票：contract §11 P2 T-22（`02-shape/tickets-v1.2-stale-archived/T-22.md` 同文）｜FR 锚点：FR-92 GWT-92.6/92.7 · NFR-08 · contract §7.7｜角色：/backend｜日期：2026-09-11
> 上游 T-02/05/09/14 事件名均已落（`02-shape/contract.md` §11）；本票收口 fail-open 逐点核对 + 查询面守卫核对。

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 上报失败不挡主路径（GWT-92.6） | Service | `backend/services/product_event_service.py:65`（emit 内 `except Exception` + warning） | 唯一吞异常收口点；本票逐上报点核对挂载位置与吞异常圈完整性 |
| relay 批量刷新上报点挂载 | Service | `backend/services/relay_service.py` | **发现并修复一处不合格**（详见 §3 缺陷记录） |
| 查询面仅超管 + 租户 404 同形（GWT-92.7） | Router 守卫 | `backend/app/api/v1/product_events.py:57` + `backend/app/api/deps.py:176` | 既有 `require_platform_admin_or_404`，守卫核对通过（不走 403 信封） |
| 事件不含明文钥匙/密码/master | Schema | `platform_core/schemas/product_event.py`（`strip_secret_props`） | 既有，未动；测试断言 plaintext 不入事件（既有 test_gwt_60_3 等） |

**分层依赖核对**：☑ Router 未 import ORM（product_events.py 只进 Service/Schema）☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/relay_service.py` | 修改 | `_usage_snapshot`（commit 前快照）+ `_emit_usage_event(snap)` 只读纯值；get_token / refresh_tokens_usage 两调用面同口径 |
| `backend/tests/test_product_events.py` | 修改 | T-22 段：GWT-92.6 七上报点异常注入（`_persist_event` boom）×7 + 生产 expire_on_commit 回归 ×1 + GWT-92.7 同形断言 ×1 |

**与票里「会改哪些文件」一致**：☐ 有偏差——票面列 `product_event_service.py`「修改：emit fail-open」；核对后 emit 已 fail-open 且合格，**唯一不合格点在 relay 挂载**（票面「发现一处不合格修一处」授权范围内），落点改为 `relay_service.py`。票面其余三文件均触碰/对照。

**未触碰「不许改的文件」**：☑ 确认（事件名字面量零改动——七事件名 grep 前后一致；WACT 口径文件未动；`billing_service.py` 写规则未动）

## 3. 关键实现决策：七上报点逐点审查（fail-open 落点清单）

| # | 事件 | 上报点（改动前） | commit 后挂载 | 异常吞掉 | 无「先报后写」倒挂 | 结论 |
|---|---|---|---|---|---|---|
| 1 | offline_order_submitted | `billing_service.py:95`（create_order） | ✓ commit@87 后 | ✓ emit 内 | ✓ 订单先落库；order_id/plan_name 快照先于 commit | 合格（既有） |
| 2 | offline_order_confirmed | `billing_service.py:153`（confirm_paid） | ✓ commit@149 后 | ✓ emit 内 | ✓ tenant/order/plan 快照先于 commit；已 paid no-op 不报 | 合格（既有） |
| 3 | outbound_key_issued | `outbound_key_service.py:113`（issue_key） | ✓ commit@105 + refresh 后 | ✓ emit 内 | ✓ props 用 Pydantic `out.id`（refresh 后纯值）；raw 不入事件 | 合格（既有） |
| 4 | relay_token_call_succeeded | `relay_service.py:275`（get_token）/ `:326`（refresh_tokens_usage） | ✓ 两处 commit 后 | **✗→✓**（见缺陷） | ✓ 观察回写先 commit 再报 | **缺陷已修** |
| 5 | market_list_paged | `public_skills.py:84` → `market_events.emit_market_list_paged` | ✓（主路径只读列表，data 先成再报） | ✓ emit 内 | ✓ 无写面可倒挂 | 合格（既有） |
| 6 | user_restored | `user_service.py:353`（restore_user） | ✓ commit@344 后 | ✓ emit 内 | ✓ tenant_id 快照先于 commit；rowcount=0（并发恢复）不报 | 合格（既有） |
| 7 | asset_imported | `asset_import_service.py:289`（_finish） | ✓ commit@288 后 | ✓ emit 内 | ✓ batch_id/origin/items/counts 全纯值（batch_id 显式 commit 前快照） | 合格（既有） |

### 缺陷记录（TDD 红→绿）：relay 批量刷新上报点

- **现象**：`refresh_tokens_usage` 旧实现 commit 后、refresh 前调 `_emit_usage_event(row, token_id)`，函数体首行 `int(row.tenant_id)` 读过期属性。生产 `get_async_session`（`platform_core/db.py:158`，`AsyncSession(async_engine)` 未传 `expire_on_commit`，默认 **True**）下抛 `sqlalchemy.exc.MissingGreenlet`。
- **为何打穿 fail-open**：抛点在 `emit_product_event` 吞异常圈**外**（属性求值发生在调用 emit 之前）→ 异常沿 refresh_tokens_usage → Router 传播 = 主路径 500（GWT-92.6 违约）；同时事件必丢（GWT-92.4「至少一次」违约）。get_token 路径因 refresh 先于 emit 而幸免。
- **为何既有测试没抓到**：conftest `db_session` 工厂显式 `expire_on_commit=False`（`conftest.py:385`），与生产会话形态相反。
- **修复**：`_usage_snapshot(row)` 在 commit 前取 token_id/tenant_id/group_id/used_tokens 纯字典；`_emit_usage_event(snap)` 只读快照；两调用面（get_token / refresh_tokens_usage）同口径。事件名、props 键、语义零变化。
- **回归钉**：`test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit` 用 `AsyncSession(db_engine)`（生产形态，不传 expire_on_commit=False）驱动整链。

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 主路径写（订单/钥匙/恢复/导入/用量回写） | 是（各自既有事务） | 本票不改 |
| 事件写入 | 否 | 独立短会话（`_persist_event` 自建 session，主路径 rollback 不带走已发生事实）——既有设计，未动 |

## 4. ORM 与 DBML 对齐

`product_events` **不加列**（票面 expand-contract）：☑ 确认。本票仅改事件**写入时机**的值来源（ORM 属性→commit 前快照），行结构/字段/事件名字面量零变化。relay_tokens 列零变化。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| emit 入口日志 | `product_event_service.emit_product_event` logger.info（name+tenant，无明文）——既有 |
| 失败降级日志 | `except Exception` → `logger.warning("产品事件上报失败（不挡主路径）…")`——既有，本次核对无 `except: pass` |
| relay 修复点 | `_usage_snapshot` 沿用既有回写日志（`_apply_usage` INFO），无新增敏感字段 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token/明文钥匙（relay 事件 props 只含 token_id/group_id/used_tokens）

## 6. 自测证据（命令与退出码原样粘贴）

```
$ uv run pytest -x -q backend/tests/test_product_events.py backend/tests/test_t32_market_events.py
.........................................                               [100%]
41 passed in 7.44s
exit: 0

$ uv run pytest -q backend/tests/test_product_events.py::test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit
（修复前·旧实现：_emit_usage_event(row, token_id) commit 后读过期属性）
E           sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here. Was IO attempted in an unexpected place? (Background on this error at: https://sqlalche.me/e/20/xd2s)
FAILED backend/tests/test_product_events.py::test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit
1 failed in 1.37s
exit: 0（pytest 语义=1 failed；红已见）

$ uv run pytest -q backend/tests/test_product_events.py::test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit
（修复后）
.                                                                        [100%]
1 passed in 1.21s
exit: 0

$ uv run pytest -q backend/tests/test_product_events.py -k "92_6 or 92_7"
........                                                                 [100%]
8 passed, 22 deselected in 2.03s
exit: 0

$ uv run pytest -q backend/tests/test_relay_token_usage.py backend/tests/test_relay_token_gateway.py backend/tests/test_relay_group_empty_state.py backend/tests/test_billing_relay.py
....................                                                       [100%]
20 passed in 7.87s
exit: 0

$ uv run pytest -x -q backend/tests
1546 passed, 38 skipped, 7 warnings in 136.70s (0:02:16)
exit: 0
（基线 1538 passed/38 skipped → +8 = 本票新增 8 测，零回退）

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend/services/relay_service.py backend/tests/test_product_events.py
All checks passed!
exit: 0
```

注：红跑的 shell `exit: 0` 是管道尾部命令语义；pytest 自身报告 `1 failed`（上方原样）。修复后同命令 `1 passed`。

### 验收项逐条对应

| GWT | 覆盖的测试 | 红 | 绿 |
|---|---|---|---|
| 92.6 offline_order_submitted / offline_order_confirmed | `test_gwt_92_6_offline_order_events_fail_open`（201+200、pending/paid 落库、零事件行） | ➖ 既有合格 | ✅ |
| 92.6 outbound_key_issued | `test_gwt_92_6_outbound_key_event_fail_open`（201、钥匙落库、明文一次、零事件行） | ➖ | ✅ |
| 92.6 relay_token_call_succeeded（通道故障） | `test_gwt_92_6_relay_usage_event_fail_open`（详情+批量刷新不炸、回写 7 落库、零事件行） | ➖ | ✅ |
| 92.6 relay 挂载缺陷（生产 expire_on_commit） | `test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit` | ✅ MissingGreenlet | ✅（事件不丢：恰好 1 行，GWT-92.4 不回退） |
| 92.6 market_list_paged | `test_gwt_92_6_market_paged_event_fail_open`（page2=200、total=25、items=5、零事件行） | ➖ | ✅ |
| 92.6 user_restored | `test_gwt_92_6_user_restored_event_fail_open`（200、用户回在册、零事件行） | ➖ | ✅ |
| 92.6 asset_imported | `test_gwt_92_6_asset_imported_event_fail_open`（200、succeeded=1、资产落库、零事件行） | ➖ | ✅ |
| 92.7 租户无查询面 | `test_gwt_92_7_tenant_query_face_same_shape_as_missing_page`（与同守卫平台页信封逐键相等、code=HTTP_404、非 403、零事实泄露） | ➖ 守卫既有 | ✅ |
| （既有回归）| test_gwt_15_3 仍绿（租户 404 shell）；relay 四文件 20 测仍绿 | — | ✅ |

TDD 说明：七点中六点审查结论为既有合格（fail-open 通道 emit 内吞已有 test_gwt_15_2 先例钉住），无自然红可演；唯一新增红=relay 挂载缺陷（上方两段输出=红/绿证据）。异常注入统一打在 `product_event_service._persist_event`（通道最底层），对七点等价于「product_events 写入异常」。

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（事件走独立短会话，主路径事务边界未改；既有 `_persist_event` 设计覆盖） | |
| 幂等 | ➖ N/A（本票无新幂等面；重复恢复 no-op 既有 T-24 钉） | |
| 并发写 | ➖ N/A（挂载点核对票，无新并发面；恢复并发 rowcount 口径既有） | |
| 外部依赖失败 | `test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit` + 七点 boom 注入（事件通道=本票的外部依赖面） | ✅ |

## 7. NFR 验证

NFR-08（FR-92 事件仅超管按发生时间可查；失败不挡主路径）：查询面守卫核对通过（§1）；失败不挡=§6 七点注入。perf 未测（无 NFR 数字要求）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | (1) relay 缺陷只在 `expire_on_commit=True` 生产形态显形——MYSQL_FIDELITY 真库轮建议直打 `POST /api/v1/relay/tokens/refresh-usage`（0→≥1 跃迁后）复核事件行存在；(2) 七点 fail-open 注入均 mock `_persist_event`，真实 DB 故障注入留 qa；(3) 92.7 同形口径=统一异常处理器信封（HTTP_404/"Not Found"），与 Starlette 裸默认 404（`{"detail"}`）**不同形**——后者不经统一处理器，属框架层，不构成泄露面（两者都零存在性信息）。 |
| `/frontend` | 无差异：T-23 页面按 404→NotFound 路由处理即可（守卫行为未变）。 |
| `/architect` | 无新增歧义。记录一处既有事实：conftest 会话 `expire_on_commit=False` 与生产 `True` 相反，凡「commit 后读 ORM 属性」类缺陷测试面天然盲区（P-BE-01 家族）；建议后续票凡动 commit 邻域补一条生产形态会话用例（本票已为 relay 立 precedent）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样；红/绿两态）
- [x] 自测全绿（1546 passed / 38 skipped，零回退；arch.sh 0；ruff 0）
- [x] 契约落位表已核对，分层无违规（Router 无 ORM）
- [x] ORM 与 DBML 一致（零列变化），未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（修复恰是消除一处隐式同步刷新）
- [x] 无 `except: pass`（吞异常均 logger.warning）
- [x] 日志已脱敏（无明文钥匙/密码）
- [x] 事务里无外部调用（事件写走独立短会话，既有）
- [x] 幂等未用「先查后插」（未动幂等面）
- [x] 条件更新的 `rows == 0` 已处理（restore rowcount=0 no-op，既有）
- [x] 外部依赖四件套（事件通道：失败降级=warning+不挡；至少一次由独立会话保证；本票无新增外部依赖）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8 /architect），未自行绕过
- [x] 上报失败不挡下单/签发/翻页（§3 表 + §6 注入）
- [x] 租户查询面 404 同形（§6 92.7 行）
- [x] 未改事件名/WACT；PC-3 仍=已确认（offline_order_confirmed 语义零变化）
