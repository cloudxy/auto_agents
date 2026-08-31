# 跨 Agent 统一记忆体系整合方案（2026-08）

> 范围：仓库内全部 agent 指令文件与记忆资产（AGENTS.md / CLAUDE.md / GEMINI.md / CODEBUDDY.md / .claude/ / .qoder/hooks/ / .agents/skills/ 等）
> 性质：设计文档（已定稿方案），本文档本身不伴随任何代码改动；实施时以第 4 章五阶段计划为准。
> 读者：团队工程师。文档可独立阅读，无需前置上下文。

---

## 1. 摘要

本仓库当前存在多套并行维护的 agent 指令与记忆资产：根目录 `AGENTS.md` 与 `CLAUDE.md` 内容高度重叠却各自独立维护，`AGENTS.md` 引用的 `GEMINI.md` 实际不存在，`.claude/` 下已有一套成熟的记忆体系但只被 Claude Code 一侧消费，而 Qoder 侧的 hooks 事实上已在跨目录读取 `.claude/` 的记忆——即"复用先例已经存在，但没有任何统一治理"。

本方案的目标是：将 **Claude Code、Codex、Grok、workbuddy、zcode、Kimi、qoder-cn、CodeBuddy、qoderworkcn、Gemini CLI 共 10 个 agent** 的记忆体系整合为**一套三层统一模型**：

- **L1 指令层**：根 `AGENTS.md` 作为唯一静态事实源，各 agent 指令文件以软链或指针方式指向它；
- **L2 记忆层**：`.claude/memory/` + `.claude/MEMORY.md` 作为唯一项目级动态记忆库；
- **L3 注入层**：hooks 按需裁剪注入，MCP 作为可选进阶通道。

实施分为五个阶段（基线固化 → 指令层收敛 → 记忆层统一 → 注入层与分发脚本 → 验收），全部改动可回滚，高风险步骤（CLAUDE.md 收敛）采用原子提交 + 保守备选方案双保险。方案同时明确否决了"完整构建管道""记忆目录物理搬迁""hooks 立即软链化""MCP 唯一通道"四个备选方向，理由见第 8 章。

---

## 2. 背景与现状

### 2.1 现有资产盘点

仓库中已存在多套 agent 指令 / 记忆资产，现状如下：

| 资产 | 现状 | 问题 |
|---|---|---|
| 根目录 `AGENTS.md`（4.5KB） | 面向通用 agent 的项目指令文件 | 与 `CLAUDE.md` 内容高度重叠，但独立维护 |
| 根目录 `CLAUDE.md`（5KB） | Claude Code 专属指令文件 | 与 `AGENTS.md` 人工同步、易漂移；当前两者均有未提交修改 |
| `GEMINI.md` | 被 `AGENTS.md` 第 82 行引用，**但文件不存在** | 悬空引用，架构审计已列为问题 |
| `.claude/` | 成熟记忆体系：`MEMORY.md` 索引、`memory/` 条目格式契约、`IDENTITY.md`、`SOUL.md`、`rules/`、`hooks/`、memory-curator agent | 仅被 Claude Code 一侧正式消费 |
| `.qoder/hooks/` | `.claude/hooks/` 的复制变体，**不入库** | 重复维护；但已实测可工作 |
| `.claude/skills -> ../.agents/skills` | 符号链接 | 证明软链模式团队可维护（先例） |

### 2.2 关键实测事实

- `.qoder/hooks/inject_context.sh` **已实测跨目录读取** `.claude/IDENTITY.md` 与 `.claude/memory/`（1KB 注入预算）——跨 agent 复用 `.claude/` 记忆的先例已经存在；
- `.claude/hooks/guard_meta.sh` 与 `.qoder/hooks/guard_meta.sh` 的 `GUARD_REGEX` **当前不覆盖根目录文件**（已实测），即根目录指令文件可被 agent 意外改写而无守卫；
- `.claude/skills -> ../.agents/skills` 符号链接长期可维护，软链模式有成功先例。

### 2.3 整合目标

整合以下 10 个 agent 的记忆体系，使其共享同一事实源与同一项目级记忆库：

> Claude Code、Codex、Grok、workbuddy、zcode、Kimi、qoder-cn、CodeBuddy、qoderworkcn、Gemini CLI。

核心原则：

1. **事实源唯一**：项目指令只在一处维护（根 `AGENTS.md`），其余入口全部为指针或软链；
2. **记忆库唯一**：项目级记忆只存在 `.claude/memory/`，不做物理搬迁；
3. **个人层明确排除**：`~/.claude` 等各工具 home 目录下的个人偏好属个人域，**不入库**；
4. **机械可检查**：关键约束（链接完整性、字节预算）由脚本门禁保障，不依赖人工自觉。

---

## 3. 总体架构：三层统一模型

```
L1 指令层（静态）  → 根 AGENTS.md 为唯一事实源，各 agent 指令文件软链或指针指向它
L2 记忆层（动态）  → .claude/memory/（frontmatter 条目）+ .claude/MEMORY.md（索引）为唯一项目级记忆库
L3 注入层（运行时）→ hooks（inject_context/suggest_memory）按需裁剪注入；MCP 为可选进阶通道
个人层（~/.claude 等）明确排除，属个人域不入库
```

