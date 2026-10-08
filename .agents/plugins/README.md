# plugins/

本仓库第三方插件的**指针农场**。启用哪些插件、钉在哪个 commit，只认仓库根 [`plugins-lock.json`](../../plugins-lock.json)；本目录的条目都是指向本机正文 `~/.zcode/local-plugins/<name>` 的符号链接，由脚本生成，不要手建。

```bash
python3 scripts/agents_plugins.py sync     # 本机缺正文就按锁克隆；建好本目录与各宿主链接；删掉锁外插件的链接
python3 scripts/agents_plugins.py check    # 只读校验（--strict 时 commit 漂移也算违规）
python3 scripts/agents_plugins.py lock     # 正文更新且已推到远端后，把锁的 commit 改成本机 HEAD
```

| 插件 | 来源（锁） | Claude Code id | Grok | Codex |
|------|-----------|----------------|------|-------|
| `sdlc-workflow` | `https://github.com/cloudxy/sdlc-plugins` | `sdlc-workflow@sdlc-workflow` | `.grok/plugins/sdlc-workflow` | `.codex/skills/sdlc-workflow`；角色子代理在 `.codex/agents/`（`link-codex.py --project`） |

宿主适配器（锁里 `hosts` 决定，`sync` 生成）：

- Claude Code → `.claude/settings.json` 的 `extraKnownMarketplaces`（`./.agents/plugins/<name>`）+ `enabledPlugins`，原地加载；`.claude/plugins/<name>` 只给 Grok 的 Claude 兼容通道扫
- Grok → `.grok/plugins/<name>`，启用名单在 `.grok/config.toml`
- Codex → 项目级 `.codex/skills/<name>` → `<name>/skills`；家目录 `~/.codex` 所有项目共用，不挂
- `capability-library/plugins` → 本目录整体（产品 `scan-plugins` 入口）

**所有 AI 工具只能引用，禁止复制**：不复制进本目录或任何适配器目录，也不用会复制的安装命令（`claude plugin install`、`grok plugin install`、`codex plugin add`）。检查：`bash tools/check/arch.sh`（PL 段，按锁文件）、`python3 tools/check/plugin_refs.py --local`。

新增插件：插件必须有可公开拉取的 git 远端。在 `plugins-lock.json` 加一条（`source` / `ref` / `commit` / `localPath` / `hosts`），跑 `sync`；要给 Claude Code 用，正文根目录须有 `.claude-plugin/marketplace.json`，再在 `.claude/settings.json` 登记 marketplace 与 `enabledPlugins`。没有远端的插件不进本仓库。
