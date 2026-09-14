# 覆盖矩阵（verify 帽）— feat-product-complete

- 生成：2026-09-12｜帽：qa｜spec 基线：v1.6（GWT-90.1 写者=平台超管）｜蓝图：v1.4
- 范围：spec 全部冻结 GWT × 实际测试用例；蓝图 §4 护栏全表抽检；NFR 抽验；IMPL-QA-5 真库轮
- 矩阵行数：**153** = 活跃 **152** + 作废 **1**（GWT-105.2）
- 验法：先逐票抽取 03-impl/T-01…T-42 evidence 的「验收项逐条对应」声明，再**回仓核对**测试文件与用例名真实存在（后端 17 项抽核全中、前端 17 个测试文件全中，见 §1.1 抽核记录）

## 0. 管理窗给定基线（本轮不重复全量）

- backend pytest：1546 passed / 38 skipped，exit 0（implement 终审）
- admin jest：224 全过；arch 红线 0；DB 迁移门禁 0；admin/shared 双 build 0
- 本帽新增定向跑：`uv run pytest -q backend/tests/test_t42_fidelity_queue_depth.py backend/tests/test_t13_public_seed_filter.py backend/tests/test_t14_public_paging.py backend/tests/test_alert_queue_depth.py` → **28 passed, 1 skipped, exit 0**（skip=真库轮文件在 sqlite 态按设计跳过）
- 本帽新增真库轮：`MYSQL_FIDELITY=1 … test_t42_fidelity_queue_depth.py` → **1 passed, exit 0**（§3）

## 1. GWT×用例覆盖矩阵

状态图例：✅ 全覆盖（含双半拼合 ✅*）｜⚠️ 部分｜🛫=测试在桩/组件级兑现，真环境半记 deferred-live（§5.B）｜⊘ 作废豁免

### 1.0 FR 索引（含豁免；FR 编号全集 = spec.md 出现的全部 FR 字面）

| FR | 处置 | 覆盖落点 |
|---|---|---|
| FR-50 | 本特征冻结（16 GWT） | §1 Wave C 表 |
| FR-51 | 本特征冻结（10 GWT） | §1 Wave C 表 |
| FR-60 | 本特征冻结（11 GWT） | §1 Wave C 表 |
| FR-61 | 本特征冻结（3 GWT） | §1 Wave C 表 |
| FR-87 | 本特征冻结（3 GWT） | §1 Wave C 表 |
| FR-80 | 本特征冻结（4 GWT） | §1 Wave U 表 |
| FR-81 | 本特征冻结（4 GWT） | §1 Wave U 表 |
| FR-82 | 本特征冻结（4 GWT） | §1 Wave U 表 |
| FR-83 | 本特征冻结（5 GWT） | §1 Wave U 表 |
| FR-84 | 本特征冻结（4 GWT） | §1 Wave U 表 |
| FR-85 | 本特征冻结（3 GWT） | §1 Wave U 表 |
| FR-88 | 本特征冻结（5 GWT） | §1 Wave U 表 |
| FR-89 | 本特征冻结（3 GWT） | §1 Wave U 表 |
| FR-90 | 本特征冻结（3 GWT） | §1 Wave U 表 |
| **FR-91** | **豁免：本轮不冻结**（等 Q-MARKET-USER；spec §3/§9.1 明文「无本轮冻结 GWT，不施工不验收」；超管七叶 FR-37 已兑保持） | 无 GWT 行=合同豁免 |
| FR-92 | 本特征冻结（9 GWT） | §1 Wave U 表 |
| FR-93 | 本特征冻结（9 GWT） | §1 Wave A 表 |
| FR-94 | 本特征冻结（5 GWT） | §1 Wave A 表 |
| FR-95 | 本特征冻结（7 GWT） | §1 Wave A 表 |
| FR-96 | 本特征冻结（4 GWT） | §1 Wave A 表 |
| FR-97 | 本特征冻结（4 GWT） | §1 Wave A 表 |
| FR-98 | 本特征冻结（7 GWT） | §1 Wave A 表 |
| FR-99 | 本特征冻结（4 GWT） | §1 Wave A 表 |
| FR-100 | 本特征冻结（8 GWT） | §1 Wave A 表 |
| FR-101 | 本特征冻结（5 GWT） | §1 Wave A 表 |
| FR-102 | 本特征冻结（5 GWT） | §1 Wave A 表 |
| FR-103 | 本特征冻结（5 GWT） | §1 Wave A 表 |
| FR-104 | 本特征冻结（4 GWT） | §1 Wave A 表 |
| FR-105 | 本特征冻结（3 活跃 GWT + 1 作废） | §1 Wave A 表 |
| FR-01…FR-05 | **豁免：v2 已关账不开票**（spec §0.2 对照表；对外诚实/注册/付费档主钮已兑） | 新裂缝由 FR-50/80 承接 |
| FR-06/FR-07 | 豁免：v2 已兑（平台写面隐藏/直打同形） | 本特征沿用面=FR-82 行（82.2/82.3 同句保持） |
| FR-08 | 豁免：v2 已兑（到期拒绝） | 保持真=83.5 到期不同句 |
| FR-09/FR-10 | 豁免：v2 已兑（入队/回流/候选） | 不重开（spec §0.2） |
| FR-12 | 豁免：v2 已兑（满额用户句/不到注册） | 保持真+收口=50.1/50.6/87.1 行 |
| FR-13 | 豁免：v2 已兑（出站未绑定拒绝） | 保持真=51.3 行（同句不放宽） |
| FR-14 | 豁免：v2 已兑（密钥离树） | 上游 key 机外（NFR-10）；arch 门禁 0 |
| FR-15 | 豁免：v2 已兑（事件路由；北极星来源） | 事件族沿用=92.x 行（不改名） |
| FR-17 | 豁免：v2 已兑（平台写面/空缓存非全开） | 保持=82.2 行 |
| FR-18 | 豁免：v2 已兑（无工人可感知） | 补「去节点」=85.x 行 |
| FR-30 | 豁免：v2 已兑（单一市场） | 不重开 D10/D14/D21（§5） |
| FR-37 | 豁免：v2 已兑（超管七叶） | 保持=96.4/98.7/100.6 行（FR-91 不动它） |
| FR-41 | 豁免：v2 已兑（夹具可搜可订） | 对照=80.4 行（清污染后仍真） |
| FR-70/FR-74 | 豁免：v2 已兑（LiteLLM 数据面/网关挂≠超限） | 保持=60.5 行同句；不焊根编排（NFR-10） |

### Wave C（FR-50/51/60/61/87）

