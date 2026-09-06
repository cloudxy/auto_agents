---
name: cicd
description: 配置 GitHub Actions CI/CD 流程
trigger: >-
  配置自动化部署、设置 CI/CD、添加持续集成、生成 GitHub Actions 工作流
---

# 配置 CI/CD 流程

权威文件：`.github/workflows/ci.yml`。本 skill 是往这份工作流加 job / 改步骤，不是再生成 `Backend Tests.yml` + `Frontend Tests.yml` + SSH Deploy。

现有 job 与改法见 [references/workflow-templates.md](references/workflow-templates.md)。

## 触发场景

- "配置自动化部署"
- "设置 CI/CD"
- "添加持续集成"

## 执行流程

### Step 1: 确认缺口

现有流水线已经覆盖：ruff + pytest（`fail_under=70`）+ MySQL 保真子集、`check-arch.sh`、`check-db-ir` / `check-db-migrations`、`check-frontend.sh` + admin/official build/test + Playwright e2e、`docker compose config` + `docker build`、main/tag 推 GHCR。

先问要补的是哪一段，而不是脚手架一套并行 workflow。

### Step 2: 改 `ci.yml`

Python **3.13** + `astral-sh/setup-uv` + `uv sync`。前端根 `npm ci`（workspaces lock 在仓库根 `package-lock.json`）。密钥用 `AUTO_AGENTS_JWT__SECRET_KEY` 这类，不要 `OPENAI_API_KEY`。

镜像发布已在 `ghcr-publish` job（push main / tag）。不要再加 appleboy/ssh-action 除非用户明确要 SSH 部署。

## 验证

推当前分支，看 GitHub Actions 五段 + 可选 GHCR。本地对应命令见 `/verify`。
