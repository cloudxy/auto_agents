"""公开值班联系：空字符串让访客页隐藏 CTA（FR-M33）。"""
from config import settings
from platform_core.logger import get_logger

logger = get_logger("api")


def public_duty_contact() -> str:
    """读 OPS.DUTY_CONTACT；空/空白视为未配置，返回 ""。"""
    logger.info("读取公开值班联系")
    return str(settings.get("OPS.DUTY_CONTACT", "") or "").strip()


def public_contact() -> dict:
    """对外联系（决策 D25）：联系邮箱与响应时效；未配置时邮箱为空串（前端隐藏或降级）"""
    logger.info("读取公开联系方式")
    return {
        "duty_contact": public_duty_contact(),
        "contact_email": str(settings.get("OPS.CONTACT_EMAIL", "") or "").strip(),
        "contact_sla": str(settings.get("OPS.CONTACT_SLA", "") or "").strip(),
    }
