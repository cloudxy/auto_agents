# 覆盖矩阵 · 四柱程序 v2（冻结施工集）

> 泳道：L4
> 上游：PRD `01-define/spec.md` v1.6｜契约 `02-shape/contract.md` v1.8｜`edge-states.md`
> 证据：`03-impl/T-01-evidence.md` … `T-33-evidence.md`
> 作者：/qa｜日期：2026-09-10｜下游：`/qc` 或 `/reviewer`
> 返工：CV-01…08（G-fresh FAIL `01a08787-aaee-72b2-9e4b-b3f9bd5d09d0`）。01.8/01.6/73.4 补 Then 断言；T-xx 证据不再当覆盖。
> 续：QC 条件 2–6。独立读测试文件后翻转 01.1 / 06.1 Then 格；NFR-01 用预发浏览器而非 TestClient。
> 返工：CV-09 / QA-01 曾把 +129s 当绿（当时 IdleAutoClose=120）。本轮 **翻回 ✅**：idle close 现 **30s** 后 live GWT-18.1（`run.py restart spider`，非 FakeRedis）。signup **200** tenant `qc181-1789008085`；task **#2** example+httpbin；+6.1s running `result_count=1`；**+40.6s completed result_count=1**；export JSON **200 rows 1**；elapsed **40.56s ≤ 120s**。Idle close **30 ≠** 18.4 标注窗 **120**。C35-QA-03 Register 已钉 copy；NFR-07 44px Jest ✅；wiring/byok `or True` 已去。01.1 / 06.1 / NFR-01 / 37.6 保持 ✅。FR-50/51/60/61 ➖。
> 范围：FR-01…20（Wave 0）+ FR-70…75（Wave L）+ FR-30…45（Wave 1）+ spec NFR。
> 方言：默认 pytest = SQLite；生产 = MySQL 8。方言敏感 SQL 标 ⚠️ 需真库；预发 MYSQL_FIDELITY 已过的格改 ✅ 并引用 `qc-cond-2-preprod.md`。
> **不**把 changelog「已关闭」、票 status=done、G-fresh PASS 当覆盖。空心 `assert True` / `or True` 当空洞。
> 六问未关：不代选。Wave 2/3 stub：➖ N/A「Wave 2/3 未施工」。

## 0. 结论先行（事实，非放行）

冻结 GWT 绝大多数有具名用例且断言对照 Then。本矩阵**不能**当发布意见。不是四柱 GA。

| 项 | 事实 |
|---|---|
| 冻结 FR 行 | 每条 FR-01…20 / 70…75 / 30…45 均有矩阵行 |
| NFR 行 | NFR-01…10 均有行；NFR-09 ➖ 本轮仅中文；NFR-01 预发浏览器卡片可见 P95 1.444558s ✅（非 TestClient）；NFR-07 触摸 ≥44px Jest ✅（Home/Pricing/Register） |
| 硬缺口 ❌ | **0 条冻结 GWT**。原 01.1 / 06.1 本轮 Then 已对照（Usage↔Pricing 三数；scan OperationLog who/what），不再是硬 ❌ |
| 空心断言 | 原 wiring:55 / byok:45 `or True` **已去掉**。本帽 `pytest -q backend/tests/test_saas_wiring.py backend/tests/test_saas_byok.py` **14 passed** exit 0。不在冻结 GWT 主映射上，不再计入空洞 |
| 需真实环境 ⚠️ | GWT-16.1 时区；IM-02/03/18/26 残余。**GWT-18.1 / TC-18.1 本轮 live Then 已过**（+40.6s completed，40.56s ≤ 120s；FakeRedis 不顶）。NFR-07 44px 已有 Jest。37.6 MYSQL_FIDELITY / NFR-01 浏览器：预发已过（`06-deliver/qc-cond-2-preprod.md`），一次性、未进仓库 CI |
| Wave 2/3 | FR-50/51/60/61 整段 ➖ Wave 2/3 未施工 |
| 六问 | Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL ➖ 不代选 |

放行决策不由本帽做。

### 状态图例

| 标记 | 含义 |
|---|---|
| ✅ | 已覆盖：有 file:line，断言对照 Then |
| ❌ **缺口** | 该测没测，或映射空心 |
| ⚠️ **需真实环境** / 部分 | SQLite 测不出、模拟夹具、或 Then 只覆盖一半 |
| ➖ **N/A** | 不适用（stub / 六问 / spec 声明） |

---

## 1. 正向：FR/NFR → 用例

