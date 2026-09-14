# 覆盖矩阵 · 合入后四角色完备（post-merge-upgrade）

> 上游：PRD `.sdlc/post-merge-upgrade/01-define/spec.md` v1.7｜契约 `02-shape/contract.md`｜`02-shape/edge-states.md`
> 作者：/qa｜日期：2026-09-14｜泳道：L3｜下游：`/qc` 或 `/reviewer`
> 本波：**不**标四柱 GA。verify r2：GWT-M12.8 已重写可失败 Then，BUG-V01 关闭。GWT-M11.12 仍 ⚠️ MYSQL_FIDELITY（SQLite ThreadPool 不算 W2 已兑）。C2 / C4 / GWT-M11.7 = 环境闸豁免。

## 1. 正向：FR/NFR → 用例

> **每条 FR/NFR 至少一行。空洞必须显式标注，不许留空。**
> 备注列 = 断言所在 `file:line`（相对仓库根）。空心断言不记 ✅。

### W1 采集

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-M01 | GWT-M01.1 正常 | TC-M01.1 | 集成 | ✅ | `backend/tests/test_fr_m01_planning_disabled.py:115` elapsed≤3、不建方案/任务；`frontend/admin/src/pages/AiPlans.m01.test.tsx:108` |
| FR-M01 | GWT-M01.2 空态 | TC-M01.2 | 集成 | ✅ | `test_fr_m01_planning_disabled.py:170`；`AiPlans.m01.test.tsx:96` |
| FR-M01 | GWT-M01.3 越权 | TC-M01.3 | 集成 | ✅ | `test_fr_m01_planning_disabled.py:187`；`AiPlans.m01.test.tsx:132` |
| FR-M01 | GWT-M01.4 成功 | TC-M01.4 | 单元 | ✅ | `AiPlans.m01.test.tsx:144` 向导「方案与试采」+列表该行。HTTP 70.1 前置对照 `test_llm_four_actions_http.py` |
| FR-M01 | GWT-M01.5 降级 74.1 | TC-M01.5 | 集成 | ✅ | `backend/tests/test_llm_four_actions_http.py:242` `test_post_plan_unreachable_only_74_1` |
| FR-M02 | GWT-M02.1 正常 | TC-M02.1 | 单元 | ✅ | `frontend/admin/src/pages/Data.test.tsx:75` csv/json 无 xlsx；导出事件 `test_fr_m06_planning_export_events.py:111` |
| FR-M02 | GWT-M02.2 空态 | TC-M02.2 | 单元 | ✅ | `Data.test.tsx:146` 金标句；禁 84.2 旧句 |
| FR-M02 | GWT-M02.3 越权 | TC-M02.3 | 集成 | ✅ | 对照 `test_fr_u01_enqueue.py:272` 跨租户 0 行同形 |
| FR-M02 | GWT-M02.4 边界 xlsx | TC-M02.4 | 单元 | ✅ | `Data.test.tsx:200` |
| FR-M02 | GWT-M02.5 100 行 | TC-M02.5 | 单元 | ✅ | `Data.test.tsx:152` 文件 100 数据行 |
| FR-M02 | GWT-M02.6 101 无文件 | TC-M02.6 | 单元 | ✅ | `Data.test.tsx:179` 不 createObjectURL |
| FR-M03 | GWT-M03.1 正常 | TC-M03.1 | 集成 | ✅ | `test_fr_m03_first_collect.py:176` 3s 已入队+本企业结果。完成态=ingest+webhook |
| FR-M03 | GWT-M03.1 C4 工人 | — | 专项 | ⚠️ **需真实环境** | 120s live Scrapy 工人是 C4 环境闸，见第 5 节 |
| FR-M03 | GWT-M03.2 空态 | TC-M03.2 | 集成 | ✅ | `test_fr_m03_first_collect.py:217`；`Spiders.test.tsx:204`；`TaskModal.test.tsx:121` |
| FR-M03 | GWT-M03.3 越权 | TC-M03.3 | 集成 | ✅ | `test_fr_m03_first_collect.py:232` 拒绝不入队 |
| FR-M06 | GWT-M06.1 | TC-M06.1 | 集成 | ✅ | `test_fr_m06_planning_export_events.py:88` `llm_planning_blocked` reason=disabled |
| FR-M06 | GWT-M06.2 | TC-M06.2 | 集成 | ✅ | 同文件 `:111` `data_export_completed` |
| FR-M06 | GWT-M06.3 | TC-M06.3 | 集成 | ✅ | 同文件 `:133` persist boom 不挡主路径 |
| FR-M06 | GWT-M06.4 | TC-M06.4 | 集成 | ✅ | 同文件 `:165` 租户 404 同形 |

