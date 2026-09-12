"""spiders 路由包共享依赖工厂（FastAPI Depends，不承载端点）

期 4 Facade 退役：原 SpiderService 门面按子域拆为三个独立 Service，
端点按职责注入对应子 Service（任务/结果/注册表）。
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_login
from backend.services.schedule_service import ScheduleService
from backend.services.spider_common import READONLY_ENQUEUE_MESSAGE
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_registry_service import SpiderRegistryService
from backend.services.spider_task_service import SpiderTaskService
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("api")


def _task_service(session: AsyncSession = Depends(get_async_db)) -> SpiderTaskService:
    return SpiderTaskService(session)


async def require_enqueue_operator(
    user: CurrentUser = Depends(require_login),
) -> CurrentUser:
    """入队提交守卫（T-12 / GWT-87.3）：与 require_operator 同判据（admin/operator），仅信封不同。

    只读直提交采集入队 → 同族中文拒绝句 + 稳定非内码 code（HTTP 400），
    可见处无 FORBIDDEN/QUOTA_EXCEEDED/裸 429；仅挂在两个入队端点
    （POST /spiders/run 与 POST /spiders/templates/{id}/run），模板 CRUD 等仍走 require_operator。
    """
    if user.role not in ("admin", "operator"):
        logger.warning(f"只读提交入队被拒绝 | user={user.username} role={user.role}")
        raise BusinessException(
            message=READONLY_ENQUEUE_MESSAGE, code="TASK_RUN_ROLE_NOT_ALLOWED",
        )
    return user


def _query_service(session: AsyncSession = Depends(get_async_db)) -> SpiderQueryService:
    return SpiderQueryService(session)


def _registry_service(session: AsyncSession = Depends(get_async_db)) -> SpiderRegistryService:
    return SpiderRegistryService(session)


def _schedule_service(session: AsyncSession = Depends(get_async_db)) -> ScheduleService:
    return ScheduleService(session)
