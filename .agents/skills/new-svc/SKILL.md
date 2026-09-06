---
name: new-svc
description: >-
  创建 FastAPI 服务模块。当用户需要新增业务模块、创建 CRUD 接口、
  或为后端添加新的 API 路由与数据模型时触发。
  适用于从零搭建完整服务层（Router + Service + Repository + ORM + Schema），
  以及需要配对生成数据模型与接口契约、并正确注册到 API 版本路由的场景。
trigger: >-
  新增业务模块、创建 CRUD 接口、添加 API 路由与数据模型、
  从零搭建完整服务层（Router + Service + Repository + ORM + Schema）、
  注册到 API 版本路由
---

# 创建 FastAPI 服务模块

对照实现：`backend/app/api/v1/api_keys.py` + `backend/services/api_key_service.py`。

## 触发场景

- "创建一个用户管理服务"
- "添加订单模块"
- "新建商品服务"

## 执行流程

### Step 1: 确认模块信息

1. 模块名称（英文，小写+下划线）
2. 租户表还是平台表（租户表 → `TenantMixin`；平台豁免表只改 `backend/app/tenant_isolation.py`）
3. 鉴权：租户接口 `require_operator` / `require_admin` / `get_current_user`；平台接口 `require_platform_admin`（不要混用）
4. 是否需要表 / Redis

底层数据契约交给 `/new-model`（含 mixin 与 converter）。schema 变更走 `/db-design`。

### Step 2: 生成代码

```
backend/app/api/v1/{module}.py
backend/services/{module}_service.py
backend/repositories/{module}_repository.py   # 可先用 BaseRepository，复杂查询再拆

platform_core/models/{module}.py
platform_core/schemas/{module}.py
```

模板：[references/code-templates.md](references/code-templates.md)。

硬约束：

- Router **禁止** import ORM（R7）。入参/出参只用 Schema；响应走 `ApiResponse` + `ok`/`created`
- Service public 方法第一行 `logger.info`（R10）
- HTTP 请求已由中间件进入 `tenant_scope` / `platform_scope`。后台任务 / 消费者必须显式 `with tenant_scope(tid):` 或 `platform_scope()`（R13）
- 异步 Redis 用 `get_async_redis()`，禁止 `redis_client().x`（R11）
- 不要新增 `from backend.services.spider_service import ...`（R12）

### Step 3: 注册路由

在 `backend/app/api/v1/__init__.py`：

```python
from . import {module}
router.include_router({module}.router, prefix="/{module}", tags=["{模块中文名}"])
```

最终路径 `/api/v1/{module}/...`。

然后更新 `backend/tests/openapi_routes_golden.txt`（`METHOD /api/v1/{module}` 每条一行，与 `test_openapi_routes_golden.py` 一致）。

## 预期产出物

```
platform_core/models/{module}.py
platform_core/schemas/{module}.py
backend/services/{module}_service.py
backend/repositories/{module}_repository.py   # 或 Service 内直接 BaseRepository
backend/app/api/v1/{module}.py
backend/app/api/v1/__init__.py                # include_router
backend/tests/openapi_routes_golden.txt       # 新路由已登记
```

表结构变更另走 `/db-design` 产出迁移。

## 验证步骤

```bash
uv run pytest -x -q backend/tests/test_openapi_routes_golden.py
uv run pytest -x -q backend/tests
bash scripts/check-arch.sh
```

不要跑不存在的 `platform_core/tests`。不要在 Router 里手搓 `from.*models import` 自检当唯一关卡——R7 正则以 `check-arch.sh` 为准。
