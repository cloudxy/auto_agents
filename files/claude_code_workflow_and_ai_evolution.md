# Claude Code 运行机制 & AI 化演进建议

## 第一部分 · Claude Code 自身的运行流程与逻辑

Claude Code 是 Anthropic 官方的"工具型 LLM CLI"。它把"对话 + 文件系统 + 终端 + Git + MCP"打通，让 LLM 以 Agent 形式真正在工程现场干活。它的运行可以拆成**启动加载、单轮对话循环、跨轮持久化**三个阶段。

### 1.1 启动加载（Session Bootstrap）

CLI 启动时会按优先级合并加载配置，**越靠后越优先**：

| 层级 | 路径 | 作用 |
|------|------|------|
| 内置系统提示 | 二进制内嵌 | 工具协议、安全策略、输出风格的硬约束 |
| 用户全局 | `~/.claude/settings.json` + `~/.claude/CLAUDE.md` | 用户跨项目偏好、全局 hook、全局 skill |
| 用户项目级偏好 | `~/.claude/projects/<project-slug>/memory/` + `MEMORY.md` | 个人在某项目下的偏好（不入 git） |
| 项目仓库 | `<repo>/CLAUDE.md`、`<repo>/.claude/*` | 团队共享的项目契约（入 git） |
| 本地覆盖 | `<repo>/.claude/settings.local.json` | 个人本地权限/环境变量（一般不入 git） |
| MCP | `<repo>/.mcp.json` + `~/.claude.json` 的 mcpServers | 接外部工具/数据源（GitHub、DB、Notion…） |

加载过程中 Claude Code 会：

1. 读 `CLAUDE.md`，把内容**注入到系统提示尾部**，作为对话级"项目说明书"
2. 读 `.claude/settings.json` 的 `hooks` 字段，注册各类生命周期钩子
3. 启动 `mcpServers` 中声明的子进程（每个 MCP 是独立进程，stdio/SSE 通信）
4. 扫描 `.claude/skills/`、`.claude/agents/` 目录，构建可调用的技能库与子 Agent 目录
5. 读 `permissions.allow / deny`，决定哪些工具调用免确认

### 1.2 单轮对话循环（Per-Turn Loop）

用户输入一条消息后，Claude Code 内部并不是"一次 LLM 调用"，而是**多轮工具循环（Tool-Use Loop）**：

```
┌──────────────────────────────────────────────────────────────────┐
│  用户输入                                                        │
│      ↓                                                           │
│  [UserPromptSubmit hook]   ← 可注入额外 context（本项目用了）    │
│      ↓                                                           │
│  组装 messages（系统提示 + CLAUDE.md + 历史 + 注入 context）     │
│      ↓                                                           │
│  调 Claude API（with tools schema）                              │
│      ↓                                                           │
│  ┌──── 模型返回 ────┐                                            │
│  │ tool_use?        │                                            │
│  └──────────────────┘                                            │
│   是↓                  否↓                                       │
│  [PreToolUse hook]    输出文本 → 用户                            │
│      ↓                    ↓                                      │
│  权限检查              [Stop hook]                               │
│  (allow/ask/deny)         ↓                                      │
│      ↓                  落盘 transcript                          │
│  执行工具                                                        │
│      ↓                                                           │
│  [PostToolUse hook]                                              │
│      ↓                                                           │
│  把 tool_result 喂回模型 → 回到调 Claude API                     │
└──────────────────────────────────────────────────────────────────┘
```

关键点：

- **工具循环没有硬上限**：模型可以连续调用 Bash/Read/Edit 几十次直到判断"任务完成"。
- **并行工具调用**：一次 assistant turn 可同时发多个 tool_use（无依赖时并行执行）。
- **Hook 是 shell 进程**：不在 LLM 上下文里，是 Claude Code 主进程在生命周期点 fork 出去执行的脚本，stdin 拿事件 JSON、stdout 决定行为。
- **权限模式三选一**：
  - `allow`：直接执行
  - `ask`：弹出用户确认（hook 也可以输出 `permissionDecision: ask` 强制走这条）
  - `deny`：拒绝，把拒绝原因当作 tool_result 喂回模型
- **上下文压缩**：接近 context window 上限时自动总结历史轮次，保留最近 N 轮原文。

### 1.3 内置工具与扩展点

| 类别 | 工具/能力 | 说明 |
|------|----------|------|
| 文件 | `Read / Write / Edit / NotebookEdit` | 直接操作工作区文件 |
| 终端 | `Bash` | 在仓库根执行 shell 命令，受 permissions 控制 |
| 检索 | `Grep / Glob / WebSearch / WebFetch` | 代码搜索 + 联网 |
| 任务 | `TaskCreate / TaskUpdate / TaskList` | 显式 todo 列表，跨工具循环可见 |
| 子 Agent | `Agent` | 起一个隔离上下文的子 Claude，跑专项任务 |
| 计划 | `EnterPlanMode / ExitPlanMode` | 只读探查 + 输出方案，不改代码 |
| 工作树 | `EnterWorktree / ExitWorktree` | 在隔离的 git worktree 跑改动 |
| 调度 | `CronCreate / ScheduleWakeup` | 定时/延迟触发 prompt |
| MCP | `mcp__<server>__<tool>` | 外部数据源/服务，通过 MCP 协议接入 |
| Skill | `Skill` | 调用工程化封装的"操作手册"（含模板、references、scripts） |

