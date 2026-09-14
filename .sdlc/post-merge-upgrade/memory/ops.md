# ops memory · post-merge-upgrade

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-14
- Hat: ops / enablement
- Outputs: `06-deliver/enablement.md`（qc 有条件放行，非四柱已完成）

## Facts

- qc：有条件放行。对外第一句=采集。不得宣称支付已通 / 市场已开店 / 北极星已在生产出现。可见面不陈述可买（营销四字）。
- 四面第一次成功：经办=空租户贴网址出数，无付费/订阅/中转前置；规划关=「智能规划未开放」→去采集任务。买方=结账「提交开通」；未配通道→待支付+「收款通道未开通，提交后等待平台确认开通」。租户管理员=出站只「出站拉数钥匙」；渠道组「未开通中转」vs「还没有令牌」。平台管理员=值班仅中转站管控；运营台确认收款；租户直打 404 同形。
- 入口只引用 `02-shape/edge-states.md` 屏 1–8、10–14、16–23。不重画。无 designer 待补屏。
- 教提交开通与待支付/已开通；不教收银台「去支付」当本波主路径。确认收款≠通道已接通。签发成功只给用法。
- 预发夹具出数 ≠ 生产北极星已出现。环境只称预发/生产。客服升级=平台管理员，不找开发。
- 旧 upgrade 教法作废：打开结账整页「收款通道未开通」不建单；「已有未完成的支付」；用量页套餐与订购。

## Open (mine)

- 无。生产通道指纹出现前，客服不得改口「去支付」为已接通（约束，不是未决产品问）。

## Do not re-litigate

- 四柱 GA / 支付已通 / 营销四字
- 规划「还没有规划」/ 已入队当规划成功
- 未开通中转 = 还没有令牌
- 出站与渠道组合一
- kubectl / 回滚 / 告警（sre）
- 把 404 同形当故障；把拦住当成没人要采集
- 新开 FR 填「用户不知道从哪交差 / 不知道提交开通」