### W2 结账

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-M10 | GWT-M10.1 正常 | TC-M10.1 | 单元 | ✅ | `Usage.test.tsx:168` 去结账、无套餐与订购 |
| FR-M10 | GWT-M10.2 空态 | TC-M10.2 | 单元 | ✅ | 同页结账：`Usage.test.tsx:168` + `Checkout.test.tsx:74` 同一 `/billing/checkout` |
| FR-M10 | GWT-M10.3 越权 | TC-M10.3 | 单元 | ✅ | `Usage.test.tsx:184` 只读无去结账；`Checkout.test.tsx:182` 经办联系管理员 |
| FR-M10 | GWT-M10.4 旧入口 | TC-M10.4 | 集成 | ✅ | `test_fr_m10_orders_closed.py:50` 零新行；`:68` 不改待支付 |
| FR-M11 | GWT-M11.1 未配通道下单 | TC-M11.1 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:76`；`Checkout.test.tsx:94` |
| FR-M11 | GWT-M11.2 打开空态 | TC-M11.2 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:106`；`Checkout.test.tsx:74` |
| FR-M11 | GWT-M11.3 经办 | TC-M11.3 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:120`；`Checkout.test.tsx:182` |
| FR-M11 | GWT-M11.4 确认开通 [SEC-3] | TC-M11.4 | 集成 | ✅ | `test_fr_m11_confirm.py:44` fulfilled、配额 50、SKU none |
| FR-M11 | GWT-M11.5 再确认 | TC-M11.5 | 集成 | ✅ | `test_fr_m11_confirm.py:63` 不叠配额、仍 1 单 |
| FR-M11 | GWT-M11.6 租户自开通 | TC-M11.6 | 集成 | ✅ | `test_fr_m11_confirm.py:81` 仍 pending |
| FR-M11 | GWT-M11.7 真通道 | — | 专项 | ⚠️ **需真实环境** | 非 W2 放行；live 收银台另波。见第 5 节 |
| FR-M11 | GWT-M11.8 第二张 | TC-M11.8 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:130` 409「已有待支付」；`Checkout.test.tsx:166` |
| FR-M11 | GWT-M11.9 跨企业 | TC-M11.9 | 集成 | ✅ | `test_fr_u30_checkout.py:215` 看不见 B；`test_fr_m11_confirm.py:114` 错单拒 |
| FR-M11 | GWT-M11.10 无取消入口 | TC-M11.10 | 单元 | ✅ | `Checkout.test.tsx:194` 无取消钮、待支付 |
| FR-M11 | GWT-M11.13 提交取消 | TC-M11.13 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:166` cancel/unpaid/PATCH/DELETE → 404/405/422；仍 pending；配额不变。BUG-V04 关闭 |
| FR-M11 | GWT-M11.11 迟到·专业档 | TC-M11.11 | 集成 | ✅ | `test_fr_m11_confirm.py:130` late_notify_at、SKU none |
| FR-M11 | GWT-M11.18 迟到·企业/中转 | TC-M11.18 | 集成 | ✅ | `test_fr_m11_confirm.py:164` 企业档不叠配额；`:179` relay 不重签令牌。BUG-V03 关闭 |
| FR-M11 | GWT-M11.12 并发 | TC-M11.12 | 专项 | ⚠️ **需真实环境** | `test_fr_m11_checkout_pending.py:143` SQLite ThreadPool **不得**当 W2 已兑。需 `MYSQL_FIDELITY=1` 双连接。BUG-V02 仍开 |
| FR-M11 | GWT-M11.14 企业档下单 | TC-M11.14 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:142` amount≠29900 |
| FR-M11 | GWT-M11.15 企业档开通 | TC-M11.15 | 集成 | ✅ | `test_fr_m12_fulfill.py:79` ENT 配额+SKU active |
| FR-M11 | GWT-M11.16 中转下单 | TC-M11.16 | 集成 | ✅ | `test_fr_m11_checkout_pending.py:154` |
| FR-M11 | GWT-M11.17 中转开通 | TC-M11.17 | 集成 | ✅ | `test_fr_m12_fulfill.py:88` SKU active、配额不变 |
| FR-M12 | GWT-M12.1 用量三数字 | TC-M12.1 | 单元 | ✅ | `Usage.test.tsx:397` 定价页同源 50/200,000/500 万；履约写 `test_fr_m12_fulfill.py:63` |
| FR-M12 | GWT-M12.2 免费上限 | TC-M12.2 | 单元 | ✅ | `Usage.test.tsx:376` 5 / 10,000 / 20 万 |
| FR-M12 | GWT-M12.3 越权档位 | TC-M12.3 | 集成 | ✅ | `test_saas_isolation.py:36` 读注入藏他租户 |
| FR-M12 | GWT-M12.4 专业≠中转 | TC-M12.4 | 集成 | ✅ | `test_fr_m12_fulfill.py:74`；`test_fr_m23_relay_empty.py:104`；`RelayGroups.test.tsx:300` |
| FR-M12 | GWT-M12.5 企业档渠道组 | TC-M12.5 | 集成 | ✅ | `test_fr_m23_relay_empty.py:83` can_issue、无上游 Key |
| FR-M12 | GWT-M12.6 第 6 任务入队 | TC-M12.6 | 集成 | ✅ | `test_fr_m12_fulfill.py:142` 5 running 后再 POST `/spiders/run` → 200「已入队」。quota JSON 单测 `:131` 不单独当 Then |
| FR-M12 | GWT-M12.7 存储 10001 | TC-M12.7 | 集成 | ✅ | `test_fr_m12_fulfill.py:159` 种 10001 条后再入队 → 200「已入队」 |
| FR-M12 | GWT-M12.8 tokens 规划 | TC-M12.8 | 集成 | ✅ | `test_fr_m12_fulfill.py:228` POST `.../plan` **200**、code≠TASK_QUOTA_LIMIT、无「已达配额上限」、selectors 可见、outbound 打网关（70.1）。对照 `:252` 免费档 200001 拦住（oracle 可失败）。BUG-V01 关闭 |
| FR-M13 | GWT-M13.1 满额去结账 | TC-M13.1 | 集成 | ✅ | `test_fr_u02_quota_copy.py:297`；`Usage.test.tsx:300`；`UpgradeIntentButton.test.tsx:80` |
| FR-M13 | GWT-M13.2 未满 | TC-M13.2 | 单元 | ✅ | `Usage.test.tsx:168` 去结账非第二套表 |
| FR-M13 | GWT-M13.3 越权 | TC-M13.3 | 集成 | ✅ | `test_fr_u02_quota_copy.py:256`/`278`；`UpgradeIntentButton.test.tsx:48` |
| FR-M14 | GWT-M14.1 | TC-M14.1 | 集成 | ✅ | `test_fr_m14_checkout_events.py:32` surface=checkout referrer=pricing |
| FR-M14 | GWT-M14.2 | TC-M14.2 | 集成 | ✅ | 同文件 `:55` fulfilled；second_story=0 |
| FR-M14 | GWT-M14.3 | TC-M14.3 | 集成 | ✅ | 同文件 `:68` 旧 POST 不计数 |
| FR-M14 | GWT-M14.4 | TC-M14.4 | 集成 | ✅ | 同 GWT-M06.4 `test_fr_m06_planning_export_events.py:165` |
| FR-M14 | GWT-M14.5 | TC-M14.5 | 集成 | ✅ | `test_fr_m14_checkout_events.py:80` referrer=usage |
| FR-M15 | GWT-M15.1 | TC-M15.1 | 单元 | ✅ | `frontend/official/src/frU24CopyScan.test.tsx:82`；admin 同名 `:123` |
| FR-M15 | GWT-M15.2 | TC-M15.2 | 单元 | ✅ | official `Pricing.test.tsx` 主钮去结账、无四字 |
| FR-M15 | GWT-M15.3 | TC-M15.3 | 单元 | ✅ | admin `frU24CopyScan.test.tsx:130` 无「编辑定价」 |

