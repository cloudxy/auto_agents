# 覆盖矩阵 · 四柱深度调整（N1 采集 + N2 市场/RBAC + N3 中转 SKU/支付 + N4 值班三态）

> 泳道：L3
> 上游：PRD `01-define/spec.md` v1.2｜契约 `02-shape/contract.md`｜`edge-states.md`
> 证据：`03-impl/T-01-evidence.md` … `T-23-evidence.md`、`T-24-evidence.md`、`T-25-evidence.md`、`T-26-evidence.md`、`T-27-evidence.md`（本波交 N1+N2+N3+N4；**T-24 已交**（checklist + 密钥扫描）；应用层 notify 仍无 RateLimitPolicy → NFR-U03 保持 ⚠️）
> 作者：/qa｜日期：2026-09-13｜下游：`/qc` 或 `/reviewer`
> 返工：implement N4 r2 后刷新 FR-U25 映射（当时 QA-01…QA-05 关闭）。Closed leftover：findings-verify-n4 QA-01/QA-02（T-24 措辞；GWT-U02.7 删夹具行）。N1–N4 GWT 映射不重开。
> 范围：本波施工 = N1（FR-U01…U04，T-01…T-07）+ N2（FR-U10…U15，T-08…T-13）+ N3（FR-U20…U24、FR-U30…U38，T-14…T-25）+ N4（FR-U25，T-26/T-27）。**不**宣称四柱 GA。可见面仍禁「当前可买」。值班「活」≠ SKU active。Notify HMAC 夹具 ≠ live 支付宝/微信。Q-OPS-DUTY 无 SLA 数字。
> 方言：默认 pytest = SQLite + FakeRedis；生产 = MySQL 8。045 夹具名单与 046 生成列均已抛开库 up-down-up。
> check-matrix.py 只抽 spec 的 `\bFR-\d+\b` / `\bNFR-\d+\b`（**不**抽 FR-U01）。v2 字面见 §1.0。

## 0. 结论先行（事实，非放行）

本矩阵证明「格子有映射或有豁免」，**不能**当发布意见。N3 中转 SKU / 支付宝微信结账 / 夹具验真履约 **已映射到测试文件**（notify 用签名夹具，**不是** live 通道收银台）。N4 值班三态 **已映射**（pytest `test_fr_u25_duty.py` **10** 条含降级非空不标活 / 第四态 / bounded `latest_result_per_channel`；Jest Overview3q / NewApiOps / App.menu **43** 条含 hasLiveRow 压过 empty、行活须 `gatewayAvailable`；网关用 monkeypatch / jest mock，**不是** live LiteLLM 管理面）。T-24 **已交**（checklist + 密钥扫描）；应用层 notify 仍无 RateLimitPolicy → NFR-U03 保持 ⚠️。禁止把 `checkout_pending`、SKU `active` 或夹具 `payment_succeeded` 写成「当前可买」或四柱 GA。值班「活」**不是**中转 SKU active，也**不是**「当前可买」。Q-OPS-DUTY **不**写 SLA 数字。

| 项 | 事实 |
|---|---|
| 本波已测 | FR-U01…U04 全部 GWT（18）+ FR-U10…U15 全部 GWT（19）+ FR-U20…U24 / U30…U38 全部 GWT（70）+ FR-U25 全部 GWT（4）有具名测试文件 |
| v2 `FR-nn` | 13 条字面均在 §1.0；豁免「前合同 v2，本波不重测」 |
| N4 | FR-U25 GWT-U25.1…U25.4 已映射 T-26/T-27 |
| 硬缺口 ❌ | N1/N2/N3/N4 GWT **0**。未把未施工波次标成缺口 |
| 空心断言 | 本波新测未用 `assert True` / `or True` |
| 需真实环境 ⚠️ | GWT-U01.1 的 120s 合格出数走 FakeRedis；N3 notify **无 live 支付宝/微信**；NFR-U01 去支付无 5s monotonic；N4 overview **无 live LiteLLM** |
| N3 | **映射完成，非 GA**。打开结账 ≠ 已买。专业档开通 ≠ 中转 active。可见面禁「当前可买」。T-16/T-19 无 `pay_url`：去支付停在 `checkout_pending`，不假装跳转通道托管页 |
| N4 | **映射完成，非 GA**。GWT-U25.1…4 有具名测。三句互斥已钉。第四态（可达+已登记+无 original）有支撑测、**不是** GWT-U25 行。屏 19 离线 hint **无 Jest**（非 GWT-U25 行，§5 ⚠️）。值班「活」≠ SKU active。mock 网关 ≠ 生产值班 SLA。Q-OPS-DUTY 本波不承诺数字 |

### 状态图例

| 标记 | 含义 |
|---|---|
| ✅ | 已覆盖：有 file:line，断言对照 Then |
| ❌ **缺口** | 该测没测，或映射空心 |
| ⚠️ **需真实环境** / 部分 | SQLite/FakeRedis 测不出、或 Then 只覆盖一半 |
| ➖ **N/A** | 不适用（前合同 / 未施工波次 / spec N/A） |

---

## 1. 正向：FR/NFR → 用例

### 1.0 闸门字面 · v2 `FR-nn`（check-matrix 必现）

spec.md 仍出现这些 `\bFR-\d+\b`。本波不重测前合同；每条必须作为字面出现。

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-01 | 闭集 B2 已由 FR-U20/U24  supersede | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-06 | 壳差；本波加深在 FR-U12/U15 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-14 | 密钥不进 git / 值班页禁掩码当 Then | — | — | ➖ **N/A** | 前合同 v2，本波不重测；值班页半句仍有效，渠道组半句已 supersede |
| FR-15 | 产品事实仅超管；本波加深 FR-U03 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-18 | 最小出数环；本波加深空非夹具 FR-U01 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-30 | 市场 D 线仍有效；本波验收在 FR-U10 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-33 | 上架后公开面可见 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-34 | 订一行、不级联、预告不可订 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-50 | stub「本波不必支付」已由 FR-U33/U35/U38 supersede | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-51 | 租户自助出站钥匙；范围外 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-70 | 数据面不请回 new-api | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-71 | 值班；本波加深 FR-U25 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |
| FR-74 | 网关挂 ≠ 套餐超限 | — | — | ➖ **N/A** | 前合同 v2，本波不重测 |

spec 无 `\bNFR-\d+\b`（只有 NFR-U*）。NFR-U 见 §1.4。

### 1.1 N1 本波施工 · FR-U01…U04

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-U01 | GWT-U01.1 正常 | TC-U01.1 | 集成+单元 | ⚠️ 部分 | `backend/tests/test_fr_u01_enqueue.py:186` `test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant`：3s「已入队」、本企业 total>0、`task_completed` 且 `is_internal_fixture=false`。UI：`frontend/admin/src/components/spider/TaskModal.test.tsx:110`。回流走 FakeRedis `_ingest_flush`，**不是** live Scrapy 120s |
| FR-U01 | GWT-U01.2 空态 | TC-U01.2 | 集成+单元 | ✅ | `test_fr_u01_enqueue.py:253` `test_gwt_u01_2_empty_results_copy_is_actionable`；`frontend/admin/src/pages/Data.test.tsx:95` 真 0 锁句；`:122` 筛选空 ≠ 真 0 |
| FR-U01 | GWT-U01.3 越权 | TC-U01.3 | 集成 | ✅ | `test_fr_u01_enqueue.py:272` `test_gwt_u01_3_cross_tenant_result_same_as_missing`：404 同形，无 A 字段 |
| FR-U02 | GWT-U02.1 无工人 | TC-U02.1 | 集成+单元 | ✅ | `test_fr_u01_enqueue.py:300` `test_gwt_u02_1_worker_offline_blocks_within_3s_and_emits_task_blocked`；`TaskModal.test.tsx:94`；`collectBlock.test.ts:40`。工人句，不入队，emit `task_blocked.reason=worker_offline` |
| FR-U02 | GWT-U02.2 存储满 | TC-U02.2 | 集成+单元 | ✅ | `backend/tests/test_fr_u02_quota_copy.py:157` `test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta`；`TaskModal.test.tsx:121`；`Usage.test.tsx:192`；`collectBlock.test.ts:11`。锁句「已达配额上限」+「去结果库」；无 `QUOTA_EXCEEDED` / 裸 429 |
| FR-U02 | GWT-U02.3 只读提交 | TC-U02.3 | 集成 | ✅ | `test_fr_u02_quota_copy.py:183` `test_gwt_u02_3_readonly_submit_rejected_no_enqueue` |
| FR-U02 | GWT-U02.4 token 满规划 | TC-U02.4 | 集成+单元 | ✅ | `test_fr_u02_quota_copy.py:199` `test_gwt_u02_4_token_full_planning_is_quota_copy_not_worker`；`TaskModal.test.tsx:145`；`collectBlock.test.ts:26`。配额句，不是工人句 |
| FR-U02 | GWT-U02.5 将满 | TC-U02.5 | 集成+单元 | ✅ | `test_fr_u02_quota_copy.py:230` `test_gwt_u02_5_usage_near_limit_is_not_full_copy`；`Usage.test.tsx:168`。将满 ≠ 已尽；无满额 CTA |
| FR-U02 | GWT-U02.6 非买方申请提升 | TC-U02.6 | 集成+单元 | ✅ | `test_fr_u02_quota_copy.py:250` / `:272` operator+viewer；`UpgradeIntentButton.test.tsx:48` / `:66`；`Usage.test.tsx:206` / `:221`。「请联系本企业管理员开通」；不建单、不到结账、不到注册 |
| FR-U02 | GWT-U02.7 买方申请提升 | TC-U02.7 | 集成+单元 | ✅ | `test_fr_u02_quota_copy.py:291` / `:313`；`Usage.test.tsx:232`；`frontend/admin/src/components/quota/UpgradeIntentButton.test.tsx:80`。路由 `/billing/checkout?product=plan_pro`。N1 空态句仍可由 N3 两通道未配走 GWT-U32.2；**打开结账 ≠ 已买** |
| FR-U03 | GWT-U03.1 正常 | TC-U03.1 | 集成 | ✅ | `backend/tests/test_t01_internal_fixture.py:69` `test_gwt_u03_1_non_fixture_completed_snapshot_false`；入队接线 `test_fr_u01_enqueue.py:186`。字段 `tenant_id` / `result_count>0` / `is_marketplace_candidate=false` / `is_internal_fixture=false` |
| FR-U03 | GWT-U03.2 空态 | TC-U03.2 | 集成 | ✅ | `test_t01_internal_fixture.py:81` `test_gwt_u03_2_fixture_excluded_from_north_star` |
| FR-U03 | GWT-U03.3 越权 | TC-U03.3 | 集成 | ✅ | `test_t01_internal_fixture.py:126` `test_gwt_u03_3_tenant_query_and_membership_are_404` |
| FR-U03 | GWT-U03.4 边界 | TC-U03.4 | 集成 | ✅ | `test_t01_internal_fixture.py:140` emit 口径；`test_fr_u01_enqueue.py:300` / `:347` 入队拦住接线。拦住 ≠ `task_completed` 且 `result_count>0` |
| FR-U03 | GWT-U03.5 正常 | TC-U03.5 | 集成 | ✅ | `test_t01_internal_fixture.py:166` `test_gwt_u03_5_completed_not_in_blocked_numerator` |
| FR-U04 | GWT-U04.1 正常 | TC-U04.1 | 单元 | ✅ | `frontend/official/src/pages/Home.test.tsx:127`；`frontend/official/src/App.test.tsx:20`。第一句采集，不讲订阅/支付/中转可买 |
| FR-U04 | GWT-U04.2 空态 | TC-U04.2 | 单元 | ✅ | `Home.test.tsx:142` 精选空不顶替 Hero |
| FR-U04 | GWT-U04.3 越权 | TC-U04.3 | 单元 | ✅ | `Home.test.tsx:156` 无「编辑官网第一句 / 改 Hero」 |

