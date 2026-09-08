# algo memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-08
- Hat: define / diagnosis
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/algo.md`

## Facts

- 2026-09-08 现网：0 eval-set；`eval/` 零命中。`check_llm_tokens_month` 仅定义+两测试，`llm_chat` 未调。`LLM.ENABLED`/`SKILLS.SCORING.ENABLED` 默认 false。MCP list≥1 后空参即 healthy；无 MCP → verify `degraded`。探针 6 题、阈值 0.15。`derive_tier` 无人分吃 AI 分；`PublicSkillResponse` 含 score/tier。试采闸 `avg_score≥40`。`SpiderService.enqueue` 不转发 tenant_id；orchestrator 试采不传。
- 主缺陷名仍是 scoring-without-eval。不选定厂商。拒绝 RAG。
- **v2 判据**：可卖=向导+人工确认+（接线后的）套餐真闸；示意=官网四步/公开 tier/healthy=能干活/探针正品/quality≥40=抽对。
- **不冻算法施工票**（评估集/换模型/开评分/改 0.15/规则规划器）。空 jsonl 目录也不进 T-xx。FR-10/FR-09 归 backend。实现帽可 skip algo。
- 旧 spec T-23/FR-72/FR-61、contract `/algo` N/A、ADR-0014、pitfalls P-AA-01…10 采信为输入，不复制为 v2 合同。
- 本帽未改模型调用代码。

## Open (mine)

- Q-A1 规则兜底是否可见（本波不实现）
- Q-A2 real_world_effect 无证据口径（评分未开）
- Q-A3 BYOK 效果白名单（本波只做套餐闸）
- Q-A4 MCP 空参失败分档
- Q-A5 similar 自动跑 → 建议否
- Q-A6 月成本/调用量
- Q-A7 公开 score/tier → 建议不展示
- Q-A8 评估集版权 → 踢出本程序

## Do not re-litigate

- 无评估集不得报准确率
- 不把 T-06 写成算法票
- 不引入 RAG / 微调 / LiteLLM 替换 / MCP 当工具面
- 不重开「未达 80% 是否禁止 register」（用试采+人工）
- 不把旧 feat-four-pillars 工件当现行合同
