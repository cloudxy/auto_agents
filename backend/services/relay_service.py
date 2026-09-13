"""租户渠道组：分组 + 虚拟令牌。不改平台渠道、不打网关库。

T-18：读路径闸在 relay_sku_entitlements（缺行≡none），禁止 COUNT 组行。
SKU≠active 隐藏骨架组/令牌；签发 422。明文只在当次签发。跨租户 404 同形。
"""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_gateway import admin as gateway_admin
from backend.services.quota_service import GATEWAY_UNREACHABLE_USER
from backend.services.relay_sku_gate import (
    load_sku_status, raise_missing, require_active_sku, sku_page as build_sku_page,
)
from backend.services.relay_usage import (
    apply_usage, emit_usage_event, observe_gateway_usage, usage_snapshot,
)
from platform_core.exceptions import AuthorizationException, BusinessException
from platform_core.logger import get_logger
from platform_core.models.relay import RelayGroup, RelayToken
from platform_core.schemas.relay import (
    RelayGroupCreate, RelayGroupOut, RelayGroupUpdate, RelaySkuPageOut,
    RelayTokenCreate, RelayTokenOut,
)

logger = get_logger("service.relay")

# spec 冻结句（GWT-60.4 / 60.7）——单一真相，Router/前端复用不另造
MSG_TOKENS_EMPTY = "还没有令牌。签发后才能按下方用法调用平台网关。"
MSG_CANNOT_ISSUE = "当前账号不能签发，请联系企业管理员"
MSG_CANNOT_MODIFY_GROUP = "当前账号不能修改渠道组，请联系企业管理员"
# ADR-0019 决策 5：网关 HTTP 失败 = 签发/吊销失败可见（60.5 同族，非套餐句）
MSG_GATEWAY_ISSUE_FAILED = "平台网关暂时不可用，令牌签发失败，请稍后重试。"
MSG_GATEWAY_REVOKE_FAILED = "平台网关暂时不可用，令牌吊销失败，请稍后重试。"
# GWT-60.5 句族（spec §7.1：用量观察面网关不可达——同一 Then，非套餐句）。
# 句子单一真相在 quota_service（已兑 FR-74 同句），此处只别名不另造。
MSG_GATEWAY_UNREACHABLE = GATEWAY_UNREACHABLE_USER
# 渠道组写面 = 负责人 owner / 公司管理员 admin（contract §3：经办只看用法）
_ISSUER_ROLES = ("owner", "admin")


def is_issuer_role(tenant_role: Optional[str]) -> bool:
    """渠道组写权判定（Router 读模型 message / 页面控件显隐共用）"""
    logger.debug("渠道组写权判定")
    return tenant_role in _ISSUER_ROLES


def _require_issuer_role(tenant_role: Optional[str]) -> None:
    """GWT-60.7：经办/只读签发/吊销 → 可见找管理员句，不是裸 403"""
    if tenant_role not in _ISSUER_ROLES:
        raise BusinessException(message=MSG_CANNOT_ISSUE, code="RELAY_TOKEN_ROLE_NOT_ALLOWED")


def _require_group_writer_role(tenant_role: Optional[str]) -> None:
    """GWT-60.7：经办/只读建组/停用 → 可见找管理员句"""
    if tenant_role not in _ISSUER_ROLES:
        raise BusinessException(
            message=MSG_CANNOT_MODIFY_GROUP, code="RELAY_GROUP_ROLE_NOT_ALLOWED",
        )


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _models_of(row: RelayGroup) -> list[str]:
    raw = row.models_json
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _gateway_alias(tenant_id: int, group: RelayGroup) -> str:
    """网关侧稳定引用。v1.100.0 /key/delete 的 KeyRequest 只收 keys/key_aliases
    （无 key_ids，OpenAPI 实读核对）——明文不落库，故引用取 key_alias。"""
    return f"relay-t{int(tenant_id)}-g{int(group.id)}-{uuid.uuid4().hex[:8]}"


