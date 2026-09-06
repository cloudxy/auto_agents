# 服务模块代码模板

ORM / Schema 的完整 mixin 模板见 `/new-model`。这里只放 Router + Service 的现行写法。

## Service（`backend/services/{module}_service.py`）

```python
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.logger import get_logger
from platform_core.models.{module} import {Module}
from platform_core.repository import BaseRepository
from platform_core.schemas.{module} import {Module}Out

logger = get_logger("service.{module}")


class {Module}Service:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = BaseRepository({Module}, session)

    async def list_for_tenant(self, tenant_id: int) -> list[{Module}Out]:
        logger.info(f"列出{模块中文名} | tenant={tenant_id}")
        rows = await self.repo.get_all()
        return [{Module}Out.model_validate(r) for r in rows]
```

`backend/services/` 是唯一允许同时 import ORM 和 Schema 的目录。转换可内联 `model_validate`，不必强行拆 `{module}_converter.py`。

后台 / 消费者路径：

```python
from platform_core.tenant_context import tenant_scope, platform_scope

with tenant_scope(tenant_id):
    ...
```

## Router（`backend/app/api/v1/{module}.py`）

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_operator
from backend.app.responses import ApiResponse, ok
from backend.services.{module}_service import {Module}Service
from platform_core.db import get_async_db
from platform_core.schemas.{module} import {Module}Out

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> {Module}Service:
    return {Module}Service(session)


@router.get("", response_model=ApiResponse[list[{Module}Out]])
async def list_{module}s(
    user: CurrentUser = Depends(require_operator),
    service: {Module}Service = Depends(_svc),
) -> ApiResponse[list[{Module}Out]]:
    return ok(await service.list_for_tenant(user.tenant_id))
```

- 禁止 `from platform_core.models...`（R7）
- 平台接口改 `require_platform_admin`，不要用租户 `require_admin` 冒充超管
- 写操作需要审计时调 `backend.app.api._helpers.record_audit`

## 路由注册

`backend/app/api/v1/__init__.py`：

```python
from . import {module}
router.include_router({module}.router, prefix="/{module}", tags=["{模块中文名}"])
```

随后把新 `METHOD /api/v1/{module}` 写入 `backend/tests/openapi_routes_golden.txt`。