### 1.1 Wave 0 · FR-01…20

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注（file:line） |
|---|---|---|---|---|---|
| FR-01 | GWT-01.1 正常 A1 | TC-01.1 | 单元 | ✅ | `Usage.test.tsx:185` 锁 `FREE_TIER_FEATURE_COPY` = Given「5 个并发任务 / 10,000 条结果存储 / 20 万 LLM tokens/月」，mock 上限从 copy 解析，页上 `/ 5 个运行中`、`10,000`、`200,000`、无预告。`Pricing.test.tsx:71` 同三句且行内无预告。将满夹具仍用 `result_storage:100`（`:45`），不顶本格。C35-QA-03 **已关**：`Register.test.tsx:177` 钉 copy 三句、禁 `10000` |
| FR-01 | GWT-01.7 正常 A2 | TC-01.7 | 单元 | ✅ | `Pricing.test.tsx:39` `href="/register"`；同 GWT-05.1。首页 CTA `Home.test.tsx:52` |
| FR-01 | GWT-01.8 正常 A3 | TC-01.8 | 单元 | ✅ | `Home.test.tsx:67` 断言「粘贴链接 / 提交任务 / 查看结果」且无预告邻接。首页含 Features/AiFlow 同树。提交路径并 FR-18 |
| FR-01 | GWT-01.9 正常 A4 | TC-01.9 | 单元 | ✅ | `FeaturesSection.test.tsx:22` CSV/JSON + 100 条，无 Excel/xlsx |
| FR-01 | GWT-01.10 正常 A5 | TC-01.10 | 单元 | ✅ | `Pricing.test.tsx:78` 成员管理/用量看板行内无预告；打开页 `Members.test.tsx:22`、`Usage.test.tsx:73` |
| FR-01 | GWT-01.2 空态 B1–B4 | TC-01.2 | 单元 | ✅ | `Pricing.test.tsx:62` 四项各自行内带「预告」Tag；付费主按钮非注册 `:44` |
| FR-01 | GWT-01.11 空态 B5 | TC-01.11 | 单元 | ✅ | 同 01.9 `FeaturesSection.test.tsx:22` |
| FR-01 | GWT-01.12 空态 B6 | TC-01.12 | 单元 | ✅ | `Pricing.test.tsx:44` 「预告不可购买」+ 无「现在就能买到并开通」；Q-PRICE 未关不测支付 |
| FR-01 | GWT-01.3 边界 | TC-01.3 | 单元 | ✅ | `Pricing.test.tsx:93` / `Home.test.tsx:85` 源无会话分支；渲染闭集 A 可买、B 预告不可购买（匿名=登录同一静态） |
| FR-01 | GWT-01.4 失败 | TC-01.4 | 单元 | ✅ | `Home.test.tsx:59` 「暂时无法加载能力」+重试；禁「还没有技能/暂无已发布」 |
| FR-01 | GWT-01.5 越权 | TC-01.5 | 单元 | ✅ | 豁免：全 `frontend/` grep「编辑官网/改定价」0 命中；未加后台入口。非正向寻找用例 |
| FR-01 | GWT-01.6 禁止句 | TC-01.6 | 单元 | ✅ | `Home.test.tsx:78` / `FeaturesSection.test.tsx:31` / `Pricing.test.tsx:87` 无抽取准确率/已校准/官方认证/正品保证 |
| FR-02 | GWT-02.1 正常 | TC-02.1 | 单元 | ✅ | `Home.test.tsx:42` 无 128,000+ / 12 节点 / 3.2 亿条 / 示意数据 |
| FR-02 | GWT-02.2 空态 | TC-02.2 | 单元 | ✅ | 同 `:42` 不渲染占位大数 |
| FR-02 | GWT-02.3 越权 | TC-02.3 | 单元 | ✅ | `Home.test.tsx:42` 无虚构规模；`:85` 无会话分支，经办打开同一静态 |
| FR-03 | GWT-03.1 正常 | TC-03.1 | 集成 | ✅ | `backend/tests/test_spider_task_flow.py:377` CSV；`:391` JSON |
| FR-03 | GWT-03.2 空态 | TC-03.2 | 集成 | ✅ | `test_spider_task_flow.py:359`；`ResultDrawer.test.tsx:59` 无文件 |
| FR-03 | GWT-03.3 边界 | TC-03.3 | 集成 | ✅ | `test_spider_task_flow.py:401` 120→100；`Data.test.tsx:47` / `ResultDrawer.test.tsx:50` 文案 |
| FR-03 | GWT-03.4 越权 | TC-03.4 | 集成 | ✅ | `test_spider_task_flow.py:439` 跨租户未执行 |
| FR-03 | GWT-03.5 官网 | TC-03.5 | 单元 | ✅ | 同 01.9；`test_spider_task_flow.py:460` xlsx 拒 |
| FR-04 | GWT-04.1 正常 | TC-04.1 | 单元 | ✅ | `Register.test.tsx:50`；`Login.test.tsx:62` from 回跳 |
| FR-04 | GWT-04.2 空态 | TC-04.2 | 集成 | ✅ | `Register.test.tsx:71`；`test_saas_signup_expiry.py:105` 弱密码不落户 |
| FR-04 | GWT-04.3 边界 | TC-04.3 | 单元 | ✅ | `Register.test.tsx:90`；`Login.test.tsx:55` 企业注册回链 |
| FR-04 | GWT-04.4 越权 | TC-04.4 | 集成 | ✅ | `test_saas_signup_expiry.py:118`；`Register.test.tsx:104` |
| FR-05 | GWT-05.1 正常 | TC-05.1 | 单元 | ✅ | 同 01.7 `Pricing.test.tsx:39` |
| FR-05 | GWT-05.2 边界 | TC-05.2 | 单元 | ✅ | 同 01.12 `Pricing.test.tsx:44` |
| FR-05 | GWT-05.3 越权 | TC-05.3 | 单元 | ✅ | `Pricing.test.tsx:44` 付费 CTA 非 `/register` + 无「再开一家免费企业」 |
| FR-06 | GWT-06.1 正常 | TC-06.1 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:119` 200+落库；`:137` 查 `OperationLog` action=`plugin.scan` target=`plugins` actor_id=1 actor_name=`test-platform-admin`。`test_audit_helpers.py:71` standalone 失败不 commit 请求 session。verify 路径未另查 OperationLog；Then 是扫描或验证，扫描格已钉 who/what。403 leftover 仍在 06.3 |
| FR-06 | GWT-06.2 空态 | TC-06.2 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:179` 「没有可同步的包」 |
| FR-06 | GWT-06.3 越权 | TC-06.3 | 集成 | ✅ | `:167` 扫描 leftover；`:309` verify；`test_b1c_newapi_channels_coverage.py:214` 改窗口；`test_saas_rbac_deep.py:97` |
| FR-06 | GWT-06.4 越权 | TC-06.4 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:158` viewer 403 零落库（作废 viewer 200） |
| FR-06 | GWT-06.5 边界 | TC-06.5 | 集成 | ✅ | `test_llm_platform_row_writes.py:26`；`LlmProviders.test.tsx:72`。**未**把 `rejects_operator` 当完成态（该 node 已不存在） |
| FR-06 | GWT-06.6 越权 | TC-06.6 | 集成 | ✅ | `test_llm_platform_row_writes.py:45` / `:81` 平台行不变 |
| FR-07 | GWT-07.1 正常 | TC-07.1 | 单元 | ✅ | 导航 `usePermission.test.tsx:137`；页 `NewApiOps.test.tsx:88` 看得到值班；`:63` 不可达降级禁「暂无渠道」（71.2/71.3 同页，本格不另造第二套 Then） |
| FR-07 | GWT-07.2 空态 | TC-07.2 | 单元 | ✅ | `usePermission.test.tsx:115` 无中转/运营/源上架写 |
| FR-07 | GWT-07.3 越权 | TC-07.3 | 单元 | ✅ | `App.test.tsx:80`；`ProtectedRoute.test.tsx:99` 404 同形无渠道/密钥/抱歉 |
| FR-07 | GWT-07.4 越权 | TC-07.4 | 集成 | ✅ | `test_b1c_newapi_channels_coverage.py:214` 额度不变。证据文件名曾写 404，实为 403 JSON 写拒绝（页 GET 走 07.3） |
| FR-07 | GWT-07.5 边界 | TC-07.5 | 单元 | ✅ | `Dashboard.test.tsx:29` 第一步 `/llm` 不到 `/newapi` |
| FR-07 | GWT-07.6 冻结 | TC-07.6 | 集成 | ✅ | `test_llm_probe.py:168`；`test_channel_config_service.py:152`。T-05「行为保持」不当覆盖 |
| FR-08 | GWT-08.1 正常 | TC-08.1 | 集成 | ✅ | `test_saas_signup_expiry.py:213` 文案 ≠ 密码错误；`:263` disabled |
| FR-08 | GWT-08.2 边界 | TC-08.2 | 集成 | ✅ | `:277` 已颁会话写拒绝，任务/token 不增 |
| FR-08 | GWT-08.3 越权 | TC-08.3 | 集成 | ✅ | `:213` 后半有效企业仍 200 |
| FR-08 | GWT-08.4 空态 | TC-08.4 | 集成 | ✅ | `:328` 平台 marketplace 不进租户结果 |
| FR-09 | GWT-09.1 正常 | TC-09.1 | 集成 | ✅ | `test_saas_wiring.py:303` / `:178` |
| FR-09 | GWT-09.2 边界 | TC-09.2 | 集成 | ✅ | `test_spider_task_flow.py:730` 定时归属 |
| FR-09 | GWT-09.3 越权 | TC-09.3 | 集成 | ✅ | `test_saas_wiring.py:207` |
| FR-09 | GWT-09.4 空态 | TC-09.4 | 集成 | ✅ | `test_saas_wiring.py:285` / `:161` 无主不入队 |
| FR-10 | GWT-10.1 正常 | TC-10.1 | 集成 | ✅ | `test_saas_wiring.py:233` |
| FR-10 | GWT-10.2 边界 | TC-10.2 | 集成 | ✅ | `test_saas_wiring.py:261`；`test_task_consumer.py:148` |
| FR-10 | GWT-10.3 越权 | TC-10.3 | 集成 | ✅ | `test_spider_task_flow.py:450` 同「没有这个任务」 |
| FR-10 | GWT-10.4 失败 | TC-10.4 | 集成 | ✅ | `test_task_consumer.py:185` / `:224` / `:245` |
| FR-11 | GWT-11.1 正常 | TC-11.1 | 集成 | ✅ | `test_skill_candidates.py:200` 候选不计存储闸 |
| FR-11 | GWT-11.2 空态 | TC-11.2 | 集成 | ✅ | `test_spider_datacenter_crud.py:602` / `:868` |
| FR-11 | GWT-11.3 越权 | TC-11.3 | 集成 | ✅ | `test_skill_candidates.py:122` / `:141` 与缺失同形 |
| FR-12 | GWT-12.1 正常 | TC-12.1 | 集成 | ✅ | `test_saas_quota.py:192` |
| FR-12 | GWT-12.2 边界 | TC-12.2 | 集成 | ✅ | `test_saas_quota.py:113`；Usage 将满无内部码 |
| FR-12 | GWT-12.3 超限 | TC-12.3 | 集成 | ✅ | `test_saas_quota.py:135`；`test_llm_four_actions_http.py:514` |
| FR-12 | GWT-12.6 出口 | TC-12.6 | 单元 | ✅ | `Usage.test.tsx:113` token 满 CTA 不到注册、mailto 联系说明。支付仍 FR-50 stub |
| FR-12 | GWT-12.7 出口 | TC-12.7 | 单元 | ✅ | `Usage.test.tsx:143` 存储满 CTA `href="/data"` 非 `/register` |
| FR-12 | GWT-12.4 越权 | TC-12.4 | 集成 | ✅ | `test_saas_quota.py:277`；`Usage.test.tsx:73` |
| FR-12 | GWT-12.5 降级 | TC-12.5 | 集成 | ✅ | `test_saas_quota.py:231` 熔断句 ≠ 套餐超限 |
| FR-13 | GWT-13.1 正常 | TC-13.1 | 集成 | ✅ | `test_external_api.py:379` |
| FR-13 | GWT-13.2 空态 | TC-13.2 | 集成 | ✅ | `test_external_api.py:402` / `:481` |
| FR-13 | GWT-13.3 越权 | TC-13.3 | 集成 | ✅ | `test_external_api.py:420`；`test_spider_datacenter_crud.py:830` ⚠️ SQL 绑 tenant 需真库 |
| FR-13 | GWT-13.4 边界 | TC-13.4 | 集成 | ✅ | `test_external_api.py:444` / `:173` |
| FR-14 | GWT-14.1 正常 | TC-14.1 | 集成 | ✅ | `test_fr14_secrets_off_tree.py:143` |
| FR-14 | GWT-14.2 空态 | TC-14.2 | 集成 | ✅ | `test_fr14_secrets_off_tree.py:123` |
| FR-14 | GWT-14.3 越权 | TC-14.3 | 单元 | ✅ | 并 GWT-07.3，禁止渠道页掩码当 Then |
| FR-14 | GWT-14.4 边界 | TC-14.4 | 单元 | ✅ | `test_llm_provider.py:145` TestMask；`:691` 列表掩码 |
| FR-14 | GWT-14.5 合规 | TC-14.5 | 单元 | ✅ | `test_fr14_secrets_off_tree.py:89` / `:95`；arch FR-14 段。轮换证据不在本 GWT |
| FR-15 | GWT-15.1 正常 | TC-15.1 | 集成 | ✅ | `test_product_events.py:63` `is_marketplace_candidate=否` |
| FR-15 | GWT-15.2 空态 | TC-15.2 | 集成 | ✅ | `test_product_events.py:98` 上报失败不挡入队 |
| FR-15 | GWT-15.3 越权 | TC-15.3 | 集成 | ✅ | `test_product_events.py:139`；`App.test.tsx:34` |
| FR-15 | GWT-15.8 正常 | TC-15.8 | 集成 | ✅ | `test_product_events.py:148` |
| FR-15 | GWT-15.4 边界 | TC-15.4 | 集成 | ✅ | `test_product_events.py:175` 无密码 |
| FR-15 | GWT-15.5 漏斗 | TC-15.5 | 集成 | ✅ | `test_product_events.py:219` |
| FR-15 | GWT-15.14 旁路 | TC-15.14 | 集成 | ✅ | `test_product_events.py:238` |
| FR-15 | GWT-15.9 正常 | TC-15.9 | 集成 | ✅ | `test_product_events.py:252`；`SiteLayout.beacon.test.tsx:38` |
| FR-15 | GWT-15.6 分档 | TC-15.6 | 集成 | ✅ | `test_product_events.py:264[pricing_pro]`；`Pricing.beacon.test.tsx:35` |
| FR-15 | GWT-15.15 分档 | TC-15.15 | 集成 | ✅ | `:264[register_free]`；`Pricing.beacon.test.tsx:28` |
| FR-15 | GWT-15.16 分档 | TC-15.16 | 集成 | ✅ | `:264[pricing_enterprise]`；`Pricing.beacon.test.tsx:43` |
| FR-15 | GWT-15.17 分档 | TC-15.17 | 集成 | ✅ | `:264[login]`；`SiteLayout.beacon.test.tsx:16` |
| FR-15 | GWT-15.18 分档 | TC-15.18 | 集成 | ✅ | `:264[browse_market]`；`SiteLayout.beacon.test.tsx:26` |
| FR-15 | GWT-15.10 正常 | TC-15.10 | 集成 | ✅ | `test_product_events.py:278` |
| FR-15 | GWT-15.11 正常 | TC-15.11 | 集成 | ✅ | `test_product_events.py:309` |
| FR-15 | GWT-15.12 正常 | TC-15.12 | 集成 | ✅ | `test_product_events.py:335` |
| FR-15 | GWT-15.7 旁路 | TC-15.7 | 集成 | ✅ | `test_product_events.py:360`；`Home.beacon.test.tsx:37` |
| FR-15 | GWT-15.19 旁路 | TC-15.19 | 集成 | ✅ | `test_product_events.py:372`；`Home.beacon.test.tsx:44` |
| FR-15 | GWT-15.13 边界 | TC-15.13 | 集成 | ✅ | `test_product_events.py:383` 按企业过滤 |
| FR-16 | GWT-16.1 正常 | TC-16.1 | 单元 | ⚠️ | `test_llm_usage_service.py:172` 上海月。时区函数 ⚠️ 需真库 DATE 语义 |
| FR-16 | GWT-16.2 边界 | TC-16.2 | 单元 | ✅ | `test_spider_stats_nodes.py:72` 近 7 日窗口 |
| FR-16 | GWT-16.3 越权 | TC-16.3 | 集成 | ✅ | `test_saas_quota.py:269`；`Usage.test.tsx:131` |
| FR-17 | GWT-17.1 正常 | TC-17.1 | 单元 | ✅ | `usePermission.test.tsx:115` 仪表盘+数据工厂；允许 FR-35 安装叶 |
| FR-17 | GWT-17.2 空态 | TC-17.2 | 单元 | ✅ | `usePermission.test.tsx:80` 权限加载中/读叶，无平台写 |
| FR-17 | GWT-17.3 越权 | TC-17.3 | 单元 | ✅ | 同 07.2 无平台写入口 |
| FR-18 | GWT-18.1 正常 | TC-18.1 | 专项 | ✅ | live 非 FakeRedis：`run.py restart spider` 后。signup **200** tenant `qc181-1789008085`；POST run example+httpbin task **#2** pending；poll **+6.1s** running `result_count=1`；**+40.6s status=completed result_count=1**；GET export JSON **200 rows 1**；elapsed **40.56s ≤ 120s**。IdleAutoClose **30s** ≠ GWT-18.4 标注窗 **120s**。FakeRedis `test_spider_min_loop.py:129` **不顶本格**。一次性 live，未进仓库 CI。旧预发 +129s（当时 idle=120）作废 |
| FR-18 | GWT-18.2 空态 | TC-18.2 | 集成 | ✅ | `test_spider_worker_offline.py:32`；`Spiders.test.tsx:77` |
| FR-18 | GWT-18.3 越权 | TC-18.3 | 集成 | ✅ | `test_t10_api_coverage.py:89` viewer 403 |
| FR-18 | GWT-18.4 边界 | TC-18.4 | 集成 | ✅ | `test_spider_worker_offline.py:56` 无终态满 **120s** 标工人不在线。`SPIDER_WORKER_OFFLINE_SECONDS=120`；**不得**复用 IdleAutoClose **30s**。`test_scrapy_idle_autoclose.py:43` 两窗分家 |
| FR-19 | GWT-19.1 正常 | TC-19.1 | 集成 | ✅ | `test_spider_zero_items.py:25` 离开 running |
| FR-19 | GWT-19.2 空态 | TC-19.2 | 集成 | ✅ | 同 `:25` 0 条可区分还在跑 |
| FR-19 | GWT-19.3 越权 | TC-19.3 | 集成 | ✅ | `test_spider_zero_items.py:71` |
| FR-20 | GWT-20.1 正常 | TC-20.1 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:211` |
| FR-20 | GWT-20.2 空态 | TC-20.2 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:200` |
| FR-20 | GWT-20.3 越权 | TC-20.3 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:437` |

