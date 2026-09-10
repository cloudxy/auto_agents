# `.agents/` — 本仓库开发协作中枢

本目录是技能 / 插件指针 /（将来）可移植智能体的**唯一仓库内真相源**。Grok、Claude、Codex、Kimi 等通过各自宿主目录的符号链接来取，不要在 `.grok/`、`.claude/`、`capability-library/plugins/` 再放一份内容。

| 子目录 | 放什么 | 不放什么 |
|--------|--------|----------|
| `skills/` | 本仓库项目协作 skill（`/new-svc` `/check-arch` 等） | 第三方插件里的 skill（那些跟着插件走，摊开会双载） |
| `plugins/` | 指向 `~/.zcode/local-plugins/<name>` 的符号链接 | 插件正文、`sdlc-workflow-eval-workspace` |
| `agents/` | 尚未启用。可移植智能体以后才进这里 | Claude 专用 frontmatter（现留 `.claude/agents/`） |

宿主适配器（发现路径各工具自己认）：

- `.grok/plugins/<name>` → `plugins/<name>`（Grok 只链启用的四个，不链 `superpowers` / `mattpocock-skills`）
- `.claude/skills` → `skills/`
- `.claude/plugins/<name>` → 与 Grok 同一份四插件子集（Grok 也会扫 `.claude/plugins`）
- `capability-library/plugins` → `plugins/`（整农场；平台 `scan-plugins` 入口，不改 `LIBRARY_ROOT`）

第三方插件正文只在 `~/.zcode/local-plugins/` 维护。新增：`ln -s ../../../.zcode/local-plugins/<name> .agents/plugins/<name>`，不要 `cp -R`。Grok 启用名单在 `.grok/config.toml`，那是宿主私有配置。

Codex / Kimi 等确认官方发现路径后再加适配器，不要假设它们扫 `.agents/plugins`。