def _group_out(row: RelayGroup) -> RelayGroupOut:
    return RelayGroupOut(
        id=int(row.id),
        name=str(row.name),
        rpm_limit=int(row.rpm_limit or 0),
        tpm_limit=int(row.tpm_limit or 0),
        models=_models_of(row),
        status=str(row.status),
        tenant_id=row.tenant_id,
        created_at=row.created_at,
    )


def _token_status(row: RelayToken) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at is not None and row.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "active"


class RelayService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def sku_status(self, tenant_id: int) -> str:
        logger.info(f"渠道组 SKU 状态 | tenant={tenant_id}")
        return await load_sku_status(self.session, tenant_id)

    async def sku_page(self, tenant_id: int, tenant_role: Optional[str]) -> RelaySkuPageOut:
        logger.info(f"渠道组 SKU 页 | tenant={tenant_id} role={tenant_role}")
        return await build_sku_page(
            self.session, tenant_id, tenant_role,
            can_issue=is_issuer_role(tenant_role),
        )

    async def list_groups(self, tenant_id: int) -> list[RelayGroupOut]:
        logger.info(f"列出渠道组 | tenant={tenant_id}")
        if await load_sku_status(self.session, tenant_id) != "active":
            return []
        rows = (await self.session.execute(
            select(RelayGroup).where(RelayGroup.tenant_id == tenant_id).order_by(RelayGroup.id.asc())
        )).scalars().all()
        return [_group_out(r) for r in rows]

    async def create_group(
        self, tenant_id: int, actor_tenant_role: Optional[str], payload: RelayGroupCreate,
    ) -> RelayGroupOut:
        logger.info(f"创建渠道组 | tenant={tenant_id} role={actor_tenant_role} name={payload.name}")
        await require_active_sku(self.session, tenant_id)
        _require_group_writer_role(actor_tenant_role)
        existing = (await self.session.execute(
            select(RelayGroup).where(
                RelayGroup.tenant_id == tenant_id, RelayGroup.name == payload.name,
            )
        )).scalar_one_or_none()
        if existing is not None:
            raise BusinessException(message="组名已存在", code="RELAY_GROUP_EXISTS")
        row = RelayGroup(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            rpm_limit=max(0, int(payload.rpm_limit)),
            tpm_limit=max(0, int(payload.tpm_limit)),
            models_json=list(payload.models),
            status="enabled",
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _group_out(row)

    async def update_group(
        self, tenant_id: int, actor_tenant_role: Optional[str], group_id: int,
        payload: RelayGroupUpdate,
    ) -> RelayGroupOut:
        logger.info(f"更新渠道组 | tenant={tenant_id} role={actor_tenant_role} group={group_id}")
        row = await self._owned_group(tenant_id, group_id)
        await require_active_sku(self.session, tenant_id)
        _require_group_writer_role(actor_tenant_role)
        if payload.name is not None:
            row.name = payload.name.strip()
        if payload.rpm_limit is not None:
            row.rpm_limit = max(0, int(payload.rpm_limit))
        if payload.tpm_limit is not None:
            row.tpm_limit = max(0, int(payload.tpm_limit))
        if payload.models is not None:
            row.models_json = list(payload.models)
        if payload.status is not None:
            if payload.status not in ("enabled", "disabled"):
                raise BusinessException(message="状态只能是 enabled/disabled", code="RELAY_BAD_STATUS")
            row.status = payload.status
        await self.session.commit()
        await self.session.refresh(row)
        return _group_out(row)

    async def list_tokens(self, tenant_id: int) -> list[RelayTokenOut]:
        logger.info(f"列出令牌 | tenant={tenant_id}")
        if await load_sku_status(self.session, tenant_id) != "active":
            return []
        rows = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.tenant_id == tenant_id, RelayToken.revoked_at.is_(None),
            ).order_by(RelayToken.id.desc())
        )).scalars().all()
        return [self._token_out(r) for r in rows if _token_status(r) == "active"]

    async def issue_token(
        self, tenant_id: int, actor_tenant_role: Optional[str], payload: RelayTokenCreate,
    ) -> RelayTokenOut:
        logger.info(
            f"签发令牌 | tenant={tenant_id} role={actor_tenant_role} group={payload.group_id}"
        )
        await require_active_sku(self.session, tenant_id)
        _require_issuer_role(actor_tenant_role)
        group = await self._owned_group(tenant_id, payload.group_id)
        if group.status != "enabled":
            raise BusinessException(message="渠道组已停用", code="RELAY_GROUP_DISABLED")
        # ADR-0019 决策 1：先网关登记虚拟 Key，再本地落 hash——失败即签发失败
        raw, gateway_key_id = await self._register_gateway_key(tenant_id, group)
        row = RelayToken(
            tenant_id=tenant_id,
            group_id=group.id,
            name=payload.name.strip(),
            key_prefix=raw[:10],
            key_hash=_hash_key(raw),
            quota_tokens=int(payload.quota_tokens),
            gateway_key_id=gateway_key_id,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            # 本地落库失败 → 网关侧孤儿 Key 按引用尽力作废（明文不可再现）
            await self._discard_gateway_key(gateway_key_id)
            raise
        await self.session.refresh(row)
        out = self._token_out(row)
        return out.model_copy(update={"plaintext_key": raw})

    async def revoke_token(
        self, tenant_id: int, actor_tenant_role: Optional[str], token_id: int,
    ) -> RelayTokenOut:
        logger.info(f"吊销令牌 | tenant={tenant_id} role={actor_tenant_role} token={token_id}")
        row = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.id == token_id, RelayToken.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if row is None:
            raise_missing()
        await require_active_sku(self.session, tenant_id)
        _require_issuer_role(actor_tenant_role)
        if row.revoked_at is None:
            # ADR-0019 决策 4：吊销 = 网关作废在前 + 本地 revoked；网关失败不本地假吊销
            if row.gateway_key_id:
                try:
                    await gateway_admin.delete_key({"key_aliases": [row.gateway_key_id]})
                except httpx.HTTPError as exc:
                    logger.warning(
                        f"网关作废失败 | tenant={tenant_id} token={token_id} "
                        f"ref={row.gateway_key_id} err={type(exc).__name__}"
                    )
                    raise BusinessException(
                        message=MSG_GATEWAY_REVOKE_FAILED,
                        code="RELAY_GATEWAY_UNAVAILABLE",
                        status_code=502,
                    ) from exc
            row.revoked_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(row)
        return self._token_out(row)

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
                used, last_used = await self._observe_gateway_usage(row)
                transitioned = apply_usage(row, used, last_used)
                snap = usage_snapshot(row) if transitioned else None
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
        # 先观察后写入：任一行网关失败 → 整批零写入（无半批状态）
        observed: list[tuple[RelayToken, int, Optional[datetime]]] = []
        try:
            for row in rows:
                used, last_used = await self._observe_gateway_usage(row)
                observed.append((row, used, last_used))
        except httpx.HTTPError as exc:
            logger.warning(
                f"网关用量观察失败（刷新失败可见） | tenant={tenant_id} "
                f"err={type(exc).__name__}"
            )
            await self.session.rollback()
            # GWT-60.5：同一 Then「平台 LLM 网关不可达」句族——不是套餐句、无 QUOTA
            raise BusinessException(
                message=MSG_GATEWAY_UNREACHABLE,
                code="LLM_GATEWAY_UNREACHABLE",
                status_code=502,
            ) from exc
        transitioned: list[tuple[RelayToken, dict[str, int]]] = []
        for row, used, last_used in observed:
            if apply_usage(row, used, last_used):
                transitioned.append((row, usage_snapshot(row)))
        if observed:
            await self.session.commit()
            for _row, snap in transitioned:
                await emit_usage_event(self.session, snap)
            for row, _snap in transitioned:
                await self.session.refresh(row)
        return [self._token_out(r) for r in
                (await self.session.execute(
                    select(RelayToken).where(RelayToken.tenant_id == tenant_id)
                    .order_by(RelayToken.id.desc())
                )).scalars().all()]

    async def usage_by_plaintext(self, tenant_id: int, plaintext: str) -> RelayTokenOut:
        """用本企业令牌读用量。他企/吊销/SKU≠active/过期 → 404 同形，无明文。"""
        logger.info(f"令牌凭证读用量 | tenant={tenant_id}")
        digest = _hash_key(plaintext or "")
        row = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.key_hash == digest, RelayToken.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if row is None:
            raise_missing()
        if await load_sku_status(self.session, tenant_id) != "active":
            raise_missing()
        if _token_status(row) != "active":
            raise_missing()
        return self._token_out(row)

    async def _observe_gateway_usage(self, row: RelayToken) -> tuple[int, Optional[datetime]]:
        return await observe_gateway_usage(row)

    async def _owned_token(self, tenant_id: int, token_id: int) -> RelayToken:
        row = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.id == token_id, RelayToken.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if row is None:
            raise_missing()
        return row

    async def _register_gateway_key(
        self, tenant_id: int, group: RelayGroup,
    ) -> tuple[str, str]:
        """网关登记虚拟 Key；返回 (明文一次, 网关引用)。任何失败=签发失败可见。"""
        alias = _gateway_alias(tenant_id, group)
        body: dict = {
            "key_alias": alias,
            "metadata": {"tenant_id": int(tenant_id), "group_id": int(group.id)},
        }
        models = _models_of(group)
        if models:
            body["models"] = models
        if int(group.rpm_limit or 0) > 0:
            body["rpm_limit"] = int(group.rpm_limit)
        if int(group.tpm_limit or 0) > 0:
            body["tpm_limit"] = int(group.tpm_limit)
        logger.info(f"网关登记虚拟 Key | tenant={tenant_id} group={group.id} alias={alias}")
        try:
            data = await gateway_admin.generate_key(body)
        except httpx.HTTPError as exc:
            logger.warning(
                f"网关登记失败 | tenant={tenant_id} group={group.id} err={type(exc).__name__}"
            )
            raise BusinessException(
                message=MSG_GATEWAY_ISSUE_FAILED,
                code="RELAY_GATEWAY_UNAVAILABLE",
                status_code=502,
            ) from exc
        raw = str((data or {}).get("key") or "")
        if not raw:
            logger.warning(f"网关登记响应无明文 key | tenant={tenant_id} group={group.id}")
            raise BusinessException(
                message=MSG_GATEWAY_ISSUE_FAILED,
                code="RELAY_GATEWAY_UNAVAILABLE",
                status_code=502,
            )
        return raw, alias

    async def _discard_gateway_key(self, gateway_key_id: str) -> None:
        """本地落库失败时尽力作废网关侧 Key；失败只记日志（可经 /key/list 对账）"""
        try:
            await gateway_admin.delete_key({"key_aliases": [gateway_key_id]})
        except httpx.HTTPError:
            logger.warning(f"网关孤儿 Key 作废失败 | ref={gateway_key_id}")

    async def _owned_group(self, tenant_id: int, group_id: int) -> RelayGroup:
        row = await self.session.get(RelayGroup, group_id)
        if row is None or int(row.tenant_id or 0) != int(tenant_id):
            raise_missing()
        return row

    @staticmethod
    def _token_out(row: RelayToken) -> RelayTokenOut:
        return RelayTokenOut(
            id=int(row.id),
            group_id=int(row.group_id),
            name=str(row.name),
            key_prefix=str(row.key_prefix),
            quota_tokens=int(row.quota_tokens),
            used_tokens=int(row.used_tokens or 0),
            status=_token_status(row),
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
            plaintext_key=None,
        )


def require_tenant_id(tenant_id: int | None) -> int:
    logger.debug("校验企业空间")
    if tenant_id is None:
        raise AuthorizationException(message="需要企业空间")
    return int(tenant_id)
