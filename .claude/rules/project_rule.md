---
description: 架构哲学与演进规则 - 价值观、设计原则、演进方向
trigger: always_on
---

# 架构哲学

> 当涉及项目架构设计、分层、解耦、演进时，遵循本规则。具体执行时查找对应 Skill。

## 激活信号（什么时候应用本规则）

| 信号类型 | 具体表现 |
|---------|---------|
| **新建模块** | 创建新的 service / API / 爬虫 / 工具库 |
| **改分层** | 修改目录结构、移动文件、调整 import 路径 |
| **引入依赖** | 新加第三方库、新增模块间引用、跨子项目调用 |
| **讨论边界** | 服务间通信、数据流、部署拓扑、技术栈选型 |
| **涉及数据** | 定义 ORM 模型、Pydantic schema、API 契约 |
| **涉及配置** | 环境变量、敏感信息、连接串、超时参数 |

## 核心价值观

| 信条 | 含义 |
|------|------|
| 配置即代码 | 硬编码是技术债，配置外置、版本化、环境隔离 |
| 日志即证据 | 关键路径必须留痕且可追溯 |
| 独立部署优于耦合 | 边界清晰才能独立演化 |
| 面向接口而非实现 | 依赖抽象让替换成为可能 |
| 数据流向不可逆 | 请求单向流动，禁止反向穿透 |
| 模型即契约 | ORM = 数据库契约，Pydantic = 接口契约 |
| 爬取与存储分离 | 爬虫只负责采集和清洗，不负责持久化 |
| 反爬是生存底线 | 没有反爬策略的爬虫是 DDoS |
| 数据质量先于数量 | 100 条干净数据 > 10000 条脏数据 |

## 架构红线（可机械检查）

上述价值观违规时，用 grep / 代码审查立即定位：

| 信条 | 红线 | 检查命令 |
|------|------|---------|
| 配置即代码 | 禁止硬编码连接串、密钥、端口 | `grep -rE "(mysql\|postgres\|redis)://[^$\{]" backend/ scrapy/` |
| 配置即代码 | 禁止在代码里写明文 password | `grep -rE 'password\s*=\s*"[^$]' backend/ scrapy/` |
| 爬取与存储分离 | scrapy 禁止 import backend 内部 | `grep -rE "from (backend\|app)\." scrapy/` |
| 爬虫不能直写主库 | scrapy 禁止使用 SQLAlchemy Session | `grep -rE "from sqlalchemy\|SessionLocal\|get_db" scrapy/` |
| 反爬是底线 | 爬虫必须配 DOWNLOAD_DELAY | `grep -rE "DOWNLOAD_DELAY" scrapy/settings.py` |
| 反爬是底线 | 爬虫必须配 USER_AGENT 轮换或中间件 | `grep -rE "USER_AGENT\|UserAgentMiddleware" scrapy/` |
| 模型即契约 | API 层禁止直接 import ORM 模型 | `grep -rE "from.*\.models import" backend/app/api/` |
| 模型即契约 | ORM 模型禁止 import Pydantic schema | `grep -rE "from.*\.schemas import" platform_core/models/` |
| 数据流向不可逆 | 禁止循环 import（A→B→A） | `python -c "import backend.app"` 能否成功加载 |
| 日志即证据 | service 方法必须有入口 logger | code review：每个 public 方法第一行 `logger.info` |
| 异步优先 | async 上下文禁止同步 `redis_client()` 链式直调（阻塞事件循环），统一走 `get_async_redis()` | `grep -rnE 'redis_client\([^)]*\)\.' backend/` |

## 核心代码边界（模块依赖方向）

除上述红线外，模块间的依赖方向必须严格遵守以下边界（`check-arch.sh` B1-B3 机械检查）：

| 边界 | 规则 | 依赖方向 |
|------|------|----------|
| B1 | `platform_core/` 禁止 import `backend/` 或 `scrapy/` | platform_core → config（单向） |
| B2 | `backend/` 禁止 import `scrapy/` | backend ⇏ scrapy（通过 Redis 队列 / API 解耦） |
| B3 | `config/` 禁止 import `backend/`、`scrapy/`、`platform_core/` | config 是最底层，无上层依赖 |

**依赖方向图**（从上到下，只允许向下依赖）：

```
scrapy/  ──┐
             ├──► platform_core/ ──► config/
backend/ ──┘
```

- `config/` 是地基：任何模块都可以读配置，但配置层不依赖任何业务代码
- `platform_core/` 是共享基建：只能依赖 `config/`，禁止反向依赖业务模块
- `backend/` 和 `scrapy/` 是平行业务模块：互相禁止直接 import，通过 Redis 队列 / HTTP API 解耦

