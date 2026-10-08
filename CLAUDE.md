@AGENTS.md

# Claude Code 专属

上面导入的 `AGENTS.md` 是所有 AI 工具共用的唯一项目指南；本文件只放 Claude Code 才有的部分，不要在这里重复项目事实。

- **规则**：`.claude/rules` → `../.agents/rules`（目录链接，每次会话自动加载；其他工具按 `AGENTS.md`「规则」一节读取）
- **技能**：`.claude/skills` → `../.agents/skills`（Codex / Grok / Gemini 原生读 `.agents/skills`，不需要链接）
- **子代理**：`.claude/agents/`（`arch-warden` / `spider-doctor` / `memory-curator`）。暂不迁入 `.agents/agents/`：能力市场同步会把那里的文件当成产品资产上架，等 D2（开发中枢与产品内容源解耦）完成后再迁
- **Hooks**：`.claude/hooks/`——`inject_context.sh` 注入项目身份与近期记忆，`guard_meta.sh` 拦截对 rules / skills / IDENTITY / SOUL / settings.json 的改动（需人工确认），`suggest_memory.sh` 提示归档经验。项目身份 `.claude/IDENTITY.md`，回答风格 `.claude/SOUL.md`
- **插件**：`.claude/settings.json` 原地加载 `plugins-lock.json` 里的 `sdlc-workflow`；个人开关写 `.claude/settings.local.json`（不入库）
- **项目记忆**：`.claude/memory/` 与 `.claude/MEMORY.md` 只在本机，不入库
