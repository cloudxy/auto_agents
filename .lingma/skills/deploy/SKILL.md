---
name: deploy
description: 生成 Docker 部署配置
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

#### Backend Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd -m appuser && USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Frontend Dockerfile

```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci && COPY . . && npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### docker-compose.yml

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "${DB_PORT:-3306}:3306"
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

  backend:
    build: ./backend
    environment:
      DB_HOST: mysql
      REDIS_HOST: redis
    depends_on:
      - mysql
      - redis
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  frontend:
    build: ./frontend
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  mysql_data:
  redis_data:
```

#### .env.example

```bash
ENVIRONMENT=production
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password_here
DB_NAME=myapp
REDIS_HOST=localhost
REDIS_PORT=6379
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

### Step 3: 部署命令

```bash
# 1. 创建 .env 文件
cp .env.example .env

# 2. 构建并启动
docker-compose up -d

# 3. 查看日志
docker-compose logs -f

# 4. 重新构建
docker-compose up -d --build
```
