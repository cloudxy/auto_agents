---
name: new-svc
description: 创建 FastAPI 服务模块
---

# 创建 FastAPI 服务模块

当用户需要创建新的业务模块时，使用此 Skill 生成完整代码。

## 触发场景

- "创建一个用户管理服务"
- "添加订单模块"
- "新建商品服务"

## 执行流程

### Step 1: 确认模块信息

1. 模块名称（英文，小写+下划线）
2. 主要功能描述
3. 是否需要数据库表/Redis 缓存

### Step 2: 生成代码

```
backend/
├── app/api/v1/{module}.py              # 路由层（注册到 v1/__init__.py）
├── services/{module}_service.py         # 业务层
├── repositories/{module}_repository.py  # 数据访问（继承 platform_core.repository.BaseRepository）

platform_core/
├── models/{module}.py                   # ORM 模型（共享数据契约）
└── schemas/{module}.py                  # Pydantic 模型（共享接口契约）
```

### Step 3: 代码模板

#### ORM 模型（`platform_core/models/{module}.py`）

```python
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func

from platform_core.models.base import Base


class {Module}(Base):
    """{模块中文名}"""
    __tablename__ = "{table_name}"

    id = Column(Integer, primary_key=True, comment="ID")
    # 每个字段必须有 comment
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
```

记得在 `platform_core/models/__init__.py` 的 `__all__` 中注册。

#### Pydantic 模型（`platform_core/schemas/{module}.py`）

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class {Module}Create(BaseModel):
    """创建请求"""
    pass


class {Module}Update(BaseModel):
    """更新请求，可选字段用 Optional"""
    pass


class {Module}Out(BaseModel):
    """响应对象"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
```

#### Service（`backend/services/{module}_service.py`）

```python
from platform_core import get_logger

logger = get_logger("api")


class {Module}Service:
    """{模块中文名}业务层"""

    async def get_by_id(self, id: int):
        logger.info(f"查询{模块中文名}, id={id}")
        # ...

    async def create(self, data: dict):
        logger.info(f"创建{模块中文名}")
        # ...
```

#### Router（`backend/app/api/v1/{module}.py`）

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/{id}")
async def get_{module}(id: int):
    """获取详情"""
    pass
```

### Step 4: 注册路由

在 `backend/app/api/v1/__init__.py` 中添加：

```python
from . import {module}
router.include_router({module}.router, prefix="/{module}", tags=["{模块中文名}"])
```

最终路径会是 `/api/v1/{module}/...`（前缀 `/api` 由 `backend/app/__init__.py` 注入，`/v1` 由 `backend/app/api/__init__.py` 注入）。
