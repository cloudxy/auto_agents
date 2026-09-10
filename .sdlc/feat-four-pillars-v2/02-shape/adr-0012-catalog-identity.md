# ADR-0012：目录身份 = 类型内全局 `name`；bundled slug 加插件前缀；不改 uq；撞名失败

> 状态：**accepted**
> 日期：2026-09-08｜决策者：/architect｜相关：FR-31 / FR-38 / FR-41 / FR-45；D3 / D12 / D18；`contract.md` §8；T-29
> 本文件是 v2 **重写**，不是旧 `.sdlc/feat-four-pillars/02-shape/adr-0012` 的拷贝。旧 FR-19/27 编号作废。

## 背景

跨插件 SKILL.md 短名会撞（如 `code-review`）。现唯一键 `uq_asset_type_name_alive` 与目录 `name` 都是 **类型内全局唯一**。若改成 `(source, name)` 复合键，公开详情、搜索、评分管线全部破坏性收缩。产品 D3 已选前缀方案；GWT-31.1 / FR-41 依赖「前缀身份 + 短名可搜」。v1 票表未写撞名合同，同步实现会顺手改唯一键或静默改名。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 禁止改 `uq_asset_type_name_alive` | 现 ORM `UniqueConstraint("asset_type","name","alive_flag")`；contract §1 本次不动 |
| 公开搜索必须能用短名 / origin 短名命中 | GWT-31.1 |
| 第一方夹具无前缀；第三方带源前缀 | FR-41；反例 `mattpocock-skills__code-review` |
| 插件撞名不得静默改名 | D12；同步失败可见 |
| alias 不得覆盖存活目录短名或存活 alias | FR-45 / GWT-45.4 |
| 禁止复制旧 02-shape 当现行合同 | spec §0 |

## 决策

- Catalog `name` **仍**类型内全局唯一。**不改** `uq_asset_type_name_alive`（不加 source、不改列序、不拆键）。
- **Bundled** 技能 / 命令 / 智能体 slug = `{plugin}__{origin_local_name}`。卡片主标题用展示名或 origin 短名，**禁止**把长前缀当主标题。命令与智能体仍是独立 catalog 行；订阅不沿父插件级联（ADR-0018）。
- 插件内字节相同的嵌套副本按 content_hash 折叠为一条。
- 两个源产生同一插件目录名：后一次 **失败**（解析失败可见），已有行的 `name` **不变**。禁止静默加源前缀改名。
- 人工 alias（FR-45）解决短 URL；同步 **不**自动建 alias；与任一存活目录短名或存活 alias 冲突 → 保存失败、两边都不变。
- 第一方夹具 `example-pdf-extractor`：无父插件、无第三方源名，商店闸打开后按该短名可搜。源同步挂上源名后按第三方，保持 unlisted 直到超管点头（ADR-0011）。

本程序不给 `skills.name` 补 `alive_flag`（无「删除再建同名」用户路径）。

T-29 验收 Then **必须**含：bundled slug 形态、`uq_asset_type_name_alive` 未改、撞名失败且已有行不变。

## 备选与否决理由

### 备选 A：唯一键改为 `(source_id, name)`

**否决理由**：破坏性收缩现存唯一约束与全部 `/{type}/{name}`、公开搜索、评分管线。D3 已否。前缀虽丑，用 alias + 搜索短名补偿。

### 备选 B：同步时对插件名静默加源前缀

**否决理由**：插件是分发单位，改名是产品事件。撞名必须失败可见，商店里不得出现一条被自动改名的新插件。

### 备选 C：本波给 `skills.name` 加上与 025 相同的 `alive_flag`

**否决理由**：无用户「删除再建同名」路径；改唯一键仍是高风险收缩。缺失只标同步缺失。若未来开放删除，再新 ADR。

### 备选 D：把身份合同并进 ADR-0011/0018 而不单开

**否决理由**：0011 管三层写权，0018 管五闸。身份键被任一侧「顺手改 uq」都会漏。单开 0012，票表 T-29 锚上。0011/0018 只指针，不重开本决策。

## 证据

```
读码：platform_core/models/capability.py UniqueConstraint("asset_type","name","alive_flag", name="uq_asset_type_name_alive")
读码：CapabilityAsset.name 注释「目录名（类型内唯一）」；tenant_id 手写恒 NULL
设计：power-market-design.md D3 前缀；D12 撞名失败；D18 alias
PRD：GWT-31.1 搜短名「代码审查」或 origin 短名命中带前缀目录名
PRD：FR-41 反例 mattpocock-skills__code-review 不是第一方
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| URL/目录名带前缀，不好看 | 主标题用短名；FR-45 alias |
| `skills.name` 无 alive 时软删重建会撞键 | 本波不提供删除；缺失≠删除 |
| 折叠错误可能丢掉真分叉 | 仅 hash 相同时折叠；hash 不同走路径段 slug |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/dba` | **不改**现存 catalog 唯一键；alias 存活全局唯一（语义，不在本 ADR 写列） |
| `/backend` | T-29 upsert 次级查找；撞名失败；bundled slug；公开 `q` 匹配短名（T-22） |
| `/frontend` | 卡片主标题不是长前缀 |
| `/qa` | T-29 Then：前缀形态、uq 未改、撞名失败；GWT-31.1 搜短名命中 |

## 后续复审条件

资产量过万或公开 URL 必须稳定短名且 alias 运维不过来时，再评估复合键——必须走 expand-contract 与路径版本。不得借复审改 uq 而不开新 ADR。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写（SH-04）。锚 FR-31/38/41/45；否决改 uq / 静默改名 / 并进 0011 而不写 Then |
