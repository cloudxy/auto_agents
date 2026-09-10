# ADR-0013：候选仍住结果表；tenant_id 禁止 NULL

> 状态：**accepted**
> 日期：2026-09-08｜决策者：/architect｜相关：FR-09…11；FR-08.4；PIT-4

## 背景

市场入站候选与租户成果同表。配额 COUNT 全表；调度/模板/AI 试采入队常不带企业。旧方案写「平台入站 `tenant_id` NULL」会在真库失败：迁移 017 起 `spider_tasks` / `spider_results` 除故事外已 NOT NULL。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 017 `tenant_id` NOT NULL（`llm_providers` 除外） | PIT-4；`017_saas_tenant_foundation.py` |
| 工人看不见企业；归属在入队时钉死 | FR-10 |
| 候选不占配额、不进我的结果/导出/出站 | FR-11 |
| Power Market 禁止 import `spider_*` | ADR-0010 B4 |

## 决策

候选 **继续**住 `spider_results.source=marketplace`（及对应任务）。**不**本波建候选表。`tenant_id` **必须**为触发企业或 **已有平台占位企业**（复用，不新开第二占位）。禁止用 NULL 表示「平台」。采集 consumer **独占写**结果；Power Market 只读候选端口（超管审核列表 SQL 分页）。配额 / 数据中心 / 导出 / 出站：`source <> marketplace` 且本企业。无主回流：不写入「我的结果」，任务侧可查失败/死信。

所有产任务路径（手工 / 定时 / 模板 / 向导试采）入队必须显式传 `tenant_id`；没有企业身份则 **不入队**。不要指望 Mixin 自动填（ORM 列仍默认可空，与 017 不一致）。

## 备选与否决理由

### 备选 A：平台候选 `tenant_id` NULL

**否决理由**：真库 INSERT 失败或挂 default；SQLite create_all 会骗人。spec X 未允许放宽 017。

### 备选 B：本波把候选迁出结果表

**否决理由**：spec §5「本波不做」。谓词隔离足够支撑 FR-11 与 WACT 排除候选。

### 备选 C：harvester / scrapy 直写主库带企业

**否决理由**：R3/R4/B2。工人不决定归属。

### 备选 D：`power_market` 直接查 `spider_results` 写审核

**否决理由**：B4。市场只消费只读端口；写仍归采集出口。

## 证据

```
PIT-4：017 TENANT_TABLES 含 spider_tasks/results，nullable=False
读码：SpiderService.enqueue 不转发 tenant_id；HTTP /run 才传
读码：list_candidates 全表进 Python 再切片
读码：check_result_storage 仍不过滤 source
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 候选与成果同表，查询必须带谓词 | 索引与默认过滤交 `/dba`；漏谓词 = 护栏事故 |
| 占位企业若泄漏到「我的结果」 | GWT-08.4；产品面过滤占位 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 入队全路径传租户；回流无主死信；配额谓词 |
| `/dba` | 不放宽 NOT NULL；访问模式含 source+tenant |
| `/qa` | 候选不进 TTFV/WACT；跨租户不可见 |
| `/data-collector` | 实现 N/A（运输层不改归属） |

## 后续复审条件

候选行量使结果表扫描成为 NFR 问题时再迁表——另开特征。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写；明确否决 NULL |