三层职责边界：

- **L1 指令层**回答"这个仓库是什么、红线在哪"——静态、入库、受门禁保护；
- **L2 记忆层**回答"我们踩过什么坑、有什么套路"——动态、条目化、有格式契约与索引；
- **L3 注入层**回答"这次会话该给 agent 看哪些"——运行时按需裁剪，避免全量注入撑爆上下文。

---

## 4. 各 Agent 适配矩阵

按各 agent 的文件约定，划分为三个接入级别：

| Agent | 接入方式 | 级别 |
|---|---|---|
| Codex / Grok / Cursor / Aider 类 | 原生读 `AGENTS.md`，零操作 | **T1 零改动** |
| Gemini CLI | `GEMINI.md` 指针/软链（补当前悬空引用） | **T2 指针** |
| Kimi | 原生读工作目录 `AGENTS.md`（官方已确认），零操作 | **T1** |
| Qoder (qoder-cn) | 原生读 `AGENTS.md` + `.qoder/rules/`；其 hooks 已跨目录读 `.claude/memory/`，零操作 | **T1** |
| Claude Code | `CLAUDE.md` 合并独有内容后 → 软链到 `AGENTS.md`（备选：`@AGENTS.md` import 保守方案） | **T2 收敛** |
| CodeBuddy | `CODEBUDDY.md` 一行指针文件 | **T2 指针** |
| workbuddy / qoderworkcn / zcode | 无公开文件约定 → 降级策略：依赖 `AGENTS.md` 兜底；`.zcode/` 仅存会话计划，不纳入记忆体系 | **T3 降级** |

级别含义：

- **T1 零改动**：agent 原生识别 `AGENTS.md`，无需任何额外文件；
- **T2 指针/收敛**：需要一行指针文件或软链，一次配置、长期免维护；
- **T3 降级**：agent 无公开文件约定，依赖 `AGENTS.md` 作为兜底事实源；日后该 agent 若推出文件约定，只需新增指针，事实源不动（见第 7 章风险表）。

---

## 5. 实施阶段（五阶段）

### 阶段一：基线固化与 .gitignore 治理（前置）

1. **固化基线**：确认/提交当前工作区未提交修改中的 `AGENTS.md` 与 `CLAUDE.md`，记录基线 `git rev-parse HEAD`。
2. **.gitignore 补充**：
   - 忽略 `AGENTS.local.md`、`CODEBUDDY.local.md`（个人层防污染）；
   - `.zcode/`、`skills-library/` 按入库决策显式处理；
   - 指针文件（`GEMINI.md` / `CODEBUDDY.md`）**保持入库**。
3. **验证**：`git check-ignore` 确认各路径归类正确。

### 阶段二：L1 指令层收敛

4. **补缺指针文件（只新增）**：
   - 新增 `GEMINI.md`，一行内容："请阅读仓库根 `AGENTS.md` 与 `.claude/rules/project_rule.md`"（修复悬空引用）；
   - 新增 `CODEBUDDY.md`，同格式指针。
5. **Gemini 软链升级（可回滚）**：环境支持符号链接时改 `ln -s AGENTS.md GEMINI.md`；Windows / `core.symlinks=false` 自动回退指针文件。
6. **CLAUDE.md 收敛（唯一高风险步，原子提交）**：
   - 先实测 diff，将 `CLAUDE.md` 独有内容（目录树、架构哲学段）合并进 `AGENTS.md`，控制总体积 **< 24KB**（给 Codex 32KiB 合并上限留余量）；
   - 再以符号链接替换实体文件，一次原子提交、可整体 `git revert`；
   - **保守备选**：仅在 `CLAUDE.md` 顶部加 `@AGENTS.md` import（Claude 官方变通），保留实体文件。

### 阶段三：L2 记忆层统一

7. **确认 `.claude/memory/` 为唯一项目级记忆库**：
   - 沿用现有格式契约（`README.md`：frontmatter 含 `name` / `description` / `metadata.type` ∈ {reference, troubleshooting, playbook, decision}，单条 ≤ 500 行）与索引规格（`MEMORY.md`：≤ 200 行、软删除）；
   - **扩展 frontmatter（可选、向后兼容）**：增加 `agents: [all]` 与 `priority: P0..P3` 字段，为按 agent 裁剪注入预留；
   - Qoder 侧零改动即已接入（实测先例，见 2.2）。
8. **hooks 去重暂缓**：`.qoder/hooks/` 是 `.claude/hooks/` 的复制变体，但 `.qoder/` 不入库且已验证可工作，本阶段仅**文档化差异**，不做软链合并；体系稳定后可选升级。
9. **守卫扩展**：`.claude/hooks/guard_meta.sh` 与 `.qoder/hooks/guard_meta.sh` 的 `GUARD_REGEX` 当前不覆盖根目录文件（已实测），追加 `AGENTS.md|CLAUDE.md|GEMINI.md|CODEBUDDY.md`，防止事实源被 agent 意外改写（hook 为 ask 非阻断、fail-open 设计）。

