---
name: check-arch
description: 架构合规检查 - 一键扫描 13 条架构红线 + 3 条核心代码边界，输出违规文件:行号报告
trigger: >-
  架构合规检查、扫描硬编码、提交前自检、PR Review、怀疑分层边界被破坏、
  /verify 交付自检后的第二道关卡
---

# 架构合规检查

把 `project_rule.md` 的 13 条架构红线 + 3 条核心代码边界打包成一次性扫描器。用于把"纸面红线"变成"机械可执行"。权威入口是 `bash scripts/check-arch.sh`，不要手搓过时的 10/12 条 grep。

## 触发场景

- "检查架构违规"、"扫描硬编码"、"check architecture"
- 提交代码前的自检
- PR Review 时
- 怀疑某次修改破坏了分层边界
- `/verify` 交付自检后的第二道关卡

## 执行流程

### Step 1: 按信条运行 13 条红线 + 3 条边界扫描

一次执行 `bash scripts/check-arch.sh`（约定见 [references/scan-commands.md](references/scan-commands.md)）。不要手搓 grep。规则定义在 `project_rule.md`，实现只在脚本里。

导航用（修复时按号路由，不要当第二套检查命令）：

**架构红线（R1-R13）：**

| 信条 | 规则 |
|------|------|
| 配置即代码 | R1 硬编码连接串、R2 明文 password |
| 爬取与存储分离 | R3 scrapy→backend 反向依赖、R4 scrapy 使用 SQLAlchemy |
| 反爬是底线 | R5 DOWNLOAD_DELAY、R6 USER_AGENT 轮换 |
| 模型即契约 | R7 API 层 import models、R8 models 反向 import schemas |
| 数据流向不可逆 | R9 循环 import |
| 日志即证据 | R10 service 方法入口缺 logger |
| 异步优先 | R11 async 上下文禁止同步 redis_client() 链式直调（网络 IO 阻塞事件循环），两段式赋值写法属盲区靠人工评审 |
| 门面退役过渡 | R12 禁止白名单外 import 过渡门面 backend.services.spider_service，白名单见 scripts/check-arch.sh |
| 租户隔离不可旁路 | R13 业务查询必须经 tenant_context 收口；豁免清单单一事实源 backend/app/tenant_isolation.py |

**核心代码边界（B1-B3）：**

| 边界 | 规则 | 依赖方向 |
|------|------|----------|
| B1 | `platform_core/` 禁止 import `backend/` 或 `scrapy/` | platform_core → config（单向） |
| B2 | `backend/` 禁止 import `scrapy/` | backend ⇏ scrapy（通过 Redis 队列解耦） |
| B3 | `config/` 禁止 import `backend/`、`scrapy/`、`platform_core/` | config 是最底层，无上层依赖 |

### Step 2: 汇总违规报告

把脚本 stdout 原样贴回，不要改写成另一张表。通过时脚本打印：

```
✓ 架构合规检查通过（13 红线 + 3 边界，全部通过）
```

有违规时按脚本的 `❌ Rn` + file:line 修复。优先级：B1/B2（边界）> R3/R4（架构）> R1/R2（安全）> R13（租户）> R5/R6（运行时）> R10（可观测）。

### Step 3: 按违规类型路由到修复 skill

| 违规 | 修复指引 |
|------|--------|
| R1 / R2 | `/config`：改为 `settings.MYSQL.DEFAULT.HOST` 形式，敏感信息入 `config/<env>/.env` 或 `AUTO_AGENTS_*` |
| R11 | 链式 `redis_client().x` 改为 `await get_async_redis()`；两段式赋值靠人工评审 |
| R3 / R4 | `project_rule.md` "为什么爬虫不能直写主库"：改用 HTTP / MQ 交互 |
| R5 / R6 | `/new-spider`：`DOWNLOAD_DELAY` / UA 在 `scrapy/settings.py`（config 注入），不要在 spider 里 `time.sleep` |
| R7 / R8 | `/new-model`：用 converter 做 ORM↔Schema 的单向转换 |
| R9 | 找环路中间节点，引入抽象层或延迟 import |
| R10 | `/logging`：public 方法第一行 `logger.info("...")` |
| R12 | 改走拆分后的子 Service，勿新增 `spider_service` 门面 import |
| R13 | 查询走 `tenant_scope`；豁免表只改 `backend/app/tenant_isolation.py`，禁止在 `platform_core/tenant_context.py` 硬编码业务表名 |
| B1 | `platform_core/` 只能依赖 `config/`，抽取共享接口或上移到 `backend/` |
| B2 | `backend/` 与 `scrapy/` 通过 Redis 队列 / HTTP API 解耦，禁止直接 import |
| B3 | `config/` 是最底层配置层，禁止反向依赖业务模块 |

## 输出约定

- 脚本退出码 0 = 通过；非 0 = 违规。贴脚本原始输出，不要自己 grep 再汇总
- 有违规必须列出脚本给出的 file:line，**禁止说"可能有违规"**

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `project_rule.md` | 13 条红线 + 核心边界定义的来源 |
| `/verify` | 交付自检的第一道关卡，本 skill 是第二道 |
| `/config` / `/logging` / `/new-spider` / `/new-model` | 违规的修复路径 |