### 1.2 Wave L · FR-70…75

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注（file:line） |
|---|---|---|---|---|---|
| FR-70 | GWT-70.1 正常规划 | TC-70.1 | 集成 | ✅ | `test_llm_four_actions_http.py:209` 只该 node；禁止 similar-suggest 勾本格 |
| FR-70 | GWT-70.5 试采 | TC-70.5 | 集成 | ✅ | `test_llm_four_actions_http.py:340` 进 `_repair_flow` |
| FR-70 | GWT-70.6 评分 | TC-70.6 | 集成 | ✅ | `test_llm_four_actions_http.py:442` `consume_once` |
| FR-70 | GWT-70.7 聊天夹具 | TC-70.7 | 集成 | ✅ | `test_skill_similar_suggest.py:71` outbound=网关 URL |
| FR-70 | GWT-70.2 空态规划 | TC-70.2 | 集成 | ✅ | `test_llm_four_actions_http.py:223` 仅 70.2 句 |
| FR-70 | GWT-70.8 空态试采 | TC-70.8 | 集成 | ✅ | `:354` |
| FR-70 | GWT-70.9 空态评分 | TC-70.9 | 集成 | ✅ | `:458` |
| FR-70 | GWT-70.10 空态聊天 | TC-70.10 | 集成 | ✅ | `test_skill_similar_suggest.py:112` |
| FR-70 | GWT-70.3 越权写 | TC-70.3 | 集成 | ✅ | `test_newapi_api.py:295` 列表不变 |
| FR-70 | GWT-70.4 越权入口 | TC-70.4 | 单元 | ✅ | 三 node：`Home.test.tsx:32` `FeaturesSection.test.tsx:12` `Pricing.test.tsx:21`；admin `App.test.tsx:96`。**不是** 72.3 同一句 |
| FR-71 | GWT-71.1 正常 | TC-71.1 | 集成 | ✅ | `test_newapi_api.py:83`；`NewApiOps.test.tsx:88` 无完整 Key |
| FR-71 | GWT-71.2 空态 | TC-71.2 | 集成 | ✅ | `test_newapi_api.py:109`；`NewApiOps.test.tsx:41` |
| FR-71 | GWT-71.3 降级 | TC-71.3 | 集成 | ✅ | `test_newapi_api.py:153`；`NewApiOps.test.tsx:63` |
| FR-71 | GWT-71.4 越权 | TC-71.4 | 单元 | ✅ | `test_newapi_api.py:263`；并 07.3 |
| FR-72 | GWT-72.1 正常 | TC-72.1 | 集成 | ✅ | `test_t20_retire_newapi.py:19` 默认 litellm + 70.1 outbound 不经 new-api |
| FR-72 | GWT-72.2 空态 | TC-72.2 | 集成 | ✅ | T-18 值班网关列表；`test_t20_retire_newapi.py:33` 无 NEWAPI 读 |
| FR-72 | GWT-72.3 越权 | TC-72.3 | 单元 | ✅ | `App.test.tsx:96` 无中转令牌；定价渠道组预告 `Pricing.test.tsx:53`。**不得**与 70.4 写成同一句 |
| FR-73 | GWT-73.1 正常保存 | TC-73.1 | 集成 | ✅ | `test_llm_platform_row_writes.py:113` |
| FR-73 | GWT-73.5 BYOK 规划 | TC-73.5 | 集成 | ✅ | `test_fr73_byok_four_actions_http.py:163` |
| FR-73 | GWT-73.7 BYOK 试采 | TC-73.7 | 集成 | ✅ | `:206` |
| FR-73 | GWT-73.8 BYOK 评分 | TC-73.8 | 集成 | ✅ | `:240` |
| FR-73 | GWT-73.9 BYOK 聊天 | TC-73.9 | 集成 | ✅ | `:277` |
| FR-73 | GWT-73.6 网关停规划 | TC-73.6 | 集成 | ✅ | `:176` 不得 74.1 |
| FR-73 | GWT-73.10 网关停试采 | TC-73.10 | 集成 | ✅ | `:221` |
| FR-73 | GWT-73.11 网关停评分 | TC-73.11 | 集成 | ✅ | `:257` |
| FR-73 | GWT-73.12 网关停聊天 | TC-73.12 | 集成 | ✅ | `:293` |
| FR-73 | GWT-73.2 空态走 70 | TC-73.2 | 集成 | ✅ | `:194` |
| FR-73 | GWT-73.3 越权 | TC-73.3 | 集成 | ✅ | `test_llm_platform_row_writes.py:132` 同 06.6 |
| FR-73 | GWT-73.4 测试连接 | TC-73.4 | 单元 | ✅ | `LlmProviders.test.tsx:120` 点击「测试连接」→ `testLlmProvider(1)` 非平台行 2；失败句含「本企业供应商」/「不是平台网关」，禁 71.2「还没有平台模型」、74.1「平台 LLM 网关不可达」。进页 `ProtectedRoute.test.tsx:70` |
| FR-74 | GWT-74.1 规划不可达 | TC-74.1 | 集成 | ✅ | `test_llm_four_actions_http.py:240` 分格，不与 70.2 互勾 |
| FR-74 | GWT-74.4 试采不可达 | TC-74.4 | 集成 | ✅ | `:373` |
| FR-74 | GWT-74.5 评分不可达 | TC-74.5 | 集成 | ✅ | `:480` |
| FR-74 | GWT-74.6 聊天不可达 | TC-74.6 | 集成 | ✅ | `test_skill_similar_suggest.py:162` |
| FR-74 | GWT-74.2 满额优先 | TC-74.2 | 集成 | ✅ | `test_llm_four_actions_http.py:514` / `:536` 可达与不可达各一 |
| FR-74 | GWT-74.3 越权 | TC-74.3 | 集成 | ✅ | 并 12.4 `test_saas_quota.py:277` |
| FR-75 | GWT-75.1 正常 | TC-75.1 | 单元 | ✅ | `test_fr14_secrets_off_tree.py:89`；`test_t20_retire_newapi.py:41` 根 compose 无 new-api；T-14 compose config |
| FR-75 | GWT-75.2 空态 | TC-75.2 | 单元 | ✅ | 并 71.1 掩码 |
| FR-75 | GWT-75.3 越权 | TC-75.3 | 单元 | ✅ | 并 07.3 / 14.3 |

