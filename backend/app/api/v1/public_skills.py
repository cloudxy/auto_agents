"""官网公开能力市场 API——无鉴权读；订阅需登录。

闸：查询侧 FR-33 再分页；字段白名单；按 IP 限流。
GET 未上架/黑名单详情 = 商店不存在句 HTML。POST 订阅 = MARKET_NOT_FOUND JSON。
静态段（aliases）必须注册在动态 /{type}/{name} 之前（PIT-1）。
公开详情接受目录短名或 alias（T-33）。
"""
from typing import Optional

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, optional_current_user, require_login
from backend.app.responses import ok
from backend.services.market_events import (
    emit_detail_opened,
    emit_market_list_paged,
    emit_public_detail,
    emit_public_list,
    run_subscribe,
)
from backend.services.power_market import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    PUBLIC_ASSET_TYPES,
    STORE_NOT_FOUND_HTML,
    PowerMarketService,
)
from backend.services.power_market.types import SubscribeRequest
from platform_core.db import get_async_db
from platform_core.exceptions import RateLimitException
from platform_core.logger import get_logger
from platform_core.queues import SKILL_PUBLIC_RATE_PREFIX
from platform_core.redis_async import get_async_redis

logger = get_logger("api.public_skills")

# 双公开端同一五类枚举（禁止一边修一边留 bogus→skill）
assert PUBLIC_ASSET_TYPES == ("skill", "plugin", "command", "agent", "team")

router = APIRouter()


def _market(session: AsyncSession = Depends(get_async_db)) -> PowerMarketService:
    return PowerMarketService(session)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _enforce_rate_limit(request: Request) -> None:
    from config import settings

    limit = int(settings.get("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN", 60) or 60)
    if limit <= 0:
        return
    try:
        redis = await get_async_redis()
        key = f"{SKILL_PUBLIC_RATE_PREFIX}{_client_ip(request)}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > limit:
            raise RateLimitException(message=f"请求过于频繁（限 {limit} 次/分钟），请稍后再试")
    except RateLimitException:
        raise
    except Exception as exc:  # noqa: BLE001 Redis 故障 fail-open（公开只读面保可用性）
        logger.warning(f"公开 API 限流检查失败（放行）: {exc}")


def _store_not_found() -> HTMLResponse:
    return HTMLResponse(content=STORE_NOT_FOUND_HTML, status_code=404)


async def _emit_paged_event(session, page: int, data: dict, anonymous_id: Optional[str]) -> None:
    """FR-92.5：翻页动作（第 2 页起）上报 market_list_paged；失败不挡列表（服务层吞）。"""
    if page < 2:
        return
    aid = (anonymous_id or "").strip() or None
    await emit_market_list_paged(
        session, page=page, result_count=len(data["items"]), anonymous_id=aid,
    )


# ---------- 能力市场：静态段必须先于 /{type}/{name}（PIT-1） ----------


@router.get("/capabilities/aliases")
async def public_reserved_aliases(request: Request):
    """PIT-1 静态段：不得被 /{type}/{name} 吞掉。解析走动态详情。"""
    await _enforce_rate_limit(request)
    return _store_not_found()


@router.get("/capabilities")
async def public_list_capabilities(
    request: Request,
    type: Optional[str] = Query(None),
    category: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=100),
    host: Optional[str] = Query(None, max_length=16),
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    anonymous_id: Optional[str] = Query(None, max_length=64),
    sort: Optional[str] = Query(None, max_length=16),
    market: PowerMarketService = Depends(_market),
    user: CurrentUser | None = Depends(optional_current_user),
):
    """官网能力市场：FR-33 查询侧闸再分页（非法 type 失败；未选=全部）。

    AD-5c：平台管理员带 preview=true 时跳闸预览（租户/匿名 preview 被忽略）。
    AD-6：sort=smart|latest|hot（缺省/非法=smart）；hot 无计数降级回 sort_applied。
    """
    await _enforce_rate_limit(request)
    preview = bool(user and user.is_platform_admin and request.query_params.get("preview") == "true")
    data = await market.list_public(
        asset_type=type, category=category, q=q, host=host,
        page=page, page_size=page_size, preview=preview, sort=sort,
    )
    if not data.get("market_closed"):
        await emit_public_list(
            market.session, asset_type=type, host=host, category=category,
            q=q, total=data["total"],
        )
        await _emit_paged_event(market.session, page, data, anonymous_id)
    return ok(data=data)


_MEDIA_KIND = {"logo": "logo", "icon": "logo", "background": "background"}
_MEDIA_EXT = {".png", ".webp", ".svg", ".jpg", ".jpeg", ".gif"}
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _safe_media_file(stored: str | None) -> Path | None:
    rel = (stored or "").replace("\\", "/").lstrip("/")
    if not rel.startswith(".agents/") or ".." in rel.split("/"):
        return None
    path = _REPO_ROOT / rel
    if path.suffix.lower() not in _MEDIA_EXT or not path.is_file():
        return None
    return path


