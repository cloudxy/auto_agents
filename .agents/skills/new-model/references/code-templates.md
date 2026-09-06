# 数据模型代码模板

对照 `platform_core/models/api_key.py`。

## ORM（`platform_core/models/{module}.py`）

租户业务表：

```python
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class {Module}(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "{module}"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    # 每个业务字段必须有 comment
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")
```

- mixin 顺序与现有模型一致：`TenantMixin, SoftDeleteMixin, AuditMixin, Base`
- **禁止**在本文件 `import pydantic` / `from platform_core.schemas ...`（R8）
- 平台豁免表不要在 `platform_core/tenant_context.py` 写表名，只改 `backend/app/tenant_isolation.py`（R13）

注册到 `platform_core/models/__init__.py` 的 `__all__`。

## Pydantic Schema（`platform_core/schemas/{module}.py`）

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class {Module}Base(BaseModel):
    pass


class {Module}Create({Module}Base):
    pass


class {Module}Update(BaseModel):
    pass  # 字段全部 Optional


class {Module}Out({Module}Base):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
```

**禁止** `from sqlalchemy` / `from platform_core.models ...`。

## 转换（可选，`backend/services/` 内）

```python
from platform_core.schemas.{module} import {Module}Create, {Module}Out
from platform_core.models.{module} import {Module}


def orm_to_out(obj: {Module}) -> {Module}Out:
    return {Module}Out.model_validate(obj)


def create_to_orm(data: {Module}Create) -> {Module}:
    return {Module}(**data.model_dump())
```

## 反模式

- ❌ 一个文件同时定义 ORM 和 Pydantic
- ❌ API router `return db_obj`（绕过 Schema）
- ❌ Update 复用 Create
- ❌ 租户表漏 `TenantMixin`，然后在查询里手搓 `tenant_id=` 当"隔离"
- ❌ 手写 Alembic SQL（走 `/db-design` autogenerate）
