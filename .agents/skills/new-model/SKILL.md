---
name: new-model
description: 配对生成 SQLAlchemy ORM + Pydantic Schema，强制"模型即契约"红线（ORM 与 Schema 不互相 import）
trigger: >-
  创建数据模型、新增数据库表、新建实体类、ORM + Schema 配对生成、
  /new-svc 流程中自动生成底层数据契约
---

# 创建数据模型

对齐 `project_rule.md` 的"模型即契约"信条：**ORM 是数据库契约，Pydantic 是接口契约，不能混用**。
本 skill 配对生成二者，并通过目录约束 + 转换层保证它们不互相 import。

## 触发场景

- "创建 User 模型"、"加一个订单表"、"新建实体类"
- `/new-svc` 流程里自动调用本 skill 生成底层数据契约
- 涉及新增字段、表、关系时

## 执行流程

### Step 1: 确认字段与约束

问用户（信息不足时），先做后问的前提是必要信息只有用户知道：

1. 模块名（小写+下划线，如 `user`、`order_item`）
2. 字段清单：字段名 + 类型 + 约束（必填 / 唯一 / 默认值 / 长度）
3. 时间戳（`created_at` / `updated_at`）是否需要
4. 软删除（`deleted_at` / `is_deleted`）是否需要
5. Pydantic 用途：
   - 只做请求入参？
   - 需要响应出参？
   - 需要 Create / Update 分离（Update 字段可选）？

### Step 2: 生成 ORM 模型

路径：`platform_core/models/{module}.py`。模板及红线自检命令见 [references/code-templates.md](references/code-templates.md)「ORM 模型模板」章节。

记得把新模型注册到 `platform_core/models/__init__.py` 的 `__all__`。

### Step 3: 生成 Pydantic Schema

路径：`platform_core/schemas/{module}.py`。模板见 [references/code-templates.md](references/code-templates.md)「Pydantic Schema 模板」章节。

### Step 4: 生成转换函数（契约桥梁）

路径：`backend/services/{module}_converter.py`（或在 service 内部内联）。模板及关键约束见 [references/code-templates.md](references/code-templates.md)「转换函数模板」章节。

### Step 5: 自动跑 check-arch 红线扫描

调用 `/check-arch` 的 R7 / R8 两条：

```bash
# R7: API 层不得 import ORM 模型
grep -rnE "from.*\.models import" backend/app/api/

# R8: ORM 模型不得 import Pydantic schema
grep -rnE "from.*\.schemas import" platform_core/models/
```

两条都无输出 = 模型即契约红线通过。

### Step 6: 生成迁移（可选）

如使用 Alembic：

```bash
uv run alembic -c backend/alembic.ini revision --autogenerate -m "add {module} table"
```

生成后**必须人工审核**迁移脚本（autogenerate 会误判删除列为"drop"）。

### Step 7: 交付自检

按下方「验证步骤」章节执行全部验证，禁止跳过。

## 预期产出物

完成后**必须**存在以下文件，缺少任何一个 = 未完成：

```
✅ 文件清单
platform_core/models/{module}.py              # ORM 模型（已注册到 __init__.py __all__）
platform_core/schemas/{module}.py             # Pydantic Schema（Base / Create / Update / Out）
backend/services/{module}_converter.py        # 契约桥梁转换函数（可选，如内联在 service 中则免）
```

如使用 Alembic，额外产出：

```
backend/alembic/versions/xxxx_add_{module}_table.py  # 迁移脚本（必须人工审核）
```

## 验证步骤

生成代码后，**必须**依次执行以下验证（调用 `/verify`）：

```bash
# 1. 架构红线 R7/R8（API 不 import ORM，ORM 不 import Schema）
grep -rnE "from.*\.models import" backend/app/api/
grep -rnE "from.*\.schemas import" platform_core/models/
# 期望：两条输出均为空

# 2. 模块可导入
uv run python -c "from platform_core.models.{module} import {Module}; from platform_core.schemas.{module} import {Module}Out; print('OK')"

# 3. 数据契约测试（如有）
uv run pytest -x -q platform_core/tests
```

全部通过后调用 `/check-arch` 做完整架构扫描。

## 常见反模式

见 [references/code-templates.md](references/code-templates.md)「常见反模式」章节。

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `project_rule.md` "模型即契约" | 本 skill 的根本依据 |
| `/check-arch` R7 / R8 | Step 5 红线扫描 |
| `/verify` | Step 7 交付自检 |
| `/new-svc` | 上游调用者——建服务时自动调本 skill |
| `/coding-style` | 命名规范（大驼峰类名、下划线字段名） |