## 设计原则

### 为什么分层？

分层的本质是**约束依赖方向**。每一层只关心自己的职责，只调用下一层，永远不反向穿透。

判断标准：如果删除某一层，上层应该只失去一种能力（如存储能力），而不是全部崩溃。

### 为什么解耦？

耦合的代价不在今天，在明天。当你想替换 MySQL 为 PostgreSQL，想用 Kafka 替代 Redis 队列——耦合越深，改动越痛。

**解耦边界**：
- **数据边界**：不共享数据库表，通过 API/MQ 传递数据
- **依赖边界**：不直接 import 对方内部实现，通过接口交互
- **部署边界**：可独立启动、扩缩容、故障隔离

### 为什么 API 内外分离？

内部接口频繁迭代，可以 breaking change；外部接口需要版本管理，必须向后兼容。混在一起 = 内部改一个字段，外部客户端全部崩溃。

### 为什么爬虫必须独立？

爬虫和后端的生命周期、故障模式、技术栈演进速度完全不同。绑在一起 = 一方的问题变成双方的故障。

### 为什么爬虫不能直写主库？

直接写主库意味着连接池互相影响、脏数据污染后端、写入压力影响查询。**正确的关系**：爬虫是生产者，后端是消费者，中间用消息队列或 API 解耦。

### 为什么反爬是底线？

没有反爬策略的爬虫：对目标网站不尊重（等同于攻击）、对自己不负责（IP/账号被封）、对项目有风险（法律/技术风险）。

## 演进方向

本项目采用多项目架构，各子项目技术栈独立、可独立部署；本地开发通过 **uv workspace** 收敛为单一 `.venv`。

演进路径：**直连 → 爬虫通过 Redis/MQ 发送数据 → 引入消息队列解耦 → 微服务化**

## 环境与依赖（uv workspace）

- 根 `pyproject.toml` 是 workspace 容器，`members = ["backend", "scrapy"]`
- 根 `.venv` 是**唯一**的 Python 虚拟环境（原 `backend/.venv` `scrapy/.venv` 已废弃）
- `platform_core/` 是**源码包**，通过 `sys.path` 引入，不打包、不进 workspace
- 子项目仍各自保留 `pyproject.toml` 声明依赖，**部署时**用 `uv sync --package auto-agents-{backend,spider}` 独立打包

红线：
- 禁止再创建 `backend/.venv` 或 `scrapy/.venv`
- 禁止 `cd backend && uv add ...`，改用 `uv add --package auto-agents-backend ...`
- 禁止把根 `uv.lock` 加入 `.gitignore`（必须提交，保证可复现）

## 目录与共享层

| 层 | 路径 | 职责 |
|----|------|------|
| 配置 | `config/` | Dynaconf 多层合并（default → scrapy/default → `<env>` → scrapy/`<env>` → `.env` → 环境变量） |
| 共享基建 | `platform_core/` | logger / db / storage / exceptions / repository / **models** / **schemas** |
| 后端 | `backend/` | API（`app/api/v1+v2`）+ 外部 API（`app/external_api`）+ services + repositories |
| 爬虫 | `scrapy/` | spiders / middlewares / pipelines / items（禁止 import backend） |
| 前端 | `frontend/{admin,official}/` | React 19 + TS（独立 npm 包） |

**注意**：ORM 模型已从 `backend/models/` 迁移到 `platform_core/models/`；Pydantic schema 已从 `backend/app/schemas/` 迁移到 `platform_core/schemas/`。这两个目录是 backend 与 scrapy 的共享数据契约。

## 技术栈

**后端**：FastAPI + SQLAlchemy + MySQL + Redis + Dynaconf + Loguru
**前端**：React + TypeScript
**爬虫**：Scrapy（独立项目）
**基建**：Docker + GitHub Actions

## 相关 Skills

当 Rule 触发后，查找对应 Skill 获取执行细节：

| 场景 | Skill |
|------|-------|
| 创建服务模块 | `/new-svc` |
| 创建爬虫 | `/new-spider` |
| 创建数据模型 | `/new-model` |
| 架构合规检查（11 条红线） | `/check-arch` |
| 交付自检 | `/verify` |
| 编码规范 | `/coding-style` |
| 日志规范 | `/logging` |
| 配置规范 | `/config` |
| 部署配置 | `/deploy` |
| CI/CD 配置 | `/cicd` |
