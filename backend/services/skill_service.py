"""技能域服务（方案 A）——A-P1a-1 起步：tier 派生

后续工单在本模块生长：扫描入库（09）/ 矫正写回（11）等。
tier 派生规则（总方案 §5.1）：人工综合分优先（缺省用 AI 建议分）映射
S≥8.5 / A≥7.0 / B≥5.0 / C<5.0；两者皆无 → None（展示"未评"）。
"""
from decimal import Decimal
from typing import Optional

from platform_core.logger import get_logger

logger = get_logger("service.skill")


# tier 派生（总方案 §5.1）：人工综合分优先（缺省用 AI 建议分）映射
# S≥8.5 / A≥7.0 / B≥5.0 / C<5.0；两者皆无 → None（展示"未评"）
def derive_tier(human_score: Optional[float], ai_score: Optional[float]) -> Optional[str]:
    logger.debug(f"tier 派生: human={human_score} ai={ai_score}")
    score = human_score if human_score is not None else ai_score
    if score is None:
        return None
    score = Decimal(str(score))
    if score >= Decimal("8.5"):
        return "S"
    if score >= Decimal("7.0"):
        return "A"
    if score >= Decimal("5.0"):
        return "B"
    return "C"
