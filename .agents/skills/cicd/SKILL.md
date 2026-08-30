---
name: cicd
description: 配置 GitHub Actions CI/CD 流程
trigger: >-
  配置自动化部署、设置 CI/CD、添加持续集成、生成 GitHub Actions 工作流
---

# 配置 CI/CD 流程

当用户需要自动化部署时，使用此 Skill 生成 GitHub Actions 工作流。

## 触发场景

- "配置自动化部署"
- "设置 CI/CD"
- "添加持续集成"

## 执行流程

### Step 1: 确认 CI/CD 需求

1. 目标分支（main/test）
2. 是否需要测试环境
3. 部署方式（SSH/Docker/K8s）
4. 是否需要人工审核

### Step 2: 生成工作流

根据需求确认结果，从 [references/workflow-templates.md](references/workflow-templates.md) 中选取并定制以下工作流：

| 工作流 | 用途 |
|--------|------|
| 后端测试工作流 | pytest + MySQL/Redis services + uv workspace |
| 前端测试工作流 | npm test + build，matrix 覆盖 admin/official |
| 部署工作流 | SSH 部署 + 人工审核（Environment Protection） |
| Secrets 配置 | DOCKER_USERNAME / PROD_SERVER_* 等 |
| Environment Protection | production 需审核，test 无保护 |
