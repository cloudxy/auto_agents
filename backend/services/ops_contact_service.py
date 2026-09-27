"""公开值班联系：空字符串让访客页隐藏 CTA（FR-M33）。"""
from config import settings
from platform_core.logger import get_logger

logger = get_logger("api")


def public_duty_contact() -> str:
    """读 OPS.DUTY_CONTACT；空/空白视为未配置，返回 ""。"""
    logger.info("读取公开值班联系")
    return str(settings.get("OPS.DUTY_CONTACT", "") or "").strip()
