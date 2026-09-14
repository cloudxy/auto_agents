# architect memory · post-merge-upgrade

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-13
- Hat: shape（FR>20 → 合同+ADR+票表，无 tickets/T-nn.md）
- Outputs: `02-shape/contract.md` v1；`02-shape/adr-0026-two-legal-fulfill-paths.md`

## Facts

- 读码 tip `1db6a47` feat/litellm-l1 ⊃ origin/main。不新建可部署单元。
- W2 断点：`confirm_paid` 拒 CHECKOUT_PRODUCTS；未配通道 `create_checkout` 零新行；Usage 仍挂 BillingPanel；文案「已有未完成的支付」。
- ADR-0026 supersede 0024 决策1绝对句/2/5，及 0025「仅 U38 写 SKU」+企业档不开中转。0019/0020 保持。`plan_pro` 仍不开中转。
- 040 `pro.quota_json`=20/500k/5M ≠ 定价页 50/200k/5M。履约必须写定价页。
- 出站三环含 api_keys；FR-M20 拉数只出站表。
- 值班叶「中转站管控」+ `/litellm/keys` API。用户可见叶子必须=1。
- Settings 租户说明态 ≠ GWT-M33.5 404。
- 票 T-01…T-24。W1=1.5 人周、W2=2、W3=1.5、W4=1.5、W5=1。W1≠live 同一 2 人周。
- [SEC-1] 通道验真 [SEC-2] 出站平面 [SEC-3] 确认金额/本笔。

## Open (mine)

- 无产品 Q-*。live 验真算法仍不选。C2 归 sre，不勾代码 FR。

## Do not re-litigate

Q-* 六问；ADR-0010 拆服务；统一 sk-；W2 接真收银台；标 GA；印当前可买；用 U32.2/U30.2 否决确认收款；xlsx；取消入口。
