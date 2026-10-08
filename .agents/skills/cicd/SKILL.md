---
name: cicd
description: >-
  Edits the five-stage GitHub Actions workflow at .github/workflows/ci.yml.
  Use when 加 CI, 改 GitHub Actions, lint/test/arch/frontend 门禁.
---

# 配置 CI/CD

先读 `.github/workflows/ci.yml` 再改。约束：[references/workflow-templates.md](references/workflow-templates.md)。

## Route

| 观察到 | 先做 |
|--------|------|
| Dockerfile / compose / 端口 / 卷 | `deploy` |
| 改 CI job、门禁、Secrets | 本 skill |

## Quick start

Copy and check off:

```
cicd:
- [ ] 五阶段仍在：python-lint-test / arch-check / db-migration-gate / frontend-build / docker-validate
- [ ] 门禁用 tools/check/*，不手写第二套 grep
- [ ] 前端：根 package-lock + 先 shared dist
- [ ] bash tools/check/arch.sh
- [ ] bash tools/check/frontend.sh
- [ ] docker compose config --quiet
```

push 任意分支 + 向 main 的 PR 跑上述 job。发布另开 job，密钥用 GitHub Secrets。

## 完成时回复

1. `.github/workflows/ci.yml` 里改了哪个 job
2. 本地跑过的 `tools/check/*` 原文
3. 五阶段名字仍在（列出来）

## Examples

**Input:** 「CI 加上架构检查」

**Then:** 在现有 `ci.yml` 加 `arch-check` job，`run: bash tools/check/arch.sh`，不新建第二份 workflow。
