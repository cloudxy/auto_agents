# ops memory · upgrade-four-pillars

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-13
- Hat: ops / enablement
- Outputs: `06-deliver/enablement.md`（N1–N4 有条件放行，非四柱 GA）

## Facts

- qc：有条件放行 N1–N4，非 GA。对外第一句=采集。支付成功=驱动，不是北极星。值班「活」≠中转已买。
- 四面第一次成功：经办=空租户交差或 3s 工人/配额句（gate）；买方=结账支付宝/微信或通道空态（不陈述可买）；租户管理员=不能上架/改平台权限，直打 `/rbac` `/newapi`=404 同形；超管=上架+总开关、商户凭据掩码、值班三态。
- 入口只引用 `02-shape/edge-states.md` 屏 1/2/6–11/13/15/18–24。不重画。
- 教结账路径与单据态；不宣布生产收银台已接通（合入闸不含沙箱）。收费故事未选定 → 禁那四个连字。
- 预发夹具出数 ≠ 生产北极星已出现。不写服务时效数字。环境只称预发/生产。
- 夹具加入/移出无 designer 独立屏 → open_question。SSO 本波 N/A。现网「提交升级申请」作废。

## Open (mine)

- designer：夹具名单维护菜单入口未入屏矩阵。
- 生产收款接通后才能把「去支付」从预发教法改成生产口播；接通前客服只对空态/单据态。

## Do not re-litigate

- 把 N1–N4 写成四柱 GA / 北极星已在生产出现。
- 可见面陈述可买。
- 值班「活」当已买中转。
- kubectl / 回滚 / 告警（sre）。
- 把拦住当成没人要采集；把 404 同形当故障。
- 新开 FR 填「用户不知道从哪交差 / 不知道结账 / 把上架当租户菜单」。
- 退回 N1-only「完全不教结账」——本轮要教路径，仍不宣布能付完。
