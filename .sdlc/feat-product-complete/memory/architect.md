# architect memory · feat-product-complete

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this.

## Last

- Date: 2026-09-11
- Hat: shape 微补轮（contract v2→v2.1，implement 终审回写）
- Outputs: `02-shape/contract.md` v2.1：§7.1 追加 8 个已实现错误码；§7.4 GWT-60.6 写面例外（IMPL-QA-1）；§7.9 GWT-93.6 越权行 IMPL-QA-3 注记；§19 v2.1 行。其余零改动（头版号仍 v2，按包指令不动）。

## Facts

- v2 基线（票映射/读码锚）见 contract §1/§4/§11/§12，不在此复制。票号：93=24/25（92.8→24）；94=26；95=27/28；96=29；97=30；98=31/32/33；99=34；100=35/36（92.9→35）；101=37；102=38；103=39/40；104=41；105=42。
- 8 个已实现码（IMPL 终审 a 项追认，均用户可见中文句、code 不渲染）：ORDER_ROLE_NOT_ALLOWED / ORDER_ONLINE_UNAVAILABLE / TASK_QUOTA_LIMIT_REACHED / TASK_RUN_ROLE_NOT_ALLOWED / RELAY_TOKEN_ROLE_NOT_ALLOWED / RELAY_GROUP_ROLE_NOT_ALLOWED / OUTBOUND_KEY_ROLE_NOT_ALLOWED / RELAY_GATEWAY_UNAVAILABLE。
- IMPL-QA-1：GWT-60.6 分裂形态=页面/GET 面 404 同形 + API 写面（改窗口/冷却/熔断）既有 403（GWT-70.3 金标钉住不破），已裁决不得互改。IMPL-QA-3：GET /admin/users 维持 require_admin 既有行为（r13 金标；列表限本租户行），93.6 同形语义由平台页守卫+恢复动作面兑现。
- check-sdlc `--require --hat shape` 退出码 6：全部是 state.yaml 六个待确认开放问题（Q-VOICE/PRICE/MARKET-USER/AGPL/OPS-COLLECT/C-REG）触发「禁入 implement」门——编辑前已存在、与 contract 无关；本帽禁代答（G1–G4），不得为绿灯改 state.yaml。
- 并行雷区（历史）：T-24×T-26 同动 user_service.py；T-31→32→33 同动 NewApiOps.tsx；T-29 先于 T-34。
- QA-05 夹具：60.3 必须真实 chat 认证响应，裸 httpx 200 不算。QA-08：列表读本地缓存禁每行打网关。QA-40：幽灵项「demo/内部项来源分组展示形态」全文只许以禁令出现。

## Open (mine)

- 导入深度扫描（病毒）未做 → /sre 账本（contract §13 残留），长期项。

## Do not re-litigate

- 不代选 Q-VOICE/PRICE/MARKET-USER/AGPL/OPS-COLLECT/Q-C-REG。
- 不标四柱 GA。不焊 litellm 进根 compose。FR-91 无票。
- `_apply_plan` 不是 FR-50 Then。不把 `test_billing_relay.py` 四测当 50/60 完成。
- 已关勿再问：Q-ADMIN-WAVE/Q-QUEUE-DEPTH（接通）/Q-OVERVIEW-3Q（三问驾驶舱）。
