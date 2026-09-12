"""出站拉数钥匙（FR-51 / ADR-0020）：签发 / 吊销 / 本企业列表 / 拉数查找。

新凭证域，与渠道组令牌分平面：
- 明文只在签发响应出现一次；库内只存 SHA-256 指纹 + 前缀（不以 sk- 开头）；
- 禁止 import 渠道组域与网关适配包（ADR-0020；grep 纪律见 contract §2.3）；
- 签发/吊销：经办（operator）+ 负责人（owner）/公司管理员（admin）；
  只读（viewer）拒绝并给「请联系企业管理员」句（GWT-51.5/51.9）；
- 拉数查找链第一环（T-05）：resolve_active_tenant——sk- 前缀不进本查找
  （与渠道组令牌查找集合不相交，GWT-51.6）；revoked/乱填 → None（0 行）。

互否文档化（GWT-51.10 / X-KEY）：ok- 钥匙从不注册进网关（本域零 import
网关适配包，结构上不可能登记——contract §2.3 grep 钉死）；渠道组页
Base URL（LiteLLM）对未知钥匙一律 401「网关不认」——不是套餐超限句，
也不写渠道组用量。网关侧拒绝句归 T-08/T-09 域；不变量测试见
test_outbound_pull_enforcement.py。
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.outbound_key_repository import OutboundKeyRepository
from platform_core.exceptions import AuthorizationException, BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.outbound_key import OutboundKey
from platform_core.schemas.outbound import (
    OutboundKeyCreate, OutboundKeyIssuedOut, OutboundKeyOut,
)

logger = get_logger("service.outbound")

# 明文前缀：只禁 sk-（db-spec §0.1，实现票自选非 sk- 前缀）；ok- = outbound key
_PLAINTEXT_PREFIX = "ok-"
_PREFIX_LEN = 10
_ISSUER_ROLES = ("owner", "admin", "operator")


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_tenant_id(tenant_id: Optional[int]) -> int:
    """出站钥匙是租户域：无企业上下文即拒（PIT-4：禁止 NULL=平台钥匙）"""
    logger.debug("校验企业空间")
    if tenant_id is None:
        raise AuthorizationException(message="出站拉数钥匙属于企业空间，当前账号没有企业上下文")
    return int(tenant_id)


def _require_issuer_role(actor_tenant_role: Optional[str]) -> None:
    """GWT-51.5/51.9：只读签发/吊销 → 不产生钥匙/不写 revoked_at，可见「请联系企业管理员」。"""
    if actor_tenant_role not in _ISSUER_ROLES:
        raise BusinessException(message="请联系企业管理员", code="OUTBOUND_KEY_ROLE_NOT_ALLOWED")


def _status_of(row: OutboundKey) -> str:
    return "active" if row.revoked_at is None else "revoked"


class OutboundKeyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = OutboundKeyRepository(session)

    async def list_keys(self, tenant_id: int) -> list[OutboundKeyOut]:
        logger.info(f"列出出站拉数钥匙 | tenant={tenant_id}")
        rows = await self.repo.list_by_tenant(tenant_id)
        return [self._key_out(r) for r in rows]

    async def resolve_active_tenant(self, api_key: str) -> Optional[int]:
        """拉数查找链第一环（ADR-0020 §2 / T-05）：明文钥匙 → 本企业 active 凭证行。

        - sk- 前缀不进本查找（与渠道组令牌查找集合不相交，GWT-51.6）；
        - revoked / 乱填 → None（0 行，GWT-51.3/51.7）；
        - SHA-256 指纹等值 + compare_digest 复核；明文与指纹都不入日志。
        未命中后由调用方走第二环 KEY_BINDINGS（FR-13 行为保持，不放宽）。
        """
        logger.info("出站拉数钥匙查找 | 链=出站钥匙表 形态=非sk-")
        if not api_key or api_key.startswith("sk-"):
            return None
        digest = _hash_key(api_key)
        row = await self.repo.get_active_by_hash(digest)
        if row is None or not hmac.compare_digest(str(row.key_hash), digest):
            return None
        return int(row.tenant_id)

    async def issue_key(
        self, tenant_id: int, actor_user_id: int, actor_tenant_role: Optional[str],
        payload: OutboundKeyCreate,
    ) -> OutboundKeyIssuedOut:
        logger.info(
            f"签发出站拉数钥匙 | tenant={tenant_id} actor={actor_user_id} role={actor_tenant_role}"
        )
        _require_issuer_role(actor_tenant_role)
        raw = _PLAINTEXT_PREFIX + secrets.token_urlsafe(32)
        row = OutboundKey(
            tenant_id=tenant_id,
            name=payload.name.strip() if payload.name else None,
            key_prefix=raw[:_PREFIX_LEN],
            key_hash=_hash_key(raw),
            issued_by_user_id=actor_user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        out = self._key_out(row)
        # GWT-92.3：签发成功上报事件（tenant_id + key_id，无明文/前缀；
        # 上报失败不挡主路径——emit_product_event 自吞异常，GWT-92.6）
        from backend.services.product_event_service import emit_product_event
        await emit_product_event(
            self.session, "outbound_key_issued",
            tenant_id=tenant_id, actor_user_id=actor_user_id,
            role=actor_tenant_role, props={"key_id": out.id},
        )
        # 明文只在这一次出现（GWT-51.1）；日志/事件侧禁止带 raw
        return OutboundKeyIssuedOut(**out.model_dump(), plaintext_key=raw)

    async def revoke_key(
        self, tenant_id: int, actor_tenant_role: Optional[str], key_id: int,
    ) -> OutboundKeyOut:
        logger.info(f"吊销出站拉数钥匙 | tenant={tenant_id} key={key_id}")
        _require_issuer_role(actor_tenant_role)
        row = await self.repo.get_owned(tenant_id, key_id)
        if row is None:
            # 他企业/不存在一律 404 同形（R13；不泄露存在性）
            raise NotFoundException("出站拉数钥匙")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(row)
        return self._key_out(row)

    @staticmethod
    def _key_out(row: OutboundKey) -> OutboundKeyOut:
        return OutboundKeyOut(
            id=int(row.id),
            name=row.name,
            key_prefix=str(row.key_prefix),
            status=_status_of(row),
            revoked_at=row.revoked_at,
            created_at=row.created_at,
        )