T-07 是 IA 证据（屏 6/7/8/9/10/11/23），不是可执行用例；锁句由 T-02/T-03/T-04 测试钉死。T-05 索引 T-01+T-02，无新测试文件。

### 1.2 N2 本波施工 · FR-U10…U15

T-08 `backend/tests/test_fr_u10_market.py`；T-09 `backend/tests/test_fr_u12_u15_rbac.py`；T-10/T-11/T-12 Jest 见下。T-13 是 IA 证据（屏 3/5/15/16/17/21/24），不是可执行用例；锁句由 T-08/T-10/T-12 钉死。

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-U10 | GWT-U10.1 正常 | TC-U10.1 | 集成+单元 | ✅ | `backend/tests/test_fr_u10_market.py:84` `test_gwt_u10_1_subscribe_one_row_no_children`：安装仅父插件 `u101-plug`，无 `u101-s1/s2`。UI：`frontend/admin/src/pages/market/TenantShelf.test.tsx:185`。证据 T-08 / T-10 |
| FR-U10 | GWT-U10.2 空态 | TC-U10.2 | 集成+单元 | ✅ | `test_fr_u10_market.py:101` `test_gwt_u10_2_open_empty_shelf_not_closed`：双公开端「暂无已上架能力」，无关闭句、无加载失败。UI：`frontend/official/src/pages/Capabilities.test.tsx:101` / `:329`；`TenantShelf.test.tsx:139` / `:152` |
| FR-U10 | GWT-U10.3 越权 | TC-U10.3 | 集成+单元 | ✅ | `test_fr_u10_market.py:115` `test_gwt_u10_3_readonly_rejected`：`MARKET_READONLY_ROLE`，零安装行。UI：`TenantShelf.test.tsx:174` 订阅 disabled、不 POST |
| FR-U10 | GWT-U10.4 边界 | TC-U10.4 | 集成+单元 | ✅ | `test_fr_u10_market.py:123` `test_gwt_u10_4_coming_soon_not_subscribable`：`subscribable=false`、`MARKET_COMING_SOON`、零行。UI：`TenantShelf.test.tsx:160`；`Capabilities.test.tsx:170` GWT-31.5 无订阅按钮 |
| FR-U11 | GWT-U11.1 正常 | TC-U11.1 | 集成+单元 | ✅ | `test_fr_u10_market.py:135` `test_gwt_u11_1_closed_subscribe_no_row`：409 `MARKET_CLOSED`，「能力市场未开放」，零安装。UI：`frontend/admin/src/components/SubscribeModal.test.tsx:122` / `:134` 不 Toast 已订阅 |
| FR-U11 | GWT-U11.2 空态 | TC-U11.2 | 集成+单元 | ✅ | `test_fr_u10_market.py:145` `test_gwt_u11_2_closed_list_not_empty_shelf`：双公开端 + 详情关闭句，禁止空货架句。UI：`Capabilities.test.tsx:303` / `:318`；`CapabilityDetail.test.tsx:150`；`TenantShelf.test.tsx:114` / `:129` |
| FR-U11 | GWT-U11.3 越权 | TC-U11.3 | 集成+单元 | ✅ | `test_fr_u10_market.py:166` `test_gwt_u11_3_tenant_admin_cannot_flip`：PUT `/admin/power-market` 403，开关仍关，目录/安装不变。UI：`TenantShelf.test.tsx:213` 无 `power-market-switch`。超管反向：`:183` `test_platform_admin_can_flip_switch`；`PowerMarketSwitch.test.tsx:34` |
| FR-U12 | GWT-U12.1 正常 | TC-U12.1 | 集成+单元 | ✅ | `backend/tests/test_fr_u12_u15_rbac.py:43` `test_gwt_u12_1_platform_admin_can_list`：超管 PATCH listing → `listed`。公开面可见沿用 v2 FR-33（§1.0 不重测）。UI：`Capabilities.governance.test.tsx:115` 治理壳上架控件。证据 T-09 / T-13 屏 24 |
| FR-U12 | GWT-U12.2 空态 | TC-U12.2 | 集成+单元 | ✅ | `test_fr_u12_u15_rbac.py:53` `test_gwt_u12_2_tenant_admin_listing_scan_404`：listing/scan-plugins/experts/skills/sources 与 `/admin/tenants` 同形 404，无上架控件/源列表。UI：`App.menu.test.tsx:301` `/capabilities/sources`；`:312` 租户 `/capabilities` 是货架不是 404 |
| FR-U12 | GWT-U12.3 越权 | TC-U12.3 | 集成+单元 | ✅ | `test_fr_u12_u15_rbac.py:74` `test_gwt_u12_3_tenant_admin_channel_and_listing_leftover`：listing+渠道写 404 同形，`listing_state` 不变，`authz.denied` leftover。UI：`App.menu.test.tsx:276` `/newapi` 同 404 壳（U15.3 壳；U25.3 同址 `:285`） |
| FR-U13 | GWT-U13.1 正常 | TC-U13.1 | 单元 | ✅ | `frontend/official/src/pages/CapabilityDetail.test.tsx:69`：`<script>alert(1)</script>` 与 `<img onerror>` 作 textContent；无 script/img 节点；`alert` 未调用。治理同钉：`frontend/admin/src/pages/Skills.test.tsx:50`。证据 T-11 |
| FR-U13 | GWT-U13.2 空态 | TC-U13.2 | 单元 | ✅ | `CapabilityDetail.test.tsx:87` 「暂无说明」；无 `skill-md` pre；无脚本执行 |
| FR-U13 | GWT-U13.3 越权 | TC-U13.3 | 单元 | ✅ | `CapabilityDetail.test.tsx:121` 未上架 404 商店不存在句；不渲染正文；404 HTML 内 XSS 不进 DOM |
| FR-U14 | GWT-U14.1 正常 | TC-U14.1 | 集成 | ✅ | `test_fr_u10_market.py:194` `test_gwt_u14_1_subscribe_event_queryable`：超管可查 `market_subscribe_succeeded`，含 `tenant_id`、`host=grok` |
| FR-U14 | GWT-U14.2 空态 | TC-U14.2 | 集成 | ✅ | `test_fr_u10_market.py:213` `test_gwt_u14_2_closed_attempt_no_succeeded`：关闭尝试 409，该次无 succeeded 行 |
| FR-U14 | GWT-U14.3 越权 | TC-U14.3 | 集成 | ✅ | `test_fr_u10_market.py:228` `test_gwt_u14_3_tenant_query_events_404`：租户打 product-events 与 `/admin/tenants` 同形 404，无「抱歉」、无事件名泄漏 |
| FR-U15 | GWT-U15.1 正常 | TC-U15.1 | 集成+单元 | ✅ | `test_fr_u12_u15_rbac.py:95` `test_gwt_u15_1_superadmin_list_save_rbac`：超管 GET/PUT `/rbac/roles`，刷新后勾选仍在。UI：`App.menu.test.tsx:191` 超管可达「角色权限菜单管理」。证据 T-09 / T-12 |
| FR-U15 | GWT-U15.2 空态 | TC-U15.2 | 单元 | ✅ | `App.menu.test.tsx:234` `GWT-U15.2 permissions unknown keeps read leaves…`：「权限加载中」+ AutoAgents 壳与能力市场读叶；无源/目录/中转站管控/平台运营台/用户管理。`usePermission.test.tsx:80` 空缓存不露平台写叶 |
| FR-U15 | GWT-U15.3 越权 | TC-U15.3 | 集成+单元 | ✅ | `test_fr_u12_u15_rbac.py:118` `test_gwt_u15_3_tenant_admin_rbac_404_no_sorry`：GET/PUT roles 404 同形，无「抱歉您没有权限」、无 roles/catalog。UI：`App.menu.test.tsx:169` `/rbac`；`:276` `/newapi`；`:301` listing sources — 均「页面不存在或已被移除」 |

### 1.3 N3 本波施工 · FR-U20…U24 / FR-U30…U38

具名测：`test_t14_n3_schema.py`（046 语义）· `test_fr_u31_payment_credentials.py` · `test_fr_u30_checkout.py` · `test_fr_u33_notify.py` · `test_fr_u37_payment_events.py` · `test_fr_u20_relay_sku.py`。Jest：`Checkout.test.tsx` · `RelayGroups.test.tsx` · `Pricing.test.tsx`（official/admin）· `Login.test.tsx` · `frU24CopyScan.test.tsx`（official/admin）· `App.menu.test.tsx`。T-25 是 IA（屏 2/5/10/11/12/13/14/21），不是可执行用例。T-24 **已交**（checklist + 密钥扫描）；应用层 notify 仍无 RateLimitPolicy → NFR-U03 保持 ⚠️。不把 GWT 标缺口。