### W3 租户管理员

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-M20 | GWT-M20.1 | TC-M20.1 | 集成 | ✅ | `test_fr_m20_outbound_lookup.py:53`；`OutboundKeys.test.tsx:86` |
| FR-M20 | GWT-M20.2 | TC-M20.2 | 单元 | ✅ | `OutboundKeys.test.tsx:74` 金标+签发 |
| FR-M20 | GWT-M20.3 | TC-M20.3 | 单元 | ✅ | `OutboundKeys.test.tsx:95` 只读无签发 |
| FR-M20 | GWT-M20.4 | TC-M20.4 | 集成 | ✅ | `test_fr_m20_outbound_lookup.py:66` sk- 0 行 |
| FR-M20 | GWT-M20.5 | TC-M20.5 | 集成 | ✅ | 同文件 `:87` `:105` api_keys/KEY_BINDINGS/垃圾 |
| FR-M20 | GWT-M20.6 | TC-M20.6 | 单元 | ✅ | `OutboundKeys.test.tsx:86` 无「API 钥匙」叶文案 |
| FR-M20 | GWT-M20.7 | TC-M20.7 | 单元 | ✅ | `App.menu.test.tsx:322` `/api-keys` 404 不重定向 |
| FR-M20 | GWT-M20.8 | TC-M20.8 | 集成 | ✅ | `test_fr_m20_outbound_lookup.py:121` ≤100 |
| FR-M21 | GWT-M21.1 | TC-M21.1 | 集成 | ✅ | `test_fr_m21_members.py:39` |
| FR-M21 | GWT-M21.2 | TC-M21.2 | 集成 | ✅ | 同文件 `:57` |
| FR-M21 | GWT-M21.3 | TC-M21.3 | 集成 | ✅ | 同文件 `:65` |
| FR-M21 | GWT-M21.4 | TC-M21.4 | 集成 | ✅ | 同文件 `:81`；`Members.test.tsx:228` 无平台超管选项 |
| FR-M21 | GWT-M21.5 | TC-M21.5 | 集成 | ✅ | `test_fr_m21_members.py:114`；`Members.test.tsx:251` |
| FR-M21 | GWT-M21.6 | TC-M21.6 | 集成 | ✅ | `test_fr_m21_members.py:137`；`Members.test.tsx:240` |
| FR-M21 | GWT-M21.7 | TC-M21.7 | 集成 | ✅ | `test_fr_m21_members.py:149` 256 字 |
| FR-M22 | GWT-M22.1 | TC-M22.1 | 单元 | ✅ | `Usage.test.tsx:153` 三类卡；`:376` 免费三数字 |
| FR-M22 | GWT-M22.2 | TC-M22.2 | 单元 | ✅ | `Usage.test.tsx:197` 0≠失败 |
| FR-M22 | GWT-M22.3 | TC-M22.3 | 单元 | ✅ | `Usage.test.tsx:184` |
| FR-M22 | GWT-M22.4 | TC-M22.4 | 集成 | ✅ | `test_fr_u02_quota_copy.py:236`；`Usage.test.tsx:236` |
| FR-M23 | GWT-M23.1 | TC-M23.1 | 集成 | ✅ | `test_fr_m23_relay_empty.py:83`/`96`；`RelayGroups.test.tsx:189` |
| FR-M23 | GWT-M23.2 | TC-M23.2 | 集成 | ✅ | `test_fr_m23_relay_empty.py:65`；`RelayGroups.test.tsx:256` |
| FR-M23 | GWT-M23.3 | TC-M23.3 | 集成 | ✅ | `test_fr_m23_relay_empty.py:115` 签发拒 |
| FR-M23 | GWT-M23.4 | TC-M23.4 | 集成 | ✅ | `test_fr_u20_relay_sku.py:228`；`test_fr_m30_duty_entry.py:22` |
| FR-M24 | GWT-M24.1 | TC-M24.1 | 单元 | ✅ | `MyInstalls.test.tsx:70` 行可见、无治理七叶 |
| FR-M24 | GWT-M24.2 | TC-M24.2 | 单元 | ✅ | `MyInstalls.test.tsx:85` |
| FR-M24 | GWT-M24.3 | TC-M24.3 | 单元 | ✅ | `MyInstalls.test.tsx:99`；`test_fr_m40_market_shelf.py:125` |
| FR-M26 | GWT-M26.1 | TC-M26.1 | 集成 | ✅ | `test_fr_m20_outbound_lookup.py:135` 无明文 |
| FR-M26 | GWT-M26.2 | TC-M26.2 | 集成 | ✅ | `test_fr_m20_outbound_lookup.py:169` 200 `total=0` items=[]。BUG-V05 关闭 |
| FR-M26 | GWT-M26.3 | TC-M26.3 | 集成 | ✅ | `test_fr_m20_outbound_lookup.py:165` 租户 404 |

