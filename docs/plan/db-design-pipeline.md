# 数据库设计流水线（D 线）方案 · 从"工具堆叠"到"带行为验收的闭环"

> 定位：修正"AI 设计数据库不可靠"的根因——不是找更强的 AI 工具，而是**分工重划 + 行为验收 + 机械执法**。
> 来源：项目所有者 2026-09-02 带入的外部评估（对某"豆包方案"逐仓库核验后半推翻），核验方法含 404 校准对照，选型表为所有者亲自验证结果。
> 关联：与 [`capability-hub-p6.md`](./capability-hub-p6.md)（第三批 P6 线）与 [`architecture-review-2026-09.md`](./architecture-review-2026-09.md)（候选 6/7 的配置与索引项）并行；工单 60-63 见 `.scratch/platform-v3/`。
> 状态：**待终审**（并入第三批，与 P6/修复线一起执行）。

---

## 1. 三条核心原则（对"工具堆叠清单"的直接修正）

1. **AI 产出目标态与理由，确定性工具产出路径与判决。** LLM 负责：数据契约 Spec、DBML 中间表示、ORM 模型、每条索引"服务哪条查询"的论证。工具负责：迁移生成（alembic autogenerate）、静态 lint、EXPLAIN 断言、CI 门禁。**LLM 禁写迁移 SQL**（ADR-0002）。
2. **先访问模式，后索引，最后 DDL。** 顺序不可跳——跳了就退化成"范式没错但业务不对、索引乱建或漏建"的 demo。
3. **验收标准全部机械可检查**——与 check-arch R1-R13 同一哲学。SKILL.md 只负责引导流程，不承担执法；执法在脚本 + CI。

## 2. 评估结论摘要（所有者核验，2026-09-02）

- 被评估方案引用的仓库**全部真实存在**（404 校准通过），但 9 个核心项目里 7 个是 0~19★ 未经验证的个人项目，却被标成"推荐首选生产方案"；其一（comparedb-ai）实际只支持 SQL Server（本栈 MySQL 不可用）；其一（pondhawk-mcp）已改名失效。
- 结构性缺陷四条：静态文本检查无行为验证 / 缺访问模式等必备输入 / Skill 无强制力未接执法 / 迁移环节分工错位（让 LLM 写迁移 SQL，无 expand-contract、无大表 ALTER 锁评估、无回滚验证）。
- **修正后选型**（全部成熟，可直接进流程）：

| 用途 | 选型 | 备注 |
|---|---|---|
| 团队 SQL 审计平台 | cookieY/Yearning（8.9k★） | 被评估方案中唯一保留项 |
| 声明式 schema / 迁移 lint / CI | ariga/atlas（**规则清单抄进自研 lint，不作运行时依赖**）；栈内 Alembic autogenerate | AI 禁写迁移 SQL 的执行面 |
| SQL 静态 lint | sqlfluff；jarulraj/sqlcheck（反模式）；kristiandupont/schemalint（结构 lint） | 规则来源 |
| 破坏性变更检查 | 语义照抄 ankane/strong_migrations 检查项清单 | drop/rename/类型收窄 → 强制 expand-contract；大表 ALTER 标注 gh-ost/pt-osc |
| ER 中间表示 | holistics/dbml（DBML 标准，经 pydbml 解析）+ drawdb-io/drawdb（可视化参考） | S1 的 IR |
| 行为验证 | docker MySQL + 既有 `MYSQL_FIDELITY` 通道（testcontainers 备选） | 本仓已建成，直接复用 |

> 0~19★ 项目不是不能用，而是**定位错了**：读它们的 SKILL.md 抄检查项进自研规则库，不进生产链路。

## 3. 流水线（S0→S5，落到本仓现有设施）

