---
name: deploy
description: >-
  Edits the existing root Dockerfile and docker-compose.yml. Use when 部署,
  容器化, 改端口, 环境变量, or volumes.
---

# Docker 部署配置

约束：[references/docker-templates.md](references/docker-templates.md)。生产步骤：`docs/ops/deploy.md`（本地私有，可能不在 git）。

## Route

| 观察到 | 先做 |
|--------|------|
| GitHub Actions / lint / 测试门禁 | `cicd` |
| 本机 `run.py` 启停，不改镜像 | 不用本 skill |

## Quick start

Copy and check off:

```
deploy:
- [ ] 读根 Dockerfile 与 docker-compose.yml（先改现有文件，不新建第二份）
- [ ] 容器 AUTO_AGENTS_API__HOST=0.0.0.0；端口与 api.yml / EXPOSE / health 一致
- [ ] 密钥只写 config/<env>/.env，键名对齐 .env.example
- [ ] docker compose config --quiet
- [ ] 若改了 Dockerfile：docker build -t auto-agents-backend .
```

命令用 `docker compose`（v2）。本地联调：`docker compose up --build`。宿主机 API：`bash init_project.sh` 后 `uv run python run.py`。

`config --quiet` 非 0：修 YAML 再跑同一条。

## 完成时回复

1. 改动的文件路径（Dockerfile / compose / `.env.example`）
2. `docker compose config --quiet` 的退出码
3. 若 build 了：镜像 tag 与最后几行

## Examples

**Input:** 「把 API 端口改成 9111」

**Then:** 同步 `config/default/api.yml`、`Dockerfile` 的 EXPOSE/HEALTHCHECK、`docker-compose.yml` 的 ports；再 `docker compose config --quiet`。