| GWT | 测试（文件::用例） | 状态 |
|---|---|---|
| 50.1 存储满→去结果库 | Usage.test.tsx「storage full CTA goes to results not register (GWT-50.1)」 | ✅ |
| 50.2 token 满申请 | 后端 test_billing_orders_write_rules::test_gwt_50_2_owner_offline_pro_creates_single_pending + 前端 Usage「owner submits offline upgrade order」 | ✅* |
| 50.3 我的订单 | 后端 test_billing_orders_read.py::test_gwt_50_3_my_orders… + 前端 MyOrders「GWT-50.3 renders plan name, zh status and yuan amount」+「readonly viewer can open」（读面） | ✅* |
| 50.4 空态 | 后端 test_gwt_50_4_backend_half…（200 空列表）+ 前端 MyOrders「GWT-50.4 empty orders show pinned copy」（钉句「还没有升级申请。」） | ✅* |
| 50.5 在线通道零单 | test_gwt_50_5_online_channel_creates_no_order + test_gwt_50_5_online_keeps_existing_pending；前端「ORDER_PENDING_EXISTS maps…」同屏并存支 | ✅ |
| 50.6 并发满 | Usage「GWT-50.6 task concurrency full shows 已达任务并发上限 with same offline entry」 | ✅ |
| 50.7 只读找管理员 | 后端 test_gwt_50_7_viewer_cannot_order…（无 FORBIDDEN/QUOTA 族断言）+ 前端「GWT-90.7 operator full sees contact-admin note」族 | ✅* |
| 50.8 经办下单 | test_gwt_50_8_operator_cannot_order_sees_contact_admin | ✅ |
| 50.9 租户确认拒绝 | test_gwt_50_9_tenant_confirm_rejected_stays_pending（owner+viewer 双拒） | ✅ |
| 50.10 超管确认（完成线） | test_gwt_50_10_admin_confirm_tenant_reads_paid（不断言 quota 履约） | ✅ |
| 50.11 再确认 no-op | test_gwt_50_11_reconfirm_no_new_row_no_stacked_side_effect | ✅ |
| 50.12 一套真相 | Usage「GWT-50.12 token full (owner) shows skeleton verb…」（后台半）+ official Pricing.test/FeaturesSection.test（预告形态、无「当前可买」） | ✅*（渠道组互否按 spec 不在本 Then） |
| 50.13 三数字同套 | Usage「GWT-50.13 (QA-23) pro-tier fixture enforces the same three numbers」（独立 oracle 50/200,000/500 万） | ✅ |
| 50.14 企业档无 SKU | test_gwt_50_14_enterprise_no_sku_no_order | ✅ |
| 50.15 第二张 pending | test_gwt_50_15_second_pending_rejected（唯一约束判重） | ✅ |
| 50.16 两张都确认 | test_gwt_50_16_two_fixture_pendings_both_paid_no_quota_stack | ✅ |
| 51.1 签发（明文一次+拉到行+产品名） | 后端 test_outbound_keys.py::test_gwt_51_1_operator_issues_plaintext_once_prefix_stored（签发半）+ test_outbound_pull_enforcement.py::test_gwt_51_1_latter_half_outbound_key_pulls_own_rows（真实 DB 全链拉行）+ 前端 OutboundKeys「gwt_51_1_51_8」 | ✅* |
| 51.2 空态句 | 后端 test_gwt_51_2_empty_state_sentence + 前端「gwt_51_2: empty sentence…not a relay page」（钉句） | ✅* |
| 51.3 未绑定仍拒 | test_gwt_51_3_unbound_or_garbage_key_rejected_zero_rows | ✅ |
| 51.4 跨企业 0 行 | test_gwt_51_4_tenant_a_key_never_returns_tenant_b_rows | ✅ |
| 51.5 只读签发 | 后端 test_gwt_51_5_viewer_cannot_issue_no_key_row + 前端「gwt_51_5_51_9: viewer sees list with note, no issue/revoke controls」 | ✅* |
| 51.6 令牌≠出站钥匙 | test_gwt_51_6_relay_sk_token_rejected_and_not_listed（真 sk- 桩签发） | ✅ |
| 51.7 吊销后 0 行 | test_gwt_51_7_revoked_key_pull_zero_rows | ✅ |
| 51.8 再进页无明文 | 后端 test_gwt_51_8_revisit_shows_prefix_and_status_only + 前端「gwt_51_1_51_8」 | ✅* |
| 51.9 只读吊销 | 后端 test_gwt_51_9_viewer_cannot_revoke_key_stays_active + 前端 51.5/51.9 例 | ✅* |
| 51.10 出站钥匙打网关→拒 | test_gwt_51_10_outbound_key_rejected_on_gateway_paths_no_usage_side_effect（不变量：非套餐句、用量基线不变） | ✅ 🛫真网关半 |
| 60.1 签发+用法 | 后端 test_relay_token_gateway.py::test_issue_registers_gateway_key_and_plaintext_once（明文一次+网关登记）+ 前端 RelayGroups「gwt_60_1」（Base URL+三步用法同屏、零 /api/v1、零 master） | ✅* |
| 60.2 用量会走（只读可见） | 后端 test_relay_token_usage.py::test_gwt_60_2_viewer_sees_usage_list_reads_local_column_only + 前端「gwt_60_2」（viewer 见 1,200） | ✅* |
| 60.3 打到网关 | test_gwt_60_3_chat_authed_usage_moves_and_event（真实 HTTP chat 对桩网关：网关认证+真响应体+usage≥1+信封无 QUOTA 词） | ✅ 🛫真 LiteLLM 轮 |
| 60.4 无令牌空态 | 后端 test_relay_group_empty_state.py（MSG_TOKENS_EMPTY）+ 前端「gwt_60_4」（钉句+签发入口+用法区在场） | ✅* |
| 60.5 网关不可达同 Then | test_gwt_60_5_gateway_unreachable_same_then_not_quota（502+LLM_GATEWAY_UNREACHABLE+无 QUOTA 词+本地不清零） | ✅ 🛫真网关半 |
| 60.6 租户改全局熔断无入口 | test_gwt_60_6_tenant_no_entry_to_platform_fuse_probe_window（GET/页面 404 同形；写面 403） | ✅ ⊕豁免：写面 403 形态（IMPL-QA-1 管理窗豁免+contract §7.4 微补注记；GET/页面同形已测） |
| 60.7 经办看用法无写权 | 后端 test_relay_group_empty_state.py::60.7 例（status≠403、无内码）+ 前端「gwt_60_7」（旁注「当前账号不能签发，请联系企业管理员」） | ✅* |
| 60.8 跨企业同形 | test_gwt_60_8_cross_tenant_revoke_and_detail_404 | ✅ |
| 60.9 官网无可买中转 | official「test_no_currently_buyable_relay_copy_gwt_60_9」（零「当前可买/可买中转」） | ✅ |
| 60.10 A 不动 B | test_gwt_60_10_tenant_a_call_does_not_move_tenant_b（用量/配额/事件三不变） | ✅ |
| 60.11 再进页无明文 | test_relay_token_usage（60.3 测内 plaintext_key is None）+ RelayGroups「gwt_60_11」（destroyOnHidden） | ✅* |
| 61.1 值班看见伪装 | NewApiOps.test「GWT-61.1 spoofed latest batch is visible…」（总览行 Tag+「伪装: N」+探针徽标+无禁用动作） | ✅ |
| 61.2 无第三套空态 | NewApiOps.test「GWT-61.2 gateway down / unregistered models…」（71.3/71.2 已冻句；「暂无渠道/暂无数据」缺席） | ✅ |
| 61.3 租户 404 同形 | App.layout.test「GWT-61.3 authenticated tenant direct hit on /newapi…」 | ✅ |
| 87.1 满额中文两句 | test_fr87_enqueue_envelope.py::test_gwt_87_1_quota_full_envelope_is_user_visible + test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects（执法本体内部码仍 QUOTA_EXCEEDED、用户面无） | ✅ |
| 87.2 未满不出现满额句 | test_gwt_87_2_under_quota_enqueues_normally | ✅ |
| 87.3 只读无入口无内码 | test_gwt_87_3_viewer_submit_rejected_user_visible（真链路 viewer JWT）+ 两入口金标（t10/b1b） | ✅ |

