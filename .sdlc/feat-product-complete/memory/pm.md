# pm memory · feat-product-complete

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-11
- Hat: define 增补周期 rework r2（并案 QA-31…39；Grok 复审 4 major + 5 minor）
- Outputs: spec.md v1.5 · user-story.md v1.5（区间同步）· metrics-blueprint.md **零改动**（hash cbefaece 未变）。`check-sdlc.sh --require --hat define` exit 0。

## Facts

- Q-QUEUE-DEPTH 已决**接通** / Q-OVERVIEW-3Q 已决**三问驾驶舱**（2026-09-11 操作者，state closed_questions）。spec §9.2 两行 + 文头「禁止再问」；Q-ADMIN-WAVE 行内旧「接通或下架」已改为「已由 Q-QUEUE-DEPTH 钉死接通」。
- v1.5 修法：QA-31 = FR-105 接通单支（GWT-105.1 唯一正常路径含静默窗；GWT-105.2 标记 [作废] 留位不重排，下架支入 §5；105.3 改可失败形态、删四栏目枚举）。QA-32 = GWT-82.4 Then 尾 + FR-102 preamble 尾互写边界（平台租户身份仅用于采集入队与方案归属）。QA-34 = §1.7 显式折算规则（Wave A 行加总 11.5–17.5 重叠计入，5–8=并集折算；停判线 >21 不动）。QA-39 = 权限矩阵负责人/公司管理员行补「设本域默认模型（FR-97）」+ GWT-97.1/97.2 主语点名。
- 拆格纪律第二次应用：GWT-93.5 改写为 username 格，**顺延追加** 93.7（email）/93.8（再恢复）/93.9（重复恢复，Then=保持启用+不重复报 user_restored）；93.4 Then 尾补占用语义（username 同租户判 / email 全局判——操作者并案给的业务规则）。§3.1 软删流转表同步两行。
- user-story v1.5 区间：US-A-01=93.1…93.9、US-A-02=95.1…95.7、US-A-06=100.1…100.8、US-A-08 注明接通已决。文头已关勿再问补 Q-QUEUE-DEPTH/Q-OVERVIEW-3Q。
- spec 文头「禁止再问」此前漏 Q-ADMIN-WAVE，本轮一并补齐（与 user-story 对齐）。
- v1.4 修法仍真：NFR-04 导入收容 + GWT-100.7/100.8/95.7；GWT-104.2「本波不保留独立入口」（QA-37 只改前言残留许可句）；GWT-95.1 重名冲突。
- 旧事实仍真：Wave A FR 93…105 map；appetite 15–21、停判线 >21；AutoAgents=站点名；平台租户不可改/删/停、不入 WACT/PC；蓝图仍 v1.4（spec §6 引用 v1.4 是蓝图版本号，非 spec 版本）。

## Do not re-litigate

- QA-01…QA-30 闭合句未回退；QA-20…24 open-carry 带入 shape。
- Q-LLM/Q-BILL/Q-RELAY/Q-OPS-DUTY/Q-ADMIN-WAVE/Q-QUEUE-DEPTH/Q-OVERVIEW-3Q 已决；六问不代选（含 Q-C-REG，已入文头禁代选）；不碰 02-shape。
- 隐患仍开：任务模板隐藏 tab 维持现状；企业删除不开。
