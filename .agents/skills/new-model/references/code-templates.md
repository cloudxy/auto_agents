# 数据模型代码模板

## ORM 模型模板

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

## Pydantic Schema 模板

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

## 转换函数模板（契约桥梁）

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

## 常见反模式（避免）

- ❌ 一个文件里同时定义 ORM 和 Pydantic（"反正都是 model"）
- ❌ API router 里直接 `return db_obj`（FastAPI 会把 ORM 序列化，绕过 Schema 契约）
- ❌ Service 层用 Pydantic 当 DTO 传到仓储层，仓储层再当 ORM 用
- ❌ Update schema 复用 Create schema（Update 字段应全部 Optional）
