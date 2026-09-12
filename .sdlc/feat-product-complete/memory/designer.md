# designer memory · feat-product-complete

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-11
- Hat: designer / shape
- Outputs: `02-shape/edge-states.md` **v2**（Wave A 增补 FR-93…105）· `02-shape/sitemap.md`（v1 未动）

## Facts

- edge-states v2：FR-93…105 全入册，新屏=用户管理/企业管理/中转站三 tab/一键导入向导/采集方案/告警规则/专家团弹窗；v1 Wave C/U 各屏原样未动。
- 中转站：网关空态只 71.2/71.3 两句（第三套禁止）；事件列表空态是列表空态、不是网关空态。立即探测入口仅总览每渠道行；探针 tab 不设第二入口。三问三区独立失败互不拖垮。
- LLM 空态句已替换为 GWT-97.3 钉句「还没有模型供应商。」（v1 的「还没有本企业供应商。添加并激活后…」作废）；「激活」只许出现在移除/禁令语境。
- 设为默认 = 负责人/公司管理员（v1.5 矩阵落位）；经办/只读无控件，经办旁注「当前账号不能设置默认，请联系企业管理员」（新造同族句）。切换有确认弹窗；无默认时表格上方文字提示（非横幅）。
- 平台租户保护呈现：名称字段只读 + 旁注 94.2 句、停用控件禁用 + 旁注 94.3 句（句在 UI 可见，后端守卫保持）；行带「默认归属」Tag；改名冲突句含冲突域（既有名∪平台租户∪AutoAgents）。
- 恢复占用冲突 = 内联红字两行（钉句 + 「该用户仍保留在已删除列表中。」），弹窗不关。
- 页头规范 §0.10：token `page-header.*` / `tab-switch.motion`；条件态提示 ≠ 装饰横幅（无工人横幅 FR-85 保留）。§0.11 = FR-96 可见口径（fallback 只在内容区；路由归 ADR-0022）。
- 自检：`check-sdlc.sh --require --hat designer` exit 0。

## Open (mine)

- 经办在 LLM 页是否保留供应商行添加/编辑写权（FR-97 未改写，edge-states 按既有=保留）——实现前找 pm/architect 确认一句。
- Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL / Q-OPS-COLLECT / Q-C-REG 仍是操作者的。

## Do not re-litigate

- Five groups; platform 404 isomorphic; 90.2 not 404; FR-91 无票不设计落点; QA-40 不建 demo 来源分组; FR-84 句式不写第二套; queue_depth 单支接通; 明文只一次。
