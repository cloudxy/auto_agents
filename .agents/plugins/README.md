# plugins/

本仓库第三方插件的**唯一指针农场**。每个条目是指向 `~/.zcode/local-plugins/<name>` 的符号链接。

宿主适配器（不要再各写一套指向 zcode 的指针）：

- `.grok/plugins/<name>`、`.claude/plugins/<name>` → 这里的启用子集（`dev-team` / `sdlc-workflow` / `drama-skills` / `oh-story`）。`.claude/plugins` 只有 Grok 会扫，Claude Code 不读
- Claude Code → `.claude/settings.json` 的 `extraKnownMarketplaces`（`./.agents/plugins/<name>`）+ `enabledPlugins`，同一份启用子集，原地加载。约束见 `../README.md`
- Codex → 用户级目录链接 `~/.codex/skills/<name>` → 这里的 `<name>/skills`（同一启用子集）；sdlc-workflow 的角色子代理由 `link-codex.py` 链进仓库 `.codex/agents/`。约束见 `../README.md`
- `capability-library/plugins` → 这里整目录（`POST /api/v1/capabilities/scan-plugins` 仍扫六个）

**所有 AI 工具只能引用，禁止复制**：不复制进本目录或任何适配器目录，也不用会复制的安装命令（`claude plugin install`、`grok plugin install`、`codex plugin add`）。源头改了这里跟着变。检查：`bash tools/check/arch.sh`（PL 段）、`python3 tools/check/plugin_refs.py --local`。

| 插件 | 唯一维护源 | Claude Code id（`enabledPlugins`） | Codex（`~/.codex/skills/<name>` 链接） |
|------|------------|------------------------------------|------|
| `sdlc-workflow` | `~/.zcode/local-plugins/sdlc-workflow` | `sdlc-workflow@sdlc-workflow` | 已链接；角色子代理见 `.codex/agents/` |
| `superpowers` | `~/.zcode/local-plugins/superpowers` | 不启用 | 不启用 |
| `mattpocock-skills` | `~/.zcode/local-plugins/mattpocock-skills` | 不启用 | 不启用 |
| `dev-team` | `~/.zcode/local-plugins/dev-team` | `dev-team@dev-team` | 已链接 |
| `drama-skills` | `~/.zcode/local-plugins/drama-skills` | `drama-skills@drama-skills` | 已链接 |
| `oh-story` | `~/.zcode/local-plugins/oh-story` | `oh-story@oh-story-skills` | 已链接 |

`drama-skills`、`sdlc-workflow` 上游没有 Claude 清单，`.claude-plugin/` 是在维护源里本地补的（2026-09-27）。`plugin-updater` 同步不带 `--delete`、完整性校验只核对上游文件，所以更新不会删掉它；上游哪天自带 `.claude-plugin/` 会覆盖它，届时核对 `name` 是否还和 `.claude/settings.json` 的键一致。

跳过 `sdlc-workflow-eval-workspace`（评测工作区，不是插件）。维护仍在 `~/.zcode/plugin-updater`。

Grok / Claude 适配器只接启用子集；`superpowers` / `mattpocock-skills` 只留在本农场给产品扫描（已含于 `dev-team`，重叠项用 Grok bundled skill）。

新增插件：

1. `ln -s ../../../.zcode/local-plugins/<name> <name>`，不要 `cp -R`。不要把插件内的 `skills/` 再摊到 `.agents/skills/`
2. 要给 Claude Code 用：确认维护源根目录有 `.claude-plugin/marketplace.json`（`source: "./"`），没有就补；`claude plugin validate ~/.zcode/local-plugins/<name>` 通过
3. `.claude/settings.json`：`extraKnownMarketplaces.<marketplace.json 的 name>` 指向 `./.agents/plugins/<name>`，再在 `enabledPlugins` 加 `<插件名>@<marketplace 名>: true`
4. 要给 Codex 用：`ln -s <仓库>/.agents/plugins/<name>/skills ~/.codex/skills/<name>`；插件带角色子代理时用它自己的链接脚本（如 sdlc-workflow 的 `link-codex.py`）
