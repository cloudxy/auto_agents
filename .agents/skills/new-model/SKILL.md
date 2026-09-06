---
name: new-model
description: 配对生成 SQLAlchemy ORM + Pydantic Schema，强制"模型即契约"红线（ORM 与 Schema 不互相 import）
trigger: >-
  创建数据模型、新增数据库表、新建实体类、ORM + Schema 配对生成、
  /new-svc 流程中自动生成底层数据契约
---

# 创建数据模型

对齐 `project_rule.md` 的"模型即契约"：ORM 是数据库契约，Pydantic 是接口契约，不能混用。
schema 变更的迁移执法在 `/db-design`，本 skill 只产配对代码。

## 触发场景

- "创建 User 模型"、"加一个订单表"、"新建实体类"
- `/new-svc` 流程里自动调用本 skill
- 涉及新增字段、表、关系时

## 执行流程

### Step 1: 确认字段与约束

1. 模块名（小写+下划线）
2. 字段清单：名 + 类型 + 约束
3. 租户表？→ 继承 `TenantMixin`。平台级含 `tenant_id` 但要豁免注入的表：只改 `backend/app/tenant_isolation.py`
4. 软删除？→ `SoftDeleteMixin`（`deleted_at`）。不要自造 `is_deleted` 列
5. 审计人？→ `AuditMixin`（`created_by` / `updated_by`）
6. Schema：Create / Update / Out 是否分离（Update 字段全部 Optional）

### Step 2: 生成 ORM

路径：`platform_core/models/{module}.py`。模板见 [references/code-templates.md](references/code-templates.md)。
注册到 `platform_core/models/__init__.py` 的 `__all__`。

### Step 3: 生成 Schema

路径：`platform_core/schemas/{module}.py`。

### Step 4: 转换

Service 内 `Schema.model_validate(orm)` 即可。需要独立函数时放 `backend/services/{module}_converter.py`（唯一允许同时 import ORM+Schema 的层）。

### Step 5: 红线扫描

```bash
bash scripts/check-arch.sh
```

不要用手搓 `from.*\.models import` 代替 R7（脚本正则覆盖子模块导入）。

### Step 6: 迁移

走 `/db-design` S3：`MYSQL_FIDELITY=1 uv run alembic revision --autogenerate`。禁止手写迁移 SQL。

### Step 7: 交付自检

见下方验证步骤。

## 预期产出物

```
platform_core/models/{module}.py
platform_core/schemas/{module}.py
```

可选：`backend/services/{module}_converter.py`。迁移文件由 `/db-design` 产出。

## 验证步骤

```bash
uv run python -c "from platform_core.models.{module} import {Module}; from platform_core.schemas.{module} import {Module}Out; print('OK')"
bash scripts/check-arch.sh
uv run pytest -x -q backend/tests
```

没有 `platform_core/tests/`。

## 常见反模式

见 [references/code-templates.md](references/code-templates.md)。

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `project_rule.md` "模型即契约" | 本 skill 的根本依据 |
| `/db-design` | 迁移 / 索引 / DBML |
| `/check-arch` | R7 / R8 / R13 |
| `/new-svc` | 上游调用者 |
| `/coding-style` | 命名 |
