# 数据库设计流水线（S0→S5）

> 强制流程：任何涉及数据库 schema 变更的工作必须走此流水线。
> 三原则（ADR-0002）：AI 产出目标态与理由 / 先访问模式后索引 / 验收全机械可查。
> SKILL.md 只引导流程，不承担执法——执法在 `check-db-*` 脚本 + CI。

## 何时使用

- 新建表 / 加列 / 加索引 / 改唯一键 / 数据模型评审
- 触发词：数据库设计 / schema / 迁移 / alembic / 索引 / DBML

## 流程（顺序不可跳）

### S0 需求 → 数据契约 Spec
产出 `db-spec.md`（放 `.scratch/<feature>/` 或工单附件）：
- 实体清单 + 关系（ER 图意涵）
- **业务唯一键**（人工评审点 A：只有人知道）
- **访问模式**：Top-N 查询 + 频率 + 走哪列（这是索引的唯一合法输入）
- 容量预估：行宽 / 日增长 / 索引大小
- 一致性边界：事务范围
- 保留与归档策略

### S1 Spec → DBML IR
产出 `<domain>.dbml`（[DBML 标准](https://dbml.dbdiagram.io)）：
- Table/Enum/Ref 声明式描述目标态
- 过 `scripts/check-db-ir.sh` 静态 lint（命名/审计字段/类型/FK 环/孤儿）

### S2 IR → ORM + Schema 配对
用 `/new-model` skill（本仓范式）产出 ORM + Pydantic 配对。
ORM 模型必须与 DBML 一致（check-db-ir 会对比）。

### S3 Alembic autogenerate（AI 禁写迁移 SQL）
```bash
# 在 MYSQL_FIDELITY 环境下 autogenerate → 人工审查 → 微调
MYSQL_FIDELITY=1 uv run alembic revision --autogenerate -m "<message>"
```
- 微调过的迁移必须过 S4 行为验证环
- 过 `scripts/check-db-migrations.sh`（破坏性变更检测 → 强制 expand-contract 拆分）

### S4 行为验证环（demo 与工业的分水岭）
```bash
MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_USER=root \
  MYSQL_FIDELITY_PASSWORD=<pwd> uv run pytest -q \
  backend/tests/test_db_behavior_loop.py -k "<your_migration>"
```
- upgrade ↑ + downgrade ↓ 全跑通
- FK 感知种子数据 + S0 声明的每条查询 EXPLAIN 断言 access type ≠ ALL
- 约束注入：唯一键/FK/NOT NULL 真挡得住脏数据

### S5 CI 门禁 + 人工评审点 B
- `check-db-ir` / `check-db-migrations` 挂 pre-commit（*.dbml 或 alembic/versions 变更时触发）
- PR 附 ER diff + 迁移 diff——人工审阅后合并

## 禁止事项

- ❌ LLM 直接手写迁移 SQL（autogenerate 是唯一路径）
- ❌ 索引由 LLM 脑补（必须从 S0 访问模式推导）
- ❌ drop/rename/类型收窄不拆 expand-contract
- ❌ 大表（>10 万行）ALTER 不标注 gh-ost/pt-osc

## 参考规则源

- atlas（ariga/atlas）：lint 规则清单
- strong_migrations（ankane/strong_migrations）：破坏性变更检查项
- sqlcheck（jarulraj/sqlcheck）：SQL 反模式
