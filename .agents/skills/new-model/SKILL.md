---
name: new-model
description: 配对生成 SQLAlchemy ORM + Pydantic Schema，强制"模型即契约"红线（ORM 与 Schema 不互相 import）
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

路径：`platform_core/models/{module}.py`

```python
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from platform_core.models.base import Base


class {Module}(Base):
    __tablename__ = "{module}"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # <业务字段>
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

**红线自检**：生成前 grep 当前文件有无 Pydantic 引用：

```bash
grep -nE "from.*\.schemas import|from pydantic" platform_core/models/{module}.py
# 期望输出：空
```

记得把新模型注册到 `platform_core/models/__init__.py` 的 `__all__`。

### Step 3: 生成 Pydantic Schema

路径：`platform_core/schemas/{module}.py`

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class {Module}Base(BaseModel):
    # <公共字段>
    pass


class {Module}Create({Module}Base):
    # <创建必填字段>
    pass


class {Module}Update(BaseModel):
    # <更新可选字段>
    pass


class {Module}Out({Module}Base):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
```

**红线自检**：生成前 grep 有无 ORM 引用：

```bash
grep -nE "from.*\.models import|from sqlalchemy" platform_core/schemas/{module}.py
# 期望输出：空
```

### Step 4: 生成转换函数（契约桥梁）

路径：`backend/services/{module}_converter.py`（或在 service 内部内联）

```python
from platform_core.schemas.{module} import {Module}Create, {Module}Out
from platform_core.models.{module} import {Module}


def orm_to_out(obj: {Module}) -> {Module}Out:
    return {Module}Out.model_validate(obj)


def create_to_orm(data: {Module}Create) -> {Module}:
    return {Module}(**data.model_dump())
```

**关键约束**：`backend/services/` 是**唯一允许**同时 import ORM 和 Schema 的目录。它是两个契约之间的翻译官（爬虫绝不允许这样做——`scrapy/` 禁止 import platform_core.models 配合 Session 写入）。

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

调用 `/verify`：
- `uv run pytest -x -q platform_core/tests`（如果有测试）
- 加载测试：`uv run python -c "from platform_core.models.{module} import {Module}; from platform_core.schemas.{module} import {Module}Out"`

## 输出约定

完成后贴三段证据（对齐 `answer_rule.md`：用工具验证，不要用嘴验证）：

```
=== 新增文件 ===
platform_core/models/{module}.py
platform_core/schemas/{module}.py
backend/services/{module}_converter.py

=== 红线 R7/R8 ===
（两条 grep 输出为空，表示通过）

=== 加载测试 ===
python -c "from ... import ..."
（无报错 = 可导入）

=== 迁移（如有） ===
backend/alembic/versions/xxxx_add_{module}_table.py
```

## 常见反模式（避免）

- ❌ 一个文件里同时定义 ORM 和 Pydantic（"反正都是 model"）
- ❌ API router 里直接 `return db_obj`（FastAPI 会把 ORM 序列化，绕过 Schema 契约）
- ❌ Service 层用 Pydantic 当 DTO 传到仓储层，仓储层再当 ORM 用
- ❌ Update schema 复用 Create schema（Update 字段应全部 Optional）

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `project_rule.md` "模型即契约" | 本 skill 的根本依据 |
| `/check-arch` R7 / R8 | Step 5 红线扫描 |
| `/verify` | Step 7 交付自检 |
| `/new-svc` | 上游调用者——建服务时自动调本 skill |
| `/coding-style` | 命名规范（大驼峰类名、下划线字段名） |
