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
├── app/api/v1/{module}_router.py  # 路由层
├── services/{module}_service.py     # 业务层
├── models/{module}_model.py         # ORM 模型
├── schemas/{module}_schema.py       # Pydantic 模型
```

### Step 3: 代码模板

#### ORM 模型

```python
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from .base import Base

class {Module}Model(Base):
    """{模块中文名}"""
    __tablename__ = "{table_name}"
    
    id = Column(Integer, primary_key=True, comment="ID")
    # 每个字段必须有 comment
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
```

#### Pydantic 模型

```python
from pydantic import BaseModel
from datetime import datetime

class {Module}Create(BaseModel):
    """创建请求"""
    pass

class {Module}Update(BaseModel):
    """更新请求，可选字段用 Optional"""
    pass

class {Module}VO(BaseModel):
    """响应对象"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True
```

#### Service

```python
from backend.cors.log_init import get_logger

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

#### Router

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/{module}", tags=["{模块中文名}"])

@router.get("/{id}")
async def get_{module}(id: int):
    """获取详情"""
    pass
```

### Step 4: 注册路由

在 `app/api/v1/__init__.py` 中添加新路由。
