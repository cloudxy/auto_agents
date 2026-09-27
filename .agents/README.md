# `.agents/` — 本仓库开发协作中枢

本目录是技能 / 插件指针 /（将来）可移植智能体的**唯一仓库内真相源**。Grok、Claude、Codex、Kimi 等通过各自宿主目录的符号链接来取，不要在 `.grok/`、`.claude/`、`capability-library/plugins/` 再放一份内容。

**所有 AI 工具只能以引用方式使用插件**：符号链接，或宿主原地读取源目录；禁止任何复制。会复制插件的命令一律不用——`claude plugin install`（写缓存副本）、`grok plugin install`（留哈希副本）、`codex plugin add`（装副本且丢弃符号链接）、`cp -R`。副本会和 `~/.zcode/local-plugins` 的源头悄悄分叉。`bash tools/check/arch.sh` 的 PL 段检查仓库内适配器（CI 同跑）；`python3 tools/check/plugin_refs.py --local` 另查本机各工具缓存里有没有副本、用户级链接是否悬空。

| 子目录 | 放什么 | 不放什么 |
|--------|--------|----------|
| `skills/` | 本仓库 SOP skill（有清单、死命令、完成条件） | 常驻约定（编码/日志/配置在根 `AGENTS.md`）；第三方插件 skill |
| `plugins/` | 指向 `~/.zcode/local-plugins/<name>` 的符号链接 | 插件正文、`sdlc-workflow-eval-workspace` |
| `agents/` | 尚未启用。可移植智能体以后才进这里 | Claude 专用 frontmatter（现留 `.claude/agents/`） |

宿主适配器（发现路径各工具自己认）：

- `.grok/plugins/<name>` → `plugins/<name>`（Grok 只链启用的四个，不链 `superpowers` / `mattpocock-skills`）
- `.claude/skills` → `skills/`
- **Claude Code 插件**：`.claude/settings.json` 的 `extraKnownMarketplaces` 把每个 `./.agents/plugins/<name>` 注册成 directory marketplace，`enabledPlugins` 启用同一份四插件子集。插件从 `plugins/<name>` 原地加载，不进 `~/.claude/plugins/cache`，源头改了下次会话生效
- `.claude/plugins/<name>` → 同一份四插件子集，只给 Grok 扫；**Claude Code 不读这个目录**
- `capability-library/plugins` → `plugins/`（整农场；平台 `scan-plugins` 入口，不改 `LIBRARY_ROOT`）
- **Codex**（CLI 0.156.1 实测）：插件机制只会复制，所以不用它。skills 走用户级目录链接 `~/.codex/skills/<name>` → `<仓库>/.agents/plugins/<name>/skills`（Codex 没有自己的项目级 skill 目录；`.agents/skills` 与 Grok、Claude 共用，放插件会重复加载），同一份四插件子集；列出时带插件名前缀（如 `sdlc-workflow:sdlc`），drama-skills 无 `plugin.json`，显示为 `short-drama-*`。sdlc-workflow 的角色子代理是 `.codex/agents/*.toml` 相对链接，由 `python3 .agents/plugins/sdlc-workflow/scripts/link-codex.py --project <仓库根>` 生成（经中枢路径调用，链接就经过中枢）；Codex 只对**受信任**项目读 `.codex/`，在本仓库首次用 Codex 时确认信任

Claude Code 的硬约束（2.1.283 实测，改接入前先读）：

- 聚合 marketplace 行不通：条目路径穿过符号链接会被拒装（`link-traversing entry`），而 `plugins/*` 全是外链。所以每个插件自己当 marketplace，插件源根目录必须有 `.claude-plugin/marketplace.json`（`source: "./"`）
- `extraKnownMarketplaces` 的键必须等于该 `marketplace.json` 的 `name`，否则插件被判孤儿不加载。oh-story 的键是 `oh-story-skills`
- 组件路径写在插件的 `.claude-plugin/plugin.json`；原地加载时 marketplace 条目里的 `agents` 等字段不生效。Claude 递归扫 `agents/`，sdlc-workflow 靠 `plugin.json` 只列顶层 19 个角色，新增角色要同步
- 相对路径按项目根解析；仓库需先通过工作区信任对话框才会注册。本机没有 `~/.zcode/local-plugins/<name>` 时只在 `/plugin` 报错，不影响会话。个人关掉某个插件：在 `.claude/settings.local.json` 写 `"<id>": false`

第三方插件正文只在 `~/.zcode/local-plugins/` 维护。新增：`ln -s ../../../.zcode/local-plugins/<name> .agents/plugins/<name>`，不要 `cp -R`；要给 Codex 用就再加 `ln -s <仓库>/.agents/plugins/<name>/skills ~/.codex/skills/<name>`。Codex 也会读仓库根 `.agents/plugins/marketplace.json`，但那条路是复制安装，本仓库不写这个文件。Grok 启用名单在 `.grok/config.toml`，那是宿主私有配置。Kimi 等确认官方发现路径后再加适配器，同样只许引用。

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
