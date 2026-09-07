# ADR-0013：Wave 0/1 市场候选仍住采集结果表；tenant_id 保持 NOT NULL

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：FR-11、GWT-15.1、`contract.md` §2.4 §7
> 本文件 **整份替换** stale ADR-0013。stale 稿写「入站结果行 `tenant_id` NULL」——与迁移 **017 NOT NULL** 冲突，**禁止当现行决策**。本文不是对 stale 句子打补丁。

## 背景

`skill_harvester` 经 Redis 落 `spider_results.source=marketplace`。`SkillService.list_candidates` / `approve_candidate` 直接读写该表，转正写 `extra.review`。`QuotaService.check_result_storage` 按租户 COUNT 全表，候选占用租户存储配额。这是共享表双方写（诊断 V4 / dba P0）。

产品 FR-11 要求：候选不计入结果存储、不出现在租户「我的结果」、租户不能导出候选库。它 **没有** 要求新实体。

迁移 `017_saas_tenant_foundation.py` 把 `spider_results` 列入 `TENANT_TABLES`，回填 `tenants.slug='default'` 后将 `tenant_id` 收紧为 **NOT NULL**（`llm_providers` 除外）。ORM Mixin 仍可空，造成 SQLite `create_all` 绿、MySQL 红。任何「平台行 NULL」方案在真库插入会失败。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 爬虫不写主库、不 import backend | R3/R4/B2；harvester 运输层正确 |
| 候选不占配额、不当采集成果 | FR-11 |
| `spider_results.tenant_id` NOT NULL | Alembic 017 |
| 本波不给 /dba 加「候选表」除非产品真需要 | appetite；第二次出现再抽象 |
| `power_market` 禁止 import `spider_*` | ADR-0010 B4 |
| WACT 必须能排除候选 | FR-15 GWT-15.1 `is_marketplace_candidate` |

## 决策

Wave 0/1 **不**新建 `capability_candidates`。

- 采集 consumer **独占写** `spider_results`。
- 市场候选审核继续走既有 `SkillService` 端口（放在技能/采集侧，不放 `power_market` 包）。
- 转正仍写 `extra.review`，**冻结 extra 协议**：不得再加新键当市场状态机。
- 配额 COUNT、租户任务结果列表、数据中心、导出：`source <> 'marketplace'`（或等价）。
- 超管候选列表：`platform_scope` 下按 source **SQL 分页**，禁止全表进 Python。
- **`tenant_id` 必须有值。** 入队路径写入触发者企业（FR-09：定时/模板/AI 试采属提交者租户）。平台超管 **无企业空间** 时触发的入站，使用 `/dba` 指定的 **平台占位租户** 行作为 FK 目标——产品面永不把该行的 marketplace 结果展示为「我的结果」（靠 source 过滤，不靠 NULL）。
- **禁止** 放宽 017、**禁止** 插入 NULL、**禁止** 把「无主候选」当成隔离策略。
- 事件 `task_completed.is_marketplace_candidate=true` 标记候选入站，供 WACT 排除；不得靠事后猜 `source`。

迁出自有表列为明确债（Q-CAND），不在本波做。

## 备选与否决理由

### 备选 A：本波新建候选表并投影

**否决理由**：产品验收不依赖新表；多一张表 + 投影延迟 + 前端候选 Tab 合同变更，会把 Wave 0 配额修复绑进 Wave 1 schema。FR-11 用过滤即可证伪。第二次「候选要独立生命周期」时再迁。

### 备选 B：继续 SkillService 读写且配额照算

**否决理由**：直接违反 FR-11；候选可把企业存储顶满（诊断 R-K / dba P0）。

### 备选 C：harvester 改直写市场表

**否决理由**：违反爬虫不写主库。运输必须继续 Redis → consumer。

### 备选 D：候选行 `tenant_id` NULL 表示平台入站（stale ADR-0013）

**否决理由**：017 起 `spider_results.tenant_id` NOT NULL。真库 INSERT NULL 失败。Mixin 可空只骗过 SQLite 测试。dba / architect 诊断均点名该路径不可行。

### 备选 E：本波 DDL 放宽 `spider_results.tenant_id` 为可空

**否决理由**：破坏性收缩（NOT NULL → NULL 虽能跑，但改变「一行必须有租户」不变量，且与 9 张表对齐债搅在一起）。FR-11 不要求这个。expand-contract 成本超出 Wave 0 下限。

## 证据

```
spike：017 是否允许 NULL
问题：spider_results.tenant_id 在 MySQL 是否可空
环境：backend/alembic/versions/017_saas_tenant_foundation.py TENANT_TABLES
结果：含 spider_results；除 llm_providers 外 alter nullable=False
结论：平台候选必须带一个真实 tenant_id
```

```
spike：配额是否计入 marketplace
问题：QuotaService.check_result_storage 是否过滤 source
环境：backend/services/quota_service.py:100-109 COUNT SpiderResult.tenant_id
结果：不过滤 source
结论：Wave 0 必须加排除条件，否则 FR-11.1 失败——与 tenant_id 是否占位无关
```

`SkillService.list_candidates`（`skill_service.py:437-441`）`select(SpiderResult).where(source=="marketplace")` 全表再切片。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 采集表继续被市场语义污染 | extra 协议冻结；B4 阻止新包 import |
| 候选若挂在某客户租户上，该租户任务列表若漏过滤会看见 | 列表/导出/配额同一谓词；qa 必测数据中心不见候选正文 |
| 占位租户若被当成客户登录 | /dba 选定后产品不提供该租户自助面；source 过滤仍挡「我的结果」 |
| 候选查询仍可能慢 | 访问模式交给 /dba：按 source + review 分页；禁止全表 Python 滤 |

选最终一致？否——同表同步过滤，强一致。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | COUNT/列表/导出加排除；候选 list 平台态分页；入队 NOT NULL tenant_id |
| `/dba` | 访问模式「平台态 source=marketplace 翻页」；指定占位租户语义（不写 DDL 在本文）；本波可不建新表 |
| `/qa` | 租户用量不含 50 条候选；数据中心看不到候选正文；GWT-15.1 候选标记 |
| `/data-collector` | **不改** harvester 出口 |

## 后续复审条件

候选审核需要与采集结果不同的保留策略、或 extra.review 不得不再加键时，新 ADR 迁表（expand-contract）。Q-CAND 关闭且产品要求独立生命周期时同样。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | stale accepted（NULL 方案） | 塑形中断稿；与 017 冲突，作废 |
| 2026-09-07 | proposed → accepted | v2：NOT NULL + source 过滤；替换 stale 文件 |