**钉死：** 夹具验真 ≠ live 收银台。打开结账 ≠ 已买。`plan_pro` 履约 ≠ SKU active。可见面 0 次「当前可买」。无 `pay_url`：去支付不跳转通道托管页。

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-U20 | GWT-U20.1 正常 | TC-U20.1 | 集成+单元 | ✅ | `backend/tests/test_fr_u20_relay_sku.py:165` `test_gwt_u20_1_active_lists_own_groups_no_upstream_key`：本企组行；blob 无 `sk-`/`api_key`/`master`；SKU 非值班 URL。UI：`frontend/admin/src/pages/RelayGroups.test.tsx:284` 用量、无 master、非「中转站管控」 |
| FR-U20 | GWT-U20.2 空态 | TC-U20.2 | 集成+单元 | ✅ | `test_fr_u20_relay_sku.py:189` `test_gwt_u20_2_active_zero_tokens_empty_copy`：「还没有令牌」、非 500。UI：`RelayGroups.test.tsx:186` |
| FR-U20 | GWT-U20.3 越权 | TC-U20.3 | 集成 | ✅ | `test_fr_u20_relay_sku.py:199` `test_gwt_u20_3_cross_tenant_404_same_shape`：B 打 A 组/令牌 404 同形；B 列表无 A 组名 |
| FR-U21 | GWT-U21.1 正常 | TC-U21.1 | 集成+单元 | ✅ | `test_fr_u20_relay_sku.py:106` / `:131` 缺行≡none；组/令牌 `[]` +「未开通中转」；买方 `upgrade.product=relay`。UI：`RelayGroups.test.tsx:252` 去升级进 `product=relay`、不拉组表 |
| FR-U21 | GWT-U21.2 空态 | TC-U21.2 | 集成+单元 | ✅ | `test_fr_u20_relay_sku.py:140` 响应无「已开通/使用中」。UI：`App.menu.test.tsx:265` 导航无该角标 |
| FR-U21 | GWT-U21.3 越权 | TC-U21.3 | 集成 | ✅ | `test_fr_u20_relay_sku.py:150` SKU none 签发 422 `RELAY_SKU_INACTIVE`；令牌数仍 0（买方+经办） |
| FR-U22 | GWT-U22.1 正常 | TC-U22.1 | 集成 | ✅ | `test_fr_u20_relay_sku.py:228` `test_gwt_u22_duty_page_404_even_when_sku_active`：SKU 页无「改全局熔断」 |
| FR-U22 | GWT-U22.2 空态 | TC-U22.2 | 集成+单元 | ✅ | 同上 GET `/newapi/overview` 404 同形。UI：`App.test.tsx:80` 公司管理员 `/newapi` |
| FR-U22 | GWT-U22.3 越权 | TC-U22.3 | 集成 | ✅ | 同上 PUT 渠道窗口 spy 未调用 + 404 |
| FR-U22 | GWT-U22.4 越权 | TC-U22.4 | 集成+单元 | ✅ | 同上 `/relay/sku` 无 litellm/`/v1/chat`。UI：`App.test.tsx:66` 经办 `/newapi` 404 |
| FR-U23 | GWT-U23.1 正常 | TC-U23.1 | 集成+单元 | ✅ | `test_fr_u20_relay_sku.py:249` 当次 `plaintext_key`；再 GET 列表/详情 `None` + 前缀。UI：`RelayGroups.test.tsx:140` / `:158` |
| FR-U23 | GWT-U23.2 空态 | TC-U23.2 | 集成 | ✅ | `test_fr_u20_relay_sku.py:276` 吊销后列表「还没有令牌」 |
| FR-U23 | GWT-U23.3 越权 | TC-U23.3 | 集成 | ✅ | `test_fr_u20_relay_sku.py:343` B 持 A 令牌 by-key 404 同形 |
| FR-U23 | GWT-U23.4 边界 | TC-U23.4 | 集成+单元 | ✅ | `test_fr_u20_relay_sku.py:306` 到期签发 422「中转已到期」；令牌数不增。UI：`RelayGroups.test.tsx:276` |
| FR-U23 | GWT-U23.5 越权 | TC-U23.5 | 集成 | ✅ | `test_fr_u20_relay_sku.py:330` 经办拒签；令牌数不变；无新明文 |
| FR-U23 | GWT-U23.6 边界 | TC-U23.6 | 集成 | ✅ | `test_fr_u20_relay_sku.py:343` SKU expired 后旧令牌 by-key 404 |
| FR-U23 | GWT-U23.7 越权 | TC-U23.7 | 集成 | ✅ | 同上 A 令牌当 B 凭证 404；B 自有令牌仍 200 |
| FR-U23 | GWT-U23.8 边界 | TC-U23.8 | 集成 | ✅ | `test_fr_u20_relay_sku.py:276` 已吊销令牌 by-key 404 |
| FR-U24 | GWT-U24.1 正常 | TC-U24.1 | 单元 | ✅ | `frontend/official/src/pages/Home.test.tsx:178`；`frontend/official/src/frU24CopyScan.test.tsx:82` 官网源码+Home/Pricing/Capabilities 渲染无该四字 |
| FR-U24 | GWT-U24.2 边界 | TC-U24.2 | 单元 | ✅ | `frU24CopyScan.test.tsx:91` Pricing 源码无 `payment_succeeded` / `/billing/notify` 分支，支付成功不能改文案。**不是** live 支付后打开定价 |
| FR-U24 | GWT-U24.3 越权 | TC-U24.3 | 单元 | ✅ | `frontend/admin/src/frU24CopyScan.test.tsx:130` 无「编辑定价」「改定价文案」 |
| FR-U24 | GWT-U24.4 边界 | TC-U24.4 | 单元 | ✅ | `frontend/admin/src/frU24CopyScan.test.tsx:123` 后台全树扫描 + Checkout/Relay/货架渲染无该四字 |
| FR-U30 | GWT-U30.1 正常 | TC-U30.1 | 集成+单元 | ⚠️ 部分 | `backend/tests/test_fr_u30_checkout.py:142` POST alipay → `checkout_pending`、channel=alipay、不到 register。UI：`Checkout.test.tsx:87` 选支付宝 POST、不 POST wechat。**无 SDK / 无 pay_url**，不跳转通道托管页 |
| FR-U30 | GWT-U30.2 空态 | TC-U30.2 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:177` 二次 POST 409 `CHECKOUT_PENDING_EXISTS`「已有未完成的支付」；仍 1 行。UI：`Checkout.test.tsx:123`。约束：`test_t14_n3_schema.py:130` |
| FR-U30 | GWT-U30.3 越权 | TC-U30.3 | 集成 | ✅ | `test_fr_u30_checkout.py:197` A 列表不见 B 单；A 零行、B 一行 |
| FR-U30 | GWT-U30.4 边界 | TC-U30.4 | 集成+单元 | ⚠️ 部分 | `test_fr_u30_checkout.py:163` wechat pending、channel≠alipay。UI：`Checkout.test.tsx:105`。同 U30.1：无托管页跳转 |
| FR-U31 | GWT-U31.1 正常 | TC-U31.1 | 集成 | ✅ | `backend/tests/test_fr_u31_payment_credentials.py:69` 保存后 GET 商户号可见、密钥 `********`、响应无全文；库内密文 ≠ 明文 |
| FR-U31 | GWT-U31.2 空态 | TC-U31.2 | 集成 | ✅ | `test_fr_u31_payment_credentials.py:55` 两通道 `configured=false`；非 5xx；无 `secrets_encrypted` |
| FR-U31 | GWT-U31.3 越权 | TC-U31.3 | 集成 | ✅ | `test_fr_u31_payment_credentials.py:96` 租户 GET/PUT 404 同形；凭据不变；响应无密钥 |
| FR-U31 | GWT-U31.4 边界 | TC-U31.4 | 集成 | ✅ | `test_fr_u31_payment_credentials.py:114` 仓库 `*.yml` 无该密钥全文、无商户密钥键名 |
| FR-U31 | GWT-U31.5 边界 | TC-U31.5 | 集成 | ✅ | `test_fr_u31_payment_credentials.py:131` 轮换 `key_version=2`、旧密文不在库。履约拒旧密钥：`test_fr_u33_notify.py:285` `test_rotate_drops_old_secret_cannot_fulfill` |
| FR-U32 | GWT-U32.1 正常 | TC-U32.1 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:214` 选未配微信：422「该通道未开通」；单据 `unpaid` + `fail=unconfigured`；支付宝仍可选；`payment_failed.reason=unconfigured`；无 succeeded。UI：`Checkout.test.tsx:169` / `:180` |
| FR-U32 | GWT-U32.2 空态 | TC-U32.2 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:97` GET 200「收款通道未开通」、不建单；`:111` POST 422 零行。UI：`Checkout.test.tsx:68` 无去支付、无 POST。事件：`test_fr_u37_payment_events.py:126` |
| FR-U32 | GWT-U32.3 越权 | TC-U32.3 | 集成+单元 | ✅ | `Checkout.test.tsx:196` 只读/经办 GET 联系管理员、无去支付。不能保存通道：`test_fr_u31_payment_credentials.py:96` |
| FR-U33 | GWT-U33.1 正常 | TC-U33.1 | 集成 | ✅ | `backend/tests/test_fr_u33_notify.py:61` 专业档 fulfilled、配额专业档、SKU none、令牌 0、「未开通中转」。只读侧：`test_fr_u20_relay_sku.py:381` |
| FR-U33 | GWT-U33.2 空态 | TC-U33.2 | 集成 | ✅ | `test_fr_u33_notify.py:80` 无已付单；档位空；SKU none |
| FR-U33 | GWT-U33.3 越权 | TC-U33.3 | 集成 | ✅ | `test_fr_u33_notify.py:94` B 开通后 A 档位/SKU 不变；A 不见 B 单 |
| FR-U33 | GWT-U33.4 边界 | TC-U33.4 | 集成 | ✅ | `test_fr_u33_notify.py:106` 微信 `relay` → SKU active；档位不变 |
| FR-U33 | GWT-U33.5 部分失败 | TC-U33.5 | 集成+单元 | ✅ | `test_fr_u33_notify.py:122` `paid_pending_fulfillment` +「支付已到账，开通处理中」；档位/SKU 仍开通前。UI：`Checkout.test.tsx:154`；`RelayGroups.test.tsx:294` 顶栏处理中、内容仍 none |
| FR-U33 | GWT-U33.6 边界 | TC-U33.6 | 集成 | ✅ | `test_fr_u33_notify.py:140` 同一成功通知两次只开通一次；配额不叠加 |
| FR-U34 | GWT-U34.1 正常 | TC-U34.1 | 集成 | ✅ | `test_fr_u33_notify.py:152` cancel → unpaid +「支付未完成，套餐未开通」；档位/SKU 未开 |
| FR-U34 | GWT-U34.2 空态 | TC-U34.2 | 集成 | ✅ | `test_fr_u33_notify.py:169` timeout → unpaid、非已买 |
| FR-U34 | GWT-U34.3 越权 | TC-U34.3 | 集成 | ✅ | `test_fr_u33_notify.py:183` 只读 confirm 拒；仍 `checkout_pending` |
| FR-U34 | GWT-U34.4 非法流转 | TC-U34.4 | 集成 | ✅ | `test_fr_u33_notify.py:193` 取消后迟到成功：unpaid + `late_notify_at`；无 `payment_succeeded`；不开通 |
| FR-U34 | GWT-U34.5 边界 | TC-U34.5 | 集成 | ✅ | `test_fr_u33_notify.py:211` `channel_error` → unpaid；非 5xx；无「当前可买」 |
| FR-U35 | GWT-U35.1 正常 | TC-U35.1 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:246` `product_code=plan_pro`。UI：`frontend/official/src/pages/Pricing.test.tsx:76`；`frontend/admin/src/pages/Pricing.test.tsx:39` 去结账不到注册 |
| FR-U35 | GWT-U35.2 空态 | TC-U35.2 | 单元 | ✅ | `frontend/admin/src/pages/Login.test.tsx:72` `from` 保留 `product=plan_pro` |
| FR-U35 | GWT-U35.3 越权 | TC-U35.3 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:300` viewer 联系管理员、零单。UI：`admin/src/pages/Pricing.test.tsx:59` |
| FR-U35 | GWT-U35.4 边界 | TC-U35.4 | 单元 | ✅ | `official/src/pages/Pricing.test.tsx:64` 免费档「免费注册」→ `/register` |
| FR-U35 | GWT-U35.5 正常 | TC-U35.5 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:258` `plan_enterprise`。UI：official `:76` / admin `:51`。无 `plan_ent`：`test_fr_u30_checkout.py:350`；`Checkout.test.tsx:210` |
| FR-U35 | GWT-U35.6 出口 | TC-U35.6 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:272` `product=relay`、`plan_id` NULL。UI：`RelayGroups.test.tsx:252` 去升级 `product=relay`、不到注册 |
| FR-U35 | GWT-U35.7 越权 | TC-U35.7 | 单元 | ✅ | `RelayGroups.test.tsx:267` 经办去升级 = 联系管理员、不到结账 |
| FR-U36 | GWT-U36.1 正常 | TC-U36.1 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:125` 仅支付宝已配：alipay 可选、wechat 不可选、`can_pay=true`、无两通道空态句。UI：`Checkout.test.tsx:169` |
| FR-U36 | GWT-U36.2 空态 | TC-U36.2 | 集成+单元 | ✅ | `test_fr_u30_checkout.py:313` 经办 GET/POST 联系管理员、零单。UI：`Checkout.test.tsx:196` |
| FR-U36 | GWT-U36.3 越权 | TC-U36.3 | 集成 | ✅ | `test_fr_u30_checkout.py:328` 匿名 POST 401/403；单据不变 |
| FR-U36 | GWT-U36.4 越权 | TC-U36.4 | 集成 | ✅ | `test_fr_u30_checkout.py:337` 超管 `CHECKOUT_SUPERADMIN_FORBIDDEN`；A 零单 |
| FR-U37 | GWT-U37.1 正常 | TC-U37.1 | 集成 | ✅ | `backend/tests/test_fr_u37_payment_events.py:37` 超管可查 `payment_succeeded`，含 `tenant_id`/`channel=alipay`/`product=plan_pro`；无密钥 |
| FR-U37 | GWT-U37.2 空态 | TC-U37.2 | 集成 | ✅ | `test_fr_u37_payment_events.py:50` `reason=cancel`；无 succeeded |
| FR-U37 | GWT-U37.3 越权 | TC-U37.3 | 集成 | ✅ | `test_fr_u37_payment_events.py:59` 租户 404 同形；无「抱歉」、无事件名 |
| FR-U37 | GWT-U37.4 边界 | TC-U37.4 | 集成 | ✅ | `test_fr_u37_payment_events.py:74` `reason=timeout`；无 succeeded |
| FR-U37 | GWT-U37.5 边界 | TC-U37.5 | 集成 | ✅ | `test_fr_u37_payment_events.py:82` `reason=channel_error`；档位未开；无 succeeded |
| FR-U37 | GWT-U37.6 空态 | TC-U37.6 | 集成 | ✅ | `test_fr_u37_payment_events.py:92` `reason=unconfigured`；单据 unpaid；无 succeeded |
| FR-U37 | GWT-U37.7 边界 | TC-U37.7 | 集成 | ✅ | `test_fr_u37_payment_events.py:107` 开通前 `paid_pending_fulfillment` 已可查 succeeded；档位/SKU 仍开通前 |
| FR-U37 | GWT-U37.8 空态 | TC-U37.8 | 集成 | ✅ | `test_fr_u37_payment_events.py:126` 仅打开结账：无新支付事件、无单据 |
| FR-U38 | GWT-U38.1 正常 | TC-U38.1 | 集成 | ⚠️ 部分 | 夹具四要素通过后走 U33.1/U33.4（`test_fr_u33_notify.py:61` / `:106`）。**不是** live 通道真通知 |
| FR-U38 | GWT-U38.2 空态 | TC-U38.2 | 集成 | ✅ | `test_fr_u33_notify.py:227` 无待支付：不开通、无 succeeded、不建已买单 |
| FR-U38 | GWT-U38.3 越权 | TC-U38.3 | 集成 | ✅ | `test_fr_u33_notify.py:238` 缺签名成功报文：仍 pending；无 succeeded |
| FR-U38 | GWT-U38.4 边界 | TC-U38.4 | 集成 | ✅ | `test_fr_u33_notify.py:251` 金额不符：仍 pending；无 succeeded |
| FR-U38 | GWT-U38.5 边界 | TC-U38.5 | 集成 | ✅ | `test_fr_u33_notify.py:262` 商户不符：仍 pending；无 succeeded |
| FR-U38 | GWT-U38.6 边界 | TC-U38.6 | 集成 | ✅ | `test_fr_u33_notify.py:273` 订单号不符：仍 pending；无 succeeded |