### 1.3 Wave 1 · FR-30…45

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注（file:line） |
|---|---|---|---|---|---|
| FR-30 | GWT-30.1 正常 | TC-30.1 | 单元 | ✅ | `SiteLayout.beacon.test.tsx:26` 唯一「能力市场」 |
| FR-30 | GWT-30.2 边界 | TC-30.2 | 单元 | ✅ | `SkillsSquare.test.tsx:32` `/skills` 已筛技能 |
| FR-30 | GWT-30.3 越权 | TC-30.3 | 单元 | ✅ | 无「专家」类型名；有智能体（T-21 + 治理七叶） |
| FR-30 | GWT-30.4 兼容 | TC-30.4 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:609` expert→agent |
| FR-31 | GWT-31.1 正常 | TC-31.1 | 单元 | ✅ | `Capabilities.test.tsx:64` / `:76`；`test_t22_list_filters.py` q 命中 |
| FR-31 | GWT-31.2 空态 | TC-31.2 | 单元 | ✅ | `Capabilities.test.tsx:100` |
| FR-31 | GWT-31.3 筛选空 | TC-31.3 | 单元 | ✅ | `Capabilities.test.tsx:111` |
| FR-31 | GWT-31.4 失败 | TC-31.4 | 单元 | ✅ | `Capabilities.test.tsx:133` / `:145` / `:154` 失败≠空 |
| FR-31 | GWT-31.5 预告 | TC-31.5 | 单元 | ✅ | `Capabilities.test.tsx:164` |
| FR-31 | GWT-31.6 越权 | TC-31.6 | 集成 | ✅ | 前端不宣称空洞缺席；`test_t22_list_filters.py:69` 服务端 |
| FR-32 | GWT-32.1 正常 | TC-32.1 | 集成 | ✅ | `test_skill_public_api.py:135`；`test_b1c_capabilities_coverage.py:655` |
| FR-32 | GWT-32.6 未登录 | TC-32.6 | 集成 | ✅ | `test_skill_public_api.py:173`；`test_t25_subscribe.py` 401 无行 |
| FR-32 | GWT-32.7 回跳 | TC-32.7 | 集成 | ✅ | `test_skill_public_api.py:180`；`test_b1c_capabilities_coverage.py:714` |
| FR-32 | GWT-32.2 预告 | TC-32.2 | 集成 | ✅ | `test_skill_public_api.py:148`；`test_b1c_capabilities_coverage.py:670` |
| FR-32 | GWT-32.3 越权 HTML | TC-32.3 | 集成 | ⚠️ | `test_skill_public_api.py:158` 真 404 字节同形。IM-02：常量 `STORE_NOT_FOUND_HTML` 与响应对照，须保持与官网 404 模板同源 |
| FR-32 | GWT-32.8 POST JSON | TC-32.8 | 集成 | ✅ | `test_skill_public_api.py:201`；`test_t25_subscribe.py:320` 无行 |
| FR-32 | GWT-32.4 XSS | TC-32.4 | 单元 | ✅ | `CapabilityDetail.test.tsx:68` 脚本当文本 |
| FR-32 | GWT-32.5 出处 | TC-32.5 | 单元 | ✅ | `CapabilityDetail.test.tsx:77` |
| FR-32 | GWT-32.9 包含 A/B | TC-32.9 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:734` |
| FR-32 | GWT-32.10 未上架子卡 | TC-32.10 | 集成 | ✅ | `:743` |
| FR-32 | GWT-32.11 黑名单/软删 | TC-32.11 | 集成 | ✅ | `:753` |
| FR-32 | GWT-32.12 许可/实验 | TC-32.12 | 集成 | ✅ | `:766` |
| FR-33 | GWT-33.1 正常 | TC-33.1 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:779` |
| FR-33 | GWT-33.2 夹具 | TC-33.2 | 集成 | ✅ | `test_skill_public_api.py:223`；`test_b1c_capabilities_coverage.py:792`。IM-04 六行无 override=1：许可特例改走 42.2 |
| FR-33 | GWT-33.3 越权 | TC-33.3 | 集成 | ✅ | `test_skill_public_api.py:235` |
| FR-33 | GWT-33.4 分页空 | TC-33.4 | 集成 | ⚠️ | 技能端 `test_skill_public_api.py:242` **钉** `len(items)==20`；MYSQL_FIDELITY 方言批含该文件（`qc-cond-2-preprod.md` §1.1）。能力端 `test_b1c_capabilities_coverage.py:802` 未钉 len（IM-03）→ 部分 |
| FR-33 | GWT-33.5 分页有货 | TC-33.5 | 集成 | ✅ | `test_skill_public_api.py:254`；`test_b1c_capabilities_coverage.py:812` |
| FR-34 | GWT-34.1 正常 | TC-34.1 | 集成 | ✅ | `test_t25_subscribe.py:57`；`SubscribeModal.test.tsx:80` |
| FR-34 | GWT-34.2 空态 | TC-34.2 | 集成 | ✅ | `test_t25_subscribe.py:78` |
| FR-34 | GWT-34.3 越权只读 | TC-34.3 | 集成 | ✅ | `:90` |
| FR-34 | GWT-34.4 越权超管 | TC-34.4 | 集成 | ✅ | `:99` |
| FR-34 | GWT-34.5 边界 | TC-34.5 | 集成 | ✅ | `:109` |
| FR-34 | GWT-34.6 幂等 | TC-34.6 | 集成 | ✅ | `:125`；`SubscribeModal.test.tsx:96` |
| FR-34 | GWT-34.7 宿主 | TC-34.7 | 集成 | ✅ | `:137`；`SubscribeModal.test.tsx:69` |
| FR-34 | GWT-34.8 礼包 | TC-34.8 | 集成 | ✅ | `:151` |
| FR-34 | GWT-34.9 未声明 | TC-34.9 | 集成 | ✅ | `:167`。MYSQL_FIDELITY `test_gwt_34_9_undeclared_host_compat_allows_any` 预发方言批 22 passed（`qc-cond-2-preprod.md` §1.1） |
| FR-34 | GWT-34.10 零项 | TC-34.10 | 集成 | ✅ | `:182`；`SubscribeModal.test.tsx:55` 四 Radio 全禁用 |
| FR-34 | GWT-34.11 配额 | TC-34.11 | 集成 | ✅ | `:194` |
| FR-34 | GWT-34.12 D25 | TC-34.12 | 集成 | ✅ | `:240` |
| FR-34 | GWT-34.13 D25 越权 | TC-34.13 | 集成 | ✅ | `:276` |
| FR-35 | GWT-35.1 正常 | TC-35.1 | 集成 | ✅ | `test_t26_installs.py:81` / `:98` 生产经办形；`MyInstalls.test.tsx:70` |
| FR-35 | GWT-35.2 空态 | TC-35.2 | 集成 | ✅ | `test_t26_installs.py:114`；`MyInstalls.test.tsx:85` |
| FR-35 | GWT-35.3 下架残留 | TC-35.3 | 集成 | ✅ | `test_t26_installs.py:126`；`MyInstalls.test.tsx:94` |
| FR-35 | GWT-35.4 只读可卸 | TC-35.4 | 集成 | ✅ | `:148` / `:246`；`MyInstalls.test.tsx:112` |
| FR-35 | GWT-35.7 卸黑名单 | TC-35.7 | 集成 | ✅ | `:170`；`MyInstalls.test.tsx:134` |
| FR-35 | GWT-35.5 只读角色 | TC-35.5 | 集成 | ✅ | `:188`；`MyInstalls.test.tsx:154` |
| FR-35 | GWT-35.6 礼包反向 | TC-35.6 | 集成 | ✅ | `:221`；`MyInstalls.test.tsx:175` |
| FR-36 | GWT-36.1 正常 | TC-36.1 | 集成 | ⚠️ | `test_t27_references.py:40`。IM-18：礼包合集边未挂对照 |
| FR-36 | GWT-36.2 边界 | TC-36.2 | 集成 | ✅ | `test_t27_references.py:70` skip+审计 |
| FR-36 | GWT-36.3 越权 | TC-36.3 | 集成 | ✅ | `test_t27_references.py:109` 商店 32.3 同句 |
| FR-37 | GWT-37.1 正常 | TC-37.1 | 单元 | ✅ | `Capabilities.governance.test.tsx:85` 七叶 |
| FR-37 | GWT-37.2 空态 | TC-37.2 | 单元 | ✅ | `:95` 命令空态非 git 路径 |
| FR-37 | GWT-37.3 越权 | TC-37.3 | 集成 | ✅ | `test_t28_listing.py:70` / `:83`；治理 UI `:104` |
| FR-37 | GWT-37.4 边界 | TC-37.4 | 集成 | ✅ | `test_t28_listing.py:95`；UI `:112` |
| FR-37 | GWT-37.5 禁止 | TC-37.5 | 单元 | ✅ | `Capabilities.governance.test.tsx:132` |
| FR-37 | GWT-37.6 listed_at | TC-37.6 | 集成 | ✅ | `test_t28_listing.py:114` unlist 保留 `listed_at`。MYSQL_FIDELITY=1 同 node **1 passed in 1.86s** exit 0（`qc-cond-2-preprod.md` §1.1）；039 DATETIME(6)。IM-17 短名未进本格 |
| FR-38 | GWT-38.1 正常 | TC-38.1 | 集成 | ✅ | `test_t29_sources.py:143` |
| FR-38 | GWT-38.2 部分失败 | TC-38.2 | 集成 | ✅ | `:189` |
| FR-38 | GWT-38.3 越权 | TC-38.3 | 集成 | ✅ | `:111` |
| FR-38 | GWT-38.4 边界 | TC-38.4 | 集成 | ✅ | `:128` |
| FR-38 | GWT-38.5 D16 | TC-38.5 | 集成 | ✅ | `:214` / `:236` |
| FR-38 | GWT-38.6 D5 | TC-38.6 | 集成 | ✅ | `:255` category 字节不变（IM-22 已钉 409） |
| FR-38 | GWT-38.7 D5 越权 | TC-38.7 | 集成 | ✅ | `:279` |
| FR-39 | GWT-39.1 正常 | TC-39.1 | 集成 | ✅ | `test_t30_command_cards.py:97`；`CommandCards.test.tsx:63`；`CapabilityDetail.test.tsx:173` |
| FR-39 | GWT-39.2 空态 | TC-39.2 | 集成 | ✅ | `test_t30_command_cards.py:127`；`CommandCards.test.tsx:76` |
| FR-39 | GWT-39.3 越权 | TC-39.3 | 集成 | ✅ | `test_t30_command_cards.py:151` 未上架 slash 公开搜空。IM-24 旧注「同步不写 command 行」过时：`test_t29_sources.py:480` `test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug` 钉 plugin.json commands → `asset_type=command`、slug=`{plugin}__{origin_local_name}`、`listing_state=unlisted`。删除源文件不收回 = C35-QA-04 minor，不发明 FR |
| FR-40 | GWT-40.1 正常 | TC-40.1 | 集成 | ✅ | `test_t28_listing.py:138`；`test_plugin_verify_no_mcp_unknown` `:251`（作废 degraded 金标） |
| FR-40 | GWT-40.2 边界 | TC-40.2 | 单元 | ✅ | `test_t26_installs.py` 40.2 copy；`MyInstalls.test.tsx:189`；治理 `:184` |
| FR-40 | GWT-40.3 越权 | TC-40.3 | 集成 | ✅ | `test_t28_listing.py:155`；治理 `:208` |
| FR-41 | GWT-41.1 正常 | TC-41.1 | 集成 | ✅ | `test_t29_sources.py:299` |
| FR-41 | GWT-41.2 空态 | TC-41.2 | 集成 | ✅ | `:324` |
| FR-41 | GWT-41.3 越权 | TC-41.3 | 集成 | ✅ | `:341` |
| FR-41 | GWT-41.4 边界 | TC-41.4 | 集成 | ✅ | `:358` attach 不自动 listed |
| FR-42 | GWT-42.1 正常 | TC-42.1 | 集成 | ✅ | `test_t31_license.py:76` |
| FR-42 | GWT-42.2 边界 | TC-42.2 | 集成 | ✅ | `:97` override=1。MYSQL_FIDELITY `test_gwt_42_2_override_appears_still_gated` 预发方言批 PASS。IM-05 TINYINT 方言债已过真库 |
| FR-42 | GWT-42.3 越权 | TC-42.3 | 集成 | ✅ | `:120` |
| FR-42 | GWT-42.4 已订 | TC-42.4 | 集成 | ✅ | `:138` |
| FR-42 | GWT-42.5 解析 | TC-42.5 | 集成 | ✅ | `:177` |
| FR-42 | GWT-42.6 越权跨租户 | TC-42.6 | 集成 | ✅ | `:195` |
| FR-43 | GWT-43.1 正常订 | TC-43.1 | 集成 | ✅ | `test_t32_market_events.py:86` |
| FR-43 | GWT-43.2 空态拒 | TC-43.2 | 集成 | ✅ | `:96` reason=`coming_soon` |
| FR-43 | GWT-43.3 越权 | TC-43.3 | 集成 | ✅ | `:108`；`App.test.tsx:34` / `:50` |
| FR-43 | GWT-43.4 列表 | TC-43.4 | 集成 | ✅ | `:116` |
| FR-43 | GWT-43.5 搜索 | TC-43.5 | 集成 | ✅ | `:129` |
| FR-43 | GWT-43.6 详情 | TC-43.6 | 集成 | ✅ | `:142` |
| FR-43 | GWT-43.7 卸载 | TC-43.7 | 集成 | ✅ | `:157` |
| FR-43 | GWT-43.8 上架变更 | TC-43.8 | 集成 | ✅ | `:170` |
| FR-43 | GWT-43.9 同步 | TC-43.9 | 集成 | ✅ | `:188` |
| FR-43 | GWT-43.10 过滤 | TC-43.10 | 集成 | ✅ | `:218` |
| FR-44 | GWT-44.1 正常 | TC-44.1 | 集成 | ✅ | `test_b1c_capabilities_coverage.py:582` |
| FR-44 | GWT-44.2 非法 | TC-44.2 | 集成 | ✅ | `:558` / `:571`；`SkillsSquare.test.tsx:41`。作废 falls_back_skill |
| FR-44 | GWT-44.3 空态 | TC-44.3 | 集成 | ✅ | `:593` |
| FR-44 | GWT-44.4 越权 | TC-44.4 | 集成 | ✅ | `:623` 五类枚举 |
| FR-45 | GWT-45.1 正常 | TC-45.1 | 集成 | ✅ | `test_t33_aliases.py:103` |
| FR-45 | GWT-45.2 空态 | TC-45.2 | 集成 | ✅ | `:116` |
| FR-45 | GWT-45.3 越权 | TC-45.3 | 集成 | ✅ | `:126` |
| FR-45 | GWT-45.4 冲突 | TC-45.4 | 集成 | ✅ | `:150` / `:174`。MYSQL_FIDELITY `test_gwt_45_4_conflict_live_alias_both_unchanged` 预发方言批 PASS |
| FR-45 | GWT-45.5 同步 | TC-45.5 | 集成 | ⚠️ | `:199` 零新建。IM-26：HTTP 夹具未钉同步出数 |

### 1.4 Wave 2/3 stub（不施工）

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| FR-50 | GWT-50.1…50.3 | — | — | ➖ **N/A** | Wave 2/3 未施工。满额 CTA 不到注册已由 GWT-12.6/12.7 覆盖，不顶 FR-50 支付出口 |
| FR-51 | GWT-51.1…51.3 | — | — | ➖ **N/A** | Wave 2/3 未施工。未绑定拒绝已由 FR-13 覆盖 |
| FR-60 | GWT-60.1…60.3 | — | — | ➖ **N/A** | Wave 2/3 未施工。Q-RELAY 未关前无租户渠道组屏；与 72.3/01.2 重叠句不顶本 stub |
| FR-61 | GWT-61.1…61.3 | — | — | ➖ **N/A** | Wave 2/3 未施工。不熔断已由 GWT-07.6 覆盖 |

### 1.5 六问（本矩阵不代选）

| 问 | 状态 | 理由 |
|---|---|---|
| Q-VOICE | ➖ **N/A** | 六问未关，本矩阵不代选；不测对外第一句 |
| Q-PRICE | ➖ **N/A** | 只测「未履约不得当前可买」（01.12/05.2），不测支付形态 |
| Q-RELAY | ➖ **N/A** | 只测「无我的渠道组/令牌」（70.4/72.3），不测租户 SKU |
| Q-MARKET-USER | ➖ **N/A** | 不测市场主用户人格 |
| Q-BILL | ➖ **N/A** | 不测在线扣款；FR-50 stub |
| Q-AGPL | ➖ **N/A** | 不撰写对外收费故事 |

state.yaml 另有 Q-OPS-DUTY / Q-OPS-COLLECT：同样不代选、不进本冻结施工集。

### 1.6 NFR

| FR/NFR | GWT | 用例 ID | 层 | 状态 | 备注 |
|---|---|---|---|---|---|
| NFR-01 性能 | — | TC-N01 | 专项 | ✅ | `06-deliver/qc-cond-2-preprod.md` §3.3：Chrome 152 headless `http://127.0.0.1:9113/capabilities` 20 次均 20 张 `.capability-market__card`、首卡 `NFR卡片399`；P95 **1.444558s &lt; 2s**。**不是** TestClient，也**不是** API P95 0.020s。一次性预发；playwright-core 在 `/tmp`，未进仓库 CI。`test_b1c_capabilities_coverage.py:835` TestClient **不顶本格** |
| NFR-02 容量 | — | TC-N02 | 集成 | ✅ | 导出 100：GWT-03.3。列表分页：GWT-33.4/33.5。禁止用 33.4 证明没拉全表 |
| NFR-03 可用性 | — | TC-N03 | 集成 | ✅ | 01.4 / 31.4 / 15.2 / 18.2 / 74.x 分格 |
| NFR-04 安全 | — | TC-N04 | 集成 | ✅ | FR-14/75 路径密钥；13.2 未绑定；32.4 纯文本；40.2 listed≠宿主运行 |
| NFR-05 权限 | — | TC-N05 | 集成 | ✅ | 见 §4；17.2 空缓存 |
| NFR-06 合规 | — | TC-N06 | 集成 | ✅ | FR-42 许可闸；72 退役不再绑 new-api AGPL 运行时。对外收费 ➖ Q-AGPL。准确率禁句 01.6 |
| NFR-07 兼容 | — | TC-N07 | 单元 | ✅ | GWT-30.2 `/skills`、30.4 expert 映射已测。触摸 ≥44px：`Home.test.tsx:76` / `Pricing.test.tsx:70` / `Register.test.tsx:192` `assertTouchTarget` `toBeGreaterThanOrEqual(44)`。本帽 Jest 4 passed exit 0。量的是 minHeight/minWidth 令牌（`--size-touch` / 44px），非 Chrome 布局实验室 |
| NFR-08 可观测 | — | TC-N08 | 集成 | ✅ | FR-15/43 仅超管查询；15.3/43.3 租户 404 |
| NFR-09 国际化 | — | — | — | ➖ **N/A** | spec：本轮仅中文 |
| NFR-10 可维护 | — | TC-N10 | 单元 | ✅ | FR-14/75 配置离树；T-14 根编排无 litellm；市场总开关 D16 GWT-38.5 |

