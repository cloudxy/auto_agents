---
name: check-arch
description: 架构合规检查 - 一键扫描 11 条架构红线 + 3 条核心代码边界，输出违规文件:行号报告
trigger: >-
  架构合规检查、扫描硬编码、提交前自检、PR Review、怀疑分层边界被破坏、
  /verify 交付自检后的第二道关卡
---

# 架构合规检查

把 `project_rule.md` 的 11 条架构红线 + 3 条核心代码边界打包成一次性扫描器。用于把"纸面红线"变成"机械可执行"。

## 触发场景

- "检查架构违规"、"扫描硬编码"、"check architecture"
- 提交代码前的自检
- PR Review 时
- 怀疑某次修改破坏了分层边界
- `/verify` 交付自检后的第二道关卡

## 执行流程

### Step 1: 按信条运行 11 条红线 + 3 条边界扫描

一次 Bash 批量执行，路径相对项目根目录。完整命令见 [references/scan-commands.md](references/scan-commands.md)，按信条分组：

**架构红线（R1-R10）：**

| 信条 | 规则 |
|------|------|
| 配置即代码 | R1 硬编码连接串、R2 明文 password |
| 爬取与存储分离 | R3 scrapy→backend 反向依赖、R4 scrapy 使用 SQLAlchemy |
| 反爬是底线 | R5 DOWNLOAD_DELAY、R6 USER_AGENT 轮换 |
| 模型即契约 | R7 API 层 import models、R8 models 反向 import schemas |
| 数据流向不可逆 | R9 循环 import |
| 日志即证据 | R10 service 方法入口缺 logger |

**核心代码边界（B1-B3）：**

| 边界 | 规则 | 依赖方向 |
|------|------|----------|
| B1 | `platform_core/` 禁止 import `backend/` 或 `scrapy/` | platform_core → config（单向） |
| B2 | `backend/` 禁止 import `scrapy/` | backend ⇏ scrapy（通过 Redis 队列解耦） |
| B3 | `config/` 禁止 import `backend/`、`scrapy/`、`platform_core/` | config 是最底层，无上层依赖 |

### Step 2: 汇总违规报告

按以下格式输出（禁止总结、必须贴具体 file:line）：

```
架构合规检查报告
==================
R1 硬编码连接串         backend/core/db.py:15        mysql://root:xxx@...
R3 scrapy→backend       scrapy/spiders/x.py:3        from backend.models ...
R5 缺失 DELAY           scrapy/settings.py:-         未配置 DOWNLOAD_DELAY
R10 service 缺 logger   backend/services/user.py:12  def create_user(...)
B1 platform_core 反向依赖 platform_core/xxx.py:1    from backend.yyy import zzz

共 5 处违规，按优先级修复：B1/B2 (边界级) > R3/R4 (架构级) > R1/R2 (安全) > R5/R6 (运行时) > R10 (可观测)
```

若无违规：

```
✓ 架构合规检查通过（10 红线 + 3 边界，全部通过）
```

### Step 3: 按违规类型路由到修复 skill

| 违规 | 修复指引 |
|------|--------|
| R1 / R2 | `/config`：改为 `settings.MYSQL.HOST` 形式，敏感信息入 `.env` |
| R3 / R4 | `project_rule.md` "为什么爬虫不能直写主库"：改用 HTTP / MQ 交互 |
| R5 / R6 | `/new-spider`：拷贝反爬配置模板 |
| R7 / R8 | `/new-model`：用 converter 做 ORM↔Schema 的单向转换 |
| R9 | 找环路中间节点，引入抽象层或延迟 import |
| R10 | `/logging`：public 方法第一行 `logger.info("...")` |
| B1 | `platform_core/` 只能依赖 `config/`，抽取共享接口或上移到 `backend/` |
| B2 | `backend/` 与 `scrapy/` 通过 Redis 队列 / HTTP API 解耦，禁止直接 import |
| B3 | `config/` 是最底层配置层，禁止反向依赖业务模块 |

## 输出约定

- 所有 grep 无结果 = 通过
- 有违规 = 在消息中列出具体 file:line，**禁止说"可能有违规"**
- 遵守 `answer_rule.md`：用工具验证，不要用嘴验证

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `project_rule.md` | 11 条红线 + 核心边界定义的来源 |
| `/verify` | 交付自检的第一道关卡，本 skill 是第二道 |
| `/config` / `/logging` / `/new-spider` / `/new-model` | 违规的修复路径 |
