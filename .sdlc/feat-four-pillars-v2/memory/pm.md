# pm memory · feat-four-pillars-v2

> Facts this role learned (**what**). Cap 2200 chars.

## Last

- Date: 2026-09-08
- Hat: 定义（Wave L GWT 关 QA-36、QA-37；下一步独立 G-fresh 第 7 轮）
- Outputs: `01-define/spec.md` v1.6 · `user-story.md` v1.6

## Facts

- v2 全新 PRD。D1–D29 不重开。未塑形。
- **Q-LLM 已决：** 平台 LLM 数据面 = LiteLLM Proxy；new-api 退出运行时。禁止再标待确认。
- **Wave L** 第一等波，appetite 4–6pw。FR-70…75 产品意图本轮未改，只补验收格。
- **QA-36：** 73.5/73.6/70.2 各拆四条 When（规划 / 试采修复 / 技能评分 / 平台路径聊天）。73.5 族 Then = 本企业供应商侧调用或用量；不出现在网关侧；不打平台供应商直连、不打 new-api。73.6 族另不是 74.1「平台 LLM 网关不可达」、不是套餐超限句。禁止「进入/不进入 LiteLLM」当观察点。编号 70.8–70.10、73.7–73.9、73.10–73.12。
- **QA-37：** 74.1 Given = 月度 token 未尽、无本企业激活供应商、平台网关不可达。When 四条同 70.1/70.5/70.6/70.7（74.1/74.4/74.5/74.6）；不含失败。Then = 「平台 LLM 网关不可达」+ 不是套餐超限句 + 无 QUOTA_EXCEEDED，不得与 70.2 / 73.6 / 12.5 互勾。成本熔断只走 12.5。
- QA-01…35 保持 closed。metrics-blueprint 未牵动。

## Open (mine)

- 六问待确认：Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL。
- Q-OPS-DUTY / Q-OPS-COLLECT。

## Do not re-litigate

- D22–D29；展示≠停用；订插件不带礼包；七叶；出数环不 stub。
- QA-01…35 closed。
- 安全/权限/一致性/出数环不砍。
- Q-LLM 已决；不得把 Wave L 写成 FR-60；不得长期双通道当卖点。
- 不得把 73.1 当规划验收；不得用「Wave L 已完成」当 72.1 Given；不得把 12.5 与 74.x 绑成一格；不得把 70.4 与 60.1 写成同一句。
- 不得用进入/不进入 LiteLLM 当观察点；不得把失败写进 74.x When；不得把 BYOK 收成仅规划；不得用「对话」代替「平台路径聊天」。
