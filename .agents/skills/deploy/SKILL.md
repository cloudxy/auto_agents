---
name: deploy
description: >-
  生成 Docker 部署配置。当用户需要将项目部署到服务器、进行容器化打包、
  生成或修改 Dockerfile / docker-compose.yml / .env 配置时触发。
  适用于首次部署、环境迁移、新增服务的容器化，以及调整已有部署的端口映射、
  环境变量、数据卷等配置的场景。
trigger: >-
  部署到服务器、生成 Docker 配置、容器化项目、环境迁移、
  调整端口映射/环境变量/数据卷、首次部署或新增服务容器化
---

# 生成 Docker 部署配置

当用户需要部署服务时，使用此 Skill 生成 Docker 配置文件。

## 触发场景

- "帮我部署到服务器"
- "生成 Docker 配置"
- "容器化这个项目"

## 执行流程

### Step 1: 确认部署信息

1. 部署环境（开发/测试/生产）
2. 是否需要数据库（MySQL/Redis）
3. 端口映射需求
4. 环境变量配置

### Step 2: 生成文件

根据部署信息，从 [references/docker-templates.md](references/docker-templates.md) 中选取并定制以下模板：

| 模板 | 用途 |
|------|------|
| Backend Dockerfile | Python 3.11-slim + uvicorn 启动 |
| Frontend Dockerfile | Node 多阶段构建 + nginx 静态服务 |
| docker-compose.yml | MySQL + Redis + Backend + Frontend 编排 |
| .env.example | 环境变量模板（DB / Redis / 端口） |
| 部署命令 | docker-compose up -d / logs / rebuild |

## 预期产出物

完成后**必须**存在以下文件，缺少任何一个 = 未完成：

```
✅ 文件清单
Dockerfile                                    # 后端容器（或按需求生成多个）
docker-compose.yml                            # 服务编排
.env.example                                  # 环境变量模板（无真实密码/密钥）
```

如包含前端部署，额外产出：

```
frontend/{admin,official}/Dockerfile          # 前端多阶段构建容器
nginx.conf                                    # 反向代理配置
```

## 验证步骤

生成配置后，**必须**依次执行以下验证（调用 `/verify`）：

```bash
# 1. Docker 构建检查
docker build -t _verify . && docker run --rm _verify echo ok
# 期望：build + run 退出码 0

# 2. docker-compose 配置验证
docker-compose config
# 期望：输出有效 YAML，无报错

# 3. 环境变量安全检查（禁止硬编码密钥）
grep -nE "password|secret|key" docker-compose.yml .env.example
# 期望：.env.example 用占位符，docker-compose.yml 用 ${} 引用

# 4. 服务启动验证
docker-compose up -d
sleep 5 && docker-compose ps
# 期望：所有服务状态为 Up / running
```
