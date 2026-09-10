# 架构扫描地图

执法入口：

```bash
bash tools/check/arch.sh
```

本页解释脚本在查什么。正则、排除目录、R12 白名单、R13 豁免以脚本为准。

## Contents

- R1–R13 红线
- B1–B3 边界
- 修复路由

## 红线（R1–R13）

| 规则 | 信条 | 脚本在查什么 |
|------|------|----------------|
| R1 | 配置即代码 | `backend/` `scrapy/` 硬编码 `mysql://` `postgres://` `redis://` |
| R2 | 配置即代码 | 明文 `password="..."` |
| R3 | 爬取与存储分离 | scrapy import `backend` / `app` |
| R4 | 爬取与存储分离 | scrapy 使用 SQLAlchemy Session |
| R5 | 反爬 | `scrapy/settings.py` 含 `DOWNLOAD_DELAY` |
| R6 | 反爬 | `scrapy/` 含 `USER_AGENT` 或 `UserAgentMiddleware` |
| R7 | 模型即契约 | API 层 import ORM（含 `platform_core.models.<sub>` 与 `external_api/`） |
| R8 | 模型即契约 | `platform_core/models/` import schemas |
| R9 | 数据流向不可逆 | `uv run python -c 'import backend.app'` 循环 import |
| R10 | 日志即证据 | `backend/services/*.py` 公开方法下一行无 `logger.` |
| R11 | 异步优先 | `redis_client(...).` 链式直调 |
| R12 | 门面退役 | 白名单外 import `backend.services.spider_service` |
| R13 | 租户过滤 | 隔离安装点 + `backend/app/tenant_isolation.py` 同步 |

## 边界（B1–B3）

| 边界 | 禁止 |
|------|------|
| B1 | `platform_core/` import `backend` / `scrapy` |
| B2 | `backend/` import `scrapy` |
| B3 | `config/` import `backend` / `scrapy` / `platform_core` |

## 修法

| 违规 | 修法 |
|------|------|
| R1 / R2 | 读 `settings.*`，密钥进 `config/<env>/.env`（AGENTS.md 配置） |
| R3 / R4 | Redis 队列 |
| R5 / R6 | `new-spider`：延迟和 UA 在 settings / middleware |
| R7 / R8 | `new-model`：转换只在 Service |
| R9 | 拆环或延迟 import |
| R10 | service 公开方法入口有 `logger.`（AGENTS.md 日志） |
| R11 | `get_async_redis()` |
| R12 | 直连子 Service；白名单只在脚本里 |
| R13 | `backend/app/tenant_isolation.py` |
| B1–B3 | `platform_core` → `config`；backend 不 import scrapy；config 无上层依赖 |

改完再跑 `bash tools/check/arch.sh`，以退出码为准。
