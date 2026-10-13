# 架构扫描地图

执法入口：

```bash
bash tools/check/arch.sh
```

本页解释脚本在查什么。正则、排除目录、R12 白名单、R13 豁免以脚本为准。

## Contents

- R1–R13 红线
- B1–B4 边界
- SZ 规模约定
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
| R10 | 日志即证据 | `backend/services/**/*.py` 模块级公开函数与顶层 `*Service` / `*Mixin` 类公开方法：docstring 后第一条语句不是含 `logger.` 的表达式（if / try 分支里的日志不算；豁免 property 访问器 / 抽象桩 / Protocol） |
| R11 | 异步优先 | `redis_client(...).` 链式直调 |
| R12 | 门面退役 | 白名单外 import `backend.services.spider_service` |
| R13 | 租户过滤 | 隔离安装点 + `backend/app/tenant_isolation.py` 同步 |

## 边界（B1–B4）

| 边界 | 禁止 |
|------|------|
| B1 | `platform_core/` import `backend` / `scrapy` |
| B2 | `backend/` import `scrapy` |
| B3 | `config/` import `backend` / `scrapy` / `platform_core` |
| B4 | 四柱域（ADR-0010）：`power_market` 直连 spider_ / newapi_ / litellm_ / relay_ / channel_ / ai_planner / llm_gateway；`ai_planner` import `llm_gateway.admin`，或 `llm_client.py` 以外 import `llm_gateway.chat`；`LITELLM.DB_DSN`；`create_async_engine` 打网关库 |

## 规模约定（SZ）

`python3 tools/check/size.py`（arch.sh 末段调用）：git 跟踪的 Python（不含测试、`conftest.py`、alembic 迁移）单文件 ≤ 500 行、单函数 ≤ 40 行（`def` 行到函数体末行，含文档串与注释，不含装饰器）。单查：`python3 tools/check/size.py <文件…>`。

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
| B4 | 域间经服务接口或网关 HTTP；`llm_gateway.chat` 调用收口到 `ai_planner/llm_client.py` |
| SZ | 行为不变地抽私有 helper；超 500 行的文件沿内聚接缝拆出同级模块并在原模块 re-export（测试 patch 目标随代码迁移） |
| PL-1–PL-5 | 插件只能引用：把副本换成符号链接（`.agents/plugins/<name>` → `~/.zcode/local-plugins/<name>`；`.claude/plugins`、`.grok/plugins` → `.agents/plugins/<name>`；`.codex/skills`、`.codex/agents` 是项目级相对链接，sdlc-workflow 的由 `link-codex.py --project` 生成；插件不挂 `~/.codex`）；Claude 插件源只用 `directory` + `./.agents/plugins/<name>`。本机缓存副本另跑 `python3 tools/check/plugin_refs.py --local` |

改完再跑 `bash tools/check/arch.sh`，以退出码为准。
