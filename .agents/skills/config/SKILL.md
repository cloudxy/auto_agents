---
name: config
description: >-
  配置规范 - 环境隔离、敏感信息管理。当用户新增配置项、创建环境配置文件、
  或排查配置加载与覆盖问题时触发。
  适用于 Dynaconf 多层合并配置管理、.env 敏感信息隔离、
  环境覆盖（default → dev/local/prod）以及命名空间组织的场景。
trigger: >-
  新增或修改配置、环境隔离问题、敏感信息管理、配置目录结构调整、
  Dynaconf 配置合并疑问
---

# 配置规范

本规范定义项目的配置管理准则。

## 核心原则

1. **配置与代码分离**：代码不知道运行在哪个环境，配置告诉它
2. **多环境隔离**：`default/`（共享）+ `dev/local/prod/`（覆盖）
3. **敏感信息不入库**：密码、密钥放 `.env`，不提交 Git
4. **命名空间**：`settings.MYSQL.HOST` 比 `settings.HOST` 更清晰

## 环境切换

通过 `APP_ENV` 环境变量切换：

```bash
APP_ENV=dev    # 开发环境
APP_ENV=local  # 本地环境
APP_ENV=prod   # 生产环境
```

配置优先级：`prod/` > `local/` > `dev/` > `default/`

## 目录结构

```
config/
├── __init__.py      # 配置入口，读取 Dynaconf
├── default/         # 共享配置（所有环境通用）
│   ├── settings.yml
│   ├── database.yml
│   └── ...
├── dev/             # 开发环境覆盖
├── local/           # 本地环境覆盖
└── prod/            # 生产环境覆盖
```

## .env 文件

敏感信息必须放在 `.env` 文件中：

```bash
# 数据库
DB_PASSWORD=your_password_here
DB_HOST=localhost

# Redis
REDIS_PASSWORD=your_redis_password

# JWT
JWT_SECRET=your_jwt_secret_key

# 第三方 API Keys
OPENAI_API_KEY=sk-xxx
```

**禁止**：
- 将 `.env` 提交到 Git（已在 `.gitignore` 中）
- 在代码中硬编码敏感信息
- 在日志中打印敏感信息

## 使用方式

```python
from config import settings

# 数据库配置
db_host = settings.MYSQL.DEFAULT.HOST

# Redis 配置
redis_host = settings.REDIS.DEFAULT.HOST

# JWT 配置
jwt_secret = settings.JWT.SECRET
```

## 验证清单

新增配置时检查：

- [ ] 是否放在 `default/` 目录（共享配置）
- [ ] 是否有环境覆盖需求（dev/local/prod）
- [ ] 是否包含敏感信息（密码/密钥 → `.env`）
- [ ] 命名是否有命名空间（`settings.MYSQL.HOST`）
