# 实现证据 · T-14 埋点收口 + T-04 补测

> 票：contract §7 T-14（含 T-04 遗漏测试补齐）｜FR 锚点：FR-08 GWT-08.1–08.4、FR-05/03 回归｜日期：2026-09-15

## 1. 交付面

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/tests/test_governance_events.py` | 新增 | 7 用例，四事件字段逐项对 GWT-08.1–08.4 |
| `backend/tests/test_public_detail_preview.py` | 新增 | 9 用例，补 T-04 票指定但缺失的测试文件 |
| `backend/app/api/v1/public_skills.py` | 改 | `detail_opened` 改为**预览与正式都发**（AD-5e） |
| `backend/services/product_event_service.py` | 改 | 单写库写锁兜底：事件不再被静默丢弃 |

## 2. 本票发现并修复的两个真缺陷

### 缺陷 1：`detail_opened` 只在预览通道发射

契约 AD-5e 原文：「公开详情端点出 payload 后发射（**preview 与正式均发**）；现有
`MARKET_DETAIL_VIEWED` 保持不动」。而 T-04 落地的实现写成了 `if preview: detail_opened
else: public_detail` 的**二选一**——租户打开抽屉不产生 `detail_opened`，GWT-08.4 的 oracle
（「管理员/租户打开资产详情抽屉」）覆盖不到租户侧。已改为：正式通道照发
`MARKET_DETAIL_VIEWED`，两条通道都追发 `detail_opened`（`actor_role` 预览为
`platform_admin`、正式取 `user.role`、匿名为 `anonymous`）。

### 缺陷 2：事务内发射的产品事件在单写库上被**永久丢弃**

`product_event_service._persist_event` 刻意开**第二个连接**提交事件（「主路径 rollback
不得带走已发生的事实」）。但当调用方已 flush 过写操作时，它持着库级写锁——SQLite 下
第二连接必然 `database is locked`，等满 `connect_args timeout=30` 后抛错，被
`emit_product_event` 的 `try/except`（「失败不挡主路径」）吞掉。**本仓库 CI 的主 pytest
job 恰好就是 SQLite**（`MYSQL_FIDELITY` 只在单独的 fidelity job 开），所以：

- `sync_completed` / `import_completed` 这类「事务内发射」的事件在 CI 口径下 **100% 丢**，
  GWT-08.1/08.3 的可检索断言在 CI 永远无法通过；
- 附带代价是每次发射干等 30 秒。实测 `test_agents_hub_sync.py` 2 个用例 96 秒、
  `test_sync_endpoint.py` 单用例 33.8 秒。

修复两段：

1. **兜底不丢**：独立会话被 `OperationalError` 挡住时，退回主会话 `add + flush`。
   代价是该事实与主路径同生共死（弱于独立会话的保证），但「弱保证」严格优于「丢事件」；
   MySQL 生产路径不会走到这个分支。
2. **不做长等**：独立会话若是 SQLite，先 `PRAGMA busy_timeout=250`，250ms 内认输走兜底。

效果（同一环境同一命令）：

```
                                      修复前      修复后
test_agents_hub_sync.py               96.13s  →   （合并计）
test_sync_endpoint.py                >120s    →   10.35s（三文件 15 用例合计）
test_mcp_bridge.py                    67.35s  →
test_governance_events.py             36.12s  →    5.43s
```

## 3. GWT × 用例对照

| GWT | 用例 | 断言要点 |
|---|---|---|
| 08.1 导入完成 | `test_gwt_08_1_import_completed_fields` | 六字段齐全 + `source=directory` + `files/created/skipped` 数值对账 |
| 08.2 导入失败 | `test_gwt_08_2_import_failed_carries_error_type` | `error_type=ValidationException` |
| 08.3 同步完成/失败 | `test_gwt_08_3_sync_completed_fields` / `..._sync_failed_carries_error_type` | `actor=manual`、added/updated/unchanged；失败带 `error_type` |
| 08.4 详情打开 | `test_gwt_08_4_detail_opened_on_normal_and_preview` | 正式与预览各发一次；`actor_role/asset_type/asset_name` 齐全 |
| AD-5e 并存 | `test_detail_viewed_event_still_emitted_alongside` | `market_detail_viewed` 未被顶替 |
| NFR-09 可检索 | 每个用例同时断言 `market_events.emit_*` 结构化日志行 | 不只验 DB，日志面一并钉 |

T-04 补测（`test_public_detail_preview.py`）：

| 锚 | 用例 |
|---|---|
| AD-5c 预览可读 unlisted | `test_admin_preview_reads_unlisted_detail_with_marker`（带 `preview_unlisted` 标记） |
| 豁免边界 | `test_preview_exempts_listing_state_only`（黑名单/许可不合规/不存在，预览态仍 404） |
| 旁路需显式 | `test_admin_without_preview_flag_still_404_on_unlisted` |
| FR-03 验收通道 | `test_admin_preview_list_bypasses_gate`（闸关下仍出数据、`gate_open=false`） |
| **GWT-03.7** | `test_gwt_03_7_tenant_and_anonymous_404_on_unlisted_detail_and_media` + `..._tenant_preview_flag_is_ignored` |
| GWT-03.4/05.6 | `test_gwt_03_4_gate_closed_tenant_detail_unchanged` |
| **GWT-03.8** | `test_gwt_03_8_listing_endpoint_404_for_non_admin_and_state_unchanged` |
| GWT-05.3 投影 | `test_detail_projects_examples_and_gate_open` |

## 4. 自测证据

```
$ python -m pytest -q backend/tests/test_governance_events.py -p no:cacheprovider
7 passed in 5.43s
$ python -m pytest -q backend/tests/test_public_detail_preview.py -p no:cacheprovider
9 passed in 7.43s
```

## 5. 交票自检

- [x] 四事件字段逐项断言 + product_events 可检索
- [x] 结构化日志行一并断言（NFR-09）
- [x] T-04 票指定的测试文件补齐（GWT-03.7/03.8 点名覆盖）
- [x] 两个真缺陷有修复 + 有回归用例
