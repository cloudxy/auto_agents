"""POWER_MARKET.ENABLED runtime gate (FR-U10 / FR-U11). Subscribe and public
list/detail read this on each request; scan-root D16 is a separate use."""
from backend.config_consts import POWER_MARKET_ENABLED
from config import settings
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.power_market")

MSG_MARKET_CLOSED = "能力市场未开放"
MSG_EMPTY_SHELF = "暂无已上架能力"
MARKET_CLOSED_CODE = "MARKET_CLOSED"


def is_power_market_enabled() -> bool:
    logger.info("power_market.flag.read")
    return bool(settings.get("POWER_MARKET.ENABLED", POWER_MARKET_ENABLED))


def set_power_market_enabled(enabled: bool) -> bool:
    logger.info(f"power_market.flag.write | enabled={enabled}")
    flag = bool(enabled)
    settings.set("POWER_MARKET.ENABLED", flag)
    return flag


def require_power_market_open() -> None:
    logger.info("power_market.flag.require_open")
    if not is_power_market_enabled():
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
