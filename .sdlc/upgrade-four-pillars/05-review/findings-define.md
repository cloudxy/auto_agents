# FINDINGS · define · upgrade-four-pillars

> 作者：G-fresh reviewer（经理落盘）｜stage: define｜decision: **fail**  
> blocker 1 · major 4 · minor 2 · 未豁免

## Snapshot

| path | sha256 |
|---|---|
| 01-define/spec.md | 59aae21045fb99d909df900beebdfd9279a4d012af1984d151dc685a0cef01cd |
| 01-define/user-story.md | 078e3d6417a60829fd9326d3d76a62f2445c3a9e2eb9fa3b21ca6a071cc8482c |
| 01-define/metrics-blueprint.md | dedc90d30170cd5aa2800a488d159674f1692bb08a9282b484bf0e14ece71431 |
| 00-discover/briefing.md | 663569c800e902edf1df900551e225cd192b0a8bd40ef6ac7f738138154db68d |
| state.yaml | 06098429d7ba0c6aa4a84f223ea062377b4ef8ccc0abdb7f8d163d41386f7625 |

## QA-01 支付回调未规定验真不得履约

- **维度**：4 安全
- **严重度**：blocker
- **证据**：FR-U33 Given「回调成功」即开通；NFR-U04 无通知验真；q_security: yes。
- **修复**：通道通知必须绑定本笔待支付（商户、金额、订单号一致）且视为通道侧真通知；否则保持未开通。补伪造/金额不符/商户不符 GWT。标 `[SEC-n]`。

## QA-02 v2 直打中转页 404 与「我的渠道组见掩码」互否

- **维度**：6 契约一致性
- **严重度**：major
- **证据**：v2 GWT-07.3 / FR-14 仍有效；本 spec 未 supersede；GWT-U20.1 打开渠道组见掩码。
- **修复**：§0 显式 superseded：值班页仍 404 同形；已开通 SKU 的「我的渠道组」= 本企业用量 + 无上游 Key 全文。

## QA-03 「申请提升」同时指向联系说明与结账

- **维度**：6 契约一致性
- **严重度**：major
- **证据**：v2 GWT-12.6 仍有效「本波不必支付」；US-N1-02 指向 US-N3-02 结账。
- **修复**：supersede GWT-12.6：只读→联系本企业管理员；买方→结账。GWT-U02.4 写明 CTA 着陆。

## QA-04 spec §6 与蓝图口径竞争

- **维度**：6 契约一致性
- **严重度**：major
- **证据**：声明以蓝图为准仍留竞争表；D3/支付失败 reason 未落到 FR GWT。
- **修复**：删 spec §6 竞争表或与蓝图逐句对齐；补拦住 vs 完成、timeout/channel_error/unconfigured GWT。

## QA-05 权限矩阵缺已开通后的越权 GWT

- **维度**：8 边界
- **严重度**：major
- **证据**：已开通后经办签发、超管代付、到期旧令牌无 Then。
- **修复**：补对应越权/副作用 GWT。

## QA-06 「长时间」未绑 3 秒；GWT-U23.3 双对象；N3 4–8 使 50% 闸不可算

- **维度**：2 标准质量
- **严重度**：minor
- **修复**：GWT 引用 NFR-U01 的 3 秒；拆 U23.3；N3 钉一个上限人周。

## QA-07 「当前可买」禁区只覆盖三页

- **维度**：7 规范
- **严重度**：minor
- **修复**：Q-AGPL 关闭前四字禁区扩到所有访客/租户可见面。

## 总计

blocker 1 · major 4 · minor 2 · **decision: fail**
