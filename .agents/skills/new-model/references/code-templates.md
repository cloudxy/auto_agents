# 数据模型代码模板

## Contents

- ORM
- Schema
- 转换（写在 Service）
- 反模式

先读再改编：`platform_core/models/user.py`、`platform_core/models/mixins.py`、`platform_core/schemas/llm_provider.py`（Update 的 Optional）。

## ORM（`platform_core/models/{module}.py`）

```python
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import SoftDeleteMixin, TenantMixin


class {Module}(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "{module}"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    # <业务字段，必须有 comment>
    created_at = Column(DateTime, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间"
    )
```

无租户 / 无软删时去掉对应 Mixin。Mixin 定义在 `platform_core/models/mixins.py`。

注册到 `platform_core/models/__init__.py` 的 `__all__`。本文件禁止 import pydantic / schemas。

## Schema（`platform_core/schemas/{module}.py`）

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class {Module}Base(BaseModel):
    title: str


class {Module}Create({Module}Base):
    pass


class {Module}Update(BaseModel):
    """PATCH：只提交的字段生效"""
    title: Optional[str] = None


class {Module}Out({Module}Base):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
```

注册到 `platform_core/schemas/__init__.py`。本文件禁止 import sqlalchemy / models。

## 转换（写在 Service，不是独立 converter）

`backend/services/` 是唯一允许同时 import ORM 与 Schema 的目录。

```python
from platform_core.models.{module} import {Module}
from platform_core.schemas.{module} import {Module}Out


def to_out(obj: {Module}) -> {Module}Out:
    return {Module}Out.model_validate(obj)
```

爬虫禁止 import `platform_core.models` 配 Session 写入。

## 反模式

- 一个文件同时定义 ORM 和 Pydantic
- Router `return db_obj`（绕过 Schema）
- Update 复用 Create（Update 每个业务字段都是 Optional）