### Wave U（FR-80…90、92）

| GWT | 测试 | 状态 |
|---|---|---|
| 80.1 种子不出现 | test_t13_public_seed_filter.py::test_gwt_80_1_skills_list_excludes_seeds / …_featured_shape / …_capabilities_list（列表/精选/total 三面） | ✅ |
| 80.2 空态=正常空列表 | test_gwt_80_2_skills_empty_after_seed_filter / …_capabilities_type…（200+total 0） | ✅ |
| 80.3 种子翻 listed 仍隐 | test_gwt_80_3_seed_flipped_listed_still_hidden_skills / …_capabilities（含详情 404 同形） | ✅ |
| 80.4 夹具对照 | test_gwt_80_4_fixture_searchable_skills / …_capabilities（q=pdf 命中 example-pdf-extractor） | ✅ |
| 81.1 ≥21 第 21 张可到 | 后端 test_t14_public_paging.py::test_gwt_81_1_public_page_size_cap_is_20 + …_21st_reachable_on_page2_skills/capabilities + 前端 official「GWT-81.1 pager shows total and next…without overlap」 | ✅* |
| 81.2 恰 20 无假翻页 | test_gwt_81_2_exactly_20_no_fake_next_page + 前端「GWT-81.2 exactly 20 items has no fake next control」 | ✅* |
| 81.3 0 上架空态 | test_gwt_81_3_zero_listed_is_empty_not_failure + 前端「GWT-81.3 zero stock keeps empty sentence without pager numbers」 | ✅* |
| 81.4 未上架任何页不可见 | test_gwt_81_4_unlisted_asset_never_on_any_page | ✅ |
| 82.1 找得到自己的叶 | App.menu.test「dirty /auth/menus tree does not drive the tenant sidebar」（脏树下渠道组✓安装✓rbac✗enterprise✗、/auth/menus 零消费） | ✅ |
| 82.2 权限未就绪 | App.menu.test「permissions not ready」（加载中句+叶不消失+无幽灵叶闪现） | ✅ |
| 82.3 深链同形 404 | App.menu.test「/rbac /enterprise 两例」（「页面不存在或已被移除」+无侧栏+无他司列表；反向：超管入口不砍） | ✅ |
| 82.4 超管无企业空间 | App.menu.test「/relay→渠道组属于企业空间…」（不发列表请求；反向：租户仍得真页）+ T-38 回归网（relay/出站域零改动） | ✅* |
| 83.1 邮箱登录进本企业 | test_auth_login_tenant.py::test_email_login_enters_own_tenant_not_other + 单测 test_email_identifier_uses_email_lookup | ✅ |
| 83.2 未知=错密码同句 | test_unknown_email_and_wrong_password_same_sentence（code+message 全等） | ✅ |
| 83.3 成功屏写邮箱 | official Register.test「GWT-83.3 success screen names the registered email…」+ fallback 例 | ✅ |
| 83.4 进 A 不进 B | test_email_login_enters_own_tenant_not_other（A/B 对称） | ✅ |
| 83.5 到期不同句 | test_disabled_tenant_email_login_uses_expiry_sentence（AUTH_TENANT_EXPIRED） | ✅ |
| 84.1 失败句+重试（六屏） | Nodes/Dashboard/Data 各例（nodes list failure…/stats failure…/results load failure…）+ RelayGroups「gwt_84_1」+ LlmProviders 失败例（T-17 汇总） | ✅（spec 点名五屏+收款在 84.4） |
| 84.2 真 0 空态句 | nodes true zero…/true zero keeps onboarding…/true zero results: 还没有采集结果+去采集（Data.test 钉句） | ✅ |
| 84.3 租户 404 同形（收款+产品事实） | PlatformOps.test「GWT-84.3 tenant direct hit on /platform-ops is 404 shell for both…」 | ✅ |
| 84.4 收款失败句 | PlatformOps.test「GWT-84.4 pending orders failure shows failure sentence + retry…」+ retry refetches 例 | ✅ |
| 85.1 横幅+去节点 | Spiders.test「T-18 GWT-85.1：0 工人…『不会出数』+『去节点』打开节点页（加载中不出横幅）」 | ✅ |
| 85.2 提交被拦 | TaskModal.test「T-18 GWT-85.2：…未入队、无『正在排队执行』、提示句含『去节点』」+前置例（有工人不拦） | ✅ |
| 85.3 只读无入口 | Spiders.test「T-18 GWT-85.3」（新增/再次运行/收藏全隐藏） | ✅ |
| 88.1 技能收回 | test_t19_governance_retract.py::test_gwt_88_1_skill_retract_after_scan / …_after_src_sync | ✅ |
| 88.2 插件收回 | test_gwt_88_2_plugin_retract_after_scan_plugins / …_after_src_sync | ✅ |
| 88.3 空态不顶满 | test_gwt_88_3_catalog_empty_state（前端钉句「还没有目录项」在 Capabilities.import.test） | ✅ |
| 88.4 租户动不了收回 | test_gwt_88_4_tenant_cannot_touch_retracted | ✅ |
| 88.5 命令不回潮 | test_gwt_88_5_command_retract_no_regression | ✅ |
| 89.1 只读四控件不渲染 | Members.test「GWT-89.1 viewer：添加成员/角色下拉/重置密码/删除不渲染，名单可见」（queryByRole×4 null） | ✅ |
| 89.2 单人企业自见 | Members.test「GWT-89.2 单人企业…负责人能看见自己」+「只读打开同一企业：仍满足 89.1」 | ✅ |
| 89.3 强提交拒绝 | 前端「GWT-89.3 viewer 无入口」（写 API 零调用）+ 后端 test_saas_members.py::test_viewer_cannot_manage / test_viewer_cannot_delete_member（403+名单不变） | ✅* |
| 90.1 保存无同步谎句（平台超管，v1.6） | Settings.test「GWT-90.1 保存官网副标题类字段：成功句只声明保存…」（message.info 零调用；只调 updateSiteConfig=无同步动作）｜**IMPL-QA-2 微票已核落**：Settings.tsx:33 `canWriteSettings = is_platform_admin===true` | ✅ |
| 90.2 非平台超管说明态 | Settings.test「GWT-90.2…只见『当前账号不能改系统设置』，无保存控件，非 404 同形」（owner/admin/operator/viewer 四角色夹具） | ✅ |
| 90.3 只读保存不可达 | Settings.test「GWT-90.2/90.3 只读打开…无 form、写 API 零调用」+「写侧不回归：平台超管仍见表单」 | ✅ |
| 92.1 submitted 事件 | test_billing_orders_read.py::test_gwt_92_1_submitted_event_with_tenant_and_plan（DB 行+/product-events 可查） | ✅ |
| 92.2 confirmed 事件 | test_gwt_92_2_confirmed_event_with_tenant_and_plan（重复确认不重报由 50.11 钉） | ✅ |
| 92.3 签发事件无明文 | test_gwt_92_3_issue_event_has_tenant_no_plaintext（props={key_id}） | ✅ |
| 92.4 成功调用事件 | test_relay_token_usage 60.3 测内：恰 1 条 relay_token_call_succeeded（tenant_id/token_id、无明文、不重复上报） | ✅ 🛫同 60.3 |
| 92.5 翻页事件 | test_gwt_92_5_market_list_paged_emitted_on_page2（+capabilities 端点+超管查询面可查+前端 anonymous_id 两例） | ✅ |
| 92.6 失败不挡主路径 | test_product_events.py::test_gwt_92_6_*（七上报点异常注入：offline×2/outbound/relay×2 含生产 expire_on_commit 红绿/market/user_restored/asset_imported） | ✅ |
| 92.7 查询面仅超管 | test_gwt_92_7_tenant_query_face_same_shape_as_missing_page（与同守卫平台页信封逐键相等） | ✅ |
| 92.8 user_restored | test_t24_user_restore.py::test_restore_success_…emits_event（tenant_id/actor/props.restored_user_id/无敏感字段） | ✅ |
| 92.9 asset_imported | test_t35_asset_import.py::test_gwt_92_9_asset_imported_event_queryable（origin/types/succeeded/failed+查询面） | ✅ |

