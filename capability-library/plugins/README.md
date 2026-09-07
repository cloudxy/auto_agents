# plugins/

平台插件目录。`POST /api/v1/capabilities/scan-plugins` 扫描这里的子目录入库。

**禁止把插件内容复制进本目录。** 每个插件只放指向唯一维护源的符号链接，源头改了这里跟着变。

| 插件 | 唯一维护源 |
|------|------------|
| `sdlc-workflow` | `~/.zcode/local-plugins/sdlc-workflow` |
| `superpowers` | `~/.zcode/local-plugins/superpowers` |
| `mattpocock-skills` | `~/.zcode/local-plugins/mattpocock-skills` |
| `dev-team` | `~/.zcode/local-plugins/dev-team`（`.claude-plugin` 仍叫 mattpocock-skills，**不**链进 `.grok/plugins`，避免盖住正本；能力库按目录名引用） |
| `drama-skills` | `~/.zcode/local-plugins/drama-skills` |
| `oh-story` | `~/.zcode/local-plugins/oh-story` |

跳过 `sdlc-workflow-eval-workspace`（评测工作区，不是插件）。维护仍在 `~/.zcode/plugin-updater`，不要把内容复制进本仓库。

新增插件：`ln -s <canonical-path> <name>`，不要 `cp -R`。
