# 项目记忆索引（MEMORY）

> 项目级长期记忆，随 git 走、团队共享。
> 区别于 `~/.claude/projects/-Users-xuyun-Projects-auto-agents/memory/`（个人偏好）。
>
> 本文件是**索引**，详情在 `.claude/memory/<slug>.md`。
> 每行 ≤ 150 字符，总行数 ≤ 200（超出请用 `/memory-curator` 归并）。
>
> 条目格式见 `.claude/memory/README.md`。

## 索引

| 条目 | 类型 | 摘要 |
|------|------|------|
| _暂无_ | _-_ | 后续随项目演进追加 |

<!--
示例：
| [redis-queue-contract](memory/redis-queue-contract.md) | reference | 爬虫→backend 通过 Redis key `auto_agents:items:<spider>` 单向投递，禁止双向 |
| [uv-workspace-pitfalls](memory/uv-workspace-pitfalls.md) | troubleshooting | 子包加依赖必须 `uv add --package`，不能 cd 进去 |
| [alembic-flow](memory/alembic-flow.md) | playbook | 模型改→`alembic revision --autogenerate`→人工 review→`alembic upgrade head` |
-->

## 类型枚举

- **reference**：稳定事实，例如外部 API 契约、约定俗成的命名
- **troubleshooting**：踩过的坑 + 排查路径
- **playbook**：可重复执行的多步操作流程
- **decision**：架构/技术选型决策 + 理由

## 维护规则

- 新条目由 `memory-curator` agent 产出 diff，**用户 review + apply** 后才入库（hook 半自动进化）
- 重复 / 过时条目通过 `/loop 1w /memory-curator` 周期归并
- 条目失效时打 `STATUS: deprecated` 而非直接删，保留历史
