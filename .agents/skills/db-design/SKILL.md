---
name: db-design
description: >-
  Produces db-spec.md, DBML, ORM, and Alembic revisions for new tables. Use
  when 新表, 加列, 索引, 唯一键, 写 DBML, or running Alembic.
---

# 数据库设计流水线（S0→S5）

执法：`tools/check/db_ir.sh`、`tools/check/db_migrations.sh`。索引只能从 S0 访问模式推导。S2 用 `new-model`。

## Route

| 观察到 | 先做 |
|--------|------|
| 只要 ORM+Schema、表已有且不改结构 | `new-model` |
| 还要 API | 本流水线过完 S2 后走 `new-svc` |

## Quick start

Copy and check off:

```
db-design:
- [ ] S0 .scratch/<feature>/db-spec.md（按下方模板，访问模式必须有行）
- [ ] S1 <domain>.dbml + bash tools/check/db_ir.sh
- [ ] S2 new-model（ORM 列与 DBML 一致）
- [ ] S3 autogenerate + 人工审核 + bash tools/check/db_migrations.sh
- [ ] S4 MYSQL_FIDELITY pytest backend/tests/test_db_behavior_loop.py
- [ ] S5 PR 附 ER diff + 迁移 diff
```

访问模式表为空：停在 S0，不要进 S1。任一步 check 非 0：修完再跑同一条，不要跳步。

### S0 模板（按这个写，缺块就还没做完）

`mkdir -p .scratch/<feature>` 后写入 `db-spec.md`：

```markdown
# db-spec: <feature>

## 实体
| 实体 | 表名 | 说明 |
|------|------|------|
|      |      |      |

## 业务唯一键（人工点 A）
| 表 | 唯一键列 | 业务含义 |
|----|----------|----------|
|    |          |          |

## 访问模式
| 查询（一句话） | 频率 | 走哪列 | 预估 QPS |
|----------------|------|--------|----------|
|                |      |        |          |

## 容量
- 行数量级（12 个月）：
- 单行大小：

## 事务边界
- 一次写入包含哪些表：
- 失败回滚口径：

## 归档
- 热数据窗口：
- 冷数据去向：
```

S3：

```bash
cd backend && MYSQL_FIDELITY=1 uv run alembic -c alembic.ini revision --autogenerate -m "<message>"
```

升级：`bash scripts/db/migrate.sh`。

S4：

```bash
MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_USER=root \
  MYSQL_FIDELITY_PASSWORD=<pwd> uv run pytest -q \
  backend/tests/test_db_behavior_loop.py -k "<your_migration>"
```

## 完成时回复

1. S0 路径（并确认访问模式表有至少一行真实查询）
2. S1：`db_ir.sh` 原文
3. S2：ORM 路径；S3：迁移文件 + `db_migrations.sh` 原文
4. 跑了 S4 则贴 pytest 末段

## Examples

**Input:** 「给 announcement 加表，title 唯一，按 tenant 列表」

**Then:** S0 访问模式至少有「按 tenant_id 列表」一行，索引从该行推导；在 S0 写完之前不跑 autogenerate。