### 1.4 三类扩展物的边界

很多人混淆 **Rules / Skills / Agents / Hooks / MCP** 五者。简表：

| 名称 | 是什么 | 在不在 LLM 上下文 | 何时介入 | 例子 |
|------|--------|------------------|---------|------|
| **CLAUDE.md** | 项目说明书 | ✅ 一直在 | 每次对话开头注入 | 仓库根 `CLAUDE.md` |
| **Rules** | 强约束方法论文档 | ⚠️ 按需 Read | 模型自行判断什么时候读 | `.claude/rules/project_rule.md` |
| **Skills** | 操作 SOP 手册 + 资源 | ⚠️ 按需 Read | 用户 `/skill` 触发或模型 Skill 工具调用 | `.claude/skills/check-arch/` |
| **Agents** | 子 Claude 任务模板 | ❌ 主对话不可见 | 主 Claude 用 `Agent` 工具调起 | `.claude/agents/arch-warden.md` |
| **Hooks** | shell 脚本 | ❌ | 生命周期事件 | `.claude/hooks/inject_context.sh` |
| **MCP** | 外部服务桥 | ⚠️ 工具 schema 注入 | 模型调 `mcp__*` 工具时 | `.mcp.json` 的 `github` |

> 一句话区分：**CLAUDE.md = 默念的家训；Rules = 案头的法典；Skills = 工具书；Agents = 外包工；Hooks = 守门员；MCP = 外联部**。

### 1.5 重要 Hook 事件清单

| 事件 | 触发时机 | 典型用途 |
|------|---------|---------|
| `UserPromptSubmit` | 用户回车提交后、模型调 API 前 | 注入额外 context（项目身份、最近记忆） |
| `PreToolUse` | 模型决定调工具、实际执行前 | 拦截敏感写、强制走 `ask` |
| `PostToolUse` | 工具执行完，结果回喂模型前 | 自动 lint / 自动测试 / 落盘审计 |
| `Stop` | 一轮对话结束 | 整理 transcript、提示归档记忆 |
| `SubagentStop` | 子 Agent 结束 | 记录子任务产出 |
| `Notification` | Claude Code 弹通知时 | 接外部告警通道 |

### 1.6 持久化与跨会话记忆

Claude Code 有三层"记忆"：

1. **transcript**（每会话 jsonl，落到 `~/.claude/projects/<slug>/`）—— 原始流水
2. **个人 memory**（`~/.claude/projects/<slug>/memory/*.md`）—— 个人偏好，不入 git
3. **项目 memory**（仓库内 `.claude/memory/*.md`）—— 团队共享，入 git

模型读取 memory 不是自动的——是它在系统提示里被"教会"了"重要时主动 Read"。所以 memory 的索引文件（`MEMORY.md`）通常会被 hook 注入或被系统提示提示成"务必先读"。

## 附录 A · 关键文件速查

| 想了解 | 看这里 |
|--------|--------|
| 项目业务架构 | `CLAUDE.md` + `.claude/rules/project_rule.md` |
| Claude Code 协作约定 | `.claude/IDENTITY.md` + `.claude/SOUL.md` |
| 红线清单 | `.claude/rules/project_rule.md`「架构红线」章节 |
| 怎么提交前自检 | `/check-arch` + `/verify` |
| Hook 实现 | `.claude/hooks/*.sh` |
| 子 Agent 定义 | `.claude/agents/*.md` |
| Skill 列表 | `.claude/skills/` 或 `.agents/skills/` |
| MCP 配置 | `.mcp.json` |
| Python 启动入口 | `run.py / run_backend.py / run_spider.py / run_frontend.py` |
| 共享基建 | `platform_core/` |

## 附录 B · 名词表

- **Tool-Use Loop**：模型在一次用户输入后连续调用多个工具直到判断"任务完成"的循环。
- **Hook**：Claude Code 主进程在生命周期事件 fork 出去执行的 shell 脚本，**不在 LLM 上下文里**。
- **Skill**：工程化封装的 SOP 文档（含 `SKILL.md` + 模板 + scripts），可被模型按需 Read。
- **Agent**：在隔离子上下文中跑专项任务的子 Claude，**主对话看不见它的中间过程**。
- **MCP**：Model Context Protocol，把外部服务（GitHub、DB、Slack…）以工具形式暴露给 LLM 的协议。
- **Prompt Caching**：Anthropic API 的特性，把系统提示/工具定义/长上下文片段缓存，命中时按 10% 计费。
- **Structured Output**：让 LLM 严格按 JSON Schema 输出，避免业务代码处理脏字符串。
- **Eval**：prompt/模型回归测试的固定 input→expected 用例集。
- **Provider-agnostic**：业务代码不感知具体 LLM 厂商，可一键切换 Claude / OpenAI / 本地模型。
