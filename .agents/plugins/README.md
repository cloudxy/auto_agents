# plugins/

本仓库第三方插件的**唯一指针农场**。每个条目是指向 `~/.zcode/local-plugins/<name>` 的符号链接。

宿主适配器（不要再各写一套指向 zcode 的指针）：

- `.grok/plugins/<name>`、`.claude/plugins/<name>` → 这里的启用子集（`dev-team` / `sdlc-workflow` / `drama-skills` / `oh-story`）
- `capability-library/plugins` → 这里整目录（`POST /api/v1/capabilities/scan-plugins` 仍扫六个）

**禁止把插件内容复制进本目录或任何适配器目录。** 源头改了这里跟着变。

| 插件 | 唯一维护源 |
|------|------------|
| `sdlc-workflow` | `~/.zcode/local-plugins/sdlc-workflow` |
| `superpowers` | `~/.zcode/local-plugins/superpowers` |
| `mattpocock-skills` | `~/.zcode/local-plugins/mattpocock-skills` |
| `dev-team` | `~/.zcode/local-plugins/dev-team` |
| `drama-skills` | `~/.zcode/local-plugins/drama-skills` |
| `oh-story` | `~/.zcode/local-plugins/oh-story` |

跳过 `sdlc-workflow-eval-workspace`（评测工作区，不是插件）。维护仍在 `~/.zcode/plugin-updater`。

Grok / Claude 适配器只链启用子集；`superpowers` / `mattpocock-skills` 只留在本农场给产品扫描（已含于 `dev-team`，重叠项用 Grok bundled skill）。

新增插件：`ln -s ../../../.zcode/local-plugins/<name> <name>`，不要 `cp -R`。不要把插件内的 `skills/` 再摊到 `.agents/skills/`。
