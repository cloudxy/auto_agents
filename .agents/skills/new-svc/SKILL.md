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

完整模板见 [references/code-templates.md](references/code-templates.md)，包含：

| 组件 | 文件路径 | 说明 |
|------|---------|------|
| ORM 模型 | `platform_core/models/{module}.py` | 数据库契约（Base 继承） |
| Pydantic 模型 | `platform_core/schemas/{module}.py` | 接口契约（Create/Update/Out） |
| Service | `backend/services/{module}_service.py` | 业务层（logger + 异步） |
| Router | `backend/app/api/v1/{module}.py` | 路由层（APIRouter） |

### Step 4: 注册路由

在 `backend/app/api/v1/__init__.py` 中添加：

```python
from . import {module}
router.include_router({module}.router, prefix="/{module}", tags=["{模块中文名}"])
```

最终路径会是 `/api/v1/{module}/...`（前缀 `/api` 由 `backend/app/__init__.py` 注入，`/v1` 由 `backend/app/api/__init__.py` 注入）。

## 预期产出物

完成后**必须**存在以下文件，缺少任何一个 = 未完成：

```
✅ 文件清单
platform_core/models/{module}.py              # ORM 模型（已注册到 __init__.py __all__）
platform_core/schemas/{module}.py             # Pydantic Schema（Create / Update / Out）
backend/services/{module}_service.py          # Service 业务层
backend/repositories/{module}_repository.py   # Repository 数据访问层
backend/app/api/v1/{module}.py                # Router 路由层
backend/app/api/v1/__init__.py                # 已 include_router 注册
```

## 验证步骤

生成代码后，**必须**依次执行以下验证（调用 `/verify`）：

```bash
# 1. 后端测试
uv run pytest -x -q backend/tests

# 2. 架构红线 R7/R8（API 不 import ORM，ORM 不 import Schema）
grep -rnE "from.*\.models import" backend/app/api/
grep -rnE "from.*\.schemas import" platform_core/models/
# 期望：两条输出均为空

# 3. 模块可导入
uv run python -c "from platform_core.models.{module} import {Module}; from platform_core.schemas.{module} import {Module}Out; print('OK')"

# 4. 服务启动 + 健康检查
uv run python run_backend.py --no-reload &
sleep 3 && curl -sS localhost:9111/api/v1/health | jq
```

全部通过后调用 `/check-arch` 做完整架构扫描。
