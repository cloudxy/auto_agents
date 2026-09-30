"""能力市场总开关（FR-U10 / FR-U11；决策 D34 = A，连带 BUG-32）

真相源：system_configs.power_market.enabled（超管切换写库，重启不丢、多 worker 一致）；
没有这行时按 yaml POWER_MARKET.ENABLED（部署默认）。打开时必须已配置 OPS.DUTY_CONTACT，
与启动检查同一口径（原先运行时切换只写进程内 settings，绕过了这道检查）。
订阅与公开列表 / 详情每次请求都读；scan-root D16 另行使用。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import POWER_MARKET_ENABLED
from backend.services.config_service import ConfigService
from backend.services.ops_contact_service import public_duty_contact
from config import settings
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.power_market")

MSG_MARKET_CLOSED = "能力市场未开放"
MSG_EMPTY_SHELF = "暂无已上架能力"
MARKET_CLOSED_CODE = "MARKET_CLOSED"
MARKET_FLAG_KEY = "power_market.enabled"
DUTY_CONTACT_REQUIRED = "DUTY_CONTACT_REQUIRED"


async def is_power_market_enabled(session: AsyncSession) -> bool:
    logger.info("power_market.flag.read")
    raw = (await ConfigService(session).get_configs([MARKET_FLAG_KEY])).get(MARKET_FLAG_KEY)
    if raw is None:
        return bool(settings.get("POWER_MARKET.ENABLED", POWER_MARKET_ENABLED))
    return str(raw).strip().lower() == "true"


async def set_power_market_enabled(session: AsyncSession, enabled: bool) -> bool:
    logger.info(f"power_market.flag.write | enabled={enabled}")
    flag = bool(enabled)
    if flag and not public_duty_contact():
        raise BusinessException(
            message="打开能力市场前请先配置值班联系人（OPS.DUTY_CONTACT）。",
            code=DUTY_CONTACT_REQUIRED, status_code=409,
        )
    await ConfigService(session).upsert_configs(
        {MARKET_FLAG_KEY: "true" if flag else "false"}, description="能力市场总开关（决策 D34）",
    )
    return flag


async def require_power_market_open(session: AsyncSession) -> None:
    logger.info("power_market.flag.require_open")
    if not await is_power_market_enabled(session):
        raise BusinessException(
            message=MSG_MARKET_CLOSED,
            code=MARKET_CLOSED_CODE,
            status_code=409,
        )


def closed_list_payload(*, page: int, page_size: int) -> dict:
    logger.info("power_market.flag.closed_list")
    return {
        "total": 0,
        "page": page,
        "page_size": page_size,
        "has_more": False,
        "items": [],
        "empty": True,
        "market_closed": True,
        "message": MSG_MARKET_CLOSED,
    }


def closed_detail_payload() -> dict:
    logger.info("power_market.flag.closed_detail")
    return {
        "market_closed": True,
        "message": MSG_MARKET_CLOSED,
        "subscribable": False,
    }