### Wave A（FR-93…105）

| GWT | 测试 | 状态 |
|---|---|---|
| 93.1 筛已删 | 后端 test_t24::test_deleted_filter_lists_only_deleted_with_marker + 前端 Users.test「GWT-93.1 筛『已删除』…」（标记/活跃缺席/无编辑删除动作） | ✅* |
| 93.2 默认视图不含已删 | 后端 test_default_list_excludes_deleted + 前端「GWT-93.2 默认视图…」（status=active） | ✅* |
| 93.3 恢复成功 | 后端 test_restore_success_returns_to_default_list_and_emits_event + 前端「GWT-93.3 恢复成功…」 | ✅* |
| 93.4 占用冲突拒绝 | 后端 test_restore_conflict_by_username_keeps_both_intact / …_by_email（各自独立格）+ test_restore_db_constraint_fallback_same_sentence（MySQL 1062 直证）+ 前端「GWT-93.4/93.8 占用冲突…」（中文句/弹窗不关/无内码） | ✅*（+本轮真库 FK 负向探针 §3） |
| 93.5 username 可释放 | test_create_reuses_released_username_in_same_tenant | ✅ |
| 93.6 越权 404 同形 | test_tenant_direct_restore_is_404_shape（+status 白名单拒绝）⊕列表面 200 为 IMPL-QA-3 architect 裁决维持（contract 注记） | ✅ ⊕豁免注记 |
| 93.7 email 可释放 | test_create_reuses_released_email_globally | ✅ |
| 93.8 再恢复同句 | test_re_restore_after_release_conflicts_with_same_sentence + 前端 93.4/93.8 例 | ✅* |
| 93.9 重复恢复 no-op | 后端 test_repeat_restore_is_noop_without_second_event + 前端「GWT-93.9 重复恢复…」 | ✅* |
| 94.1 种子 admin 不可删 | test_t26_base_protection.py::test_seed_admin_undeletable_even_with_second_platform_admin（库级行未软删+中文句；UI 渲染信封 message 既有模式） | ✅ |
| 94.2 平台租户不可改名 | 后端 test_platform_tenant_rename_rejected + 前端 EnterpriseManagement「平台租户守卫（UI 面）」（句+入口禁用） | ✅* |
| 94.3 不可停用 | 后端 test_platform_tenant_disable_rejected_login_unaffected（登录门不受影响）+ 前端守卫例（钉句） | ✅* |
| 94.4 无删除企业入口 | test_no_tenant_delete_endpoint（app.routes 机械断言）+ 前端无删除控件断言 | ✅* |
| 94.5 越权 404 同形 | test_tenant_direct_patch_platform_is_404_shape（404+"Not Found" 同形） | ✅ |
| 95.1 改名+同显+冲突 | 后端 test_t27::test_gwt_95_1_rename_success_both_surfaces_same_truth / …_conflict_with_existing_name / …_reserved_names（平台租户/AutoAgents 参数化）/ …_too_short + 前端「改名成功…」「改名冲突：400 句原样…」 | ✅* |
| 95.2 停用同显 | 后端 test_gwt_95_7_disable_then_reenable_roundtrip（库级+列表）+ 前端「停用：确认弹窗后果句…」 | ✅* |
| 95.3 平台租户显式化 | 后端 test_gwt_95_3_list_marks_platform_default + 前端「平台默认租户标注：行带『默认归属』Tag…」+ 无 AutoAgents 断言 | ✅* |
| 95.4 归属规则显式化 | 后端 test_gwt_95_4_user_without_tenant_lands_on_platform / …_zero_tenant_maps_to_platform + 前端文案（Users 套件回归） | ✅* |
| 95.5 列表失败≠空 | 后端 test_gwt_95_5_list_failure_envelope_shape（data 非列表）+ 前端「列表失败：失败句 + 重试…」 | ✅* |
| 95.6 越权 404 同形 | test_gwt_95_6_tenant_admin_direct_patch_404_shape（名称与状态不变） | ✅ |
| 95.7 再启用 | 后端 roundtrip 测 + 前端「再启用：已停用行『启用』→…」 | ✅* |
| 96.1 跨组切换不闪 | App.layout.test「cross-group menu click keeps the same sider instance and expansion」（侧栏 DOM 同一引用+展开保持+queryByText('权限加载中') 缺席） | ✅ |
| 96.2 组内切换 | 同文件「in-group leaf switch…」（滚动位置以 DOM 节点未换蕴含——jsdom 限制已注记） | ✅ |
| 96.3 首访允许一次 | AdminLayout 既有逻辑保留+两切换用例末尾断言缺席 | ✅ |
| 96.4 租户菜单不变式 | 404 同形两例（/users、/newapi）+ 既有 App.test 4 例 + usePermission.test 4 例（菜单过滤零 diff） | ✅ |
| 97.1 「默认」文案 | LlmProviders.test「owner surface uses 默认/设为默认 only — no 激活 anywhere」（body.textContent 全扫+说明句） | ✅ |
| 97.2 互斥呈现 | 「set default confirm modal uses pinned sentence, then mutual exclusion」+failure/offline 两例 | ✅ |
| 97.3 空态钉句 | 「empty state pins 还没有模型供应商 with 添加供应商 for authorized」+readonly 例+「list failure shows failure sentence, not empty state」 | ✅ |
| 97.4 只读无设默认控件 | 「readonly member sees default mark, no set-default controls」+「operator keeps CRUD write but no set-default control」（SHAPE-QA-03） | ✅ |
| 98.1 tab 上提 | NewApiOps.test「page tabs sit in the header row with the welcome text; content starts directly」+fallback 例（T-31） | ✅ |
| 98.2 总览三问同屏 | NewApiOps.test「GWT-98.2 three questions on one screen…」（健康/模型数/判定+延迟/24h 事件/窗口用量/Top 事件）⊕三处数据降级=IMPL-QA-4 已接受（tooltip 注明，后端端点转账本） | ✅ ⊕降级豁免注记 |
| 98.3 问题渠道置顶 | 「GWT-98.3 spoofed and offline channels are pinned before original ones」（行序断言） | ✅ |
| 98.4 立即探测 | NewApiOps.test「GWT-98.4 manual probe: in-flight row state, then verdict/latency update from this round」+「GWT-98.4 edge: one region failing…」（T-32/T-33 双格） | ✅ 🛫真引擎轮 |
| 98.5 事件跳转 | 「GWT-98.5 clicking a top event row switches to the events tab and highlights the row」 | ✅ |
| 98.6 网关不可达 | 「GWT-98.6 unreachable gateway…」（不可用灯+71.3 句+本地探针行继续+无 71.2/暂无渠道）+既有 GWT-71.3 | ✅ |
| 98.7 越权 404 同形 | 后端 test_t33_probe_trigger.py::test_operator_trigger_is_404_shape_without_side_effects（引擎未调用） | ✅ |
| 99.1 六页头规范 | LlmProviders/Users/Spiders/AiPlans/Settings/NewApiOps 各套件页头例（T-34 映射表 10 例） | ✅ |
| 99.2 失败句不吞 | LlmProviders「list failure…」+ Users「错误态…」既有例不动全绿 | ✅ |
| 99.3 动作等价 | 各页动作行断言（新建供应商/刷新/新建用户/新建采集计划/保存并发布） | ✅ |
| 99.4 只读写控件不回退 | LlmProviders GWT-97.4/SHAPE-QA-03 两例不动全绿 | ✅ |
| 100.1 单文件导入未上架 | 后端 test_gwt_100_1_single_zip_import_unlisted + 前端「GWT-100.1 UI 三步流转…」 | ✅* |
| 100.2 目录部分成功 | 后端 test_gwt_100_2_directory_partial_success + 前端「GWT-100.2/100.5/100.7 失败原因逐条呈现…」 | ✅* |
| 100.3 空态中性句 | 后端 test_gwt_100_3_nothing_importable + 前端「GWT-100.3 空批次中性句…」（无 alert） | ✅* |
| 100.4 四类齐 | 后端 test_gwt_100_4_four_types_auto_detected + 前端「GWT-100.4 四类类型中文化…」 | ✅* |
| 100.5 超大含上限数字 | 后端 test_gwt_100_5_oversize_rejection_with_limit_number + 前端（「10485760 字节」句直出） | ✅* |
| 100.6 越权无入口 | 后端 test_gwt_100_6_non_admin_direct_post_404_shape + 前端「GWT-100.6 非超管无导入入口…」 | ✅* |
| 100.7 路径逃逸 | 后端 test_gwt_100_7_escape_three_forms_zero_leak（../、绝对、symlink+目录通道；tmp 快照差集）+ 前端（「路径指向资产目录之外：evil.md，已拒绝」直出） | ✅* |
| 100.8 幂等重导 | 后端 test_gwt_100_8_idempotent_reimport（skipped=1 单行）+ 前端「GWT-100.8 幂等重导行标『已存在，跳过』…」 | ✅* |
| 101.1 agent 成员 | 后端 test_expert_team.py::test_team_mixed_members_expert_union_agent(+route) + 组件「team detail lists members with type tag」 | ✅* |
| 101.2 混合成员标注 | 同上三处 | ✅ |
| 101.3 可选域=两类组长专家 | 组件「member domain is expert∪agent, leader stays expert-only」+ 后端 test_team_leader_must_be_expert_not_agent | ✅* |
| 101.4 无 agent 空态 | 组件「zero agent assets shows empty copy and expert-only team still works」+ 后端 test_team_expert_only_when_no_agent_assets | ✅* |
| 101.5 越权 404 同形 | test_team_upsert_tenant_404_same_shape_zero_rows（operator+admin 双角色、零行、authz.denied 落库） | ✅ |
| 102.1 试采入队 | test_t38_platform_tenant_enqueue.py::test_gwt_102_1_platform_admin_enqueue_belongs_to_platform_tenant + …_plan_and_test_capture_share_platform_identity | ✅ 🛫真队列轮 |
| 102.2 上线同身份 | test_gwt_102_2_online_enqueue_same_platform_identity | ✅ 🛫同上 |
| 102.3 配额不绕 | test_gwt_102_3_platform_tenant_quota_not_bypassed（复用 T-12 中文句族） | ✅ |
| 102.4 归属不变 | test_gwt_102_4_regular_tenant_attribution_unchanged（+全量零回退） | ✅ |
| 102.5 冒名拒绝 | test_gwt_102_5_non_admin_impersonation_rejected（无内码） | ✅ |
| 103.1 编辑参数生效 | 后端 TestApiParamsEdit/TestEnqueueTakesDefinitionParams/TestFlowParamsEdit/代码型受限 6 测 + 前端 FileTab.test api/flow/代码型三例（回显+payload+成功句） | ✅* |
| 103.2 未引用删除 | 后端 test_unreferenced_delete_still_succeeds/test_operator_can_delete_unreferenced + 前端 FileTab 删除流 | ✅* |
| 103.3 被引用拒绝 | 后端 test_reject_message_names_tasks/test_delete_referenced_rejected_lists_tasks + 前端「删除被引用：确认弹窗原样展示后端拒绝句（含 #任务号）…」 | ✅* |
| 103.4 空态句 | 数据半：test_t41_plan_view_purity.py::test_all_internal_yields_empty_view（空可达、不回填 demo）+ UI 半：FileTab.test.tsx:174「空态（GWT-103.4）：冻结句『还没有采集方案。』+ 说明与次链，旧句不残留」（钉句+次链「去 AI 采集规划」+旧句「未发现爬虫定义」缺席断言）｜**T-40 微票已核落**（evidence「GWT-103.4 微票」节） | ✅* |
| 103.5 越权 | 后端 test_cross_tenant_edit_404_and_target_unchanged/test_cross_tenant_delete…/viewer_403×2 + 前端「非经办（viewer）无编辑/删除按钮」 | ✅* |
| 104.1 方案视图纯净 | test_plan_view_excludes_internal_and_unregistered / test_fallback_config_seeds_filtered_on_db_error / test_internal_manifest_is_frozen_contract | ✅ |
| 104.2 无独立入口+不删 | test_capabilities_catalog_has_no_spider_entry（路由表+目录项双断言）/ test_view_reads_delete_no_rows / test_view_filter_deletes_nothing_on_disk | ✅ |
| 104.3 空态不顶满 | test_all_internal_yields_empty_view | ✅ |
| 104.4 只读同口径 | test_viewer_sees_same_filtered_view | ✅ |
| 105.1 接通（超阈值→通知+命中+静默） | test_alert_queue_depth.py::test_queue_depth_over_threshold_triggers_notify_and_hit_row / …_silence_window_suppresses_repeat / …_expired_triggers_again / …_under_threshold_no_trigger + **本轮真库轮**（§3：真 INSERT+FK+静默二连） | ✅*（mock+真库双证） |
| 105.2 ~~下架支~~ | ⊘ 作废（Q-QUEUE-DEPTH 已决接通，spec §5/§9.2；验收禁止按本格执行） | ⊘ 豁免 |
| 105.3 无死规则（可失败验收） | test_all_four_rule_types_have_trigger_path（四类型各触发一次，存在无路径类型即 fail）+ 既有 consecutive/timeout 两金标 | ✅ |
| 105.4 越权 | 既有 test_b1b_alert_rules_coverage.py（operator 403/anonymous 401）+ R13 同形 404（回归网） | ✅ |

