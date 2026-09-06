# capability-library

跨工具共享的内容库：SKILL.md 原文 + 分发适配器。技能治理（扫描入库 / 评分 / 矫正 / 分类）走主平台 `v1/skills` 与 admin「技能中心」，本目录不再提供本地后台。

本目录位于 `auto_agents/capability-library/`，与项目协作 skill（`.agents/skills/`）分开：

| 路径 | 职责 |
|------|------|
| `.agents/skills/` | 本仓库开发协作 skill（`/new-svc` `/check-arch` 等），随项目走 |
| `capability-library/` | 跨工具内容文件与适配器；治理真相源在主库 |

## 数据流

- **内容真相源**：`skills/<name>/` 文件（SKILL.md 正文 / meta.yaml 治理快照 / CHANGELOG.md），git 版本化
- **治理真相源**：主库 `skills` / `skill_reviews` / `skill_jobs`
- 管理面写操作由主后端写回 meta.yaml（tmp+rename）并追加 CHANGELOG
- 扫描：`POST /api/v1/skills/scan`（admin）增量入库
- 分发：`adapters/*.sh` + `sync.sh`

## 目录结构

```
skills/<name>/
  SKILL.md      工具原生格式（YAML frontmatter + 正文），不要在这里塞治理字段
  meta.yaml     库治理元数据：category / industries / capability 评分 / status / similar_to / source
  SOURCE.md     来源链接、作者、引入日期
  CHANGELOG.md  每次手动更新的记录（日期 | 操作人 | 摘要）
manifests/<tool>.yaml   每个工具启用哪些 skill（每行 "- <name>"）
adapters/<tool>.sh      每个工具的分发脚本（symlink 型 或 拼接生成型）
taxonomy/
  industries.yaml   行业标签表，可增删
  rubric.md         评分标准说明（completeness/doc_quality/maintenance/real_world_effect）
index/
  build_index.py    扫描 skills/ 重建 index.db，纯派生缓存
sync.sh             跑所有 adapters，可选 --reindex
```

## 常用操作

```bash
cd capability-library
./sync.sh              # 把 manifests 里启用的 skill 分发到各工具
./sync.sh --reindex     # 分发后重建 index/index.db
```

不要在本目录再建 `.venv`，用仓库根 `uv sync`。

## 引入新 skill

1. 在 `skills/<name>/` 下放 `SKILL.md`（保持工具原生 frontmatter）。
2. 配 `meta.yaml`、`SOURCE.md`、`CHANGELOG.md`。
3. 按 `taxonomy/rubric.md` 打分。
4. 在对应 `manifests/<tool>.yaml` 加一行 `- <name>`。
5. 跑 `./sync.sh --reindex`；主平台扫描走 `POST /api/v1/skills/scan`。

## 各工具适配

| 工具 | 机制 | 适配方式 |
|---|---|---|
| Claude Code | `~/.claude/skills/<name>/` | symlink（`adapters/claude-code.sh`） |
| Codex | 暂按单一规则文件 | 拼接生成 `~/.codex/capability-library.md`（`adapters/codex.sh`） |
