"""货架排序子句（feat-agents-market AD-6；自 service.py 抽出以守 AD-11 行数预算）。

三档语义（contract §4「排序细节」/ spec GWT-04.1–04.4）：

- ``smart``（默认，UI「综合」）：``featured DESC, updated_at DESC``
- ``latest``（UI「最新」）：``updated_at DESC``
- ``hot``（UI「最热」）：alive 订阅计数派生表 LEFT JOIN，
  ``COALESCE(cnt, 0) DESC, updated_at DESC``——MySQL 无 ``NULLS LAST``
  语法（db-spec §9:306 明示不可照抄），左联归零与「无计数不显示数字」同义。

全库 alive 订阅计数为 0 → ``hot`` 实际按 ``smart`` 出序并回
``sort_applied="smart"``（GWT-04.4）。非法/缺省 sort 值按 ``smart`` 处理：
契约 §4 只对非法 ``type`` 约定 422，排序档不设新错误面。

本模块函数一律 ``_`` 前缀（同 projection.py）：纯子句装配不是服务入口，
不进 R10 日志面；可观测性由 ``list_public`` 入口日志的 ``sort=`` 承担。
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilityInstall

logger = get_logger("service.power_market")

SORT_SMART = "smart"
SORT_LATEST = "latest"
SORT_HOT = "hot"
PUBLIC_SORTS = (SORT_SMART, SORT_LATEST, SORT_HOT)


def _parse_sort(value: Optional[str]) -> str:
    """请求档归一化：非三档一律回落 smart（不新增 422 面）。"""
    text = (value or "").strip().lower()
    return text if text in PUBLIC_SORTS else SORT_SMART


def _tiebreak() -> tuple:
    """三档共用次序键：updated_at 倒序；id 兜底保证分页稳定。"""
    return (CapabilityAsset.updated_at.desc(), CapabilityAsset.id.desc())


def _install_counts():
    """alive 订阅计数派生表（asset_id, cnt）。"""
    return (
        select(
            CapabilityInstall.asset_id.label("asset_id"),
            func.count().label("cnt"),
        )
        .where(CapabilityInstall.deleted_at.is_(None))
        .group_by(CapabilityInstall.asset_id)
        .subquery()
    )


async def install_count_for(session: AsyncSession, asset_id: int) -> int:
    """QA-11：单资产 alive 订阅计数——OQ-D3 裁定"预览态显示订阅计数"，但
    实现一直没有对应字段，抽屉只能渲染永远是 undefined 的 install_count。
    复用 hot 排序同一份 CapabilityInstall 计数口径（deleted_at IS NULL），
    不新开一套统计逻辑。
    """
    logger.debug(f"power_market.install_count_for | asset={asset_id}")
    row = (await session.execute(
        select(func.count())
        .select_from(CapabilityInstall)
        .where(
            CapabilityInstall.asset_id == asset_id,
            CapabilityInstall.deleted_at.is_(None),
        )
    )).scalar_one()
    return int(row or 0)


async def _resolve_sort(session: AsyncSession, requested: Optional[str]) -> str:
    """请求档 → 实际档：hot 且全库 alive 订阅计数为 0 → 降级 smart（GWT-04.4）。"""
    wanted = _parse_sort(requested)
    if wanted != SORT_HOT:
        return wanted
    alive = (await session.execute(
        select(func.count()).select_from(CapabilityInstall)
        .where(CapabilityInstall.deleted_at.is_(None))
    )).scalar_one()
    return SORT_HOT if int(alive or 0) > 0 else SORT_SMART


def _apply_sort(stmt, applied: str):
    """给行查询挂排序（hot 先左联计数派生表）。总数查询不得走本函数。"""
    if applied == SORT_LATEST:
        return stmt.order_by(*_tiebreak())
    if applied == SORT_HOT:
        counts = _install_counts()
        return stmt.join(
            counts, counts.c.asset_id == CapabilityAsset.id, isouter=True,
        ).order_by(func.coalesce(counts.c.cnt, 0).desc(), *_tiebreak())
    return stmt.order_by(CapabilityAsset.featured.desc(), *_tiebreak())
