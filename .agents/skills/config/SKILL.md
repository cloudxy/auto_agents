---
name: config
description: >-
  配置规范 - 环境隔离、敏感信息管理。当用户新增配置项、创建环境配置文件、
  或排查配置加载与覆盖问题时触发。
  适用于 Dynaconf 多层合并配置管理、.env 敏感信息隔离、
  环境覆盖（default → <env>）以及命名空间组织的场景。
trigger: >-
  新增或修改配置、环境隔离问题、敏感信息管理、配置目录结构调整、
  Dynaconf 配置合并疑问
---

# 配置规范

事实源：`config/__init__.py`。不要另写一套加载顺序。

## 核心原则

1. 代码不硬编码环境；`APP_ENV` 决定读哪一层
2. 敏感信息不入库：放 `config/<env>/.env`，用 `AUTO_AGENTS_*` 覆盖
3. 命名空间：`settings.MYSQL.DEFAULT.HOST`，不要 `settings.HOST`

## 加载顺序（后者覆盖前者）

1. `config/default/*.yml`
2. `config/scrapy/default/*.yml`
3. `config/<env>/*.yml`（`<env>` = `APP_ENV`，缺省 `local`）
4. `config/scrapy/<env>/*.yml`
5. `config/<env>/.env`
6. 环境变量 `AUTO_AGENTS_*`（最高优先级；嵌套用双下划线）

一次只加载一个 `<env>`，**不是** prod > local > dev 叠四层。

```bash
APP_ENV=local   # 默认
APP_ENV=dev
APP_ENV=prod
```

## 目录

```
config/
├── __init__.py
├── default/          # settings.yml jwt.yml log.yml ...
├── local/            # mysql.yml redis.yml + .env
├── dev/
├── prod/
└── scrapy/
```

没有 `config/default/database.yml`。MySQL 在 `config/<env>/mysql.yml`。

## 环境变量

`envvar_prefix="AUTO_AGENTS"`。嵌套键：

```bash
export AUTO_AGENTS_JWT__SECRET_KEY="..."
export AUTO_AGENTS_MYSQL__DEFAULT__HOST="mysql"
export AUTO_AGENTS_API__HOST="0.0.0.0"
export AUTO_AGENTS_API__PORT="9111"
```

`.env` 示例（只放密钥，不要提交）：

```bash
# config/local/.env
MYSQL_DEFAULT_PASSWORD=...
REDIS_DEFAULT_PASSWORD=...
AUTO_AGENTS_JWT__SECRET_KEY=...
AUTO_AGENTS_WEBHOOK__SECRET_KEY=...
```

扁平 `DB_PASSWORD` / `OPENAI_API_KEY` 不是本仓库约定。LLM 走 `config/default/llm.yml` + `AUTO_AGENTS_LLM__*`；LiteLLM sidecar 默认关（`LITELLM.ENABLED` 等保持 false）。

## 使用

```python
from config import settings

host = settings.MYSQL.DEFAULT.HOST
redis_host = settings.REDIS.DEFAULT.HOST
jwt_secret = settings.JWT.SECRET_KEY
```

## 新增配置清单

- [ ] 非密钥：`config/default/<域>.yml` 带命名空间
- [ ] 环境差异：只写 `config/<env>/` 覆盖，不要复制整份 default
- [ ] 密钥：`config/<env>/.env` 或 `AUTO_AGENTS_*`
- [ ] 读取用 `settings.DOMAIN.KEY` / `settings.get("DOMAIN.KEY", default)`