### 1.3b N4 本波施工 · FR-U25（T-26 / T-27，implement r2 后）

具名测：`backend/tests/test_fr_u25_duty.py`（T-26，**10** pytest）。Jest：`frontend/admin/src/components/newapi/Overview3q.test.tsx` · `frontend/admin/src/pages/NewApiOps.test.tsx` · `frontend/admin/src/App.menu.test.tsx`（T-27，三套合计 **43** Jest）。证据：`03-impl/T-26-evidence.md` · `T-27-evidence.md`。

**钉死：** 空 / 降级 / 活 三句互斥，禁止「暂无渠道」。值班「活」≠ SKU active ≠ 「当前可买」。租户直打仍 404 同形（与 GWT-U22.2 同形，是值班越权 Then，不是「我的渠道组」）。伪装不自动关渠（GWT-07.6 回归，**不**重测 v2 FR-nn）。网关用 monkeypatch / jest mock，**不是** live LiteLLM。Q-OPS-DUTY **无** SLA 数字。屏 19 离线 hint **无 Jest** → 不升 GWT-U25 行（§5 ⚠️）。

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-U25 | GWT-U25.1 正常 | TC-U25.1 | 集成+单元 | ✅ | `backend/tests/test_fr_u25_duty.py:293` `test_gwt_u25_1_live_row_not_empty_or_degrade`：行 `duty_row_status=live` / 「活」；页 `duty_page_state=live`；非空/降级句。UI：`Overview3q.test.tsx:158` GWT-U25.1；`NewApiOps.test.tsx:550` GWT-U25.1。互斥：`Overview3q.test.tsx:90` / `:111` **hasLiveRow 压过 empty/degrade**（`duty_page_state=empty` 仍出 live）；`:137` **行活须 `gatewayAvailable`**（false 即使 API 标 live 也不标「活」）；`:280` empty+活行不出空句。证据 T-26 / T-27 |
| FR-U25 | GWT-U25.2 空态 | TC-U25.2 | 集成+单元 | ✅ | `test_fr_u25_duty.py:135` `test_gwt_u25_2_empty_reachable_zero_models`：Given=**0 模型**；「还没有平台模型，去网关登记」；`duty_page_state=empty`；禁「暂无渠道」；非加载失败。UI：`Overview3q.test.tsx:185`；`NewApiOps.test.tsx:89` GWT-71.2。第四态不塌进本句：见 TC-U25.4th |
| FR-U25 | GWT-U25.3 越权 | TC-U25.3 | 集成+单元 | ✅ | `test_fr_u25_duty.py:323` `test_gwt_u25_3_tenant_company_admin_duty_apis_404`：overview/events/probe-results/channels/POST probe 与 `/admin/tenants` 同形 404；无列表/密钥/抱歉。UI：`App.menu.test.tsx:285` GWT-U25.3（无总览 Tab、无空/降级句、无密钥、无「抱歉您没有权限」）。租户 404 壳与 GWT-U22.2 同形，**不是**渠道组 |
| FR-U25 | GWT-U25.4 降级 | TC-U25.4 | 集成+单元 | ✅ | `test_fr_u25_duty.py:154` `test_gwt_u25_4_degrade_unreachable_keeps_local`：「LLM 网关管理面不可达，仅本地事件/探针」；本地 24h 仍回；不拉 `latest_result`；禁空句/暂无渠道。非空夹具：`:177` `test_gwt_u25_4_degrade_nonempty_models_not_live`（注入已标 live 的行 → 不得 `duty_row_status=live`）。UI：`Overview3q.test.tsx:205`；`NewApiOps.test.tsx:114` GWT-71.3。网关不可达走 mock，不把 mock 可达写成 Q-OPS-DUTY SLA |

### 1.4 NFR-U*

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| NFR-U01 | 提交 3s 入队/拦住；去支付 5s | TC-U01.1 / TC-U02.1 / TC-U32.2 / TC-U36.1 | 集成+单元 | ⚠️ 部分 | 入队/工人拦住 pytest monotonic ≤3s（`test_fr_u01_enqueue.py:204`）。去支付：GET 即出通道 Radio 或「收款通道未开通」（`test_fr_u30_checkout.py:97` / `:125`；`Checkout.test.tsx:68` / `:169`）。**无 5s monotonic** |
| NFR-U02 | 同一商品最多 1 笔待支付 | TC-U30.2 | 集成+单元 | ✅ | GWT-U30.2：409 + UNIQUE `open_product_slot`（`test_t14_n3_schema.py:130`）。导出 100 条沿用 v2，本波不重测 |
| NFR-U03 | 单通道不可用 / 两通道空态 | TC-U32.1 / TC-U32.2 / TC-U02.1 / TC-U25.4 | 集成+单元 | ⚠️ 部分 | U32.1/U32.2 + 工人不在线已测。网关挂走 U25.4 降级句，不是套餐超限（v2 FR-74 仍豁免不重测）。T-24 **已交**（checklist + 密钥扫描）；应用层 notify 仍无 RateLimitPolicy → NFR-U03 保持 ⚠️。不把 GWT 标缺口 |
| NFR-U04 | 商户凭据 / 令牌一次明文 / [SEC-1] | TC-U31.1 / U23.1 / U38.3 / U13.1 / U01.3 | 集成+单元 | ✅ | 凭据加密落库+掩码+不进 yml：U31。明文一次：U23.1。跨租户：U01.3/U20.3/U30.3/U23.3。SKILL.md：U13.1。[SEC-1]：U38.3–6 伪造/不符不开通、无 succeeded |
| NFR-U05 | 权限三态 | TC-U15.1 / U15.2 / U15.3 | 集成+单元 | ✅ | 未知=「权限加载中」+读叶（`App.menu.test.tsx:234`）；拒绝=404 同形无「抱歉您没有权限」（`test_fr_u12_u15_rbac.py:118`）；允许=超管保存勾选（`:95`） |
| NFR-U06 | 可见面禁四字切片 | TC-U24.1 / U24.4 | 单元 | ✅ | T-23 机械钉：official+admin 非测试 src 全树 + homepage/pricing/checkout/relay/capabilities 渲染。Q-AGPL 未关；**支付通道能收款 ≠ 本问已答** |
| NFR-U07 | 不破坏夹具出数环 | — | 集成 | ⚠️ 部分 | T-02 回归 `test_spider_min_loop.py`（FakeRedis）。live 120s 工人未跑（本波也未重跑 v2 GWT-18.1 live） |
| NFR-U08 | 拦住 vs 完成可查；支付失败 reason 闭集 | TC-U03.4 / U03.5 / U14.1 / U37.1…U37.6 | 集成 | ✅ | D3 已由 FR-U03 覆盖。`market_subscribe_succeeded` 已由 FR-U14 覆盖。`payment_failed.reason` 闭集 `cancel`/`timeout`/`channel_error`/`unconfigured`：U37.2/4/5/6。验真失败无 succeeded：U38.3–6。T-05 开放：规划 token 满仍发 `quota_exceeded`（入队不查 token；GWT-U03.4 When 是工人拦住，不把该开放标 ❌） |
| NFR-U09 | 国际化 | — | — | ➖ **N/A** | spec 本轮仅中文 |
| NFR-U10 | 凭据/总开关来自运行配置 | TC-U11.3 / TC-U31.4 | 集成 | ✅ | 市场总开关 `POWER_MARKET.ENABLED`：`test_fr_u10_market.py:166` / `:183`。商户凭据：表内密文、yml 无密钥键（U31.4）；不把 yaml 当支付密钥 |

---

## 2. 反向：用例 → FR/NFR

