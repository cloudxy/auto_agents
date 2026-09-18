"""治理策展写：精选开关（AD-6）与详情示例区维护（AD-7）。

两者都是**治理字段**：agents_hub 同步的 `_desired` 白名单不含 featured/examples
（db-spec §9），所以同步不会把管理员的策展结果重置回默认值。

- `set_featured`：`featured` smallint（0/1），综合序置顶区依据（GWT-04.1/04.5）。
- `set_examples`：`examples` JSON list[str]，上限 20 条 × 200 字（AD-7），
  超限 422；空列表 = 取消维护 → 详情投影空列表 → 前端隐藏区块（GWT-05.3）。

越权门面在 API 层（require_platform_admin_or_404 → 404 存在性隐藏，GWT-04.6）；
资产不存在同样 404（listing._load_asset 抛 NotFoundException）。
"""
from typing import List

from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.listing import _load_asset, _public_type
from backend.services.power_market.types import _to_public_asset_type
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset

logger = get_logger("service.power_market")

EXAMPLES_MAX_ITEMS = 20
EXAMPLES_MAX_CHARS = 200


class PatchFeaturedRequest(BaseModel):
    featured: bool


class PatchExamplesRequest(BaseModel):
    examples: List[str]

    @model_validator(mode="after")
    def bounded(self):
        items = [str(x).strip() for x in (self.examples or [])]
        if len(items) > EXAMPLES_MAX_ITEMS:
            raise ValueError(f"示例最多 {EXAMPLES_MAX_ITEMS} 条")
        for text in items:
            if len(text) > EXAMPLES_MAX_CHARS:
                raise ValueError(f"单条示例最多 {EXAMPLES_MAX_CHARS} 字")
        self.examples = [x for x in items if x]
        return self


def _snapshot(row: CapabilityAsset) -> dict:
    """行快照（contract §4 #5/#6 响应）。"""
    return {
        "id": row.id,
        "name": row.name,
        "asset_type": _to_public_asset_type(row.asset_type),
        "featured": int(row.featured or 0),
        "examples": list(row.examples or []),
        "listing_state": row.listing_state,
    }


async def set_featured(
    session: AsyncSession, asset_type: str, name: str, featured: bool,
) -> dict:
    """精选开关（FR-04 治理入口，GWT-04.5）。"""
    logger.info(
        f"power_market.set_featured | type={asset_type} name={name} featured={featured}"
    )
    row = await _load_asset(session, _public_type(asset_type), name)
    row.featured = 1 if featured else 0
    snapshot = _snapshot(row)
    await session.commit()
    return snapshot


async def set_examples(
    session: AsyncSession, asset_type: str, name: str, examples: List[str],
) -> dict:
    """示例区维护（附加 d，AD-7）。空列表 = 取消维护。"""
    logger.info(
        f"power_market.set_examples | type={asset_type} name={name} n={len(examples or [])}"
    )
    row = await _load_asset(session, _public_type(asset_type), name)
    row.examples = list(examples or [])
    snapshot = _snapshot(row)
    await session.commit()
    return snapshot
