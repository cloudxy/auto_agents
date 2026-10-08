# `.agents/` — 本仓库开发协作中枢

本目录是技能、规则、插件指针的**唯一仓库内真相源**，随仓库入库（插件链接除外，由 `scripts/agents_plugins.py sync` 生成）。Codex、Grok、Gemini 原生读取 `skills/`；Claude Code 经 `.claude/skills`、`.claude/rules` 两个目录链接来取。不要在 `.grok/`、`.claude/`、`.codex/`、`capability-library/plugins/` 再放一份内容。

**所有 AI 工具只能以引用方式使用插件**：符号链接，或宿主原地读取源目录；禁止任何复制。会复制插件的命令一律不用——`claude plugin install`（写缓存副本）、`grok plugin install`（留哈希副本）、`codex plugin add`（装副本且丢弃符号链接）、`cp -R`。副本会和 `~/.zcode/local-plugins` 的源头悄悄分叉。`bash tools/check/arch.sh` 的 PL 段检查仓库内适配器（CI 同跑）；`python3 tools/check/plugin_refs.py --local` 另查本机各工具缓存里有没有副本、用户级链接是否悬空。

| 子目录 | 放什么 | 不放什么 |
|--------|--------|----------|
| `skills/` | 本仓库 SOP skill（有清单、死命令、完成条件） | 常驻约定（编码/日志/配置在根 `AGENTS.md`）；第三方插件 skill |
| `rules/` | 所有工具共用的规则（`AGENTS.md`「规则」一节列出何时读）；`.claude/rules` 链到这里 | 能机械检查的红线正文（以 `tools/check/arch.sh` 为准） |
| `plugins/` | 指向本机正文的符号链接，按根 `plugins-lock.json` 由 `sync` 生成（不入库，`README.md` 除外） | 插件正文、手建链接 |
| `agents/` | 暂不启用：能力市场同步会把这里的文件当成产品资产上架，等 D2（中枢与产品内容源解耦）后再用 | 开发用子代理（现留 `.claude/agents/`） |

宿主适配器（发现路径各工具自己认）：

- `.grok/plugins/<name>` → `plugins/<name>`（只链 `plugins-lock.json` 里 hosts 含 grok 的插件）
- `.claude/skills` → `skills/`
- **Claude Code 插件**：`.claude/settings.json` 的 `extraKnownMarketplaces` 把每个 `./.agents/plugins/<name>` 注册成 directory marketplace，`enabledPlugins` 启用锁内 hosts 含 claude 的插件。插件从 `plugins/<name>` 原地加载，不进 `~/.claude/plugins/cache`，源头改了下次会话生效
- `.claude/plugins/<name>` → 锁内 hosts 含 claude 的插件，只给 Grok 扫；**Claude Code 不读这个目录**
- `capability-library/plugins` → `plugins/`（整农场；平台 `scan-plugins` 入口，不改 `LIBRARY_ROOT`）
- **Codex**（CLI 0.156.1 实测）：`.codex/` 与 `.claude/` 对称，只在本项目生效（家目录 `~/.codex`、`~/.claude` 是所有项目共用的，项目插件一律不挂那里，以隔离不同项目的 skill）。`.codex/skills/<name>` → `../../.agents/plugins/<name>/skills`（相对链接，锁内 hosts 含 codex 的插件；Codex 从任一子目录都会读仓库根的 `.codex/skills/`，官方文档未写）；`.codex/agents/*.toml` 是 sdlc-workflow 角色子代理的相对链接。sdlc-workflow 两者都由 `python3 .agents/plugins/sdlc-workflow/scripts/link-codex.py --project <仓库根>` 生成（经中枢路径调用，链接就经过中枢）。列出时带插件名前缀（如 `sdlc-workflow:sdlc`）。本仓库 SOP skill 不进 `.codex/skills`：Codex 已原生读取 `.agents/skills`，再链会重复。Codex 的插件机制只会复制（装进 `~/.codex/plugins/cache`），不用它。`.codex/agents` 只对**受信任**项目生效，首次在本仓库用 Codex 时确认信任

Claude Code 的硬约束（2.1.283 实测，改接入前先读）：

- 聚合 marketplace 行不通：条目路径穿过符号链接会被拒装（`link-traversing entry`），而 `plugins/*` 全是外链。所以每个插件自己当 marketplace，插件源根目录必须有 `.claude-plugin/marketplace.json`（`source: "./"`）
- `extraKnownMarketplaces` 的键必须等于该 `marketplace.json` 的 `name`，否则插件被判孤儿不加载
- 组件路径写在插件的 `.claude-plugin/plugin.json`；原地加载时 marketplace 条目里的 `agents` 等字段不生效。Claude 递归扫 `agents/`，sdlc-workflow 靠 `plugin.json` 只列顶层 19 个角色，新增角色要同步
- 相对路径按项目根解析；仓库需先通过工作区信任对话框才会注册。本机没有 `~/.zcode/local-plugins/<name>` 时只在 `/plugin` 报错，不影响会话。个人关掉某个插件：在 `.claude/settings.local.json` 写 `"<id>": false`

第三方插件采用「引用 + 锁文件」：仓库根 `plugins-lock.json` 是唯一清单（git 来源 + 固定 commit + hosts），正文只在本机 `~/.zcode/local-plugins/<name>`。新增或删除插件只改锁文件，再跑 `python3 scripts/agents_plugins.py sync`（缺正文按锁克隆、建链接、删锁外链接），不要手建链接、不要 `cp -R`。没有 git 远端的插件不进本仓库。Codex 也会读仓库根 `.agents/plugins/marketplace.json`，但那条路是复制安装，本仓库不写这个文件。Grok 启用名单在 `.grok/config.toml`，那是宿主私有配置。Kimi 等确认官方发现路径后再加适配器，同样只许引用。

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