@router.get("/capabilities/{asset_type}/{name}/media/{kind}")
async def public_capability_media(
    asset_type: str,
    name: str,
    kind: str,
    request: Request,
    market: PowerMarketService = Depends(_market),
    user: CurrentUser | None = Depends(optional_current_user),
):
    """货架卡片图：只吐 .agents 下已入库的 icon/background。

    AD-5c：管理员 preview=true 豁免闸与 listed 分量；租户/匿名不变。
    """
    await _enforce_rate_limit(request)
    mapped = _MEDIA_KIND.get((kind or "").strip().lower())
    if mapped is None:
        return _store_not_found()
    preview = bool(
        user and user.is_platform_admin
        and request.query_params.get("preview") == "true"
    )
    stored = await market.get_media_path(asset_type, name, mapped, preview=preview)
    path = _safe_media_file(stored)
    if path is None:
        return _store_not_found()
    return FileResponse(path)


@router.post("/capabilities/{asset_type}/{name}/subscribe")
async def public_subscribe_capability(
    asset_type: str,
    name: str,
    request: Request,
    payload: SubscribeRequest | None = None,
    user: CurrentUser = Depends(require_login),
    market: PowerMarketService = Depends(_market),
):
    """订阅提交：未上架/黑名单/从不存在短名 → MARKET_NOT_FOUND JSON（非 HTML 404）。"""
    await _enforce_rate_limit(request)
    host = payload.host if payload else None
    data = await run_subscribe(
        market.session, market, asset_type=asset_type, name=name, host=host, user=user,
    )
    return ok(data=data)


@router.get("/capabilities/{asset_type}/{name}")
async def public_get_capability(
    asset_type: str,
    name: str,
    request: Request,
    market: PowerMarketService = Depends(_market),
    user: CurrentUser | None = Depends(optional_current_user),
):
    """公开详情：非 FR-33 可见 → 商店不存在句 HTML。

    AD-5c：管理员 preview=true 预览（豁免闸 + listed 分量，payload 带标记）；
    GWT-08.4：非预览成功读触发 detail_opened 治理事件。
    """
    await _enforce_rate_limit(request)
    preview = bool(
        user and user.is_platform_admin
        and request.query_params.get("preview") == "true"
    )
    data = await market.get_public(asset_type, name, preview=preview)
    if data is None:
        return _store_not_found()
    if data.get("market_closed"):
        return ok(data=data)
    # AD-5e：detail_opened 预览与正式**都发**（GWT-08.4 的 oracle 是「抽屉渲染完成」，
    # 不区分通道）；既有 MARKET_DETAIL_VIEWED 原样保留，两者并存不互斥。
    if not preview:
        await emit_public_detail(market.session, data)
    await emit_detail_opened(
        market.session,
        actor_role=("platform_admin" if preview else (user.role if user else "anonymous")),
        asset_type=str(data.get("asset_type") or ""), asset_name=name,
        actor_user_id=user.id if user else None,
    )
    return ok(data=data)


# ---------- 技能筛（同一 FR-33 读模型；禁止 LIMIT 后再内存滤） ----------


@router.post("/skills/{name}/subscribe")
async def public_subscribe_skill(
    name: str,
    request: Request,
    payload: SubscribeRequest | None = None,
    user: CurrentUser = Depends(require_login),
    market: PowerMarketService = Depends(_market),
):
    await _enforce_rate_limit(request)
    host = payload.host if payload else None
    data = await run_subscribe(
        market.session, market, asset_type="skill", name=name, host=host,
        user=user, default="skill",
    )
    return ok(data=data)


@router.get("/skills/{name}")
async def public_get_skill(
    name: str,
    request: Request,
    market: PowerMarketService = Depends(_market),
):
    await _enforce_rate_limit(request)
    data = await market.get_public("skill", name, default="skill")
    if data is None:
        return _store_not_found()
    if data.get("market_closed"):
        return ok(data=data)
    await emit_public_detail(market.session, data)
    return ok(data=data)


@router.get("/skills")
async def public_list_skills(
    request: Request,
    q: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = None,
    type: Optional[str] = Query(None),
    host: Optional[str] = Query(None, max_length=16),
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    anonymous_id: Optional[str] = Query(None, max_length=64),
    market: PowerMarketService = Depends(_market),
):
    """公开技能列表：默认 type=skill；与 /public/capabilities 同一五类枚举。"""
    await _enforce_rate_limit(request)
    assert PUBLIC_ASSET_TYPES  # 与 /public/capabilities 同一五类
    data = await market.list_public(
        asset_type=type, default="skill", category=category, q=q, host=host,
        page=page, page_size=page_size,
    )
    if not data.get("market_closed"):
        await emit_public_list(
            market.session, asset_type=type or "skill", host=host, category=category,
            q=q, total=data["total"],
        )
        await _emit_paged_event(market.session, page, data, anonymous_id)
    return ok(data=data)