### 1.1 抽核记录（映射 ≠ 空测）

- 后端 17 个声明用例名逐一 `grep -rl` 回仓核对：**17/17 命中真实测试文件**（test_billing_orders_write_rules / test_outbound_pull_enforcement / test_relay_token_usage / test_fr87_enqueue_envelope / test_t13_public_seed_filter / test_t14_public_paging / test_t19_governance_retract / test_alert_queue_depth / test_t35_asset_import / test_expert_team / test_t38_platform_tenant_enqueue / test_t24_user_restore / test_t26_base_protection / test_t27_tenant_admin_enhance / test_auth_login_tenant / test_saas_wiring）
- 前端 17 个声明测试文件逐一存在：MyOrders/Usage/OutboundKeys/RelayGroups/official Pricing+FeaturesSection/NewApiOps/App.layout/App.menu/official Register/Spiders/TaskModal/Members/Settings/Users/EnterpriseManagement/Capabilities.import/FileTab 全命中
- 断言非空心抽读：50.2（rows[0].key==pending:{tid}+message 断言）、51.6（sk- 拒绝+不入列）、60.3（choices/usage.total_tokens≥1+信封无 QUOTA）、87.1（两句中文+禁集断言）、103.4 缺口即由本节方法发现（钉句 grep 不中→读源码证实）
- TDD 红/变异红证据抽读：T-01（6 failed 红+4 变异红）、T-08（6 failed 红）、T-27（红因逐条）、T-24（DB 1062 直证）均原样粘贴命令+退出码