---

## 2. 反向：用例 → FR/NFR

> 主映射按票。无直接 FR 的技术夹具见下表处理。

| 用例 ID | 名称 | 对应 FR/NFR | 层 |
|---|---|---|---|
| TC-01.* | official Home/Pricing/Features Jest + admin Usage 01.1 | FR-01/02/05/70.4 | 单元 |
| TC-03.* | `test_spider_task_flow` 导出 | FR-03 | 集成 |
| TC-04.* | Register/Login + signup_expiry | FR-04 | 单元/集成 |
| TC-06.* | b1c scan/verify + llm_platform_row_writes | FR-06/20 | 集成 |
| TC-07.* | usePermission/App/ProtectedRoute/Dashboard + probe | FR-07/17 | 单元/集成 |
| TC-08.* | signup_expiry 到期 | FR-08 | 集成 |
| TC-09/10.* | saas_wiring + task_consumer | FR-09/10 | 集成 |
| TC-11.* | skill_candidates + datacenter | FR-11 | 集成 |
| TC-12.* | saas_quota + Usage Jest | FR-12/74.3 | 集成 |
| TC-13.* | external_api | FR-13 | 集成 |
| TC-14.* | fr14_secrets_off_tree + TestMask | FR-14/75 | 单元 |
| TC-15.* | product_events + beacon | FR-15 | 集成 |
| TC-16.* | llm_usage_service / stats | FR-16 | 单元 |
| TC-18.* | 18.1 live Then ✅（+40.6s completed / 40.56s ≤ 120s；idle 30 ≠ 18.4 窗 120）；18.2+ worker_offline / FakeRedis 不顶 18.1 | FR-18 | 专项/集成 |
| TC-19.* | spider_zero_items | FR-19 | 集成 |
| TC-70.* | llm_four_actions_http + similar_suggest | FR-70/74 | 集成 |
| TC-71.* | newapi_api + NewApiOps.test | FR-71 | 集成 |
| TC-72.* | t20_retire_newapi | FR-72 | 单元 |
| TC-73.* | fr73_byok_four_actions_http | FR-73 | 集成 |
| TC-30/44 | b1c 五类 + SkillsSquare | FR-30/44 | 集成 |
| TC-31 | Capabilities.test + t22_list_filters | FR-31 | 单元/集成 |
| TC-32 | skill_public_api + CapabilityDetail | FR-32/33 | 集成 |
| TC-34 | t25_subscribe + SubscribeModal | FR-34 | 集成 |
| TC-35 | t26_installs + MyInstalls | FR-35 | 集成 |
| TC-36 | t27_references | FR-36 | 集成 |
| TC-37/40 | t28_listing + governance Jest | FR-37/40 | 集成 |
| TC-38/41 | t29_sources | FR-38/41 | 集成 |
| TC-39 | t30_command_cards | FR-39 | 集成 |
| TC-42 | t31_license | FR-42 | 集成 |
| TC-43 | t32_market_events | FR-43 | 集成 |
| TC-45 | t33_aliases | FR-45 | 集成 |
| TC-N01 | qc-cond-2-preprod.md §3.3 Chrome 卡片可见 P95（TestClient 不顶） | NFR-01 | 专项 |
| TC-N07 | Home/Pricing/Register Jest `assertTouchTarget` ≥44px | NFR-07 | 单元 |

