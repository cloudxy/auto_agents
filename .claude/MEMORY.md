# 项目记忆索引（MEMORY）

> 项目级长期记忆，随 git 走、团队共享。
> 区别于 `~/.claude/projects/-Users-xuyun-Projects-auto-agents/memory/`（个人偏好）。
>
> 本文件是**索引**，详情在 `.claude/memory/<slug>.md`。
> 每行 ≤ 150 字符，总行数 ≤ 200（超出请用 `/memory-curator` 归并）。
>
> 条目格式见 `.claude/memory/README.md`。
> 已执行计划不进 memory（清出工作区）。宣称对账见 `docs/claims.md`。
> 架构事实以 `project_rule.md` + `scripts/check-arch.sh`（13 红线 + 3 边界）为准。

## 索引

| 条目 | 类型 | 摘要 |
|------|------|------|
| [frontend-query-testing](memory/frontend-query-testing.md) | troubleshooting | useQuery 测试/构建：withQuery、queryFn 可选参、antd Alert/message |
| [playwright-admin-e2e](memory/playwright-admin-e2e.md) | playbook | admin E2E：build→e2e、NO_PROXY、端口 46112、记住我 |
| [litellm-billing-defaults](memory/litellm-billing-defaults.md) | decision | LiteLLM 默认全关；计费人工确认；webhook 租户 opt-in |

## 类型枚举

- **reference**：稳定事实，例如外部 API 契约、约定俗成的命名
- **troubleshooting**：踩过的坑 + 排查路径
- **playbook**：可重复执行的多步操作流程
- **decision**：架构/技术选型决策 + 理由

## 维护规则

- 新条目由 `memory-curator` 产出；主对话明确要求整理/写入时落盘
- 重复 / 过时条目归并；失效打 `STATUS: deprecated` 而非直接删
- 不写会话流水、不重复 `project_rule.md` / AGENTS.md 已有红线
- 个人 IDE 偏好留在 `~/.claude/projects/.../memory/`（如 PyCharm 模块依赖）