### W4 平台管理员

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-M30 | GWT-M30.1 | TC-M30.1 | 集成 | ✅ | `test_fr_u25_duty.py:293`；`Overview3q.test.tsx:158` 活+三问 |
| FR-M30 | GWT-M30.2 | TC-M30.2 | 集成 | ✅ | `test_fr_u25_duty.py:135`；`Overview3q.test.tsx:185` 禁「暂无渠道」 |
| FR-M30 | GWT-M30.3 | TC-M30.3 | 集成 | ✅ | `test_fr_m30_duty_entry.py:22` |
| FR-M30 | GWT-M30.4 | TC-M30.4 | 集成 | ✅ | `test_fr_m30_duty_entry.py:29`；`App.menu.test.tsx:340` |
| FR-M30 | GWT-M30.5 | TC-M30.5 | 单元 | ✅ | `DutyKeysTab.test.tsx:47` 权限加载中、写入口不藏 |
| FR-M31 | GWT-M31.1 | TC-M31.1 | 集成 | ✅ | `test_fr_m31_ops_console.py:35`；`PlatformOps.test.tsx:111` |
| FR-M31 | GWT-M31.2 | TC-M31.2 | 集成 | ✅ | `test_fr_m31_ops_console.py:53`；`PlatformOps.test.tsx` 空态「暂无待确认收款」 |
| FR-M31 | GWT-M31.3 | TC-M31.3 | 集成 | ✅ | `test_fr_m31_ops_console.py:60` |
| FR-M31 | GWT-M31.4 [SEC-3] | TC-M31.4 | 集成 | ✅ | `test_fr_m11_confirm.py:92` |
| FR-M31 | GWT-M31.5 [SEC-3] | TC-M31.5 | 集成 | ✅ | `test_fr_m11_confirm.py:114` |
| FR-M31 | GWT-M31.6 [SEC-3] | TC-M31.6 | 集成 | ✅ | `test_fr_m31_ops_console.py:70` 企业档写成 ¥299 拒 |
| FR-M32 | GWT-M32.1 | TC-M32.1 | 集成 | ✅ | `test_fr_m32_user_lifecycle.py:36` |
| FR-M32 | GWT-M32.2 | TC-M32.2 | 集成 | ✅ | 同文件 `:67`；`Users.test.tsx:58` |
| FR-M32 | GWT-M32.3 | TC-M32.3 | 集成 | ✅ | 同文件 `:75`；`App.menu.test.tsx:358` |
| FR-M32 | GWT-M32.4 | TC-M32.4 | 集成 | ✅ | 同文件 `:85` |
| FR-M33 | GWT-M33.1 | TC-M33.1 | 集成 | ✅ | `test_fr_m33_contact_settings.py:12`；`SiteLayout.test.tsx:16` |
| FR-M33 | GWT-M33.2 | TC-M33.2 | 集成 | ✅ | `test_fr_m33_contact_settings.py:31` |
| FR-M33 | GWT-M33.3 | TC-M33.3 | 集成 | ✅ | 同文件 `:46` |
| FR-M33 | GWT-M33.4 | TC-M33.4 | 集成 | ✅ | 同文件 `:57`；`Settings.test.tsx` 保存不称官网已同步 |
| FR-M33 | GWT-M33.5 | TC-M33.5 | 集成 | ✅ | `test_fr_m33_contact_settings.py:69`；`Settings.test.tsx:104` |
| FR-M34 | GWT-M34.1 | TC-M34.1 | 单元 | ✅ | `DutyKeysTab.test.tsx:56` 明文一次、无支付已通/live |
| FR-M34 | GWT-M34.2 C2 闸 | — | 专项 | ⚠️ **需真实环境** | 真网关轮记录是 C2 环境闸，代码 FR 不替代。见第 5 节 |
| FR-M34 | GWT-M34.3 | TC-M34.3 | 集成 | ✅ | `test_fr_m30_duty_entry.py:29` 租户无钥匙写面；`App.menu.test.tsx:340` |
| FR-M35 | GWT-M35.1 | TC-M35.1 | 集成 | ✅ | `test_fr_m30_duty_entry.py:36` |
| FR-M35 | GWT-M35.2 | TC-M35.2 | 集成 | ✅ | 同文件 `:53` |
| FR-M35 | GWT-M35.3 | TC-M35.3 | 集成 | ✅ | 同文件 `:66` |

