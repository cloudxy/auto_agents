# Docker 部署模板

## Backend Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd -m appuser && USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
```

## Frontend Dockerfile

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

## docker-compose.yml

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

## .env.example

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

## 部署命令

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