**无直接 FR 的用例处理**

| 用例 | 处理 |
|---|---|
| `test_saas_isolation` 豁免表夹具 | PIT-3 / NFR-05 租户过滤，非产品 GWT |
| `test_arch_sh_has_verbatim_b4_greps` | NFR-10 / B4 架构，非 GWT |
| `test_saas_wiring.py` 原 `:55` `or True` | **已关**：配额拒绝断言 `QUOTA_EXCEEDED` + 用户可见句（见 §5） |
| `test_saas_byok.py` 原 `:45` `or True` | **已关**：括号化 `provider:{id}` + 可见名互不可见（见 §5） |
| `test_llm_cooldown.py::test_nfr01_redis_failure_fail_open` | 旧 LLM 冷却 NFR 编号，**不是**本 spec NFR-01 |

---

## 3. 状态流转覆盖

### 3.1 上架 `listing_state`

| 状态＼操作 | 超管 listed | 超管 coming_soon | 超管 unlisted | 同步自动 listed | 租户改上架 |
|---|---|---|---|---|---|
| unlisted | ✅ TC-37.6 / 40.1 | ✅ 预告夹具 32.2/33.2 | — 已在 | ❌ 非法 TC-38.1/41.4 | ❌ 非法 TC-37.3 |
| listed | — 幂等未单测 | ✅ 预告路径（治理 UI） | ✅ TC-37.6 listed_at 保留 | — | ❌ TC-37.3 |
| coming_soon | ✅ 33.1 可上架后可订 | — | ✅ 商店消失（32.2 拒订） | — | ❌ TC-37.3 |
| blacklist | ❌ 拒存 `test_blacklist_cannot_list` `test_t28_listing.py:185` | ❌ | — | — | ❌ |

非法三项：状态未变 ✅；记录 leftover 仅 06.3/37.3 HTTP 403；副作用商店不变 ✅。

空格子：listed→coming_soon 无独立 HTTP 名（UI 有预告控件，后端 PATCH 枚举未单列）。记 ⚠️ 非硬缺口。

### 3.2 安装行

| 状态＼操作 | 订 Grok | 再订 Claude | 再订 Grok | 卸 | 改启用/信任 |
|---|---|---|---|---|---|
| 无行 | ✅ 34.1 | — | — | — | — |
| 已订 | ❌ 预告 34.2 / 未上架 32.8 | ✅ 34.5 | ✅ 34.6 幂等 | ✅ 35.1 | 只读角色 ❌ 35.5 |
| unlist 残留 | ❌ 再订禁用 35.3 | — | — | ✅ 35.3 | 锁 35.4 |
| 黑名单/软删行 | ❌ 新订 32.8 | — | — | ✅ 35.7 经办可卸 | ❌ 35.4 锁 |

### 3.3 企业 / 任务

| 流转 | 用例 | 状态 |
|---|---|---|
| active→expired 登录拒 | TC-08.1 | ✅ |
| 已颁会话写拒 | TC-08.2 | ✅ |
| pending/running→completed 有条 | TC-18.1 | ✅ live +40.6s `completed` `result_count=1`；export 200 rows 1；40.56s ≤ 120s（FakeRedis 不顶） |
| →completed 0 条 | TC-19.1 | ✅ |
| 无工人不装正在爬 | TC-18.2 | ✅ |
| 无主入队拒绝 | TC-09.4 | ✅ |
| 无主回流不写结果 | TC-10.4 | ✅ |

---

## 4. 权限矩阵覆盖

| 角色＼操作 | 逛商店 | 订阅 | 卸载 | 扫描/验证 | 改平台模型 | 直打值班 | 查产品事实 |
|---|---|---|---|---|---|---|---|
| 匿名 | ✅ 31/33 | ❌ 32.6 401 | — | ❌ 401 scan | — | ✅ 07.3 404 | ❌ |
| 租户只读 | ✅ | ❌ 34.3 | ❌ 35.5 | ❌ 06.4 | ❌ | ✅ 07.3 | ❌ 15.3 |
| 租户经办 | ✅ | ✅ 34.1 | ✅ 35.1 | ❌ 20.3 | ❌ 70.3 | ✅ 07.3 | ❌ 15.3 |
| 租户负责人 | ✅ | ✅ | ✅ | ❌ | ❌ 06.6；本企业行 ✅ 06.5 | ✅ 07.3 | ❌ |
| 租户公司管理员 | ✅ | ✅ | ✅ | ❌ 06.3 leftover | ❌ | ✅ 07.3 同 404 | ❌ |
| 平台超管 | ✅ | ❌ 无企业 34.4 | — | ✅ 06.1 落库+审计 | ✅ 70.3 反面 | ✅ 71.1 | ✅ 15/43 |

三类越权：

- [x] ① 换角色 — 06.3/06.4/34.3/35.5/70.3
- [x] ② 换数据范围 — 03.4/09.3/10.3/42.6
- [x] ③ 直接调接口 — 全部 pytest HTTP，不靠隐藏按钮
- [x] ④ 跨租户 — 03.4/10.3/13.3/42.6/43.10

---

## 5. 空洞明细

### 本轮关闭（不再是硬 ❌）

| 格 | 关闭依据（读测试，非 changelog） |
|---|---|
| GWT-01.1 | `Usage.test.tsx:185` + `Pricing.test.tsx:71`：三句与页上数字对照、无预告。C35-QA-03 **已关**：`Register.test.tsx:177` 钉 `FREE_TIER_FEATURE_COPY` 三句、禁 `10000` |
| GWT-06.1 | `test_scan_plugins_ok` `:137` 查 OperationLog who/what；`test_audit_helpers.py:71` 不 commit 请求 session。verify 未另查 log，不把扫描格打回 ❌ |
| GWT-18.1 / TC-18.1 | live Then：idle close **30s** 后 `run.py restart spider`；+40.6s `completed` `result_count=1`；export **200 rows 1**；**40.56s ≤ 120s**。非 FakeRedis。18.4 窗仍 120 |
| NFR-07 | Home/Pricing/Register Jest `assertTouchTarget` ≥44px（4 passed exit 0） |
| wiring/byok 空心 | `or True` 已删除；`pytest` 两文件 14 passed exit 0 |

### ❌ 空心断言（非 GWT 主格）

| 项 | 内容 |
|---|---|
| 位置 | 原 `backend/tests/test_saas_wiring.py:55` `assert ... or True` |
| 现状 | **已关**。现断言 `QUOTA_EXCEEDED` +「任务并发」+ `PLAN_FULL_USER` / `PLAN_FULL_CTA`（约 `:55`） |
| 关系 | 仍不映射冻结 Then 主格；不再计入空洞 |
| 证据 | 本帽 `uv run pytest -q backend/tests/test_saas_wiring.py backend/tests/test_saas_byok.py` **14 passed** exit 0 |

| 项 | 内容 |
|---|---|
| 位置 | 原 `backend/tests/test_saas_byok.py:45` `"a-key" in cfg.source or True` |
| 现状 | **已关**。括号化：`cfg.source == f"provider:{a_id}"` + URL + 可见名互不可见 |
| 关系 | 仍不在冻结 GWT 主映射；不再计入空洞 |

### ⚠️ 需真实环境

| 用例 | 为什么 SQLite/本机测不出 | 状态 |
|---|---|---|
| TC-18.1 | FakeRedis ≠ 真 Worker；Then 要 120s 内**进入完成**且条数>0 | **本格 ✅**。live（`run.py restart spider`，非 FakeRedis）：tenant `qc181-1789008085`；task **#2** example+httpbin；+6.1s running `result_count=1`；**+40.6s completed result_count=1**；export JSON **200 rows 1**；elapsed **40.56s ≤ 120s**。Idle close **30 ≠** 18.4 窗 **120**。旧预发 +129s（idle 当时 120）作废。FakeRedis min_loop 不顶。未进仓库 CI |
| TC-N01 | TestClient 不得顶浏览器卡片可见 | **预发已过**：同文件 §3.3 Chrome P95 1.444558s。本格 ✅。`/tmp` playwright-core，未进仓库 CI |
| TC-37.6 | DATETIME 精度 | **预发已过**：MYSQL_FIDELITY 1 passed in 1.86s；039 DATETIME(6)。本格 ✅ |
| TC-34.9 / 42.2 / 45.4 | JSON/TINYINT/NULL 唯一 | **预发已过**：方言批 22 passed。本格 ✅ |
| TC-33.4 | 能力端未钉 `len(items)==page_size`（IM-03）；技能端真库已跑 | 仍 ⚠️ 部分（IM-03） |
| TC-16.1 | 时区 / DATE 语义 | 仍 ⚠️；本轮方言批未含该 node |
| TC-13.3 | SQL 绑 tenant | 备注 ⚠️；主格仍 ✅（HTTP 跨租户） |
| Alembic 037/038/039 | skip unless MYSQL_FIDELITY=1 | 空库 upgrade head 039 已过；`downgrade base` 仍 1553 |
| NFR-07 触摸 ≥44px | 曾无 Jest 量宽 | **本格 ✅**：`Home.test.tsx:76` / `Pricing.test.tsx:70` / `Register.test.tsx:192`。jsdom 令牌量宽，非 Chrome 实验室 |

转 `/sre` 残余：GWT-18.1 live Then **已过**（+40.6s / 40.56s；idle 30 ≠ 18.4 窗 120）；NFR-07 44px **已过** Jest。仍余：16.1 时区；条件 2 一次性证据未入库 CI。dockerd sock / 机外轮换不在本矩阵。

### ⚠️ 实现帽未关闭 minor（不扩 Wave 2/3）