| 用例 ID | 名称 | 对应 FR/NFR | 层 |
|---|---|---|---|
| TC-U01.1 | `test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant` + `TaskModal.test.tsx` 已入队 | FR-U01 / GWT-U01.1 / NFR-U01 | 集成+单元 |
| TC-U01.2 | `test_gwt_u01_2_empty_results_copy_is_actionable` + `Data.test.tsx` | FR-U01 / GWT-U01.2 | 集成+单元 |
| TC-U01.3 | `test_gwt_u01_3_cross_tenant_result_same_as_missing` | FR-U01 / GWT-U01.3 | 集成 |
| TC-U02.1 | `test_gwt_u02_1_worker_offline_blocks_within_3s_and_emits_task_blocked` | FR-U02 / GWT-U02.1 / NFR-U01 | 集成 |
| TC-U02.2 | `test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta` | FR-U02 / GWT-U02.2 | 集成 |
| TC-U02.3 | `test_gwt_u02_3_readonly_submit_rejected_no_enqueue` | FR-U02 / GWT-U02.3 | 集成 |
| TC-U02.4 | `test_gwt_u02_4_token_full_planning_is_quota_copy_not_worker` | FR-U02 / GWT-U02.4 | 集成 |
| TC-U02.5 | `test_gwt_u02_5_usage_near_limit_is_not_full_copy` | FR-U02 / GWT-U02.5 | 集成 |
| TC-U02.6 | `test_gwt_u02_6_operator_upgrade_intent_contact_admin_no_order` / viewer 同名 | FR-U02 / GWT-U02.6 | 集成 |
| TC-U02.7 | `test_gwt_u02_7_buyer_upgrade_intent_checkout_path_no_order` + `Checkout.test.tsx` | FR-U02 / GWT-U02.7 | 集成+单元 |
| TC-U03.1 | `test_gwt_u03_1_non_fixture_completed_snapshot_false` | FR-U03 / GWT-U03.1 | 集成 |
| TC-U03.2 | `test_gwt_u03_2_fixture_excluded_from_north_star` | FR-U03 / GWT-U03.2 | 集成 |
| TC-U03.3 | `test_gwt_u03_3_tenant_query_and_membership_are_404` | FR-U03 / GWT-U03.3 | 集成 |
| TC-U03.4 | `test_gwt_u03_4_blocked_distinct_from_completed` + `test_storage_full_emits_task_blocked_not_completed` | FR-U03 / GWT-U03.4 / NFR-U08 | 集成 |
| TC-U03.5 | `test_gwt_u03_5_completed_not_in_blocked_numerator` | FR-U03 / GWT-U03.5 | 集成 |
| TC-U04.1 | `Home.test.tsx` / `App.test.tsx` Hero 第一句 | FR-U04 / GWT-U04.1 | 单元 |
| TC-U04.2 | `GWT-U04.2 featured empty does not replace hero` | FR-U04 / GWT-U04.2 | 单元 |
| TC-U04.3 | `GWT-U04.3 no edit-hero entry on official home` | FR-U04 / GWT-U04.3 | 单元 |
| TC-U03.idem | `test_add_fixture_is_idempotent_unique_tenant` | FR-U03 名单唯一键 | 集成 |
| TC-U02.conc | `test_concurrency_full_enqueue_uses_upgrade_cta_not_worker` | FR-U02 工人句分家 | 集成 |
| TC-U10.1 | `test_gwt_u10_1_subscribe_one_row_no_children` + `TenantShelf.test.tsx` GWT-U10.1 | FR-U10 / GWT-U10.1 | 集成+单元 |
| TC-U10.2 | `test_gwt_u10_2_open_empty_shelf_not_closed` + official/admin 空货架 Jest | FR-U10 / GWT-U10.2 | 集成+单元 |
| TC-U10.3 | `test_gwt_u10_3_readonly_rejected` + `TenantShelf.test.tsx` GWT-U10.3 | FR-U10 / GWT-U10.3 | 集成+单元 |
| TC-U10.4 | `test_gwt_u10_4_coming_soon_not_subscribable` + TenantShelf / official GWT-31.5 | FR-U10 / GWT-U10.4 | 集成+单元 |
| TC-U11.1 | `test_gwt_u11_1_closed_subscribe_no_row` + `SubscribeModal.test.tsx` MARKET_CLOSED | FR-U11 / GWT-U11.1 | 集成+单元 |
| TC-U11.2 | `test_gwt_u11_2_closed_list_not_empty_shelf` + official/admin 关闭句 Jest | FR-U11 / GWT-U11.2 | 集成+单元 |
| TC-U11.3 | `test_gwt_u11_3_tenant_admin_cannot_flip` + TenantShelf 无总开关 | FR-U11 / GWT-U11.3 / NFR-U10 | 集成+单元 |
| TC-U12.1 | `test_gwt_u12_1_platform_admin_can_list` + governance 上架控件 | FR-U12 / GWT-U12.1 | 集成+单元 |
| TC-U12.2 | `test_gwt_u12_2_tenant_admin_listing_scan_404` + `App.menu.test.tsx` sources 404 | FR-U12 / GWT-U12.2 | 集成+单元 |
| TC-U12.3 | `test_gwt_u12_3_tenant_admin_channel_and_listing_leftover` + `/newapi` 404 壳 | FR-U12 / GWT-U12.3 | 集成+单元 |
| TC-U13.1 | `CapabilityDetail.test.tsx` GWT-U13.1 + `Skills.test.tsx` GWT-U13.1 | FR-U13 / GWT-U13.1 / NFR-U04 | 单元 |
| TC-U13.2 | `CapabilityDetail.test.tsx` GWT-U13.2 暂无说明 | FR-U13 / GWT-U13.2 | 单元 |
| TC-U13.3 | `CapabilityDetail.test.tsx` GWT-U13.3 unlisted 商店不存在 | FR-U13 / GWT-U13.3 | 单元 |
| TC-U14.1 | `test_gwt_u14_1_subscribe_event_queryable` | FR-U14 / GWT-U14.1 / NFR-U08 | 集成 |
| TC-U14.2 | `test_gwt_u14_2_closed_attempt_no_succeeded` | FR-U14 / GWT-U14.2 | 集成 |
| TC-U14.3 | `test_gwt_u14_3_tenant_query_events_404` | FR-U14 / GWT-U14.3 | 集成 |
| TC-U15.1 | `test_gwt_u15_1_superadmin_list_save_rbac` + `App.menu.test.tsx` 超管 /rbac | FR-U15 / GWT-U15.1 / NFR-U05 | 集成+单元 |
| TC-U15.2 | `App.menu.test.tsx` GWT-U15.2 + `usePermission.test.tsx` 空缓存 | FR-U15 / GWT-U15.2 / NFR-U05 | 单元 |
| TC-U15.3 | `test_gwt_u15_3_tenant_admin_rbac_404_no_sorry` + `/rbac` `/newapi` 404 壳 | FR-U15 / GWT-U15.3 / NFR-U05 | 集成+单元 |
| TC-U11.flip | `test_platform_admin_can_flip_switch` + `PowerMarketSwitch.test.tsx` | FR-U11 超管可改开关（U11.3 反向） | 集成+单元 |
| TC-U20.1 | `test_gwt_u20_1_active_lists_own_groups_no_upstream_key` + `RelayGroups.test.tsx` GWT-U20.1 | FR-U20 / GWT-U20.1 | 集成+单元 |
| TC-U20.2 | `test_gwt_u20_2_active_zero_tokens_empty_copy` + RelayGroups GWT-U20.2 | FR-U20 / GWT-U20.2 | 集成+单元 |
| TC-U20.3 | `test_gwt_u20_3_cross_tenant_404_same_shape` | FR-U20 / GWT-U20.3 | 集成 |
| TC-U21.1 | `test_gwt_u21_1_missing_row_empty_copy_upgrade_relay` + RelayGroups GWT-U21.1 | FR-U21 / GWT-U21.1 / GWT-U35.6 | 集成+单元 |
| TC-U21.2 | `test_gwt_u21_2_nav_has_no_subscribed_badge` + `App.menu.test.tsx` GWT-U21.2 | FR-U21 / GWT-U21.2 | 集成+单元 |
| TC-U21.3 | `test_gwt_u21_3_issue_refused_when_inactive` | FR-U21 / GWT-U21.3 | 集成 |
| TC-U22.duty | `test_gwt_u22_duty_page_404_even_when_sku_active` + App.test `/newapi` | FR-U22 / GWT-U22.1…U22.4 | 集成+单元 |
| TC-U23.1 | `test_gwt_u23_1_plaintext_once_later_prefix_only` | FR-U23 / GWT-U23.1 / NFR-U04 | 集成 |
| TC-U23.2 | `test_gwt_u23_2_revoked_only_shows_empty_tokens` | FR-U23 / GWT-U23.2 / GWT-U23.8 | 集成 |
| TC-U23.4 | `test_gwt_u23_4_expired_sku_issue_copy` + RelayGroups GWT-U23.4 | FR-U23 / GWT-U23.4 | 集成+单元 |
| TC-U23.5 | `test_gwt_u23_5_operator_cannot_issue_when_active` | FR-U23 / GWT-U23.5 | 集成 |
| TC-U23.cred | `test_gwt_u23_3_6_7_token_as_credential` | FR-U23 / GWT-U23.3 / U23.6 / U23.7 | 集成 |
| TC-U24.1 | official `Home.test.tsx` GWT-U24.1 + `frU24CopyScan.test.tsx` | FR-U24 / GWT-U24.1 / U24.2 / NFR-U06 | 单元 |
| TC-U24.4 | admin `frU24CopyScan.test.tsx` | FR-U24 / GWT-U24.3 / U24.4 / NFR-U06 | 单元 |
| TC-U30.1 | `test_gwt_u30_1_alipay_creates_pending` + Checkout GWT-U30.1 | FR-U30 / GWT-U30.1 | 集成+单元 |
| TC-U30.2 | `test_gwt_u30_2_second_pending_409` + Checkout GWT-U30.2 | FR-U30 / GWT-U30.2 / NFR-U02 | 集成+单元 |
| TC-U30.3 | `test_gwt_u30_3_tenant_a_cannot_see_b` | FR-U30 / GWT-U30.3 | 集成 |
| TC-U30.4 | `test_gwt_u30_4_wechat_creates_pending` + Checkout GWT-U30.4 | FR-U30 / GWT-U30.4 | 集成+单元 |
| TC-U31.1 | `test_gwt_u31_1_save_then_get_masks_secret` | FR-U31 / GWT-U31.1 / NFR-U04 | 集成 |
| TC-U31.2 | `test_gwt_u31_2_empty_form_both_unconfigured` | FR-U31 / GWT-U31.2 | 集成 |
| TC-U31.3 | `test_gwt_u31_3_tenant_404_same_shape_no_secret` | FR-U31 / GWT-U31.3 / GWT-U32.3 | 集成 |
| TC-U31.4 | `test_gwt_u31_4_secret_not_in_config_or_git` | FR-U31 / GWT-U31.4 / NFR-U10 | 集成 |
| TC-U31.5 | `test_gwt_u31_5_rotate_drops_old_secret` + notify 旧密钥拒履约 | FR-U31 / GWT-U31.5 | 集成 |
| TC-U32.1 | `test_gwt_u32_1_unconfigured_channel_pending_then_unpaid` | FR-U32 / GWT-U32.1 / NFR-U03 | 集成 |
| TC-U32.2 | `test_gwt_u32_2_get_both_unconfigured_200_empty_no_order` + Checkout GWT-U32.2 | FR-U32 / GWT-U32.2 / NFR-U01 / NFR-U03 | 集成+单元 |
| TC-U32.3 | Checkout operator/readonly GET + U31.3 | FR-U32 / GWT-U32.3 | 集成+单元 |
| TC-U33.1 | `test_gwt_u33_1_plan_pro_opens_pro_not_relay` | FR-U33 / GWT-U33.1 / GWT-U38.1 | 集成 |
| TC-U33.2 | `test_gwt_u33_2_no_paid_order_keeps_plan` | FR-U33 / GWT-U33.2 | 集成 |
| TC-U33.3 | `test_gwt_u33_3_tenant_b_pay_does_not_open_a` | FR-U33 / GWT-U33.3 | 集成 |
| TC-U33.4 | `test_gwt_u33_4_relay_wechat_opens_sku_not_plan` | FR-U33 / GWT-U33.4 / GWT-U38.1 | 集成 |
| TC-U33.5 | `test_gwt_u33_5_verified_before_fulfill_shows_processing` + Checkout/Relay 处理中 | FR-U33 / GWT-U33.5 | 集成+单元 |
| TC-U33.6 | `test_gwt_u33_6_duplicate_notify_fulfills_once` | FR-U33 / GWT-U33.6 | 集成 |
| TC-U34.1 | `test_gwt_u34_1_cancel_stays_unpaid` | FR-U34 / GWT-U34.1 | 集成 |
| TC-U34.2 | `test_gwt_u34_2_timeout_not_bought` | FR-U34 / GWT-U34.2 | 集成 |
| TC-U34.3 | `test_gwt_u34_3_viewer_cannot_mark_paid` | FR-U34 / GWT-U34.3 | 集成 |
| TC-U34.4 | `test_gwt_u34_4_late_success_after_cancel` | FR-U34 / GWT-U34.4 | 集成 |
| TC-U34.5 | `test_gwt_u34_5_channel_error_unpaid` | FR-U34 / GWT-U34.5 | 集成 |
| TC-U35.1 | `test_gwt_u35_1_product_plan_pro` + official/admin Pricing | FR-U35 / GWT-U35.1 | 集成+单元 |
| TC-U35.2 | `Login.test.tsx` GWT-U35.2 | FR-U35 / GWT-U35.2 | 单元 |
| TC-U35.3 | `test_gwt_u35_3_viewer_no_order` + admin Pricing GWT-U35.3 | FR-U35 / GWT-U35.3 | 集成+单元 |
| TC-U35.4 | official Pricing 免费注册 `/register` | FR-U35 / GWT-U35.4 | 单元 |
| TC-U35.5 | `test_gwt_u35_5_product_plan_enterprise` + Pricing 企业档 | FR-U35 / GWT-U35.5 | 集成+单元 |
| TC-U35.6 | `test_gwt_u35_6_product_relay` + RelayGroups 去升级 | FR-U35 / GWT-U35.6 | 集成+单元 |
| TC-U35.7 | RelayGroups GWT-U35.7 | FR-U35 / GWT-U35.7 | 单元 |
| TC-U36.1 | `test_one_channel_unconfigured_other_selectable` | FR-U36 / GWT-U36.1 / NFR-U01 | 集成 |
| TC-U36.2 | `test_gwt_u36_2_operator_contact_admin_no_order` | FR-U36 / GWT-U36.2 | 集成 |
| TC-U36.3 | `test_gwt_u36_3_anonymous_no_order` | FR-U36 / GWT-U36.3 | 集成 |
| TC-U36.4 | `test_gwt_u36_4_superadmin_cannot_pay` | FR-U36 / GWT-U36.4 | 集成 |
| TC-U37.1 | `test_gwt_u37_1_succeeded_queryable_with_channel_product` | FR-U37 / GWT-U37.1 / NFR-U08 | 集成 |
| TC-U37.2 | `test_gwt_u37_2_cancel_failed_no_succeeded` | FR-U37 / GWT-U37.2 / NFR-U08 | 集成 |
| TC-U37.3 | `test_gwt_u37_3_tenant_404_same_shape` | FR-U37 / GWT-U37.3 | 集成 |
| TC-U37.4 | `test_gwt_u37_4_timeout_failed_event` | FR-U37 / GWT-U37.4 / NFR-U08 | 集成 |
| TC-U37.5 | `test_gwt_u37_5_channel_error_failed_plan_unchanged` | FR-U37 / GWT-U37.5 / NFR-U08 | 集成 |
| TC-U37.6 | `test_gwt_u37_6_unconfigured_failed_no_succeeded` | FR-U37 / GWT-U37.6 / NFR-U08 | 集成 |
| TC-U37.7 | `test_gwt_u37_7_succeeded_visible_before_fulfill` | FR-U37 / GWT-U37.7 | 集成 |
| TC-U37.8 | `test_gwt_u37_8_open_checkout_no_payment_events` | FR-U37 / GWT-U37.8 | 集成 |
| TC-U38.2 | `test_gwt_u38_2_unknown_order_no_noop` | FR-U38 / GWT-U38.2 / NFR-U04 | 集成 |
| TC-U38.3 | `test_gwt_u38_3_missing_sign_stays_pending` | FR-U38 / GWT-U38.3 / NFR-U04 | 集成 |
| TC-U38.4 | `test_gwt_u38_4_amount_mismatch` | FR-U38 / GWT-U38.4 / NFR-U04 | 集成 |
| TC-U38.5 | `test_gwt_u38_5_merchant_mismatch` | FR-U38 / GWT-U38.5 / NFR-U04 | 集成 |
| TC-U38.6 | `test_gwt_u38_6_wrong_order_no` | FR-U38 / GWT-U38.6 / NFR-U04 | 集成 |
| TC-N3.schema | `test_t14_n3_schema.py` 一待支付槽 / CAS unpaid→fulfilled 0 行 / 凭据 UNIQUE | FR-U30 / U33 / U38 约束 | 集成 |
| TC-N3.cas | `test_illegal_fulfill_cas_unpaid_rowcount_zero` | FR-U34.4 非法开通原语 | 集成 |
| TC-U25.1 | `test_gwt_u25_1_live_row_not_empty_or_degrade` + Overview3q `:158` / NewApiOps `:550` GWT-U25.1 | FR-U25 / GWT-U25.1 | 集成+单元 |
| TC-U25.2 | `test_gwt_u25_2_empty_reachable_zero_models` + Overview3q `:185` / NewApiOps `:89` | FR-U25 / GWT-U25.2 | 集成+单元 |
| TC-U25.3 | `test_gwt_u25_3_tenant_company_admin_duty_apis_404` + `App.menu.test.tsx:285` GWT-U25.3 | FR-U25 / GWT-U25.3 | 集成+单元 |
| TC-U25.4 | `test_gwt_u25_4_degrade_unreachable_keeps_local` + Overview3q `:205` / NewApiOps `:114` | FR-U25 / GWT-U25.4 / NFR-U03 | 集成+单元 |
| TC-U25.4n | `test_gwt_u25_4_degrade_nonempty_models_not_live`（`:177`） | FR-U25 / GWT-U25.4 非空夹具（QA-03） | 集成 |
| TC-U25.4th | `test_gwt_u25_reachable_registered_no_original_not_empty`（`:208`） | FR-U25 第四态（非 GWT 行；可达+≥1 模型+无 original → page_state null，不塌 U25.2） | 集成 |
| TC-U25.scope | `test_overview_latest_probe_scoped_to_current_gateway_refs`（`:232`） | FR-U25 查询收口：当前 gateway_ref + 24h 窗（QA-05） | 集成 |
| TC-U25.noscan | `test_latest_result_per_channel_without_ids_does_not_scan`（`:258`） | FR-U25 无集合不 execute（QA-05） | 单元 |
| TC-U25.sql | `test_latest_result_per_channel_sql_bounded_to_ids_and_since`（`:271`） | FR-U25 SQL IN + since + LIMIT（QA-05） | 单元 |
| TC-U25.liveov | Overview3q `:111` hasLiveRow overrides empty/degrade；`:280` empty+活行不出空句 | FR-U25 / GWT-U25.1 页标题（QA-02） | 单元 |
| TC-U25.gw | Overview3q `:137` `showDutyLiveRow` 须 `gatewayAvailable` | FR-U25 / GWT-U25.1 行活闸（QA-02） | 单元 |
| TC-U25.spoof | `test_gwt_u25_spoofed_does_not_auto_disable_channel`（`:347`）+ Overview3q spoofed + NewApiOps GWT-61.1 | FR-U25 伪装不关渠（v2 GWT-07.6 回归，不重测 FR-nn） | 集成+单元 |
| TC-U25.fail | Overview3q `:229` / NewApiOps `:584` `load fail is not empty` | FR-U25 加载失败 ≠ 空（屏 19 错误族；**不是**离线 hint） | 单元 |