### 1.2 矩阵总计

| 状态 | 数 | 明细 |
|---|---|---|
| ✅ 全覆盖（含双半拼合 ✅* 44 格） | **152 / 152** | 其中 🛫 deferred-live 注记 9 格（51.10/60.3/60.5/92.4/98.4/102.1/102.2 真环境半——桩级已绿，真轮入交付清单） |
| ⚠️ 部分 | **0** | —（GWT-103.4 已由 T-40 微票收口，格内已刷 ✅*） |
| ⊘ 作废豁免 | 1 | GWT-105.2（已决接通） |
| 无测试且无豁免记录的洞 | **0** | — |

## 2. 蓝图护栏抽检（metrics-blueprint §4 全表）

| 护栏（红线） | 验法（测试名） | 状态 |
|---|---|---|
| 公开商店测试种子 0 | test_gwt_80_1_×3（列表/精选/全部+plugin）+ test_gwt_80_3_×2（listed 翻转仍隐+详情 404 同形）+ 80.4 对照 | 绿 |
| 用户可见配额内码 0 | 87.1/87.3（信封+真链路 viewer JWT+两入口金标）、50.7/50.8（下单面禁集含 QUOTA_PLAN_LOCKED）、Usage 前端无 code 字面断言、102.3（平台租户配额句族） | 绿 |
| 失败装空 0 | T-17 三屏（nodes/stats 含局部卡/results）+ RelayGroups gwt_84_1 + LlmProviders 失败例 + PlatformOps 84.4 + EnterpriseManagement 95.5——spec 点名面每屏至少一测 | 绿 |
| 对外两套真相 0 | Usage「GWT-50.12 skeleton verb」（购买形零出现+并存句）+ official Pricing/Features（预告形态）；渠道组互否按蓝图明确不在抽检内 | 绿 |
| 「当前可买中转」0 | official test_no_currently_buyable_relay_copy_gwt_60_9（零字面/等价句；审查另核实用户可见面零出现） | 绿 |
| 跨租户出站或渠道组 0 | 51.4（A 钥匙 0 行 B）+51.6（令牌≠钥匙）+60.8（B 吊销 A 组 404）+60.10（A 调用不动 B 三件套）+103.5+101.5+105.4（R13） | 绿 |
| 平台基座破坏 0 | 94.1（第二超管在场仍拒+库级断言）+94.2/94.3（守卫句+状态保持+登录门）+94.4（app.routes 机械断言无 DELETE）+95.1 保留名双保险 | 绿 |
| 恢复覆盖现有用户 0 | 93.4/93.8（username 同租户/email 全局各拆格+双方 intact）+test_restore_db_constraint_fallback_same_sentence（1062 同句）+**本轮真库 FK 负向探针**（伪造 user_id 被 FK 拒） | 绿（真库加强） |
| 方案视图混入 0 | test_plan_view_excludes_internal_and_unregistered（四类混入 DB+yml 双路）+fallback_on_db_error+viewer 同集 | 绿 |
| 告警死规则 0 | test_all_four_rule_types_have_trigger_path（可失败验收：存在无路径类型即 fail）+105.1 全链（+真库轮） | 绿 |
| 管理台内码 0 | 93.4/93.8 占用中文句（前端原样内联+无内码断言）、94.1-94.3 三句、100.5「10485760 字节」上限数字句、102.3 句族、103.3 引用任务中文说明 | 绿 |
| 〔继承〕公开泄漏未上架/黑名单 0 | 81.4（任何页不可见）+80.3/80.4+88.1-88.5（收回行公开商店无） | 绿 |
| 〔继承〕非超管改渠道/平台 LLM 0 | 60.6（写面 403 金标+页面 404 同形⊕IMPL-QA-1 豁免）+97.4+98.7（零副作用） | 绿 |
| 〔继承〕new-api 运行时 0（Wave L 后） | 非本特征改动面；arch 门禁 0 + 出站域零 import 审查核实 | 绿（回归口径） |