### W5 市场 · 文案 · 注册

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-M40 | GWT-M40.1 | TC-M40.1 | 集成 | ✅ | `test_fr_m40_market_shelf.py:61`；`TenantShelf.test.tsx:225` |
| FR-M40 | GWT-M40.2 | TC-M40.2 | 集成 | ✅ | `test_fr_m40_market_shelf.py:81` |
| FR-M40 | GWT-M40.3 | TC-M40.3 | 集成 | ✅ | 同文件 `:102` |
| FR-M40 | GWT-M40.4 | TC-M40.4 | 集成 | ✅ | 同文件 `:115` |
| FR-M41 | GWT-M41.1 | TC-M41.1 | 集成 | ✅ | `test_fr_m41_listing.py:44` |
| FR-M41 | GWT-M41.2 | TC-M41.2 | 集成 | ✅ | 同文件 `:60` |
| FR-M41 | GWT-M41.3 | TC-M41.3 | 集成 | ✅ | 同文件 `:74`；`Capabilities.governance.test.tsx:294` |
| FR-M41 | GWT-M41.4 | TC-M41.4 | 集成 | ✅ | `test_fr_m41_listing.py:91`；`Capabilities.governance.test.tsx:281` |
| FR-M50 | GWT-M50.1 | TC-M50.1 | 单元 | ✅ | official `frU24CopyScan.test.tsx:82` |
| FR-M50 | GWT-M50.2 | TC-M50.2 | 单元 | ✅ | 源码机械钉含定价；确认开通≠指纹（同扫描） |
| FR-M50 | GWT-M50.3 | TC-M50.3 | 单元 | ✅ | admin `frU24CopyScan.test.tsx:130` |
| FR-M50 | GWT-M50.4 | TC-M50.4 | 单元 | ✅ | admin `frU24CopyScan.test.tsx:123` 租户面 |
| FR-M51 | GWT-M51.1 | TC-M51.1 | 集成 | ✅ | `test_fr_m51_signup_enterprise.py:43`；`Register.test.tsx:242` |
| FR-M51 | GWT-M51.2 | TC-M51.2 | 集成 | ✅ | `test_fr_m51_signup_enterprise.py:76`；`Register.test.tsx:260` |
| FR-M51 | GWT-M51.3 | TC-M51.3 | 集成 | ✅ | `test_fr_m51_signup_enterprise.py:105`；`Register.test.tsx:279` |
| FR-M51 | GWT-M51.4 | TC-M51.4 | 集成 | ✅ | `test_fr_m51_signup_enterprise.py:93`；`Register.test.tsx:270` |

### NFR-M01…M10

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| NFR-M01 | 采集 3s / 规划未开放 3s | TC-M01.1 TC-M03.1 | 集成 | ✅ | elapsed≤3 硬断言 |
| NFR-M01 | 规划成功可见方案 | TC-M01.4 | 单元 | ✅ | UI Then；不测墙钟 3s |
| NFR-M01 | 点去结账 5s | — | 专项 | ⚠️ **需真实环境** | Jest 不测 5s 路由墙钟 |
| NFR-M01 | 合格出数 120s | — | 专项 | ⚠️ **需真实环境** | C4 live worker |
| NFR-M02 | 导出/拉数 100；一商品一待支付 | TC-M02.5/6 TC-M20.8 TC-M11.8 | 集成 | ✅ | 顺序一待支付已测；并发格见 GWT-M11.12 ⚠️ MYSQL_FIDELITY |
| NFR-M03 | 未配通道可待支付；规划/工人可感知 | TC-M11.1 TC-M01.1 | 集成 | ✅ | 工人句对照 `test_fr_u01_enqueue.py` GWT-U02.1 |
| NFR-M04 | [SEC-1][SEC-2][SEC-3] 隔离 密钥 | TC-M20.* TC-M11.4 TC-M31.4 | 集成 | ✅ | 通道验真对照 `test_fr_u33_notify.py`；密钥 `test_fr14_secrets_off_tree.py:89`；凭据 `test_fr_u31_payment_credentials.py` |
| NFR-M05 | 权限三态 | TC-M30.5 | 单元 | ✅ | 见第 4 节矩阵 |
| NFR-M06 | 禁四字；事件无明文 | TC-M50.* TC-M26.1 | 单元 | ✅ | |
| NFR-M07 | 夹具出数；xlsx 非导出；New API 退役 | TC-M03.1 TC-M02.4 | 集成 | ✅ | `test_t20_retire_newapi.py:19` |
| NFR-M08 | 事件仅超管 | TC-M06.* TC-M14.* TC-M35.* | 集成 | ✅ | second_story=0 在 TC-M14.2/3 |
| NFR-M09 | 国际化 | — | — | ➖ **N/A** | spec §4：本轮仅中文 |
| NFR-M10 | 运行配置不写死 | TC-M33.* | 集成 | ✅ | 值班联系/配置走超管 API；网关不并根编排 `test_t20_retire_newapi.py:41` |

