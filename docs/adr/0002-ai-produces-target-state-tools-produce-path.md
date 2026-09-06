# ADR-0002：AI 产出目标态，确定性工具产出迁移路径与行为判决

- 状态：已接受（2026-09-02）
- 决策人：项目所有者（D 线数据库设计流水线定案）
- 关联：ADR-0001（验证原则同源——平台不信未经亲验的能力）；`docs/plan/db-design-pipeline.md`

## 背景

AI 直接生成数据库设计与迁移 SQL 的问题：迁移不可复现、易错；校验停留在"DDL 文本看起来对不对"（静态 lint / checklist），而 demo 与工业标准的分水岭是**行为**——迁移能否在真实库正向应用 + 回滚、声明的查询是否真走索引（EXPLAIN）、约束是否真挡得住脏数据。外部评估（所有者核验）证实"更强的 AI 工具堆叠"无法解决此问题。

## 决策

**分工重划：**

1. **AI（LLM）只产出目标态与理由**——数据契约 Spec（含访问模式 Top-N 查询 + 频率、容量预估、一致性边界、保留策略）、DBML 中间表示、SQLAlchemy ORM / Pydantic 配对、每条索引"服务哪条查询"的论证。
2. **确定性工具产出路径与判决**——Alembic autogenerate 生成迁移（**LLM 禁写迁移 SQL**）、自研 IR/迁移 lint（破坏性变更 → 强制 expand-contract；大表 ALTER 标注 gh-ost/pt-osc）、行为验证环（MYSQL_FIDELITY 通道：逐迁移 upgrade/downgrade + EXPLAIN access type 断言 + 约束注入）、CI 门禁。
3. **顺序铁律：先访问模式，后索引，最后 DDL。** 索引从查询模式推导，不由 LLM 脑补、不事后 lint 补救。
4. **SKILL.md 只引导流程，不承担执法**——执法一律脚本 + pre-commit/CI（与 check-arch R1-R13 同哲学）。

## 后果

- 新增 `.agents/skills/db-design/`（流程引导）+ `check-db-ir` / `check-db-migrations`（执法）+ 行为验证测试（复用 MYSQL_FIDELITY）；
- 迁移产出方式收敛为 autogenerate + 人工微调（微调过的迁移必须过行为验证环）；
- 引入 `pydbml` 依赖（IR 解析）；成熟开源（atlas/strong_migrations/sqlcheck 等）只抄规则清单，不作运行时依赖；
- 例外通道：紧急 hotfix 手写迁移时，行为验证环（downgrade + 约束注入）仍不可豁免。