## 3. IMPL-QA-5 真库轮（MYSQL_FIDELITY=1）— 已执行，PASS

- 背景：sqlite 轮 test_alert_queue_depth.py 对 session 全桩（fake_async_session），notifications 命中行 INSERT 与 user_id FK 从未打到真库（审查 IMPL-QA-5）。
- 本帽新增真库保真测试：`backend/tests/test_t42_fidelity_queue_depth.py`（MYSQL_FIDELITY=1 专属，sqlite 态整文件 skip——已验证 skip 干净不破 CI）。
- 执行（凭据走 MYSQL_FIDELITY_* 环境变量，不入任何文件）：

```
$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD=*** \
  uv run pytest -q backend/tests/test_t42_fidelity_queue_depth.py
1 passed in 3.42s
exit_code=0
```

- 真库证明的四件事：①命中行 INSERT 落真 MySQL（tenant_id/user_id=创建者在册 id/type='alert'/resource_type='alert_rule'/resource_id/content 含深度数字）；②last_triggered_at 落库、静默窗二连不重复（真库 60 分钟窗）；③user_id 外键真实生效——伪造接收人 999999 被 FK（1452→IntegrityError）拒绝；④pending 深度经真表 ix_spider_tasks_tenant_status_priority 等值查询。
- 环境注记（交交付清单）：本机 `auto_agents` 用户无 CREATE DATABASE 权限（1044），真库轮须 `MYSQL_FIDELITY_USER=root` 或预授权 `GRANT CREATE ON 'test_auto_agents_%'.*`；schema 用 create_all（与迁移链的基线对拍口径=列集，迁移门禁管理窗已过 0）。

## 4. NFR 抽验

| NFR | 验法 | 状态 |
|---|---|---|
| NFR-01 市场列表 P95<2s | jsdom 不可测 | **deferred-live**（§5.B-1：Playwright 计时方案） |
| NFR-02 页大小≤20+第 21 张当且仅当 | test_gwt_81_1_public_page_size_cap_is_20（MAX=20 闸：21/50→422、20→200）+21st_reachable×2+81.2 恰 20 无假翻页；导出 100 条已兑未动 | 绿 |
| NFR-03 失败不装空/无工人/网关≠超限/侧栏不闪 | FR-84/85/60.5/96 全测（见矩阵） | 绿 |
| NFR-04 安全项 | 未绑定拒绝（51.3）；明文一次（51.8/60.11 双面）；出站钥匙打网关拒绝且用量不变（51.10 不变量）；事件无明文（92.3/92.4 props 断言）；平台网关钥匙零出现（RelayGroups 全页零 master）；A 不动 B（60.10）；恢复不覆盖（93.4+1062+真库 FK）；导入不执行不自动上架（100.1 unlisted）；路径逃逸收容（100.7 三形态+快照差集） | 绿 |
| NFR-05 权限矩阵 | 82.3/93.6/94.5/95.6/100.6/98.7/61.3/60.6/97.4/89.3/101.5 全有 404 同形或控件隐藏测 | 绿 |
| NFR-06 合规 | 官网 0「当前可买中转」（60.9）；不发明电话（无施工面） | 绿 |
| NFR-07 兼容 | /skills 路由由 80.1 skills 例（打 /skills 端点）+81.1 skills 翻页例延续；未改公开 404 文案 | 绿 |
| NFR-08 可观测 | 92.7 查询面仅超管（逐键同形）；X-QUOTA 断言族遍布 50/87/93/102；92.8/92.9 仅超管可查 | 绿 |
| NFR-09 国际化 | — | N/A（本轮仅中文，spec 自注） |
| NFR-10 可维护 | 密钥/路径配置来源（真库轮凭据走环境变量亦循此口径）；LLM.ENABLED 机外（60.5 不要求打开）；网关不进根编排（T-08 无 DSN 守卫测试+arch 0） | 绿 |

## 5. 缺口清单

### A. 本特征必须补（轻量，建议随 review 批次带微票；处置归管理窗）

1. 已补：T-40 微票 2026-09-12（GWT-103.4 空态句收口——FileTab.test.tsx:174 钉句+次链，证据=03-impl/T-40-evidence.md「GWT-103.4 微票」节；矩阵格已刷 ✅*、§1.2 总计已同步 152/152）。

### B. deferred-live（联调/真环境，交交付清单）