| id | 影响格 | 处理 |
|---|---|---|
| IM-02 | 32.3 | 常量 HTML 对照；保留真 404 字节链，不升 ❌ |
| IM-03 | 33.4 能力端 | 技能端已钉 len=20；能力端未钉 → 部分 |
| IM-04 | 33.2 | override 改走 42.2 |
| IM-05 | 42.2 | 方言债 MYSQL_FIDELITY 已过；本格 ✅ |
| IM-12 | 订阅弹窗离线 | edge-states 离线句未用冻结文案 |
| IM-13 | CTA `from` | 负向未解码 |
| IM-17 | 37 治理 | 「在目录中打开」丢短名（不挡 37.6） |
| IM-18 | 36.1 | 礼包合集边未挂 |
| IM-19 | 37 | 治理叶无分页 |
| IM-24 | 39.3 / src_sync 命令 | **过时「同步不写 command 行」**。现：`test_t29_sources.py:480` 写 unlisted command + ADR-0012 slug。GWT-39.3 公开搜仍空。删除源文件不收回 = C35-QA-04 minor，不发明 FR |
| IM-26 | 45.5 | 同步 HTTP 未钉出数 |

### 需真库验证清单（方言）

| 用例 | 为什么 SQLite 测不出 | 状态 |
|---|---|---|
| TC-33.4/33.5 | LIMIT/OFFSET + 查询侧闸 vs 内存滤 | 技能端 MYSQL_FIDELITY 已跑（方言批含 `test_skill_public_api.py`）。能力端 IM-03 未钉 len |
| TC-34.9 | `host_compat` NULL vs `[]` JSON | 已执行 PASS（方言批） |
| TC-42.2 | override TINYINT vs SmallInteger | 已执行 PASS（方言批） |
| TC-45.4 | 存活 alias 唯一 + NULL | 已执行 PASS（方言批） |
| TC-37.6 | datetime 精度 / listed_at | 已执行 PASS：1 passed in 1.86s；039 DATETIME(6) |
| ESC-2 回归 | NULLS LAST 编译 | 方言批含 `test_null_aware_sort_roundtrip_mysql_fidelity` PASS |

---

## 6. 裁剪声明

| 项 | 策略 | 说明 |
|---|---|---|
| 参数组合 | **pairwise / 分格** | 四动作 ×（网关成功/无模型/不可达/满额/BYOK）禁止 `or_cell_failure` 一名三格；T-16/T-17 已分 node |
| 等价类 | 每类一代表 | listing 三态；五类资产用技能代表 + 命令独立 FR-39 |
| E2E | 仅主干 | 仓库无独立 E2E 套件（state.yaml e2e=null）。浏览器路径用 Jest RTL + HTTP 集成代替 |
| 六问 | 裁掉正向 CTA 人格/支付 | 只留「不得写成当前可买 / 不得发令牌」 |
| Wave 2/3 | 整段不测 | 「Wave 2/3 未施工」 |

---

## 7. edge-states 对屏

> 设计六态是异常态唯一来源。空格子 = 该屏该态无自动化。

| 屏 | 加载 | 空 | 错误 | 权限 | 边界 | 离线 |
|---|---|---|---|---|---|---|
| 官网首页 | ✅ Home | ✅ 无假统计 | ✅ 01.4 | ✅ 匿名 | ✅ 无规模数字 | ⚠️ 失败句兼离线 |
| 定价 | ✅ | ➖静态 | ✅ mailto | ✅ | ✅ 闭集 B | ⚠️ 无独立离线测 |
| 企业注册 | ✅ | ➖表单 | ✅ 04.2 | ✅ 04.4 | ✅ 空书名号 | ✅ Register offline |
| 注册成功 | ➖ | ➖ | ➖ | ✅ | ✅ 次钮 | ⚠️ 跳登录 |
| 能力市场列表 | ✅ 31 | ✅ 31.2/31.3 | ✅ 31.4 | ✅ 31.6 | ✅ 预告 | ⚠️ 失败句兼 |
| 能力市场详情 | ✅ | ➖404 | ✅ 加载失败 | ✅ 登录后订阅 | ✅ XSS/出处 | ⚠️ IM-12 弹窗离线 |
| 官网 404 | ➖ | ➖ | ➖ | ✅ 32.3 | ✅ 字节同形 | ➖ |
| 后台登录 | ✅ | ➖ | ✅ 到期≠密码 | ✅ | ✅ from | ⚠️ |
| 后台壳 | ✅ 17.2 | ➖ | ✅ 失败保留读叶 | ✅ 07.2 | ✅ | ⚠️ 同失败 |
| 仪表盘 | ⚠️ smoke | ⚠️ | ⚠️ | ✅ 07.5 | ✅ 不到中转 | ⚠️ |
| 用量看板 | ✅ | ✅ 16.3 | ✅ 网关≠配额 | ✅ 12.4 | ✅ 将满/满 | ⚠️ |
| 成员管理 | ✅ smoke | ⚠️ | ⚠️ | ⚠️ owner 列表 | ⚠️ | ❌ 无离线 |
| 采集任务 | ⚠️ 18.2 文案 | ✅ | ⚠️ | ✅ 18.3 | ✅ 18.4 | ✅ Spiders offline |
| 导出/结果 | ✅ 03 | ✅ 03.2 | ⚠️ | ✅ 03.4 | ✅ 100 条 | ⚠️ |
| 数据中心 | ⚠️ 后端 11.2 | ✅ | ⚠️ | ⚠️ | ⚠️ | ❌ |
| 节点监控 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ 无冻结 GWT 专屏测 |
| 运行日志 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| AI 采集规划 | ✅ 70 HTTP | ✅ 70.2 | ✅ 74.1 | ✅ 只读 403 | ✅ 满额 74.2 | ⚠️ |
| LLM 配置 | ✅ 73.4 | ⚠️ | ⚠️ | ✅ 06.5/06.6 | ✅ 测试连接 | ⚠️ |
| 值班 /newapi | ✅ 71.1 | ✅ 71.2 | ✅ 71.3 | ✅ 71.4 | ✅ 无 Key | ⚠️ 降级兼 |
| 治理台七叶 | ✅ 37 | ✅ 37.2 | ⚠️ | ✅ 37.3 | ✅ 37.4/37.6 | ⚠️ IM-19 分页 |
| 我的安装 | ✅ 35 | ✅ 35.2 | ⚠️ | ✅ 35.5 | ✅ unlist/黑名单 | ⚠️ |
| 订阅弹窗 | ✅ | ➖宿主 | ✅ code 分支 | ✅ | ✅ 四宿主 | ⚠️ IM-12 |
| 平台运营台 | ✅ 15 超管 | ⚠️ | ⚠️ | ✅ 15.3 404 | ✅ 15.13 | ⚠️ |
| 系统设置 | ⚠️ 14.4 掩码 | ⚠️ | ⚠️ | ⚠️ | ⚠️ 掩码 | ❌ |
| 后台 404 | ➖ | ➖ | ➖ | ✅ 07.3 | ✅ | ➖ |

节点监控 / 运行日志：edge-states 有屏，冻结 FR 无独立 GWT。记六态未测，**不**发明 FR。

---

## 8. 覆盖统计

| 项 | 数量 |
|---|---|
| 冻结 FR 总数 / 有行 | 42 / 42（01–20=20，70–75=6，30–45=16） |
| stub FR ➖ | 4（50/51/60/61） |
| NFR 总数 / 已覆盖 / N/A | 10 / 8 ✅ / 1（NFR-09）；NFR-07 44px Jest ✅；NFR-01 预发浏览器 ✅ |
| 冻结 GWT 有行 | 241（spec 表内冻结格，含 37.6 一次） |
| 缺口 ❌ | **0 条冻结 GWT**；wiring/byok `or True` 已关（不再计入空洞） |
| 需真实环境 ⚠️ | 16.1 时区；IM-02/03/18/26；若干六态。**GWT-18.1 live Then 已过**（+40.6s / 40.56s）。37.6 / NFR-01 预发已过 |
| Wave 2/3 GWT ➖ | 12 |
| 六问 ➖ | 6 |
| 用例层（约） | 单元 Jest 为主干文案；集成 pytest 为契约；E2E=0；专项=NFR-01 浏览器 + 18.1 live（18.1 ✅） |
| 状态流转空格 | listed→coming_soon 无独立 HTTP 名 |
| 权限格子 | 上表无空；三类越权+跨租户齐全 |

**覆盖率数字不作为质量结论。** 原空心 `or True` 已去掉。01.1 / 06.1 不再是硬 ❌。GWT-18.1 现 live Then ✅。

---

## 9. 给下游

| 给谁 | 内容 |
|---|---|
| `/backend` | wiring/byok `or True` **已关**（14 passed）。仍余：33.4 能力端 `len(items)==page_size`（IM-03）；C35-QA-04 源侧删除命令是否收回 |
| `/frontend` | C35-QA-03 Register copy **已关**；NFR-07 44px **已关**。仍余 IM-12/13/17 |
| `/sre` | 条件 2：37.6 / NFR-01 预发已过。**GWT-18.1 live Then ✅**：+40.6s completed / export 200 rows 1 / 40.56s ≤ 120s。Idle close **30 ≠** 18.4 窗 **120**。残余：16.1 时区；一次性证据未入库 CI；dockerd / 机外轮换不在本矩阵 |
| `/qc` | 本文件；01.1 / 06.1 / NFR-01 / 37.6 / **TC-18.1 / GWT-18.1 / NFR-07** ✅。FR-50/51/60/61 仍 ➖。**不要**把 T-33 PASS 当覆盖完成，也**不要**当四柱 GA。**不要**把 18.4 窗改成 30 |
| `/pm` | 六问仍开放；不代选。Wave 2/3 仍 stub。本帽**不改** GWT：Then 仍「120 秒内进入完成」；产品 idle close 30 使 live 落入该窗。18.4 标注仍 120s |

---

## 10. 自检