### 对照仍有效（check-matrix 抽取的 FR-\\d+）

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-01 | 免费档三数字 | TC-M12.2 | 单元 | ✅ | `Usage.test.tsx:376`；official `Pricing.test.tsx` |
| FR-13 | 未绑企业拒绝 | TC-M20.5 | 集成 | ✅ | 出站未签发 0 行 |
| FR-18 | 工人闸 | TC-U02.1 | 集成 | ✅ | `test_fr_u01_enqueue.py:300`；`Spiders.test.tsx` |
| FR-34 | 下架不级联 | TC-M41.4 | 集成 | ✅ | |
| FR-50 | 用量页线下订购 | — | — | ➖ **N/A** | spec §0.2 superseded by FR-M10/M13 |
| FR-51 | 出站签发/明文一次 | TC-M20.1 | 单元 | ✅ | `OutboundKeys.test.tsx` gwt_51_* |
| FR-60 | 渠道组 | TC-M23.* | 集成 | ✅ | `test_fr_u20_relay_sku.py`；GWT-60.4 Given=中转已开通 |
| FR-70 | 规划 70.1/70.2/74.1 | TC-M01.4/5 | 集成 | ✅ | `test_llm_four_actions_http.py` |
| FR-80 | 公开翻页 | TC-U80 | 集成 | ✅ | `backend/tests/test_t14_public_paging.py` |
| FR-81 | 去种子 | TC-U81 | 集成 | ✅ | `backend/tests/test_t13_public_seed_filter.py` |
| FR-82 | 侧栏单一真相 | TC-M20.7 | 单元 | ✅ | `App.menu.test.tsx` |
| FR-84 | 失败≠空 | TC-M02.2 | 单元 | ✅ | `Data.test.tsx`；GWT-84.2 superseded by M02.2 |
| FR-85 | 无工人去节点 | TC-U02.1 | 集成 | ✅ | |
| FR-87 | 禁内码 | TC-M01.1 | 集成 | ✅ | `test_fr87_enqueue_envelope.py` |
| FR-89 | 只读写隐藏 | TC-M21.3 | 集成 | ✅ | |
| FR-90 | 设置不说谎 | TC-M33.4 | 集成 | ✅ | |
| FR-91 | 市场冻结 | — | — | ➖ **N/A** | superseded by FR-M40 |
| FR-92 | user_restored | TC-M32.4 | 集成 | ✅ | |
| FR-93 | 软删恢复 | TC-M32.4 | 集成 | ✅ | `test_t24_user_restore.py` |
| FR-94 | 基座/种子 | TC-M32 | 集成 | ✅ | `test_t26_base_protection.py:74`；`Users.test.tsx:70` |
| FR-98 | 值班三问 | TC-M30.1 | 单元 | ✅ | `Overview3q.test.tsx` |
| FR-103 | 定义编辑 | TC-U103 | 集成 | ✅ | `test_t39_definition_edit_delete.py:68` |

### 状态图例

| 标记 | 含义 | 要求 |
|---|---|---|
| ✅ | 已覆盖且通过 | 有用例 ID + file:line |
| ❌ **缺口** | 该测但没测 | **必须在第 5 节说明 + 缺陷** |
| ⚠️ **需真实环境** | 测试环境测不出 | 转 `/sre`，跟踪结果 |
| ➖ **N/A** | 不适用 | 引用 PRD 声明 |

## 2. 反向：用例 → FR/NFR

| 用例 ID | 名称 | 对应 FR/NFR | 层 |
|---|---|---|---|
| TC-M01.1 | `test_gwt_m01_1_submit_disabled_copy_no_plan_no_enqueue` | FR-M01 / NFR-M01 | 集成 |
| TC-M01.5 | `test_post_plan_unreachable_only_74_1` | FR-M01 / FR-70 | 集成 |
| TC-M02.6 | Data 101 无文件 | FR-M02 / NFR-M02 | 单元 |
| TC-M03.1 | `test_gwt_m03_1_empty_free_non_fixture_enqueues_without_paywall` | FR-M03 / NFR-M07 | 集成 |
| TC-M06.4 | 租户无产品事实面 | FR-M06 / NFR-M08 | 集成 |
| TC-M10.4 | 旧 `POST /orders` 零新行 | FR-M10 / FR-M14 | 集成 |
| TC-M11.1 | 未配通道待支付 | FR-M11 / NFR-M03 | 集成 |
| TC-M11.4 | confirm 专业档 [SEC-3] | FR-M11 / NFR-M04 | 集成 |
| TC-M11.8 | 已有待支付 | FR-M11 / NFR-M02 | 集成 |
| TC-M11.12 | SQLite ThreadPool 同商品（非 W2 已兑） | FR-M11 / NFR-M02 | 专项 |
| TC-M11.13 | 直打 cancel/unpaid 404/405/422 | FR-M11 | 集成 |
| TC-M11.18 | 企业档/relay 迟到不叠不重签 | FR-M11 | 集成 |
| TC-M12.6 | 5 running 后第 6 任务已入队 | FR-M12 | 集成 |
| TC-M12.7 | 存储 10001 后再入队 | FR-M12 | 集成 |
| TC-M12.8 | 专业档 200001 token 规划 200+selectors | FR-M12 | 集成 |
| TC-M26.2 | 错平面事件空筛 total=0 | FR-M26 | 集成 |
| TC-M12.4 | 专业档不开中转 | FR-M12 / FR-M23 | 集成 |
| TC-M13.1 | 申请提升→结账 | FR-M13 | 集成 |
| TC-M14.1 | checkout_story_started | FR-M14 | 集成 |
| TC-M15.1 | 机械钉禁四字 | FR-M15 / FR-M50 / NFR-M06 | 单元 |
| TC-M20.4 | 渠道组令牌拉数 0 行 | FR-M20 / NFR-M04 | 集成 |
| TC-M21.4 | 不能设平台超管 | FR-M21 | 集成 |
| TC-M23.2 | 未开通中转 | FR-M23 | 集成 |
| TC-M24.2 | 还没有安装 | FR-M24 | 单元 |
| TC-M26.1 | outbound_wrong_plane_rejected | FR-M26 | 集成 |
| TC-M30.5 | permissionsReady | FR-M30 / NFR-M05 | 单元 |
| TC-M31.6 | 企业档金额≠¥299 | FR-M31 / NFR-M04 | 集成 |
| TC-M32.1 | 停用后登录失败 | FR-M32 | 集成 |
| TC-M33.5 | 租户设置 404 同形 | FR-M33 | 集成 |
| TC-M34.1 | 签发≠live | FR-M34 | 单元 |
| TC-M35.1 | duty_entry_opened | FR-M35 | 集成 |
| TC-M40.2 | 关旗≠空货架 | FR-M40 | 集成 |
| TC-M41.4 | 下架不级联 | FR-M41 / FR-34 | 集成 |
| TC-M51.1 | 创建企业 | FR-M51 | 集成 |

