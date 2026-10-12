"""渠道组令牌的用量观察面（GWT-60.2/60.3/60.5，db-spec §12，审计 F3-9）。

令牌详情触发的单令牌观察、按页显式刷新、日粒度事实回写。以 mixin 挂在
RelayService 上，方法名不变（_observe_gateway_usage 仍是测试打桩点）；
依赖宿主提供 session 与 _token_out。
"""
from collections.abc import Sequence
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.quota_service import GATEWAY_UNREACHABLE_USER
from backend.services.relay_enforcement import (
    reconcile_tenant, reconcile_tokens, record_daily_usage,
)
from backend.services.relay_sku_gate import load_sku_status, raise_missing, require_active_sku
from backend.services.relay_usage import (
    apply_usage, emit_usage_event, observe_gateway_usage, usage_snapshot,
)
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.models.relay import RelayToken
from platform_core.schemas.relay import RelayTokenOut

logger = get_logger("service.relay")

# (令牌, 单调累计用量, 网关最近使用时刻)
_Observed = tuple[RelayToken, int, Optional[datetime]]


def _split_observation(obs) -> tuple[int, Optional[datetime], Optional[dict]]:
    """观察结果兼容 (used, last_used) 与 (used, last_used, daily) 两种形态"""
    used, last_used = obs[0], obs[1]
    daily = obs[2] if len(obs) > 2 else None
    return int(used or 0), last_used, daily


class RelayTokenUsageMixin:
    """RelayService 的令牌用量观察方法（宿主须提供 session 与 _token_out）"""

    session: AsyncSession

    async def get_token(self, tenant_id: int, token_id: int) -> tuple[RelayTokenOut, bool]:
        """令牌详情（GWT-60.2/60.3 回写触发点之一，db-spec §12）。

        先对网关做一次用量观察（key info + spend 日志），回写本地缓存列；
        网关不可达 → 详情不失败，返回 (本地缓存视图, degraded=True)，
        由 Router 以 60.5 句族标注——数字保持缓存值，不显示「已用完」。
        已吊销 / 040 骨架（gateway_key_id NULL）行不观察，直接读本地。
        """
        logger.info(f"查看令牌详情 | tenant={tenant_id} token={token_id}")
        row = await self._owned_token(tenant_id, token_id)
        if await load_sku_status(self.session, tenant_id) != "active":
            raise_missing()
        degraded = False
        if row.gateway_key_id and row.revoked_at is None:
            try:
                used, last_used, daily = _split_observation(await self._observe_gateway_usage(row))
                used = await self._record_usage(row, used, daily)
                transitioned = apply_usage(row, used, last_used)
                snap = usage_snapshot(row) if transitioned else None
                await reconcile_tokens(self.session, [row], strict=False)
                await self.session.commit()
                await self.session.refresh(row)
                if snap is not None:
                    await emit_usage_event(self.session, snap)
            except httpx.HTTPError as exc:
                logger.warning(
                    f"网关用量观察失败（详情降级本地缓存） | tenant={tenant_id} "
                    f"token={token_id} err={type(exc).__name__}"
                )
                await self.session.rollback()
                # rollback 后对象过期：重新 SELECT 取本地缓存视图（P-BE-01 同口径）
                row = await self._owned_token(tenant_id, token_id)
                degraded = True
        return self._token_out(row), degraded

    async def refresh_tokens_usage(self, tenant_id: int) -> list[RelayTokenOut]:
        """显式刷新本企业令牌用量（按页批量触发点，QA-08：列表渲染不走此面）。

        对全部「已登记网关且未吊销」的行观察并回写；网关不可达 = 整批失败
        可见（502 LLM_GATEWAY_UNREACHABLE，60.5 句族，非套餐句），不落半批。
        """
        logger.info(f"刷新令牌用量 | tenant={tenant_id}")
        await require_active_sku(self.session, tenant_id)
        rows = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.tenant_id == tenant_id,
                RelayToken.revoked_at.is_(None),
                RelayToken.gateway_key_id.isnot(None),
            ).order_by(RelayToken.id.asc())
        )).scalars().all()
        observed = await self._observe_all(tenant_id, rows)
        if observed:
            await self._commit_observed(tenant_id, observed)
        return [self._token_out(r) for r in
                (await self.session.execute(
                    select(RelayToken).where(RelayToken.tenant_id == tenant_id)
                    .order_by(RelayToken.id.desc())
                )).scalars().all()]

    async def _observe_all(self, tenant_id: int, rows: Sequence[RelayToken]) -> list[_Observed]:
        """先观察后写入：任一行网关失败 → 回滚、整批零写入（无半批状态）"""
        observed: list[_Observed] = []
        try:
            for row in rows:
                used, last_used, daily = _split_observation(await self._observe_gateway_usage(row))
                used = await self._record_usage(row, used, daily)
                observed.append((row, used, last_used))
        except httpx.HTTPError as exc:
            logger.warning(
                f"网关用量观察失败（刷新失败可见） | tenant={tenant_id} "
                f"err={type(exc).__name__}"
            )
            await self.session.rollback()
            # GWT-60.5：同一 Then「平台 LLM 网关不可达」句族——不是套餐句、无 QUOTA
            raise BusinessException(
                message=GATEWAY_UNREACHABLE_USER,
                code="LLM_GATEWAY_UNREACHABLE",
                status_code=502,
            ) from exc
        return observed

    async def _commit_observed(self, tenant_id: int, observed: list[_Observed]) -> None:
        """回写观察值 → 对齐网关封禁 → 提交；跨阈值的令牌发用量事件后刷新"""
        transitioned: list[tuple[RelayToken, dict[str, int]]] = []
        for row, used, last_used in observed:
            if apply_usage(row, used, last_used):
                transitioned.append((row, usage_snapshot(row)))
        await reconcile_tenant(self.session, tenant_id, strict=False)
        await self.session.commit()
        for _row, snap in transitioned:
            await emit_usage_event(self.session, snap)
        for row, _snap in transitioned:
            await self.session.refresh(row)

    async def _observe_gateway_usage(self, row: RelayToken):
        return await observe_gateway_usage(row)

    async def _record_usage(self, row: RelayToken, used: int, daily: Optional[dict]) -> int:
        """写日粒度事实并返回单调累计值（审计 F3-9）；观察形态不带按日明细时整笔记今天"""
        if daily is None:
            recorded = int(row.used_tokens or 0)
            if used > recorded:
                from backend.services.relay_enforcement import utc_now_naive
                from platform_core.models.relay import RelayUsageDaily

                today = utc_now_naive().date()
                existing_today = (await self.session.execute(
                    select(RelayUsageDaily.total_tokens).where(
                        RelayUsageDaily.token_id == row.id, RelayUsageDaily.stat_date == today)
                )).scalar_one_or_none() or 0
                daily = {today: int(existing_today) + (used - recorded)}
            else:
                daily = {}
        total = await record_daily_usage(self.session, row, daily)
        return max(int(used), total)

    async def _owned_token(self, tenant_id: int, token_id: int) -> RelayToken:
        row = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.id == token_id, RelayToken.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if row is None:
            raise_missing()
        return row