- [x] 每条冻结 FR/NFR 都有一行，无留空
- [x] Wave 2/3 与六问 ➖ 有理由
- [x] 每个主用例能反向指回 FR/NFR
- [x] 状态流转无完全空白的必测非法格
- [x] 权限矩阵无空格，四类越权齐全
- [x] 每个 ❌ / ⚠️ 在 §5 展开
- [x] 裁剪策略已声明
- [x] 需真库清单已列
- [x] 未把 changelog「已关闭」当覆盖
- [x] 空心 `or True`（wiring + byok）本轮已关，不再记洞
- [x] 未改 GWT、未修产品、未写 release-opinion.md
- [x] 01.8 / 01.6 / 73.4 有 Then 断言才标 ✅；01.1 / 06.1 本轮 Then 已钉故翻 ✅（不再是两个硬 ❌）
- [x] 未把 T-xx 证据当覆盖；NFR-07 现有 Jest ≥44px → ✅；NFR-01 未用 TestClient 盖章
- [x] FR-50/51/60/61 与六问保持 ➖；未答六问；未标 Wave 2/3 已覆盖
- [x] GWT-18.1 / TC-18.1 **✅** 仅因 live Then：completed ≤120s 且 count>0（+40.6s / result_count=1 / 40.56s）。未把 FakeRedis 或旧 +129s 当完成。18.4 窗仍 120s。未改产品 / GWT

---

## 11. 本轮返工自测（CV-01…08）

锁 Then 的用例（非产品补丁）。命令 + 退出码：

```
$ npm test --prefix frontend/official -- --runInBand --testPathPattern='Home.test|FeaturesSection.test|Pricing.test'
Test Suites: 3 passed, 3 total
Tests:       17 passed, 17 total
```

exit code 0

```
$ npm test --prefix frontend/admin -- --runInBand --testPathPattern='LlmProviders.test'
Test Suites: 1 passed, 1 total
Tests:       4 passed, 4 total
```

exit code 0

| CV | 处置 |
|---|---|
| CV-01 / 01.8 | 补 `Home.test.tsx:67` 三词 + 无预告邻接 |
| CV-02 / 01.6 | 补三 node `test_no_accuracy_or_certification_copy` |
| CV-03 / 73.4 | 补 `LlmProviders.test.tsx:120` 点击 + `testLlmProvider(1)` + 本企业失败句 |
| CV-04 | 01.3/02.3/01.10/05.3/12.6/12.7 改为 file:line，去掉 T-xx |
| CV-05 | NFR-07 当时整行 ⚠️（无量宽）；现 §14 Jest ≥44px ✅ |
| CV-06 | 07.1 引 `NewApiOps.test.tsx:88` / `:63` |
| CV-07 | §5 补 `test_saas_byok.py:45` |
| CV-08 | 01.2 四项各自行内「预告」Tag |

---

## 12. 本轮条件 2–6 续（独立读测试）

锁 Then 的用例（非产品补丁）。命令 + 退出码：

```
$ npm test --prefix frontend/admin -- --runInBand --testPathPattern='Usage.test' --testNamePattern='FREE_TIER_FEATURE_COPY'
PASS src/pages/Usage.test.tsx
Tests:       5 skipped, 1 passed, 6 total
```

exit code 0

```
$ npm test --prefix frontend/official -- --runInBand --testPathPattern='Pricing.test' --testNamePattern='closed-set B'
PASS src/pages/Pricing.test.tsx
Tests:       6 skipped, 1 passed, 7 total
```

exit code 0

```
$ uv run pytest -q \
    backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_ok \
    backend/tests/test_audit_helpers.py \
    backend/tests/test_t29_sources.py::test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug
......
6 passed in 1.91s
```

exit code 0

预发三项（**本节当时**；旧 18.1 +129s 已被 §14 live 取代）：MYSQL_FIDELITY 37.6 1 passed in 1.86s exit 0；方言批 22 passed in 17.79s exit 0；当时 18.1 live item +5s / export 200 成立、completed +129s **不满足** Then（IdleAutoClose 当时 120）；NFR-01 Chrome P95 1.444558s exit 0。

| 格 | 处置 |
|---|---|
| TC-01.1 | ❌→✅ `Usage.test.tsx:185` + `Pricing.test.tsx:71`（保持） |
| TC-06.1 | ❌→✅ `test_b1c_capabilities_coverage.py:137` + `test_audit_helpers.py:71`（保持） |
| TC-18.1 | 当时 ✅→⚠️ CV-09 / QA-01（+129s）；**现 §14 ⚠️→✅** live +40.6s / 40.56s |
| TC-37.6 | ⚠️→✅ MYSQL_FIDELITY 1.86s（保持） |
| TC-34.9 / 42.2 / 45.4 | ⚠️→✅ 方言批（保持） |
| TC-N01 | ⚠️→✅ 预发 Chrome §3.3；**禁止** TestClient（保持） |
| IM-24 | 更新：src_sync 写 unlisted command；不发明 FR |
| NFR-07 | 当时保持 ⚠️；**现 §14 ✅** Jest ≥44px |
| wiring:55 / byok:45 | 当时空洞；**现 §14 已关** |
| FR-50/51/60/61 · 六问 | 保持 ➖ |

---

## 13. Debug record（CV-09 / QA-01 · verify rework round 2+）

### Reproduce

G-fresh FAIL `05-review/findings.md` QA-01：主格 GWT-18.1 / TC-18.1 标 ✅，但 live completed 是 +129s。Then（`01-define/spec.md:513`）是「120 秒内任务进入完成且条数>0」。

```
$ python3 -c "
from pathlib import Path
c=Path('04-verify/coverage.md').read_text()
print('GWT-18.1 row has checkmark:', any('GWT-18.1' in l and '✅' in l for l in c.splitlines()))
"
```

修前：`GWT-18.1 row has checkmark: True`（主格 line 142 状态列 ✅；§5「本格 ✅」）。exit 0。对照 `qc-cond-2-preprod.md` §2：item +5s `result_count=1` **仍 running**；webhook completed **+129s**。

### Isolate

| 假设 | 探针 | 结果 |
|---|---|---|
| FakeRedis min_loop 被当覆盖 | coverage 已写 `test_spider_min_loop.py:129` 不顶本格 | 排除：不是本 FAIL 机制 |
| item +5s / result_count=1 即「进入完成」 | 预发「任务 result_count=1 仍 running」 | 排除：出数 ≠ 终态 completed |
| IdleAutoClose 空闲 120s 等于 Then 120s 窗 | 提交 08:35:23 → webhook 08:37:32 = +129s | 排除：Then 从等待开始算进入完成，不是空闲阈值本身 |
| qc-cond-2「PASS（出数）」可翻矩阵格 | 出数/导出 200 成立；Then 还要 120s 内完成 | **命中**：把出数半句当整句 Then |

### Root cause

Live Worker IdleAutoClose 在末条后再空闲 120s 才 finished，故 completed ≈ +129s；Then 要求 120s 内进入完成，item-while-running 被误当 ✅。

### Fix

最小面：主格及 §0/§3.3/§5/§8/§9/§12 凡写 18.1 ✅ 的改回 ⚠️。记录出数成立 / 完成不成立。不改产品、不改 GWT。01.1 / 06.1 / NFR-01 / 37.6 保持 ✅；FR-50/51/60/61 ➖。

### Re-run

```
$ python3 skills/coverage/scripts/check-matrix.py \
    .sdlc/feat-four-pillars-v2/04-verify/coverage.md \
    .sdlc/feat-four-pillars-v2/01-define/spec.md
✓ 覆盖矩阵完整：56 条 FR/NFR 全覆盖
```

exit code 0

```
$ bash scripts/check-sdlc.sh --require --hat verify .sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
```

exit code 0

主格当时 `| GWT-18.1 正常 | TC-18.1 | 专项 | ⚠️ |`。本节是 CV-09 历史；本轮 idle=30 live Then 翻格见 **§14**。37.6 / NFR-01 / 34.9 / 42.2 / 45.4 的「本格 ✅」保持。

---

## 14. 本轮（idle close 30 · live GWT-18.1 Then）

Then（`01-define/spec.md:513`）未改：120 秒内进入完成且条数>0。产品 IdleAutoClose 现 **30s**（`config/scrapy/default/settings.yml` `SPIDER_IDLE_CLOSE_SECONDS: 30`）；GWT-18.4 标注仍 **120s**（`SPIDER_WORKER_OFFLINE_SECONDS: 120`；`spider_worker_gate.py` 两钟分家）。**不得**把 18.4 窗写成 30。

### Live GWT-18.1（orchestrator 独立跑；非 FakeRedis）

`run.py restart spider` 后：

| 步 | 事实 |
|---|---|
| POST signup | **200** tenant `qc181-1789008085` |
| POST run example+httpbin | task **#2** pending |
| poll +6.1s | `running` `result_count=1` |
| poll **+40.6s** | **`status=completed` `result_count=1`** |
| GET export JSON | **200 rows 1** |
| elapsed | **40.56s ≤ 120s** |

本格 **✅**。FakeRedis `test_spider_min_loop.py` 仍不顶。旧预发 +129s（idle 当时 120）作废。

### 可选洞（本帽独立读测试后翻）

```
$ npm test --prefix frontend/official -- --runInBand \
    --testPathPattern='Home.test|Pricing.test|Register.test' \
    --testNamePattern='NFR-07|FREE_TIER_FEATURE_COPY|free-tier copy'
Test Suites: 3 passed, 3 total
Tests:       21 skipped, 4 passed, 25 total
```

exit code 0

```
$ uv run pytest -q backend/tests/test_saas_wiring.py backend/tests/test_saas_byok.py
..............                                                           [100%]
14 passed in 3.45s
```

exit code 0

| 格 | 处置 |
|---|---|
| TC-18.1 / GWT-18.1 | ⚠️→✅ live +40.6s completed / count=1 / 40.56s ≤ 120s；idle 30 ≠ 18.4 窗 120 |
| TC-18.4 | 保持 ✅；标注窗 **仍 120s** |
| C35-QA-03 Register | 已关：`Register.test.tsx:177` 钉 `FREE_TIER_FEATURE_COPY`、禁 `10000` |
| NFR-07 | ⚠️→✅ Home:76 / Pricing:70 / Register:192 ≥44px |
| wiring/byok `or True` | 已关；14 passed |
| FR-50/51/60/61 · 六问 | 保持 ➖；未答六问；未标 Wave 2/3 已覆盖 |

### 闸

```
$ python3 skills/coverage/scripts/check-matrix.py \
    .sdlc/feat-four-pillars-v2/04-verify/coverage.md \
    .sdlc/feat-four-pillars-v2/01-define/spec.md
✓ 覆盖矩阵完整：56 条 FR/NFR 全覆盖
```

exit code 0

```
$ bash scripts/check-sdlc.sh --require --hat verify .sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
```

exit code 0

主格 `| GWT-18.1 正常 | TC-18.1 | 专项 | ✅ |`；`| GWT-18.4 边界 | TC-18.4 | 集成 | ✅ |` 标注窗仍 120s。