```
S0 需求 → 数据契约 Spec（.scratch/<feature>/db-spec.md 或 docs/plan 附属）
   实体/关系/业务唯一键 + Top-N 查询模式与频率 + 容量预估（行宽/增长/索引大小）
   + 一致性边界（事务范围）+ 保留与归档策略
   └─ 人工评审点 A：业务唯一键、量级、保留策略——只有人知道，AI 不拍板
S1 Spec → DBML IR（*.dbml）：现成标准，可 lint / 可 diff / 可渲染 ER 图
   └─ IR 静态 lint（scripts/check-db-ir，pydbml 解析，~30 条自研规则：
      命名/审计字段(created_at,updated_at)/类型/FK 环/孤儿关系）
S2 IR → SQLAlchemy ORM + Pydantic 配对（复用既有 /new-model 范式）
S3 Alembic autogenerate 生成迁移（AI 禁写迁移 SQL）
   └─ 迁移 lint（scripts/check-db-migrations）：破坏性变更检测 → 强制 expand-contract 拆分；
      大表 ALTER（spider_results 量级）标注 gh-ost/pt-osc 建议
S4 行为验证环（demo 与工业的分水岭；复用 MYSQL_FIDELITY 通道）
   docker MySQL → upgrade ↑ + downgrade ↓ 全跑通（既有 test_alembic_baseline 扩展为逐迁移）
   → FK 感知种子数据（1e4 行级 CI 档 / 1e5 全量档 env 切换）→ S0 声明的每条查询 EXPLAIN，
     断言 access type ≠ ALL → 约束注入（唯一键/FK/NOT NULL 真挡得住脏数据）
S5 CI 门禁 + 人工评审点 B（ER diff + 迁移 diff）
```

## 4. 与现有体系的衔接（不新造轮子）

| 既有设施 | D 线复用方式 |
|---|---|
| `/new-model` skill（ORM+Schema 配对范式） | S2 的生成面（db-design 编排它，不替代） |
| `MYSQL_FIDELITY` 保真通道 + test_alembic_baseline | S4 的执行面（扩展：逐迁移 apply/downgrade + EXPLAIN + 约束注入） |
| check-arch 门禁哲学 + pre-commit/CI | S5 执法面：`check-db-ir` + `check-db-migrations` 挂 pre-commit（仅当 `*.dbml` 或 `alembic/versions` 变更时触发，不拖慢日常提交） |
| E0.1 模型工厂 | S4 种子数据泛化（FK 感知） |
| 评审候选 6（settings 常量收口）/ 候选 7（复合索引） | D4 试点直接兑现候选 7 的 DB 项 |

## 5. 工单切片（D 线，60-63，编号续 platform-v3）

| 工单 | 内容 | Blocked by |
|---|---|---|
| 60 D1 | `.agents/skills/db-design/SKILL.md`：S0→S5 流程固化（Spec 模板 / 访问模式输入表 / 评审点 A/B / AI 职责边界），注册进 AGENTS.md Skill 路由表 | — |
| 61 D2 | IR + 迁移双 lint 脚本（pydbml ~30 规则 + strong_migrations 语义清单），挂 pre-commit/CI（条件触发） | — |
| 62 D3 | 行为验证环测试：逐迁移 upgrade/downgrade + EXPLAIN 断言 + 约束注入（复用 MYSQL_FIDELITY，工厂泛化 FK 感知种子） | — |
| 63 D4 | 试点：spider_results 复合索引重设计走全流水线（Spec/DBML/迁移/EXPLAIN 断言工件入库）——兑现评审候选 7 DB 项 | 62 |

**并行性**：D1-D3 无互相依赖（60/61/62 可并行）；D4 是流水线首个真实客户。C2（capability_assets 迁移 018）鼓励走 D 线但不阻塞（018 若先行，按旧路径交付后由 D4 同法补验证）。

## 6. 开放默认（可推翻）

- DBML 解析用 `pydbml`（纯 Python、成熟）；lint 脚本语言 bash+python 混合（与 check-arch 同构）；
- CI 种子 1e4 行（速度），1e5 全量档经 env 开关；
- Yearning 引入为**远期可选项**（团队 SQL 审计流程建立后接），本期不部署。

---

*生成：2026-09-02 · 所有者核验结论 + 三原则采纳 · 词汇入 `CONTEXT.md`，分工原则入 `docs/adr/0002`*
