# pm memory · feat-four-pillars-v2

> Facts this role learned (**what**). Cap 2200 chars.

## Last

- Date: 2026-09-08
- Hat: 定义（并入 Q-LLM 用户可见合同 + 关 QA-31；下一步独立 G-fresh 第 5 轮）
- Outputs: `01-define/spec.md` v1.4 · `user-story.md` · `metrics-blueprint.md` v1.4 · `CONTEXT.md` 中转站词条

## Facts

- v2 全新 PRD。D1–D29 不重开。未塑形。
- **Q-LLM 已决：** 平台 LLM 数据面 = LiteLLM Proxy；new-api **退出运行时**（退役，非长期双通道）。禁止再标待确认 / 「不在本 PRD 选择」/ 「禁止代选 Q-LLM」。
- **Wave L** 第一等波，appetite **4–6pw**（architect），插在 Wave 0 之后、不晚于 Wave 1 市场评分依赖稳定平台路径。Wave 0 仍 **5–7**：只密钥离树（FR-14）+ 值班写权 + FR-12 接线，不塞完整切换。
- Wave L 冻结 **FR-70…75**：规划/评分/平台聊天走 LiteLLM；BYOK 直连（FR-73）；值班空态区分没配过 vs 网关挂（FR-71）；new-api 退役（FR-72）；网关挂≠套餐句（FR-74，与 GWT-12.5 同一句）；密钥不进 git（FR-75）。
- **不得**做成 Wave 3 stub。FR-60/61 仍阻塞 Q-RELAY（租户产品面）。
- 范围外：不另起市场微服务；不把 LiteLLM 并进根编排；不发租户虚拟令牌。
- Q-AGPL：退役 new-api 后运行时不再绑其 AGPL；对外收费故事仍待，不代选。
- **QA-31 closed：** GWT-32.12（A 过闸可列；E 未放行许可、F 已上架+实验/测试中/已弃用 不列）。
- 北极星 WACT。查询面仅超管。商店不存在句只约束 GET 详情。GWT-33.4/33.5、GWT-32.9/10/11 保持。

## Open (mine)

- 六问待确认：Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL。
- Q-OPS-DUTY / Q-OPS-COLLECT。
- 对应问关闭前，相关 FR 不得当已选解法进方案帽（Wave L 数据面除外）。

## Do not re-litigate

- D22–D29；展示≠停用；订插件不带礼包；七叶；出数环不 stub。
- QA-01…31 closed；勿把 HTML 404 套到订阅提交；勿把 33.4 当「没拉全表」证明。
- 安全/权限/一致性/出数环不砍。
- Q-LLM 已决；不得把 Wave L 写成 FR-60；不得长期双通道当卖点。