### 阶段四：L3 注入层与分发脚本

10. **新增 `scripts/sync-agent-files.sh`（幂等，约 30 行）**：校验/重建全部符号链接与指针文件（清单硬编码于脚本内）；检测到非符号链接环境时降级为"重写指针文件"模式。
11. **挂入门禁**：
    - `.pre-commit-config.yaml` 增加该脚本为 hook；
    - `scripts/check-arch.sh` 增加"指令文件链接完整性 + `AGENTS.md` 字节预算"检查（沿用退出码 = 违规数模式）。
12. **可选进阶——MCP 共享记忆通道**：在 `.mcp.json` 增加 memory MCP server（如 `@modelcontextprotocol/server-memory`），为支持 MCP 的 agent 提供运行时按需检索；**仅当记忆条目规模增长后启用**，本期只预留挂载点说明。

### 阶段五：验收

13. **冒烟验证**：在 Claude Code、Codex、Gemini、Qoder 中各跑一次"复述本仓库架构红线"，确认读到同一事实源。
14. `bash scripts/check-arch.sh` 退出码 0；`bash scripts/sync-agent-files.sh` 幂等复跑无变化。
15. 在 `AGENTS.md` 尾部追加"统一记忆矩阵"表，实现体系自文档化。

---

## 6. 依赖关系

- **阶段一（步骤 1-3）是所有后续步骤的硬前置**；
- 阶段二的步骤 4、5、6 **相互独立可并行**；其中 6 依赖 1（基线固化）；
- 阶段三（7-9）依赖阶段二完成（事实源位置定型）；
- 阶段四（10-12）依赖阶段二、三（链接清单定型）；
- 阶段五依赖全部。

```
阶段一(1-3) ──► 阶段二(4/5/6 并行) ──► 阶段三(7-9) ──► 阶段四(10-12) ──► 阶段五(13-15)
```

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 符号链接在 Windows/CI 被 checkout 成文本垃圾 | 高风险文件（`CLAUDE.md`）优先用 `@AGENTS.md` import 保守方案；sync 脚本带降级复制模式；CI 加 `head -1` 冒烟检查 |
| 合并时丢失 `CLAUDE.md` 独有内容 | 先 diff 后合并，原子提交可 `git revert` |
| 弱模型忽略一行指针文件 | 指针写明双入口（`AGENTS.md` + `project_rule.md`）；硬红线本由 `check-arch.sh` 机械检查，不依赖指令文件 |
| `AGENTS.md` 膨胀超 Codex 32KiB 上限 | 保持"地图而非手册"原则，细节留在 `project_rule.md` 与 memory 条目；门禁加字节数检查 |
| workbuddy / qoderworkcn / Grok 机制后续变化 | T3 降级策略与之解耦——换文件名只需改指针，事实源不动 |
| 个人偏好污染团队记忆 | scope 边界写入 memory README：user-level 偏好留在各工具 home 目录 |

---

## 8. 已否决的备选方案

| 备选方案 | 否决理由 |
|---|---|
| 完整构建管道（记忆 SQLite 索引 + 生成式分发 + 适配器模板） | 记忆条目当前为零、索引为空，构建管道属过度工程；其有价值元素（字节预算、priority 裁剪、适配矩阵）已吸收进本方案，待条目规模化后可作为阶段四第 12 步之后的演进方向 |
| 将 `.claude/memory/` 迁移为 `.agents/memory/` 并全软链 | 移动已验证工作的目录会迫使三个 hook 路径变更，回归风险大于收益；`.claude/memory/` 事实上已被 qoder hooks 跨目录复用，"名义归属"问题用文档说明代替物理搬迁 |
| 立即将 `.qoder/hooks/` 软链化收敛 | 该目录不入库、已是工作变体，合并失败无回滚凭证；暂缓至体系稳定 |
| MCP memory server 作为唯一共享通道 | 并非所有目标 agent 支持 MCP，不能作为唯一通道，仅作静态文件的补充 |

---

## 9. 验收标准（Checklist）

- [ ] `AGENTS.md` 与 `CLAUDE.md` 基线已提交，基线 commit 已记录
- [ ] `.gitignore` 经 `git check-ignore` 验证：`*.local.md` 被忽略，指针文件入库
- [ ] `GEMINI.md` / `CODEBUDDY.md` 指针文件存在且内容指向双入口
- [ ] `CLAUDE.md` 已收敛（软链或 `@AGENTS.md` import），`AGENTS.md` 体积 < 24KB
- [ ] `.claude/memory/` frontmatter 扩展字段（`agents` / `priority`）文档化，向后兼容
- [ ] 两份 `guard_meta.sh` 的 `GUARD_REGEX` 已覆盖四个根目录指令文件
- [ ] `scripts/sync-agent-files.sh` 幂等复跑无变化
- [ ] `bash scripts/check-arch.sh` 退出码 0（含新增链接完整性 + 字节预算检查）
- [ ] 四端（Claude Code / Codex / Gemini / Qoder）冒烟复述架构红线一致
- [ ] `AGENTS.md` 尾部含"统一记忆矩阵"表