**无直接 FR 的用例处理**：无。本波 FR-M 套件均能指回 spec。

## 3. 状态流转覆盖

### 结账单据（W2 闭集）

| 状态＼操作 | 买方提交开通 | 超管确认收款（金额一致） | 超管确认（金额不符） | 租户自标已开通 | 买方取消 | 迟到通道成功 | HMAC 夹具当 live |
|---|---|---|---|---|---|---|---|
| 无单 | ✅ TC-M11.1/14/16 | ❌ 无单 | ❌ 无单 | ❌ TC-M11.6 | ➖ 无单 | ➖ | ➖ |
| 待支付 | ❌ TC-M11.8 不建第二笔 | ✅ TC-M11.4/15/17 | ❌ TC-M31.4/6 保持待支付 | ❌ TC-M11.6 | ❌ TC-M11.10 无入口；❌ TC-M11.13 直打取消 | ➖ W2 不走通道开通 | ❌ TC-M15.1 |
| 已开通 | ➖ 本波不再下同商品待支付（有则 M11.8 同类） | ❌ TC-M11.5 不叠 | ➖ | ➖ | ➖ | ✅ TC-M11.11 专业档；✅ TC-M11.18 企业/relay | ❌ TC-M50.2 |

live 波才构造（待支付→开通处理中 / 未完成 / FR-U38 通道开通）：➖ 本波不验收，不进矩阵当缺口。

**非法流转三项断言**：状态未变 / 记录符合预期 / 无配额副作用 — W2 已测格含 TC-M11.13。并发两买方见 M11.12 ⚠️ 真库，不填 ✅。

### 采集 / 出站 / 市场

| 流转 | 覆盖 |
|---|---|
| 规划未开放 → 不入队不产方案 | ✅ TC-M01.1 |
| 无付费前置第一次采集 | ✅ TC-M03.1 |
| 无钥匙 → 签发 → 拉数 | ✅ TC-M20.1 |
| 错平面拉数 → 0 行 | ✅ TC-M20.4/5 |
| 关旗不得新安装 | ✅ TC-M40.2/4 |
| 下架不删安装 | ✅ TC-M41.4 |

## 4. 权限矩阵覆盖

| 角色＼操作 | 采集提交 | 规划提交 | 数据中心导出 | 结账下单 | 确认收款 | 出站签发 | 渠道组签发 | 成员写 | 值班 | 上架 | 用户停用 | 设置写 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 匿名 | ❌ 401 | ❌ | ❌ | ❌ `test_fr_u30` U36.3 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ TC-M41.3 | ❌ | ❌ |
| 只读 | ❌ TC-M03.3 | ❌ TC-M01.3 | 读✅ | ❌ TC-M10.3 | ❌ | ❌ TC-M20.3 | ❌ | ❌ TC-M21.3 | ❌ 404 | ❌ | ❌ | ❌ TC-M33.5 |
| 经办 | ✅ TC-M03.1 | ✅/未开放 TC-M01.1 | ✅ TC-M02 | ❌ TC-M11.3 | ❌ | ✅ TC-M20.1 | ❌ TC-M23.3 未开通 | ❌ 超管角色 | ❌ 404 | ❌ TC-M40.3 | ❌ | ❌ |
| 公司管理员 | ✅ | ✅ | ✅ | ✅ TC-M11.1 | ❌ TC-M11.6 | ✅ | ✅ 中转已开通 | ✅ TC-M21.1 | ❌ TC-M30.3 | ❌ TC-M40.3 | ❌ TC-M32.3 | ❌ TC-M33.5 |
| 平台超管 | 无企业则不能代订 | — | 跨企业查事件 ✅ | 不能代付 | ✅ TC-M11.4 | — | — | 不能改平台租户名 ✅ FR-94 | ✅ TC-M30.1 | ✅ TC-M41.1 | ✅ TC-M32.1 | ✅ TC-M33.4 |

**三类越权覆盖**：

- [x] ① 换角色 — TC-M11.3 / TC-M21.3 / TC-M10.3
- [x] ② 换数据范围 — TC-M02.3 / TC-M11.9 / TC-M21.5 / TC-M24.3 / TC-M31.5
- [x] ③ 直接调接口 — 全部 `test_fr_m*` HTTP，不靠前端隐藏
- [x] ④ 跨租户 — 上列 + 404 同形（无「抱歉您没有权限」）

## 5. 空洞明细

本波 GWT-M **无剩余 ❌ 缺口**。空心 M12.8 已重写（见下关闭表）。仍开的只有环境闸 / 真库 ⚠️。

### 已关闭

| 票 | GWT | 关闭依据 |
|---|---|---|
| BUG-V03 | GWT-M11.18 | `test_fr_m11_confirm.py:164` / `:179` |
| BUG-V04 | GWT-M11.13 | `test_fr_m11_checkout_pending.py:166` |
| BUG-V05 | GWT-M26.2 | `test_fr_m20_outbound_lookup.py:169` |
| BUG-V01 | GWT-M12.6/7/8 | `:142` 第 6 任务已入队；`:159` 10001 再入队；`:228` plan **200**+selectors+outbound；`:252` 免费档拦住可失败 |

### ⚠️ 需真实环境：GWT-M11.12 两买方并发（BUG-V02）

