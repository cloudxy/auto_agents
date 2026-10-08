# 服务模块代码模板

## Contents

- Repository / Service / Router
- 路由注册
- 测试

ORM+Schema 用 `new-model`（本文件不重复）。先读再改编：`backend/app/api/v1/members.py`、`backend/repositories/user_repository.py`、`backend/tests/test_auth_service.py`。Router 不 import ORM。

## Repository（`backend/repositories/{module}_repository.py`）

```python
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.{module} import {Module}
from platform_core.repository import BaseRepository


class {Module}Repository(BaseRepository[{Module}]):
    def __init__(self, session: AsyncSession):
        super().__init__(model={Module}, session=session)
```

## Service（`backend/services/{module}_service.py`）

Service 是**唯一**允许同时 import ORM 与 Schema 的层。ORM 实体不出 API。`get_logger("api")`（对齐 `LOGGERS`）。

```python
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.{module}_repository import {Module}Repository
from platform_core.logger import get_logger
from platform_core.schemas.{module} import {Module}Create, {Module}Out

logger = get_logger("api")


class {Module}Service:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = {Module}Repository(session)

    async def get_by_id(self, id: int) -> {Module}Out | None:
        logger.info(f"查询{模块中文名}, id={id}")
        obj = await self.repo.get_by_id(id)
        return {Module}Out.model_validate(obj) if obj else None

    async def create(self, data: {Module}Create) -> {Module}Out:
        logger.info(f"创建{模块中文名}")
        obj = await self.repo.create(**data.model_dump())
        return {Module}Out.model_validate(obj)
```

租户表：方法签名加 `tenant_id: int`，查询带该过滤，对齐 `backend/services/member_service.py`。

## Router（`backend/app/api/v1/{module}.py`）

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.responses import created, ok
from backend.services.{module}_service import {Module}Service
from platform_core.db import get_async_db
from platform_core.logger import get_logger
from platform_core.schemas.{module} import {Module}Create

logger = get_logger("api")
router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> {Module}Service:
    return {Module}Service(session)


@router.get("/{id}")
async def get_{module}(id: int, service: {Module}Service = Depends(_service)):
    return ok(data=await service.get_by_id(id))


@router.post("")
async def create_{module}(
    body: {Module}Create,
    service: {Module}Service = Depends(_service),
):
    return created(data=await service.create(body))
```

租户表或要鉴权时，对齐 `members.py`：

```python
from backend.app.api.deps import CurrentUser, get_current_user

@router.get("/{id}")
async def get_{module}(
    id: int,
    user: CurrentUser = Depends(get_current_user),
    service: {Module}Service = Depends(_service),
):
    return ok(data=await service.get_by_id(id, tenant_id=user.tenant_id))
```

## 路由注册

`backend/app/api/v1/__init__.py`：在现有 `from . import ...` 行追加 `{module}`，并增加一行：

```python
router.include_router({module}.router, prefix="/{module}", tags=["{模块中文名}"])
```

只写 `include_router`、漏改 import，运行时 `NameError`。

## 测试（`backend/tests/test_{module}_service.py`）

改编 `backend/tests/test_auth_service.py`（mock session，不连真库）。至少：

```python
@pytest.mark.asyncio
async def test_create_returns_out():
    ...

@pytest.mark.asyncio
async def test_get_by_id_returns_out_or_none():
    ...
```
