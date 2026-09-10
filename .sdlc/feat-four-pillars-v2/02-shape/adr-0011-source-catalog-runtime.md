# ADR-0011：Source / Catalog / Runtime 三层不可混

> 状态：**accepted**
> 日期：2026-09-08｜决策者：/architect｜相关：FR-38 / FR-41 / FR-37；D5 / D16

## 背景

今日扫描对 `capability-library/plugins` `iterdir`，无源注册表、无 `POWER_MARKET` 配置。实盘仍是 6 条相对 symlink + `.grok/plugins` 5 条 runtime 链。若把「同步」做成「扫描成功即 listed」或把指针写进 `plugins/`，会自动上架第三方并污染库存。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 同步不把第三方标 listed | FR-38.1；D7 |
| 市场总开关关或源列表空 → 今日本机扫描 | FR-38.5；D16 |
| 纠正对第三方不可用，不写源树 | FR-38.6；D5；spec §5 |
| 第一方夹具 `example-pdf-extractor` 商店闸打开后可见 | FR-41 |
| 指针不进 `plugins/` | 诊断 K-3LAYER |

## 决策

三层：

| 层 | 独占 | 谁写 |
|---|---|---|
| **Source** | 源登记、同步作业、上次错误 | 仅超管；`url` 类源创建失败并说明未支持 |
| **Catalog** | 平台目录行、listing、许可、治理 status | 超管点头才 listed；同步只 upsert 目录 |
| **Runtime（租户）** | 安装行、启用/信任 | 经办订阅；平台不代写宿主磁盘 |

指针落 `capability-library/pointers/`（或等价非 `plugins/` 目录），**不**进 `plugins/`。不扩展 per-plugin symlink 森林。`ENABLED=false` 或 SOURCES 空：扫描行为与 **今日本机插件目录扫描**一致，不登记冒充已切源的源名。

回填：仅第一方（平台自有、无父插件、无第三方源名）且已发布/推荐 → listed；宿主名单保持 **未声明**。禁止在 schema 迁移里 attach `zcode_local`。原第一方被源同步挂上源名后按第三方，保持 unlisted 直到超管点头。

`src_sync` 复用 `skill_jobs.job_type`（短码装得下），不建通用 job 框架。

目录身份（bundled slug、**不改** `uq_asset_type_name_alive`、撞名失败）见 [ADR-0012](adr-0012-catalog-identity.md)。本 ADR 不重开身份键。T-29 Then 锚 0012。

## 备选与否决理由

### 备选 A：切源前清仓收回现有 6 链

**否决理由**：D16 承认现链为库存。清仓会让治理台空窗，且无回滚。

### 备选 B：同步成功即 listed

**否决理由**：公开泄漏护栏 = 0；第三方必须二次确认。

### 备选 C：纠正写回第三方源树 / `export_meta` 写盘

**否决理由**：D5；本程序 N/A。只写库内快照。

### 备选 D：指针写入 `plugins/` 当「也是一种源」

**否决理由**：扫描 `iterdir` 会把指针当包，身份与 listed 回填失控。

## 证据

```
全库无 POWER_MARKET 配置键（诊断）
scan_plugins 对 plugins/ iterdir
capability-library/plugins = symlink；.grok/plugins 无 dev-team
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 两套扫描行为（回退 vs 源表） | GWT-38.5 钉回退；开关默认关 |
| 回填误伤第三方 | 第一方规则可观察 + 夹具短名 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 源表 + 同步不 listed；回退扫描 |
| `/dba` | 源实体语义；job_type 短码 |
| `/sre` | CACHE_DIR / ENABLED 配置外置 |
| `/ops` | 开张值班人名不在本 ADR（Q-OPS-DUTY） |

## 后续复审条件

要支持 `url` 类源或第三方源树写回——另开 FR。不得借同步票做 enable-host。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写 |
| 2026-09-08 | accepted（补） | SH-04：身份合同指针到 ADR-0012；不并入本 ADR 正文 |