**无直接 FR 的用例处理**：T-01 `test_snapshot_unchanged_after_membership_remove` / `test_null_legacy_events_excluded_from_non_fixture_filter` 支撑北极星等值谓词，属 FR-U03 隐含。`test_plan_pro_order_does_not_open_relay` 属 FR-U33.1 只读侧。`test_gwt_u35_enterprise_notify_opens_enterprise` 属 U35.5 履约。T-07 / T-13 / T-25 无测试文件（设计票）。T-24 **已交**（checklist + 密钥扫描，无新测试文件）；应用层 notify 仍无 RateLimitPolicy。T-26 `test_fr_u25_duty.py` 10 条；T-27 Overview3q / NewApiOps / App.menu 43 Jest。TC-U25.4th / scope / noscan / sql **不是** GWT-U25 行，指回 FR-U25 支撑。屏 19 离线 hint 无用例 ID（§5 ⚠️）。

---

## 3. 状态流转覆盖

### 3.1 采集任务（本波加深，必填）

| 状态＼操作 | 提交（有工人+配额） | 提交（无工人） | 提交（存储/并发满） | 只读提交 | 跨租户读结果 |
|---|---|---|---|---|---|
| （无任务） | ✅ TC-U01.1 | ✅ TC-U02.1 | ✅ TC-U02.2 | ✅ TC-U02.3 | ✅ TC-U01.3 |
| pending/queued | ✅ 入队后 status≠running | ❌ 零新行 | ❌ 零新行 | ❌ 零新行 | — 不读他企 |
| running → completed 条数>0 | ⚠️ FakeRedis 回流 | — | — | — | ✅ 他企 0 行 |
| 拦住（不入队） | — | ✅ `task_blocked` | ✅ `task_blocked` quota_* | ✅ 拒绝无事件要求 | — |

✅ = 合法流转已测｜❌ = 非法流转已测｜➖ = 本波不适用

**非法流转三项断言**：状态未变（零新任务行）☑；记录符合预期（`task_blocked` vs `task_completed`）☑；无副作用（结果不写入他企）☑

### 3.2 中转 SKU

| 状态＼操作 | 验真成功商品=relay | 验真成功商品=plan_pro | 伪造/金额/商户/单号不符 | 到期签发 | 用旧令牌读用量 |
|---|---|---|---|---|---|
| SKU none（缺行/显式 none） | ✅ TC-U33.4 → active | ❌ TC-U33.1 保持 none；令牌 0 | ❌ TC-U38.3…6 保持 none；无 succeeded | — | — |
| SKU active | — 已开通 | — 档位开通不改 SKU | — | — | ✅ 本企 200；❌ 跨企 TC-U23.cred |
| SKU expired | — 续费边未单独开票（走 U33.4 同类） | — | — | ❌ TC-U23.4 无新令牌 | ❌ TC-U23.cred expired 后 404 |

