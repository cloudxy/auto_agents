# frontend memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-10
- Hat: sdlc-workflow:frontend（qc cond B + NFR-07 44px）
- Outputs: `Register.tsx` · `Register.test.tsx` · `Home.tsx` · `Home.test.tsx` · `Pricing.tsx` · `Pricing.test.tsx` · `tokens.css` · `03-impl/prep-register-nfr07-evidence.md`

## Facts

- `FREE_TIER_FEATURE_COPY` =「5 个并发任务 / 10,000 条结果存储 / 20 万 LLM tokens/月」。Pricing / Usage / Register 同三句。Register 组合 `免费档：{三句}`，禁止手写 `10000`。
- GWT-01.1 Given 字面：`5` / `10,000` / `20 万`（用量页展示 `200,000`）。独立 oracle，禁止 `mock(DEFAULT_QUOTA); expect(DEFAULT_QUOTA)`。
- NFR-07：官网主按钮 minHeight/minWidth ≥44。`--size-touch: 44px` + `.site-touch-target` + 内联 `var(--size-touch, 44px)`（jsdom 量宽）。落点：Home 免费注册、Pricing 档 CTA、Register 创建企业/登录管理后台。
- 闸：Register+Home+Pricing Jest 25；GWT-04.1–04.4 未改断言。

## Open (mine)

- 前端 `DEFAULT_QUOTA` 与 backend 仍是拷贝。

## Do not re-litigate

- 不代选六问。不实现支付。不改 GWT。不 Wave 2/3。不把 Usage 默认夹具改成免费档上限。