1. NFR-01 P95<2s（责任面 /sre+/qa）：主口径=Playwright 计时（official 市场列表路由 `/skills`，夹具 ≤400 非种子 listed），采样「点开/点下一页→第 20 张卡可见」，≥50 样本取 P95<2s；或 Lighthouse CI 性能预算同口径。命令模板：

   ```bash
   # (a) Playwright 骨架（主口径=浏览器渲染时延；BASE=official 站点地址，/sre 出环境）
   # const samples = []
   # for (let i = 0; i < 50; i++) {
   #   const t0 = performance.now()
   #   if (i > 0) await page.getByRole('button', { name: '下一页' }).click()
   #   else await page.goto(`${BASE}/skills`)
   #   await page.locator('.capability-market__card').nth(19).waitFor({ state: 'visible' })
   #   samples.push(performance.now() - t0)          // 断言 p95(samples) < 2000ms
   # }
   # (b) curl 计时循环（轻量口径=API 半独跑，/qa 可独立执行）
   $ for i in $(seq 1 50); do curl -s -o /dev/null -w '%{time_total}\n' \
       "$BASE/api/v1/skills?page=1&page_size=20"; done \
     | sort -n | awk '{a[NR]=$1} END {print "P95=" a[int(NR*0.95+0.5)] "s (N=" NR ")"}'
   ```
2. GWT-60.3/92.4 真 LiteLLM 网关轮：现为桩网关 HTTP 契约级（认证+响应体+usage 回写全链）；真轮依赖 LLM.ENABLED+上游 key（操作者机外，NFR-10 禁写需求）。联调时复用 T-09 测口径（Bearer=签发明文→chat→used_tokens≥1→事件恰 1 条）。
3. GWT-51.10/60.5 真网关面：同 2 的环境闸（拒绝形态+用量基线不变的不变量已测）。
4. GWT-98.4 真探针引擎轮（责任面 /sre+/qa）：前端进行中态+行内更新已测、越权 404 后端已测；真引擎触发（10 维指纹）联调一枪。命令模板：

   ```bash
   # TOKEN=平台超管登录（username=邮箱标识；密码走环境变量，不入任何文件）
   $ TOKEN=$(curl -s "$BASE/api/v1/auth/login" -H 'Content-Type: application/json' \
       -d "{\"username\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}" \
       | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["access_token"])')
   # 触发手动探测（与 test_t33_probe_trigger.py 同端点同载荷）
   $ curl -s -X POST "$BASE/api/v1/newapi/probe" -H "Authorization: Bearer $TOKEN" \
       -H 'Content-Type: application/json' -d '{"gateway_ref": "<目标渠道 ref>"}'
   # 轮询探针结果直至出本轮判定（verdict/latency；本地表始终可用，可按 channel_id 过滤）
   $ watch -n 5 'curl -s "$BASE/api/v1/newapi/probe-results?page=1&page_size=20" \
       -H "Authorization: Bearer $TOKEN"'
   ```
5. GWT-102.1/102.2 真队列/工人环（责任面 /sre+/qa）：服务路径（入队+归属+配额）已测；端到端（Redis 队列→worker→completed）联调。命令模板（超管登录→AI 规划→试采→轮询终态）：

   ```bash
   # TOKEN 取法同 B-4（平台超管；GWT-102.1=方案与试采同归属平台租户）
   # ① 建 AI 采集方案（与 test_t38_platform_tenant_enqueue.py PLANS_URL 同载荷）
   $ PLAN=$(curl -s -X POST "$BASE/api/v1/ai/plans" -H "Authorization: Bearer $TOKEN" \
       -H 'Content-Type: application/json' -d '{"target_url": "https://<联调目标>"}' \
       | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')
   # ② 试采（flow_generic 经 orchestrator 同链入队；102.2 上线=POST /api/v1/ai/plans/$PLAN/plan 同口径）
   $ curl -s -X POST "$BASE/api/v1/ai/plans/$PLAN/test" -H "Authorization: Bearer $TOKEN"
   # ③ 轮询任务终态：Redis 队列→worker→completed（status: pending/running/completed/failed；
   #    store 回流另查 GET /api/v1/spiders/tasks/{id}/store）
   $ watch -n 5 'curl -s "$BASE/api/v1/spiders/tasks?limit=100" -H "Authorization: Bearer $TOKEN" \
       | python3 -c "import sys,json; [print(t[\"id\"], t[\"status\"]) for t in json.load(sys.stdin)[\"data\"][\"items\"][:5]]"'
   ```
6. MYSQL_FIDELITY 全量真库轮（本轮仅 T-42 定向）：命令模板见 §3 环境注记；注意 auto_agents 用户权限。
7. WACT/PC-1…PC-4 四上海周窗：产品事实查询面取数（蓝图 §2/§3；PC-1 邮箱标识/PC-3 打开我的订单/PC-4 签发分母按蓝图 §6 抽检）。

### C. 后续票账本（已裁决/预存，不阻塞本特征）

1. T-32 三处数据降级的服务端补齐端点（per-channel 24h 聚合/窗口用量真值/sha256 镜像）——IMPL-QA-4 接受降级（tooltip 注明，无编造）。
2. IMPL-QA-3：`GET /admin/users` 列表面对租户管理员 200（r13 历史金标）——architect 裁决维持，contract 注记。
3. IM-02/03/12/13/18/26、C35-QA-05 测试/文档债（spec §5 转账本，非本特征）。
4. alembic 039/040 环境漂移转 /sre；分支 ahead 7 进交付清单（工程债）。

## 6. 结论

- **152/152 活跃 GWT 全部有 ≥1 个真实测试映射（用例名回仓核实），0 个无豁免记录的洞**；1 格部分覆盖（103.4 UI 钉句，轻量微票可收）。
- 豁免三处全部有裁决记录：60.6 写面 403（IMPL-QA-1）、93.6 列表面 200（IMPL-QA-3）、105.2 作废（Q-QUEUE-DEPTH）。90.1 写者错配已经 spec v1.6 回写+前端微票落核（Settings.tsx:33 守卫+四角色测试）。
- 蓝图 §4 护栏 11/11+继承 3/4（new-api 为回归口径）全绿，每条有具名测试；IMPL-QA-5 真库轮本轮执行 PASS（命中行+FK+静默窗真 MySQL 直证）。
- NFR：02/03/04/05/06/07/08/10 绿；01 deferred-live（jsdom 不可测，测法已给）。
- **覆盖足以进入 review**：唯一 ⚠️（103.4）是钉句字面缺口，Then 其余两支已证、整改 <0.5 人时，建议随 review 批次带微票收口，不构成阻塞。deferred-live 七项均环境闸或产品四周窗，已有桩级/组件级证据与交付清单命令。
