---
name: cicd
description: 配置 GitHub Actions CI/CD 流程
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

### Step 2: 生成后端测试工作流

```yaml
name: Backend Tests

on:
  push:
    branches: [main, test]
    paths:
      - 'backend/**'
      - 'scrapy/**'
      - 'platform_core/**'
      - 'config/**'
      - 'pyproject.toml'
      - 'uv.lock'

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: test_password
          MYSQL_DATABASE: test_db
        options: >-
          --health-cmd="mysqladmin ping"
          --health-interval=10s
          --health-retries=3
        ports:
          - 3306:3306
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd="redis-cli ping"
          --health-interval=10s
          --health-retries=3
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Setup Python
        run: uv python install 3.13

      - name: Install dependencies (uv workspace)
        run: uv sync --frozen

      - name: Run tests
        env:
          APP_ENV: dev
        run: uv run pytest backend/tests platform_core/tests -v --cov=backend --cov=platform_core --cov-report=xml
```

### Step 3: 生成前端测试工作流

```yaml
name: Frontend Tests

on:
  push:
    branches: [main, test]
    paths: ['frontend/**']

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        app: [admin, official]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/${{ matrix.app }}/package-lock.json

      - name: Install & test
        working-directory: frontend/${{ matrix.app }}
        run: npm ci && npm test -- --watchAll=false && npm run build
```

### Step 4: 生成部署工作流

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    
    steps:
      - name: Wait for approval
        if: github.ref == 'refs/heads/main'
        uses: trstringer/manual-approval@v1
      
      - name: Deploy
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.PROD_SERVER_HOST }}
          username: ${{ secrets.PROD_SERVER_USER }}
          key: ${{ secrets.PROD_SERVER_SSH_KEY }}
          script: |
            cd /opt/myapp
            docker-compose pull && docker-compose up -d
```

### Step 5: 配置 Secrets

在 GitHub → Settings → Secrets and variables → Actions 中添加：

```
DOCKER_USERNAME
DOCKER_PASSWORD
PROD_SERVER_HOST
PROD_SERVER_USER
PROD_SERVER_SSH_KEY
```

### Step 6: 配置 Environment Protection

在 GitHub → Settings → Environments 中：

- **production**：Required reviewers（至少 1 人审核）
- **test**：无保护规则
