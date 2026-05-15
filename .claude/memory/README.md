# 项目记忆条目格式

每个条目是 `.claude/memory/<kebab-case-slug>.md`，必须有 frontmatter：

```markdown
---
name: redis-queue-contract
description: 爬虫→backend 通过 Redis 单向投递的字段契约和 key 命名约定
metadata:
  type: reference
  origin: PR#42 / 2026-05-15
  status: active
---

# 标题（与 description 一致）

正文 …

## 相关
- [[other-memory-slug]]（链接其他条目）
- `.claude/rules/project_rule.md#爬取与存储分离`
```

## 字段说明

| 字段 | 必填 | 取值 |
|------|------|------|
| `name` | ✅ | kebab-case，与文件名一致 |
| `description` | ✅ | 一句话，进 `MEMORY.md` 索引 |
| `metadata.type` | ✅ | `reference \| troubleshooting \| playbook \| decision` |
| `metadata.origin` | 推荐 | PR# 或日期，便于审计 |
| `metadata.status` | 可选 | `active`（默认）/ `deprecated` |

## 规范

- 文件名 = name = kebab-case，例 `uv-workspace-pitfalls.md`
- 单条 ≤ 500 行，超出请拆分
- 链接其他条目用 `[[slug]]` 形式
- 不要把临时调试记录写进来 —— 用 git commit message
- 不要把 user-level 偏好写进来 —— 那是 `~/.claude/projects/...` 的领地
