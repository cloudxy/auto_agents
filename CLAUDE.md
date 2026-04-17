# Auto Agents 项目指南

## 项目概览

多应用混合项目，包含爬虫、后端 API、官方网站、后台管理系统。

```
auto_agents/
├── backend/              # FastAPI 后端服务
├── scrapy/               # Scrapy 爬虫项目
├── platform_core/        # 共享基础设施层（日志、数据库、存储）
├── frontend/             # 前端官网（React）
├── admin/                # 后台管理系统（React）
└── .lingma/              # 规则和技能库
```

## 核心架构哲学

- **配置即代码**：所有配置外置、版本化、环境隔离
- **日志即证据**：关键路径必须留痕且可追溯
- **独立部署优于耦合**：各子项目可独立启动、扩缩容、故障隔离
- **爬取与存储分离**：爬虫只采集和清洗，不负责持久化
- **反爬是生存底线**：每个爬虫必须实现反爬策略

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + MySQL + Redis |
| 爬虫 | Scrapy + Loguru |
| 前端 | React + TypeScript |
| 基建 | Docker + GitHub Actions |
| 配置 | Dynaconf |

## 快速开始

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
./run_backend.py
```

### 爬虫

```bash
cd scrapy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
scrapy crawl {spider_name}
```

## 规则和技能

使用 `.lingma/` 中的规则和技能：

| 规则 | 描述 |
|------|------|
| `answer_rule` | 回答思维框架 - 解决问题优先 |
| `project_rule` | 架构哲学、设计原则、演进方向 |

| 技能 | 描述 |
|------|------|
| `/new-svc` | 创建 FastAPI 服务模块 |
| `/new-spider` | 创建 Scrapy 爬虫 |
| `/coding-style` | 编码规范 |
| `/logging` | 日志规范 |
| `/config` | 配置规范 |

## 项目状态

当前分支：`feature/project-structure`

正在进行项目结构重构，将异常处理、CORS、日志初始化等从各模块统一到 `platform_core`。

## 关键文件

- `run_backend.py` - 后端启动脚本
- `backend/app/__init__.py` - FastAPI 应用工厂
- `platform_core/infra.py` - 基础设施初始化
- `.lingma/` - 规则和技能库