**非法流转三项断言**：SKU 未误升 active ☑；无 `payment_succeeded`（伪造）☑；无新令牌（到期/经办）☑

### 3.3 支付单据

| 状态＼操作 | 夹具验真+开通完成 | 验真通过开通未完成 | 取消/超时/通道失败 | 选未配通道去支付 | 伪造/四要素不符 | 迟到成功 | 只读标已买 |
|---|---|---|---|---|---|---|---|
| （无单） | ❌ TC-U38.2 不开通 | — | — | — | ❌ TC-U38.2 | — | — |
| 打开结账未 POST | — 不建单 TC-U32.2 / U37.8 | — | — | — | — | — | — |
| checkout_pending | ✅ TC-U33.1 / U33.4 → fulfilled | ✅ TC-U33.5 → paid_pending | ✅ TC-U34.1/2/5 → unpaid | ✅ TC-U32.1 先 pending 再 unpaid | ❌ TC-U38.3…6 仍 pending | — | ❌ TC-U34.3 仍 pending |
| paid_pending_fulfillment | ✅ TC-U33.6 二次通知 → fulfilled 一次 | — 保持处理中句 | — | — | — | — | — |
| unpaid | ❌ TC-U34.4 保持 unpaid | — | — 终态 | — | — | ❌ TC-U34.4 `late_notify_at` | — |
| fulfilled | ❌ TC-U33.6 不叠加上限 | — | — | — | — | — | — |

**非法流转三项断言**：状态未非法跃迁 ☑；记录（`late_notify_at` / 无 succeeded）☑；无副作用（档位/SKU/配额不叠加）☑

不把 N2 订一行填进支付状态机。不把夹具 `payment_succeeded` 写成「当前可买」。

### 3.4 市场总开关 / 安装行（N2）

| 状态＼操作 | 经办订 listed 插件 | 只读订 | 订预告 | 关市订 | 公司管理员开开关 |
|---|---|---|---|---|---|
| 开 + 有 listed | ✅ TC-U10.1 一行无子卡 | ❌ TC-U10.3 零行 | ❌ TC-U10.4 零行 | — | — |
| 开 + 可见行=0 | — 空货架 TC-U10.2 | — | — | — | — |
| 关 | ❌ TC-U11.1 零行；无 succeeded TC-U14.2 | — | — | ❌ 关闭句 ≠ 空货架 TC-U11.2 | ❌ TC-U11.3 开关仍关 |

**非法流转三项断言**：安装行未增 ☑；无 `market_subscribe_succeeded`（关市）☑；listing_state / 开关值不变 ☑

### 3.5 值班页三态（N4）

| 状态＼操作 | 超管打开值班页 | 租户直打值班地址 | 伪装探针 |
|---|---|---|---|
| 可达 + 0 模型 | ✅ TC-U25.2 空句；禁「暂无渠道」；非加载失败 | ❌ TC-U25.3 404 同形 | — |
| 可达 + 已登记 + original | ✅ TC-U25.1 行「活」；页非空/降级；hasLiveRow 压过 empty（TC-U25.liveov）；行活须网关可达（TC-U25.gw） | ❌ TC-U25.3 404 同形 | ❌ 伪装行不标活 TC-U25.spoof |
| 可达 + 已登记 + 无 original | ✅ TC-U25.4th 页态 null（不是 empty/degrade）；行不标活；禁空句 | ❌ TC-U25.3 404 同形 | ❌ 伪装不关渠 TC-U25.spoof |
| 管理面不可达 | ✅ TC-U25.4 降级句 + 本地事件/探针；禁空句；禁标活。非空夹具 TC-U25.4n 不得 live | ❌ TC-U25.3 404 同形 | — |
| overview 加载失败 | ✅ TC-U25.fail 失败句 ≠ 空 ≠ 降级 | — | — |

✅ = 合法流转已测｜❌ = 非法流转已测｜➖ = 本波不适用｜空格子无：离线 hint 不是本表操作（§5 ⚠️，非 GWT-U25）

**非法流转三项断言**：页级标题未串成「暂无渠道」☑；租户无渠道列表/密钥/抱歉 ☑；伪装无关渠副作用 ☑。值班「活」不写入 SKU / 支付单。降级非空不得标活 ☑。第四态不得塌成 U25.2 空句 ☑。

---

## 4. 权限矩阵覆盖

N1 采集面（已测）。N2 市场/RBAC（已测）。N3 结账建单 / 签发令牌 / 凭据（已测）。N4 值班三态（已测）。

| 角色＼操作 | 提交采集 | 看本企业结果 | 看他企结果 | 申请提升 | 查产品事实 | 改 Hero | 建支付单 | 打开我的渠道组 | 签发令牌 | 配商户凭据 |
|---|---|---|---|---|---|---|---|---|---|---|
| 匿名访客 | ➖ 未测本波（须登录） | ➖ | ➖ | ➖ | ➖ | ✅ 无入口 TC-U04.3 | ❌ TC-U36.3 | ➖ 须登录 | ➖ | ➖ |
| 租户只读 | ❌ TC-U02.3 | — 本波无独立只读读结果测 | ❌ 同 U01.3 形 | ❌ TC-U02.6 联系管理员 | ❌ TC-U03.3 | ✅ 无入口 | ❌ TC-U32.3 / U35.3 | ✅ 可读空态 | ❌ TC-U21.3 / U23.5 | ❌ TC-U31.3 |
| 租户经办 | ✅ TC-U01.1 | ✅ TC-U01.1 | ❌ TC-U01.3 | ❌ TC-U02.6 | ❌ TC-U03.3 | ✅ 无入口 | ❌ TC-U36.2 | ✅ 可读 | ❌ TC-U23.5 | ❌ TC-U31.3 |
| 公司管理员/买方 | — 本波提交走经办夹具 | ✅ 业主头读本企 | ❌ TC-U01.3 | ✅ TC-U02.7 / U35.1 进结账 | ❌ TC-U03.3 | ✅ 无入口 | ✅ TC-U30.1（已配通道） | ✅ TC-U20.1 / U21.1 | ✅ TC-U23.1（SKU active） | ❌ TC-U31.3 |
| 平台超管 | — | — | — | — | ✅ TC-U03.1 | — | ❌ TC-U36.4 无代付 | — 无企业空间既有壳 | — | ✅ TC-U31.1 |

### 4.1 N2 市场 / 平台写面

| 角色＼操作 | 逛公开货架 | 订一行 | 改总开关 | 上架/扫描 | 平台 RBAC | 改平台渠道 |
|---|---|---|---|---|---|---|
| 匿名访客 | ✅ 关=关闭句 TC-U11.2；开空=空货架 TC-U10.2；详情纯文本 TC-U13.1 | ➖ 须登录 | ➖ | ➖ | ➖ | ➖ |
| 租户只读 | ✅ 同货架句 | ❌ TC-U10.3 | ➖ | ➖ | ➖ | ➖ |
| 租户经办 | ✅ | ✅ 开+listed TC-U10.1；❌ 关/预告 | ❌ 无超管面 | ❌ 同 U12 形 | ❌ TC-U14.3 事件查询 | ➖ |
| 公司管理员 | ✅ 租户 `/capabilities` 是货架不是 404 | — 本波订一行走经办夹具 | ❌ TC-U11.3 | ❌ TC-U12.2 / U12.3 | ❌ TC-U15.3 | ❌ TC-U12.3 |
| 平台超管 | — 治理壳 TC-U12.1 | — | ✅ TC-U11.flip | ✅ TC-U12.1 | ✅ TC-U15.1 | — 写面守卫已换 404；本波无超管改窗成功测（v2 渠道窗） |

### 4.2 N3 支付事实 / N4 值班

| 角色＼操作 | 查支付事件 | 打开值班页（三态） | 直打值班页 |
|---|---|---|---|
| 匿名访客 | ➖ 须登录 | ➖ 须登录 | ➖ |
| 租户只读/经办/买方 | ❌ TC-U37.3 404 同形 | ❌ TC-U25.3 404 同形（无列表/密钥/抱歉） | ❌ TC-U22.2 / TC-U25.3 404 同形（不是渠道组） |
| 平台超管 | ✅ TC-U37.1 | ✅ TC-U25.1 活 / U25.2 空 / U25.4 降级 | ✅ 超管可达（U25.1） |

**三类越权覆盖**：

- [x] ① 换角色（只读提交、非买方申请提升、只读订阅、公司管理员改开关/上架/RBAC、只读建单/标已买、经办签发、超管代付、租户打开值班页）—— TC-U02.3 / TC-U02.6 / TC-U10.3 / TC-U11.3 / TC-U12.2 / TC-U15.3 / TC-U32.3 / TC-U34.3 / TC-U23.5 / TC-U36.4 / TC-U25.3
- [x] ② 换数据范围（企业 B 打开企业 A 结果 / 渠道组 / 支付单 / 令牌）—— TC-U01.3 / TC-U20.3 / TC-U30.3 / TC-U23.cred / TC-U33.3
- [x] ③ 直接调接口（绕过前端：`/run`、product-events、名单 POST、listing PATCH、scan、channels/config、`/rbac/roles`、subscribe、power-market PUT、checkout POST、notify POST、credentials PUT、relay issue、confirm、`/newapi/overview` 等值班 API）—— 同上后端测
- [x] ④ 跨租户 —— TC-U01.3；产品事实租户 404 —— TC-U03.3；市场/支付事件租户 404 —— TC-U14.3 / TC-U37.3；凭据租户 404 —— TC-U31.3；值班 API 租户 404 —— TC-U25.3

N4 值班三态格：已填（超管三态 + 租户 404）。

---

## 5. 空洞明细

### ⚠️ 需真实环境：GWT-U01.1 120s live 工人

| 项 | 内容 |
|---|---|
| 该测什么 | 非夹具企业贴 `https://httpbin.org/get`，live 工人 120s 内 completed 且条数>0 |
| 为什么测不了 | T-02 用 FakeRedis `_ingest_flush` + webhook complete，断言 Then 的数据面，不启动 Scrapy |
| 转给谁 | `/sre` 或下一次 live 夹具窗；不得用本格宣称北极星已在生产出现 |
| 状态 | 未执行 live。v2 GWT-18.1 live 前合同已有一次，本波不重测（FR-18 豁免） |

### ⚠️ 部分：NFR-U01 去支付 5s / GWT-U30.1·U30.4 无托管页

| 项 | 内容 |
|---|---|
| 该测什么 | 点去支付 5s 内通道界面或 FR-U32 空态；Then「进入支付宝/微信支付」 |
| 为什么没测满 | 通道 Radio / 空态句已在 GET/POST 断言；**无 monotonic 5s**。T-16/T-19 无 `pay_url`、不调 SDK，201 停在 `checkout_pending` |
| 已采取的行动 | 映射到 TC-U30.1/U30.4/U32.2/U36.1；标 ⚠️ 而非 ❌。不假装跳转通道托管页 |
| 当前风险 | 生产若接 SDK 跳转，本矩阵未覆盖托管页。误把 pending 写成已买才是风险——本矩阵禁止 |

