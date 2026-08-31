# skills-library

多工具共享的 skill 库：单一源头 + 溯源记录 + 人工能力评分 + 行业标签 + 本地管理后台。

本目录位于 `auto_agents/skills-library/`，与项目协作 skill（`.agents/skills/`）分开：

| 路径 | 职责 |
|------|------|
| `.agents/skills/` | 本仓库开发协作 skill（`/new-svc` `/check-arch` 等），随项目走 |
| `skills-library/` | 跨工具共享的 skill 目录库（治理元数据、评分、分发适配器、本地后台） |

git 历史跟 auto_agents 主仓库走，每次改动一次 commit，方便回滚。

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
  build_index.py    扫描 skills/ 重建 index.db，纯派生缓存，可随时删除重建
backend/
  app.py            本地管理后台 (FastAPI)，只监听 127.0.0.1
  web/              原生 HTML/JS 前端，无构建步骤
sync.sh             总入口：跑所有 adapters，可选 --reindex / --serve
```

## 环境准备

后台和索引脚本需要 PyYAML / FastAPI / uvicorn。直接用 auto_agents 根目录的 uv workspace，不要在本目录再建 `.venv`：

```bash
# 在 auto_agents 根目录
uv sync
```

`sync.sh` 会按顺序查找：`auto_agents/.venv/bin/python3` → 本目录 `.venv` → 系统 `python3`。

## 常用操作

```bash
cd skills-library
./sync.sh              # 把 manifests 里启用的 skill 分发到各工具（symlink / 拼接生成）
./sync.sh --reindex     # 分发后重建 index/index.db
./sync.sh --serve       # 分发 + 重建索引 + 启动本地后台 (默认 http://127.0.0.1:8765)
```

后台功能：

- 列表：按分类/行业/状态筛选，按评分排序
- 详情：查看 SOURCE.md / CHANGELOG.md / meta.yaml 全字段
- 编辑评分与分类：写回对应 skill 的 `meta.yaml`，保存后自动重建索引
- 检查更新：对配置了 `source.url` 的 skill 做只读拉取 + 哈希对比，不自动覆盖文件，diff 提示后手动决定是否更新并追加 CHANGELOG
- 对比：同 category 下多个 skill 并排看 rubric 细分，辅助判断保留哪个

## 引入新 skill 流程

1. 在 `skills/<name>/` 下放 `SKILL.md`（保持工具原生 frontmatter 格式）。
2. 配一份 `meta.yaml`（可参照 `skills/example-pdf-extractor/meta.yaml` 模板）、`SOURCE.md`、`CHANGELOG.md`。
3. 按 `taxonomy/rubric.md` 打分，填 `capability` 字段；如需 AI 评审参考分，让 agent 读 SKILL.md 按同一 rubric 给 `ai_suggested_score`，人工确认后再定 `capability.score`。
4. 想让哪个工具用，在对应 `manifests/<tool>.yaml` 加一行 `- <name>`。
5. 跑 `./sync.sh --reindex` 生效，或在后台点"同步到各工具"。

## 手动更新流程（不做自动抓取）

后台"检查更新"只读比对源地址内容哈希，发现变化后：手动替换 `SKILL.md`/资源文件 → 在后台填一行更新说明写入 `CHANGELOG.md` → 手动更新 `meta.yaml.source.content_hash`。全程靠 git 记录改动，可回滚。

## 各工具适配情况

| 工具 | 机制 | 适配方式 |
|---|---|---|
| Claude Code | `~/.claude/skills/<name>/`，原生支持独立目录 | symlink（`adapters/claude-code.sh`） |
| Codex | 机制未最终确认，暂按"只吃单一规则文件"处理 | 拼接生成 `~/.codex/skills-library.md`（`adapters/codex.sh`），若后续确认有独立目录机制会切换为 symlink |
| Kimi / Grok / workbuddy / zcode / traework / Qoder | 未知，需要官方文档或实际配置路径确认 | 待补，届时退化为 symlink 型或拼接型两种 fallback 之一 |
