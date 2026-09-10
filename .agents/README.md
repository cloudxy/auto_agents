# `.agents/` — 本仓库开发协作中枢

本目录是技能 / 插件指针 /（将来）可移植智能体的**唯一仓库内真相源**。Grok、Claude、Codex、Kimi 等通过各自宿主目录的符号链接来取，不要在 `.grok/`、`.claude/`、`capability-library/plugins/` 再放一份内容。

| 子目录 | 放什么 | 不放什么 |
|--------|--------|----------|
| `skills/` | 本仓库 SOP skill（有清单、死命令、完成条件） | 常驻约定（编码/日志/配置在根 `AGENTS.md`）；第三方插件 skill |
| `plugins/` | 指向 `~/.zcode/local-plugins/<name>` 的符号链接 | 插件正文、`sdlc-workflow-eval-workspace` |
| `agents/` | 尚未启用。可移植智能体以后才进这里 | Claude 专用 frontmatter（现留 `.claude/agents/`） |

宿主适配器（发现路径各工具自己认）：

- `.grok/plugins/<name>` → `plugins/<name>`（Grok 只链启用的四个，不链 `superpowers` / `mattpocock-skills`）
- `.claude/skills` → `skills/`
- `.claude/plugins/<name>` → 与 Grok 同一份四插件子集（Grok 也会扫 `.claude/plugins`）
- `capability-library/plugins` → `plugins/`（整农场；平台 `scan-plugins` 入口，不改 `LIBRARY_ROOT`）

第三方插件正文只在 `~/.zcode/local-plugins/` 维护。新增：`ln -s ../../../.zcode/local-plugins/<name> .agents/plugins/<name>`，不要 `cp -R`。Grok 启用名单在 `.grok/config.toml`，那是宿主私有配置。

Codex / Kimi 等确认官方发现路径后再加适配器，不要假设它们扫 `.agents/plugins`。

## 项目 skill 写法（`.agents/skills/<name>/SKILL.md`）

**标准：** [Agent Skills 概述](https://platform.claude.com/docs/zh-CN/agents-and-tools/agent-skills/overview) 与 [Skill 编写最佳实践](https://platform.claude.com/docs/zh-CN/agents-and-tools/agent-skills/best-practices)。[intro](https://platform.claude.com/docs/zh-CN/intro) 是平台入口，不含字段表。

- **Frontmatter 必填** `name`（小写+连字符，≤64，无保留字）和 `description`（第三人称：**先写功能，再写 Use when**，≤1024）。
- **三级披露**：启动只注入 name/description；触发后读 SKILL.md（正文 ≤500 行）；模板和命令矩阵放 `references/`，从 SKILL.md **一层**链过去。
- **正文**：Quick start（复杂流程用可勾选清单）→ 必要时 Examples → Advanced 链到 references。脆弱操作给死命令；验证失败则修完再跑同一条。
- **交叉 SOP**：正文开头用 Route 表（可观察条件 → 先做哪个 skill），不要让执行者自己猜交接。
- **完成回复**：规定回复的块与顺序（路径 + 命令原文），完成条件必须能对勾，不要写「然后就好了」。
- **简洁**：只写 Claude 不知道的仓库约定。先读现成文件再改编。编码 / 日志 / 配置是常驻约定，写在根 `AGENTS.md`，不单独做 skill。事实只放一处：ORM/Schema 在 `new-model`，new-svc 只链过去。
- **ZCode 宿主约束**（非 Anthropic 字段）：每轮只注入 description 前 250 字符，所以触发词不要放在描述末尾；`$` 调 skill。不要臆造 `.zcode/commands`。
- **插件 skill** 仍在 `~/.zcode/local-plugins/`，本目录只放指针。