### ⚠️ 部分：GWT-U38.1 夹具验真 ≠ live 通道

| 项 | 内容 |
|---|---|
| 该测什么 | 通道侧真通知携带同一订单号/商户/金额并完成验真 |
| 为什么没测满 | T-17 用 `signed_body` 夹具；无 live 支付宝/微信 |
| 已采取的行动 | U38.1 映射 U33.1/U33.4；伪造/不符走 U38.3–6。不把夹具 succeeded 写成四柱 GA 或「当前可买」 |
| 当前风险 | 真通道报文形状与夹具不一致时验真可能漏。算法名不进用户文案已钉 |

### ⚠️ 部分：T-24 已交；应用层 notify 仍无 RateLimitPolicy（NFR-U03）

| 项 | 内容 |
|---|---|
| 该测什么 | 公开通知入口限流；密钥不进镜像；通道失败可观测 |
| 为什么没测满 | T-24 **已交**（checklist + 密钥扫描）。密钥不进镜像/yml 已由 U31.4 + T-24 rg 覆盖。通道失败空态已由 U32/U34.5 覆盖。**应用层 notify 仍无 RateLimitPolicy**（限流在反代笔记，未改 `rate_limiter.py`） |
| 已采取的行动 | 不把 FR-U31/U38 GWT 标缺口；NFR-U03 **保持 ⚠️**（不升 ❌）。不写缺陷票堵 N3 GWT |
| 当前风险 | 无反代 `limit_req` 时 notify 公网暴露可 DoS。转 `/sre`（qc 条件 9） |

### ⚠️ 部分：N4 值班无 live LiteLLM

| 项 | 内容 |
|---|---|
| 该测什么 | 真网关管理面可达 / 0 模型 / 不可达时三句互斥；行「活」 |
| 为什么没测满 | T-26 monkeypatch `list_models`；T-27 jest mock overview/channels/probes。GWT Then 锁句已钉。r2 已补：降级非空不标活、第四态 page_state null、ids+since+LIMIT、hasLiveRow 压过 empty、行活须 `gatewayAvailable` |
| 已采取的行动 | 映射 TC-U25.1…4 + 支撑测；不把 mock 可达写成 Q-OPS-DUTY SLA 或四柱 GA。不把 GWT-U25 标缺口。**无 SLA 数字** |
| 当前风险 | 真网关错误形状与 mock 不一致时降级句可能漏。SLA 本波不承诺（Q-OPS-DUTY） |

### ⚠️ 屏 19 离线 hint 无 Jest（非 GWT-U25 行）

| 项 | 内容 |
|---|---|
| 该测什么 | edge-states 屏 19 离线：「值班页加载失败」+ 若已有本地事件「网络不可用，以下为已加载的本地数据。」禁止改写成「暂无渠道」 |
| 为什么没测 | `OFFLINE_LOCAL_HINT` 在 `newapiShared.ts` / Overview3q 有实现；**无**对应 Jest。GWT-U25.1…4 的 When 都不是「浏览器离线」 |
| 已采取的行动 | **不**升 GWT-U25 行；**不**标 ❌。记本 ⚠️。加载失败已由 TC-U25.fail 覆盖（reject overview ≠ navigator.offLine） |
| 当前风险 | 离线时可能只出失败句、不出「以下为已加载的本地数据」。不阻塞 FR-U25 GWT |

### 需真库验证清单（方言）

| 用例 | 为什么 SQLite 测不出 | 状态 |
|---|---|---|
| T-01 `internal_fixture_tenants` UNIQUE | SQLite 唯一键语义与 InnoDB 不完全同 | T-01 evidence 已在抛开库 `SHOW CREATE TABLE` + 045 up-down-up exit 0 |
| T-14 `open_product_slot` STORED 生成列 + 046 | SQLite 生成列/UNIQUE NULL 与 InnoDB 不同 | T-14 evidence 抛开库 `SHOW CREATE TABLE` + 046 up-down-up exit 0（`test_t14_migration_046.py` MYSQL_FIDELITY） |
| 产品事件等值 `is_internal_fixture=false`（NULL 旧行） | SQLite 三值逻辑通常能测；生产索引 `idx_product_events_name_fixture_occurred` 需 MySQL | 单测已钉 NULL 不进 false；生产索引未在本波 MYSQL_FIDELITY 套件 |

### T-05 开放（不升级为 N1 ❌）

规划 token 满仍发 `quota_exceeded` 而非 `task_blocked.reason=quota_tokens`。GWT-U03.4 When = 工人不在线拦住；入队不查 token。记下给后续埋点票，不在本波开缺陷票。

无 N1/N2/N3/N4 GWT ❌ 缺口，故本波不写缺陷票。T-24 已交不算 GWT 空洞；NFR-U03 因应用层 notify 无 RateLimitPolicy 保持 ⚠️。屏 19 离线 hint 无 Jest 不升 GWT-U25、不写票。

---

## 6. 裁剪声明

| 项 | 策略 | 说明 |
|---|---|---|
| 波次 | 验收 N1+N2+N3+N4 | N4（FR-U25）GWT-U25.1…4 已映射 T-26/T-27 r2。T-24 已交（checklist + 密钥扫描）；NFR-U03 因应用层 notify 无 RateLimitPolicy 保持 ⚠️。v2 FR-nn 仍豁免「前合同 v2，本波不重测」 |
| 参数组合 | 配额三维各取已尽一格；市场开/关 × 空货架/listed/预告；支付通道 pairwise 支付宝/微信 × 商品三码；值班 空/活/降级/失败/第四态 互斥 | 存储满 / token 满 / 并发满分家。关闭句 ≠ 空货架句。`plan_pro` ≠ `relay`。无 `plan_ent`。值班禁「暂无渠道」。第四态 ≠ 空句。离线 hint 不升 GWT |
| 角色 | N1 经办提交 + 只读拒绝 + 买方/非买方申请提升；N2 经办订一行 + 只读拒订 + 公司管理员拒开关/上架/RBAC + 超管上架/RBAC；N3 买方建单 + 经办/只读拒付 + 超管拒代付 + 超管配凭据；N4 超管值班三态 + 租户直打 404 | 匿名提交本波不另开（须登录壳，沿用 v2） |
| E2E | 不做 | 主干在集成（入队/结果/事件/订阅/结账/notify/SKU/值班 overview）；UI 锁句在 Jest |
| live 工人 / live 支付 / live LiteLLM | 裁到 ⚠️ | 见 §5；本波不写新测试 |
| 前合同 v2 | 不重测 | FR-01/06/14/15/18/30/33/34/50/51/70/71/74 豁免 |
| T-13 / T-07 / T-25 | IA 不进可执行用例列 | 屏 ID 与锁句由对应前端/后端测钉死 |
| 通道 SDK | 裁 | 合同无 `pay_url`；不测托管页跳转 |

---

## 7. 覆盖统计

| 项 | 数量 |
|---|---|
| spec `\bFR-\d+\b` / 矩阵出现 | 13 / 13（全豁免前合同） |
| spec NFR-\d+ | 0 |
| FR-U 总数 / 本波已覆盖 / 豁免未施工 | 25 / 25（U01–U04 + U10–U15 + U20–U25 + U30–U38） / 0 |
| NFR-U 总数 / 已覆盖（含部分） / N/A | 10 / 9（U01 部分、U02 待支付、U03 部分、U04 凭据+SEC-1、U05、U06 机械钉、U07 部分、U08 支付事件、U10 凭据+开关） / U09 中文 |
| N1 GWT 总数 / 已覆盖 | 18 / 18（U01.1 为 ⚠️ 部分） |
| N2 GWT 总数 / 已覆盖 | 19 / 19 |
| N3 GWT 总数 / 已覆盖 | 70 / 70（U30.1/U30.4/U38.1 为 ⚠️ 部分） |
| N4 GWT 总数 / 已覆盖 | 4 / 4（U25.1…U25.4；网关 mock 非 live LiteLLM；第四态/查询收口为支撑测非 GWT 行） |
| 用例（单元 / 集成 / E2E / 专项） | N1+N2 既有 + N3 pytest 具名 GWT（U20/U30/U31/U33/U37 文件）+ N4 pytest `test_fr_u25_duty.py` **10** + Jest Overview3q/NewApiOps/App.menu **43** + Checkout/Relay/Pricing/frU24；E2E 0；专项 0 |
| 缺口数 ❌ | 0（N1/N2/N3/N4 GWT） |
| 需真实环境 ⚠️ | live 120s 工人 + live 支付通道 + 去支付 5s + 应用层 notify 无 RateLimitPolicy（T-24 已交）+ live LiteLLM 值班 + 屏 19 离线 hint 无 Jest |
| 采集状态流转格子 / 已覆盖 | 5×5 表无空格（含 ❌ 非法格） |
| 市场安装流转格子 / 已覆盖 | 3.4 表无空格（含 ❌ 非法格） |
| 中转/支付流转格子 / 已覆盖 | 3.2 / 3.3 无空格（含 ❌ 非法格；无 SDK 跳转标在备注） |
| 值班三态流转格子 / 已覆盖 | 3.5 表无空格（含 ❌ 非法格） |
| 权限矩阵 N1+N2+N3+N4 格 | 已填 |

**覆盖率数字不作为质量结论。** 本波结论：N1+N2+N3+N4 映射有测试或有 ⚠️；**不是**四柱 GA；可见面 **不允许**「当前可买」。值班「活」≠ SKU active ≠ 已买。

---

## 8. 自检

- [x] 每条 FR/NFR 都有一行，无留空（含 v2 `FR-nn` 与 FR-U / NFR-U）
- [x] 每个本波用例都能反向指回 FR/NFR
- [x] 采集状态流转无空格子；市场安装格子已填；支付/SKU 格子已填；值班三态格子已填（含 ❌ 非法格）
- [x] 权限矩阵 N1+N2+N3+N4 无空格子，三类越权齐全
- [x] 每个 ⚠️ 在第 5 节展开（含屏 19 离线 hint；未升 GWT-U25）
- [x] 裁剪策略已声明
- [x] 需真库清单已记录（045/046 抛开库已跑；live 工人/live 支付/live LiteLLM 未跑）
- [x] 无空心用例（抽核 T-14…T-24 / T-26 r2 10 pytest / T-27 r2 43 Jest 断言对照 Then；T-07/T-13/T-25 为 IA；T-24 已交（checklist + 密钥扫描）；应用层 notify 仍无 RateLimitPolicy）
- [x] **未**声称四柱 GA
- [x] **未**允许「当前可买」
- [x] **未**把值班「活」写成 SKU active 或「当前可买」
- [x] **未**把 Q-OPS-DUTY 写成 SLA 数字
- [x] 未把 N2 货架/订一行写成中转履约
- [x] 未把夹具 notify 写成 live 收银台
- [x] 未写新测试、未修产品代码、未写缺陷票（无 GWT ❌）
- [x] v2 `FR-nn` 13 条仍豁免「前合同 v2，本波不重测」
- [x] N4 r2：hasLiveRow 压过 empty；行活须 gatewayAvailable；降级非空不标活；第四态 page_state null；latest_result 有界查询
- [x] Closed leftover QA-01/QA-02：T-24 已交（checklist + 密钥扫描）；GWT-U02.7 已删 `Checkout.test.tsx:36`；NFR-U03 保持 ⚠️
