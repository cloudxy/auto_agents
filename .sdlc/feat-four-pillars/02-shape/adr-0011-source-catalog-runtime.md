# ADR-0011：Source / Catalog / Runtime 三层分离，指针不进旧扫描根

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：PRD FR-25 FR-27、D1/D1b/D8/D15/D16、`contract.md` §2.5
> 本文件 **整份替换** stale ADR-0011。决策与 D1–D16 对齐，不重开产品。

## 背景

今日插件接入靠 `capability-library/plugins/` 下每人一条 symlink，同时 `.grok/plugins` 又是 runtime 投影。扫描根、git 可提交物、本机启用目录是同一片森林。Wave 1 若继续扩 symlink，会把开发机布局写进平台目录，CI 无 `~/.zcode` 即断。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 禁止把第三方树 copy 进 git | D1 |
| 旧 `scan_plugins` 对 `plugins/` `iterdir`，yaml-only 目录会报 plugin.json 缺失 | D1b |
| 绝对路径入库违反 R1 | D15；`project_rule.md` R1 |
| `POWER_MARKET.ENABLED=false` 时必须保住现测试回退 | D16；`test_b1c` / `test_mcp_bridge` |

## 决策

三层不可混：

| 层 | 真相源 | 谁写 |
|---|---|---|
| Source | 外部目录或 git working tree | updater / git / Kimi 桌面；平台只读 |
| Catalog | DB 治理 + 仓库内 `capability-library/pointers/plugins/<name>/SOURCE.yaml` | sync 写索引；超管写 listing/status |
| Runtime | `.grok/plugins` 等宿主投影 | 显式 enable-host；**Wave 1 不交付该按钮**（FR-26）；生产默认关 |

读正文只走 `resolve_origin_path(source, origin_ref)`。`skills.file_path` 存合成指针，**不是**解析输入。禁止 `Path(https://...).resolve()`。git 源的根是 `CACHE_DIR/<source.name>`。

现有 catalog symlink **不收回、不扩展**；D16 回退继续扫 `LIBRARY_ROOT/plugins`。新接入走源注册表。`WRITE_POINTERS` 默认 false，PR9 再开。

## 备选与否决理由

### 备选 A：继续扩 per-plugin symlink 森林

**否决理由**：相对链在他人机器与 CI 断裂；绝对链无法提交；每宿主再链一次把 runtime 写进 catalog。已发生 6+ 条链，再扩会把本机 home 布局固化进仓库。

### 备选 B：只把路径存 DB，不写指针文件

**否决理由**：出站适配器与 git 审阅看不到「这个插件来自哪」。CI 无 home 时无法从仓库重建索引意图。指针是可提交的非内容痕迹。

### 备选 C：把指针写进 `capability-library/plugins/<name>/SOURCE.yaml`

**否决理由**：旧扫描器 `iterdir` 会把无 `plugin.json` 的目录记为解析失败，污染 D16 回退与存量测试。

### 备选 D：切源前收回除 sdlc-workflow 外的 catalog symlink

**否决理由**：与 D16「空 SOURCES 时保持今日遍历」冲突，且易变成清仓 PR（rabbit hole）。本波承认现有链为回退库存。

## 证据

仓库内 `capability-library/plugins/` 已是 symlink 森林；`.grok/plugins` 同时存在。全库 `POWER_MARKET` 0 命中。设计 D1b 把 POINTER_ROOT 与扫描根隔离，避免 yaml-only 目录被当成坏插件。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 双轨：回退扫描根 vs 源注册表 | `ENABLED` 默认 false；测试 overlay 前缀 |
| git clone 进 CACHE_DIR 无 updater 门禁 | 生产只指已审查树或 git 源；不在平台复制门禁 |
| 操作者本机 Kimi 长路径 | 只允许 local overlay，不进 `config/default` |

选最终一致（源树 vs DB 索引）：可接受延迟 = 一次 sync 周期。期间商店仍显示上次索引。sync 失败记录在该源，不清空已上架商店（FR-25.2）。不一致被发现时：对该源重跑 sync；不靠对账表。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 适配器只读源树；upsert 后可选写指针（`WRITE_POINTERS` 默认 false） |
| `/dba` | `origin_ref` / `source_id` 语义见 `contract.md` §7 |
| `/sre` | CACHE_DIR 不进 git；磁盘配额观察 |

## 后续复审条件

CI 必须索引第三方且不能依赖 D16 回退时，打开 `WRITE_POINTERS` 并停止向 `plugins/` 加链。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 采纳（替换 stale 稿） |