| 项 | 内容 |
|---|---|
| 该测什么 | 两名买方同时对同一商品提交 → 只 1 笔待支付；另一人「已有待支付」；配额不变 |
| 为什么测不了 / 为何不算 W2 已兑 | 现有 `test_gwt_m11_12_concurrent_same_product_one_pending`（`:143`）用 **SQLite + ThreadPool** 共用同一 TestClient。SQLite 库级锁 / 生成列 UNIQUE 弱于 MySQL。verify G-fresh QA-02：**不得**当 W2 并发 Then 已兑 |
| 需要什么 | `MYSQL_FIDELITY=1` 双连接同时 POST |
| 转给谁 | `/sre` + `/backend` |
| 状态 | 待真库。顺序二次提交 M11.8 仍 ✅ |

### ⚠️ 需真实环境：GWT-M11.7 live 收银台

| 项 | 内容 |
|---|---|
| 该测什么 | 支付宝已配置、买方去支付 → 进入通道或 5s 内见通道句。开通仍须 FR-U38 |
| 为什么测不了 | spec 明文：不是 W2 放行；live 沙箱另波 |
| 转给谁 | `/sre` live 波 |
| 状态 | 待执行。**不得**把 HMAC 夹具写成已通 |

### ⚠️ 需真实环境：C4 live worker（GWT-M03.1 120s 出数）

| 项 | 内容 |
|---|---|
| 该测什么 | 非夹具免费企业 example/httpbin 120s 内 completed 且条数>0（真 Scrapy 工人） |
| 为什么测不了 | 套件完成态=本进程 ingest+webhook（测试自证） |
| 转给谁 | `/sre` C4 |
| 状态 | 待执行。3s 已入队已在 CI 断言 |

### ⚠️ 需真实环境：C2 真网关轮（GWT-M34.2 / FR-M34）

| 项 | 内容 |
|---|---|
| 该测什么 | 令牌已签发且 C2 记录未通过时，按页上用法发一条 → 失败可见、不是套餐超限 |
| 为什么测不了 | 真 LiteLLM 上游。本 FR 不替代环境闸 |
| 转给谁 | `/sre` |
| 状态 | 待执行。文案「签发≠live」已测 TC-M34.1 |

### ⚠️ 需真实环境：NFR-M01 结账 5s / 出数 120s

墙钟 SLA。Jest 路由跳转与 ingest 夹具不代替。

### 需真库验证清单（方言）

| 用例 | 为什么 SQLite 测不出 | 状态 |
|---|---|---|
| GWT-M11.12 / `uk_orders_tenant_open_product` | 生成列唯一 + 并发；SQLite 库级锁 / NULL 唯一与 MySQL 不同 | 待 `/sre` `MYSQL_FIDELITY=1`；SQLite ThreadPool 已有但不算 W2 已兑。BUG-V02 |
| 确认收款 CAS 金额 | 行锁；SQLite 单写者 | 金额不符已单线程测（M31.4）；并发 CAS 未测 |
| ESC-2 ORDER BY / JSON | 历史债：默认 pytest 走 SQLite | 本波 FR-M 未新引入 NULLS LAST；未跑 MYSQL_FIDELITY 全量 |

## 6. 裁剪声明

| 项 | 策略 | 说明 |
|---|---|---|
| 参数组合 | 商品闭集全组合 | `plan_pro` / `plan_enterprise` / `relay` 下单+确认全测；未做通道×商品 pairwise（live 波） |
| 等价类 | 每类一代表 | 只读 vs 经办 vs 买方；未对每个 viewer 账号重复 |
| E2E | 未跑 Playwright 主干 | 本波以 HTTP 集成 + 组件 Jest 为主；`frontend/admin/e2e/smoke.spec.ts` 不映射 GWT-M |
| 对照 FR-U / FR-\\d+ | 抽代表 | 仍有效句用既有 `test_fr_u*` / `test_t*`，不重开总台 |

## 7. 覆盖统计

| 项 | 数量 |
|---|---|
| FR-M 总数 / 已覆盖（至少一行非空洞） | 26 / 26 |
| NFR-M 总数 / 已覆盖 / N/A | 10 / 8 / 1（NFR-M09）；NFR-M01 部分 ⚠️ |
| 对照 FR-\\d+ 出现在矩阵 | 22 / 22（含 2 条 superseded=N/A） |
| GWT-M 总数 / ✅ / ❌ / ⚠️ | 130 / 127 / 0 / 3（⚠️ M11.7、M11.12、M34.2；M03.1 主路径 ✅ 另附 C4 ⚠️） |
| 本轮执行：单元(Jest) / 集成(pytest FR-M) / E2E / 专项 | 222 Jest / 既有 + M12.8 两测 2 passed 1.39s / 0 / 0 |
| 缺口数 ❌ | 0 |
| 需真实环境 ⚠️ | 6（M11.7、M11.12 MYSQL_FIDELITY、C4、C2、结账 5s、真库 CAS） |
| 状态流转格子 已填 | W2 闭集无空格（live 边标 ➖） |
| 权限矩阵格子 | 已填；三类越权+跨租户齐全 |

**覆盖率数字不作为质量结论。** 剩余风险是 M11.12 未真库并发，不是矩阵空洞。**不**标四柱 GA。SQLite ThreadPool 不记 W2 已兑。

## 8. 自检

- [x] 每条 FR-M / NFR-M 都有一行，无留空
- [x] check-matrix 所需 FR-\\d+ 均出现
- [x] 每个用例都能反向指回 FR/NFR
- [x] 状态流转矩阵无空格子（不适用标 ➖）
- [x] 权限矩阵无空格子，三类越权齐全
- [x] 每个空洞在第 5 节展开
- [x] 裁剪策略已声明
- [x] 需真库 / C2 / C4 / live 收银台已交 `/sre` 跟踪
- [x] 无 `assert True` / `or True` 记入 ✅（`test_fr_m*` 已扫）
