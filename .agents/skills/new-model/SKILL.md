---
name: new-model
description: >-
  Pairs a SQLAlchemy ORM model with a Pydantic schema; convert only in Service.
  Use when 实体, 数据契约, ORM/Schema 配对, or when new-svc needs the model layer.
---

# 创建数据模型

先读 `platform_core/models/user.py`。骨架：[references/code-templates.md](references/code-templates.md)。

## Route

| 观察到 | 先做 |
|--------|------|
| 新表 / 列 / 索引 / 唯一键（还没有 db-spec） | `db-design` S0，再回来做本 skill |
| 还要 Router+Service+API | 做完本 skill 后走 `new-svc` |
| 只要请求/响应 Schema、无表 | 跳过迁移两步，仍导出 Schema |

## Quick start

Copy and check off:

```
new-model:
- [ ] 字段：名/类型/约束/comment；是否 TenantMixin / SoftDeleteMixin
- [ ] platform_core/models/{module}.py 并导出 models/__init__.py
- [ ] platform_core/schemas/{module}.py 并导出 schemas/__init__.py
- [ ] Create 有必填字段；Update 每个业务字段 Optional；Out 含 id + 时间戳
- [ ] Service 里 {Module}Out.model_validate(obj)（无 Service 则留给 new-svc）
- [ ] 有表：autogenerate + 人工审核迁移
- [ ] backend/tests 增加导入或 round-trip 断言
- [ ] uv run pytest -x -q backend/tests
- [ ] bash tools/check/arch.sh
```

有表时：

```bash
cd backend && uv run alembic -c alembic.ini revision --autogenerate -m "add {module} table"
```

升级：`bash scripts/db/migrate.sh`。

```bash
uv run python -c "from platform_core.models.{module} import {Module}; from platform_core.schemas.{module} import {Module}Out; print('OK')"
```

任一步命令非 0：修完再跑同一条。

## 完成时回复

1. ORM / Schema / 两个 `__init__.py` 路径
2. 上面 `-c` 导入的 stdout
3. 有表则迁移文件路径；pytest + arch.sh 末段

## Examples

**Input:** 「给 announcement 加 ORM 和 Schema，租户表，字段 title/body」

**Then:** `Announcement(TenantMixin, SoftDeleteMixin, Base)`；`AnnouncementUpdate.title/body` 均为 `Optional`；两处 `__init__.py` 已导出；`-c` 打印 `OK`；arch.sh 退出码 0。
