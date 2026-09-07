# ADR-0012：目录身份保持类型内全局 `name`，bundled 子资产加插件前缀

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：D3/D3b/D3c/D12、FR-19 FR-27、`contract.md` §7
> 本文件 **整份替换** stale ADR-0012。不重开 D3。

## 背景

跨插件 SKILL.md 短名约 51 个冲突（`code-review` 等）。现唯一键 `uq_asset_type_name_alive` 与 `skills.name` 都是类型内全局唯一。若改成 `(source, name)` 复合键，所有 `/skills/{name}` 与公开 URL 都要破坏性收缩。

产品 D3 已选前缀方案。本 ADR 把它升为数据身份合同，避免实现时「顺手改唯一键」。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 禁止改 `uq_asset_type_name_alive` | ADR-0002 破坏性；dba 诊断 |
| 公开搜索必须能用短名命中 | FR-19 / D3 |
| 插件撞名不得静默改名 | D12 / FR-27.2 |
| 无「删除再建同名」用户路径 | spec 9.2 答 dba Q1 |
| 别名不得覆盖存活目录名 | GWT-19.4 |

## 决策

- Catalog `name` 仍类型内全局唯一。
- Bundled 技能 / 命令 / 智能体 slug = `{plugin}__{origin_local_name}`；展示与搜索用 `origin_local_name` / `title`，**禁止**把长前缀当主标题。命令与智能体同样是独立 catalog 行（D26/D27），订阅不沿父插件级联（D24）。
- 插件内字节相同的嵌套副本按 content_hash 折叠为一条（D3b）。
- `origin_ref` 相对 adapter root（D3c）：git 单插件 clone 用 `"."`。
- 两个源产生同一插件目录名：后一次 `parse_error`，已有行的 `name` 不变。
- 人工 vanity alias 表解决「想用短 URL」；同步不自动建 alias；与存活 `capability_assets.name` 冲突 → 保存失败。

不在本波给 `skills.name` 补 `alive_flag`（产品无删后重建路径）。

## 备选与否决理由

### 备选 A：唯一键改为 `(source_id, name)`

**否决理由**：要改现存唯一约束与全部 `/skills/{name}`、公开详情、评分管线，属破坏性收缩。D3 已否。前缀虽丑，可用 alias + 搜索短名补偿。

### 备选 B：同步时对插件名静默加源前缀

**否决理由**：插件是分发单位，改名是产品事件。FR-27.2 要求记解析失败而不是商店里出现一条被自动改名的新插件。

### 备选 C：本波给 `skills.name` 加上与 025 相同的 `alive_flag`

**否决理由**：无用户「删除再建同名」路径；改唯一键仍是高风险收缩。缺失只标 `sync_state=missing`。若未来开放删除，再新 ADR。

## 证据

设计本机盘点：跨插件 51 个重名。现 ORM `UniqueConstraint("asset_type", "name", "alive_flag")`。公开搜索若不匹配 `origin_local_name`，用户搜 `code-review` 会找不到 `mattpocock-skills__code-review`（FR-19）。`CapabilityService.list_assets(q=)` 今日只 `name LIKE`。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| URL/目录名带前缀，不好看 | 主标题用短名；D18 alias |
| `skills.name` 无 alive 时软删重建会撞键 | 本波不提供删除；缺失≠删除 |
| 折叠错误可能丢掉真分叉 | 仅 hash 相同时折叠；hash 不同走路径段 slug |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/dba` | 不改现存 catalog 唯一键；alias 存活全局唯一 |
| `/backend` | upsert 次级查找；公开 `q` 匹配短名 |
| `/frontend` | 卡片主标题不是长前缀 |
| `/qa` | 重名夹具；搜 `code-review` 命中；别名冲突失败 |

## 后续复审条件

资产量过万或公开 URL 必须稳定短名且 alias 运维不过来时，再评估复合键——必须走 expand-contract 与路径版本。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 采纳（对齐已决 D3，不重开产品） |
