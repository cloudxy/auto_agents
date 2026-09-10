# architect memory · feat-four-pillars-v2

> Facts (**what**). Procedures in SKILL.md. Cap 2200. Frozen snapshot.

## Last

- Date: 2026-09-08
- Hat: 票 r2 FAIL → **只关 TK-05…08**。TK-01…04 独立 closed。SH-01…18 closed。contract **v1.8**。不写实现。不代选六问。
- Outputs: `tickets/T-16.md` `T-20.md` `T-01.md`；`contract.md` v1.8

## Facts

- TK-05 闸=分格 `::node`，禁 `or_cell_failure` 一名三格。规划：`::test_post_plan_outbound_gateway`（只 70.1）、`::test_post_plan_no_model_only_70_2`、`::test_post_plan_unreachable_only_74_1`；试采/评分同构。T-20 70.1 只钉成功格。SH-01 点名 `test_saas_byok.py::test_no_own_key_falls_back_to_platform`（outbound=网关 URL）。禁整文件 `test_saas_byok.py` 当绿闸。`test_saas_provider_semantics.py` `https://pub` 同 PR 作废/降级。
- TK-06 闸加 `::test_operator_similar_suggest_no_model_envelope_only_70_10` / `::test_operator_similar_suggest_unreachable_envelope_only_74_6`。
- TK-07 满额两格：`::test_post_plan_quota_full_gateway_reachable_only_12_3` / `::_unreachable_only_12_3` → Then 只 12.3 句，不是网关不可达句。未加不得勾 74.2。
- TK-08 T-01 70.4 三 node：Home / FeaturesSection / Pricing `::test_no_direct_gateway_or_relay_token_copy`。未加不得勾 T-01 侧 70.4。禁只跑 Pricing.test。

## Open (mine)

- `/sre` 钉 LiteLLM tag（禁 latest）。`/dba` `gateway_ref` 加列、禁改 `channel_id` 类型。不代选六问。

## Do not re-litigate

市场微服务；LiteLLM 并根 compose；网关 DSN；resume pyc；Q-LLM 再开放；Wave L=FR-60；六问代选；重开 QA-01…37 / SH-01…18 / TK-01…04；新建聊天 UI；测试内 llm_chat 勾 70.7；入队 200 勾 Then；金标 `test_trigger_plan_endpoint` 当 70.1；只靠 `test_create_endpoint_rejects_operator` 勾 FR-73；T-16 单独勾 70.3/70.4/74.3「是」；T-13「相关 pytest」；`or_cell_failure` 一名三格；整文件 `test_saas_byok.py` 当 T-16 绿闸；T-20 用失败格勾 70.1；只跑 Pricing.test 勾 T-01 70.4。
