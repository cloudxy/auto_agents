# Auto Agents

自动化代理系统 - 基于 FastAPI + Scrapy 的分布式爬虫管理平台

## 项目结构

```
auto_agents/
├── backend/                    # Python 后端（FastAPI）
│   ├── app/                   # FastAPI 应用
│   │   ├── __init__.py        # 应用核心层（初始化、配置）
│   │   └── api/               # API 路由层
│   │       ├── __init__.py    # 路由聚合器
│   │       └── v1/            # API V1 版本
│   ├── cors/                  # 核心模块（日志、数据库、存储）
│   ├── models/                # SQLAlchemy ORM
│   ├── schemas/               # Pydantic 校验
│   └── services/              # 业务逻辑
├── scrapy/                     # Scrapy 爬虫（独立项目）
│   ├── spiders/               # 爬虫实现
│   ├── items.py               # 数据项定义
│   ├── pipelines.py           # 数据管道
│   ├── middlewares.py         # 中间件
│   └── settings.py            # Scrapy 配置
├── config/                    # 配置管理
│   ├── __init__.py            # 配置加载入口
│   ├── default/               # 默认配置
│   ├── local/                 # 本地环境
│   ├── dev/                   # 开发环境
│   └── prod/                  # 生产环境
├── frontend/                  # 前端应用
│   ├── admin/                 # 管理后台
│   └── official/              # 官方网站
├── scripts/                   # 运维脚本
├── run_app.py                 # ✨ API 启动文件（根目录）
├── run_spider.py              # ✨ 爬虫启动文件（根目录）
└── README.md                  # 项目文档
```

## 快速开始

### 1. 启动 API 服务

```bash
# 方式1：直接运行
python run_app.py

# 方式2：使用脚本
bash scripts/start.sh
```

访问地址：
- API 文档: http://127.0.0.1:9111/api/v1/docs
- 健康检查: http://127.0.0.1:9111/api/v1/health

### 2. 启动爬虫服务

```bash
# 方式1：直接运行
python run_spider.py --spider example

# 方式2：使用脚本
bash scripts/run-spider.sh example
```

## 配置管理

### 环境切换

```bash
# 本地开发环境（默认）
./scripts/start.sh

# 开发环境
APP_ENV=dev ./scripts/start.sh

# 生产环境
APP_ENV=prod ./scripts/start.sh
```

### 配置文件结构

#### 默认配置 (`config/default/`)
- `settings.yml` - 应用基础配置
- `web.yml` - Web 服务配置（CORS、服务器）
- `log.yml` - 日志配置
- `mysql.yml` - MySQL 配置
- `redis.yml` - Redis 配置
- `storage.yml` - 存储配置
- `jwt.yml` - JWT 认证配置
- `scrapy.yml` - Scrapy 爬虫配置
- `admin.yml` - 管理后台配置
- `official.yml` - 官方网站配置

#### 环境配置 (覆盖默认配置)
- `config/local/` - 本地开发环境
- `config/dev/` - 开发环境
- `config/prod/` - 生产环境

### 使用配置

```python
from config import settings

# 访问配置
settings.APP_NAME           # "Auto Agents"
settings.API_PORT           # 9111
settings.MYSQL.DEFAULT.HOST # "127.0.0.1"
```

## API 版本管理

项目支持多版本 API，当前使用 V1 版本：

- **V1**: `/api/v1/*` - 当前稳定版本
- **V2**: `/api/v2/*` - 未来版本（待开发）

### 添加新版本

1. 创建 `backend/app/api/v2/` 目录
2. 在 `backend/app/api/__init__.py` 中注册 V2 路由
3. 实现 V2 的业务逻辑

## 技术栈

- **后端**: FastAPI + SQLAlchemy + Scrapy
- **数据库**: MySQL + Redis
- **配置**: Dynaconf
- **日志**: Loguru
- **前端**: React + TypeScript

## 开发规范

### 代码规范
- 代码遵循 PEP 8 规范
- API 路由按版本分目录管理
- 配置通过 YAML 文件管理，支持环境变量覆盖
- 日志统一使用 Loguru，支持多日志器路由

### 架构原则

#### 核心价值观
1. **配置即代码** - 硬编码是技术债，配置必须外置、版本化、环境隔离
2. **日志即证据** - 没有日志的执行等于没执行，关键路径必须留痕且可追溯
3. **独立部署优于耦合** - 能独立运行的就不要捆在一起，边界清晰才能独立演化
4. **面向接口而非实现** - 依赖抽象让替换成为可能
5. **数据流向不可逆** - 请求单向流动，禁止反向穿透
6. **模型即契约** - ORM 模型是数据库契约，Pydantic 模型是接口契约
7. **爬取与存储分离** - 爬虫只负责采集和清洗，不负责持久化
8. **反爬是生存底线** - 没有反爬策略的爬虫不是爬虫，是 DDoS
9. **数据质量先于数量** - 100 条干净数据 > 10000 条脏数据

#### 分层架构
```
接入层 (API Routes) → 业务层 (Services) → 数据层 (Models)
     ↓                      ↓                    ↓
  请求校验              逻辑编排              数据读写
```

**铁律**：
- 上层可以调用下层，下层禁止调用上层
- 业务层可以调用外部服务，外部服务禁止反向调用业务层
- 数据只能通过接口或消息队列跨项目传递，禁止跨项目直接 import

#### 前端架构

**目录结构**：
```
src/
├── components/          # 通用组件（可复用）
├── pages/              # 页面组件（路由级别）
├── services/           # API 服务层
├── hooks/              # 自定义 Hooks
├── store/              # 状态管理
├── utils/              # 工具函数
├── types/              # TypeScript 类型定义
└── assets/             # 静态资源
```

**分层原则**：
- **Components vs Pages**：纯 UI 组件无业务逻辑，页面级组件包含业务逻辑
- **Services 层**：所有 API 调用必须通过 services 层，禁止在组件中直接使用 axios
- **状态管理**：简单状态用 `useState`，跨组件共享用 Context API，复杂全局状态用 Redux/Zustand

**技术栈**：
- React 19 + TypeScript
- Ant Design (admin) / Framer Motion (official)
- React Router v7 + Axios + React Query

### 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 违反依赖方向（反向调用、跨层直接操作） | 分层失效，架构腐败 | 遵循单向依赖 |
| 硬编码配置 | 改配置要改代码、重新构建 | 配置外置，Dynaconf 管理 |
| 关键路径无日志 | 出问题无法定位 | 每步都记录 |
| 爬虫直写主库 | 共享连接，互相影响 | 发送到 Redis/MQ |
| 爬虫直接导入后端模块 | 耦合→无法独立部署 | 通过 API 或消息队列 |
| 保留未清洗的脏数据 | 下游处理成本高 | Pipeline 中清洗和验证 |
| 前端绕过 API 直接访问数据库 | 安全漏洞，架构破坏 | 所有数据通过 API 获取 |
