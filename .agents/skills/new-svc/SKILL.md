---
name: new-svc
description: >-
  Scaffolds a FastAPI Router, Service, and Repository, then registers the v1
  route. Use when 新增业务模块, CRUD, 新 API 路由, or adding a backend module.
---

# 创建 FastAPI 服务模块

先读 `backend/app/api/v1/members.py` 再改编。Router/Service/Repository：[references/code-templates.md](references/code-templates.md)。ORM+Schema 用 `new-model`。

## Route

| 观察到 | 先做 |
|--------|------|
| 新表 / 列 / 索引 / 唯一键 | `db-design`（从 S0 起），做完再回来 |
| 只要 ORM+Schema，不要 API | `new-model` |
| 抓站 / 爬虫 | `new-spider` |

缺模块名 / 是否租户表 / 是否鉴权：先问，再动手。

## Quick start

Copy and check off:

```
new-svc:
- [ ] new-model：ORM + Schema + models/schemas 的 __init__.py 导出
- [ ] Repository 继承 BaseRepository
- [ ] Service：公开方法入口 logger. + model_validate；get_logger("api")
- [ ] Router：ok/created + Depends(get_async_db)
- [ ] 租户表或要鉴权：Depends(get_current_user)，tenant_id 从 CurrentUser 传入 Service
- [ ] v1/__init__.py：from . import 追加模块，并 include_router(prefix="/{module}")
- [ ] backend/tests/test_{module}_service.py（改编 test_auth_service.py；get/create 各一条）
- [ ] uv run pytest -x -q backend/tests
- [ ] bash tools/check/arch.sh
- [ ] uv run python run.py start backend && curl -sS localhost:9111/api/v1/health
```

```
platform_core/models/{module}.py
platform_core/schemas/{module}.py
backend/repositories/{module}_repository.py
backend/services/{module}_service.py
backend/app/api/v1/{module}.py
backend/tests/test_{module}_service.py
backend/app/api/v1/__init__.py
```

路径 `/api/v1/{module}/...`。任一步命令非 0：修完再跑同一条。

## 完成时回复

按这个顺序贴：

1. 上面 7 个路径（`__init__.py` 写出 prefix）
2. pytest 与 arch.sh 的 stdout 末段（退出码 0）
3. health curl 的 HTTP 与 body

## Examples

**Input:** 「加一个公告模块 announcement，租户表，要鉴权」

**Then:** 三项已齐，不再问。`new-model` 出 `Announcement` + `TenantMixin`；Router `Depends(get_current_user)`；`include_router(..., prefix="/announcement")`；测试文件在；三条命令退出码 0。
