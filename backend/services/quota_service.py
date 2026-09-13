"""租户配额与用量服务（SaaS S3-1）

tenants.quota JSON 契约：{task_concurrency, result_storage, llm_tokens_month}
三类检查点：
- 任务并发：enqueue 时统计本租户 running/pending 任务数，超并发拒绝；
- 结果存储：结果回流时统计本租户 spider_results 行数，超存储拒绝；
- LLM token：月度用量（llm_token_usage 聚合）超配额拒绝 LLM 调用。
超限统一抛 QuotaExceededException（业务码 QUOTA_EXCEEDED，文案可行动）。
内部码可保留；用户可见句不得渲染 QUOTA_EXCEEDED / 裸 429。
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_result_repository import SpiderResultRepository
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.redis_async import get_async_redis

logger = get_logger("service.quota")

# 用户可见句（FR-U02）。内部码 QUOTA_EXCEEDED 不得出现在这些常量里。
PLAN_FULL_USER = "已达配额上限"
PLAN_FULL_CTA = "申请提升"
TASK_QUOTA_LIMIT_CODE = "TASK_QUOTA_LIMIT_REACHED"
NEAR_LIMIT_USER = "接近上限。超额操作会被拒绝。"
GATEWAY_UNREACHABLE_USER = "平台 LLM 网关不可达"
NO_MODEL_USER = "还没有平台模型"
PROVIDER_ERROR_USER = "本企业供应商调用失败"
STORAGE_CLEANUP_CTA = "去结果库"
CONTACT_ADMIN_UPGRADE = "请联系本企业管理员开通"
CHECKOUT_EMPTY_USER = "收款通道未开通"
CHECKOUT_PRODUCTS = frozenset({"plan_pro", "plan_enterprise", "relay"})
DEFAULT_UPGRADE_PRODUCT = "plan_pro"
BUYER_TENANT_ROLES = frozenset({"owner", "admin"})
SHANGHAI_TZ = "Asia/Shanghai"


def shanghai_now() -> datetime:
    logger.debug("计算 Asia/Shanghai 当前时刻")
    return datetime.now(ZoneInfo(SHANGHAI_TZ))


def shanghai_today() -> date:
    logger.debug("计算 Asia/Shanghai 业务日")
    return shanghai_now().date()


def shanghai_year_month() -> str:
    logger.debug("计算 Asia/Shanghai 业务月")
    return shanghai_now().strftime("%Y-%m")


def shanghai_window_start(days: int = 6) -> datetime:
    logger.debug(f"计算 Asia/Shanghai 窗口起点 | days={days}")
    start_local = datetime.combine(
        shanghai_today() - timedelta(days=days), datetime.min.time(),
        tzinfo=ZoneInfo(SHANGHAI_TZ),
    )
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


def user_visible_llm_failure(code: str, message: str = "") -> str:
    logger.debug(f"映射 LLM 失败码 | code={code}")
    if code == "QUOTA_EXCEEDED":
        return f"{PLAN_FULL_USER}。{PLAN_FULL_CTA}"
    if code == "LLM_GATEWAY_UNREACHABLE":
        return GATEWAY_UNREACHABLE_USER
    if code == "LLM_GATEWAY_NO_MODEL":
        return NO_MODEL_USER
    if code == "LLM_PROVIDER_ERROR":
        return PROVIDER_ERROR_USER
    if code == "LLM_COST_FUSE":
        return message or "平台 LLM 成本熔断，请稍后重试"
    return message or "调用失败"


def _full_cta(metric: str) -> str:
    logger.debug(f"满额 CTA | metric={metric}")
    if metric == "result_storage":
        return STORAGE_CLEANUP_CTA
    return PLAN_FULL_CTA


def build_usage_alerts(usage: dict, quota: dict, llm_error_code: str | None = None) -> list[dict]:
    logger.debug(f"生成用量告警 | llm_error_code={llm_error_code}")
    alerts: list[dict] = []
    if llm_error_code == "LLM_GATEWAY_UNREACHABLE":
        alerts.append({
            "metric": "llm_gateway", "level": "error",
            "message": user_visible_llm_failure(llm_error_code),
        })
    for key in ("task_concurrency", "result_storage", "llm_tokens_month"):
        limit = int(quota.get(key) or 0)
        used = int(usage.get(key) or 0)
        if limit <= 0:
            continue
        ratio = used / limit
        if ratio >= 1.0:
            alerts.append({
                "metric": key, "level": "full",
                "message": PLAN_FULL_USER, "cta": _full_cta(key),
            })
        elif ratio >= 0.9:
            alerts.append({
                "metric": key, "level": "near", "message": NEAR_LIMIT_USER,
            })
    return alerts


def checkout_path_for(product: str) -> str:
    logger.debug(f"结账路由 | product={product}")
    return f"/billing/checkout?product={product}"


def wrap_quota_exceeded(exc: "QuotaExceededException") -> BusinessException:
    """入队/规划 HTTP 信封：已达配额上限 + 分维 CTA；禁 429 / QUOTA_EXCEEDED。"""
    logger.warning(f"配额满信封 | inner={getattr(exc, 'code', None)}")
    dimension = getattr(exc, "dimension", "unknown")
    cta = STORAGE_CLEANUP_CTA if dimension == "storage" else PLAN_FULL_CTA
    return BusinessException(
        message=f"{PLAN_FULL_USER}。{cta}",
        code=TASK_QUOTA_LIMIT_CODE,
        data={"dimension": dimension, "cta": cta},
    )


def resolve_upgrade_intent(tenant_role: str | None, product: str = DEFAULT_UPGRADE_PRODUCT) -> dict:
    """申请提升分角色着陆（FR-U02）：配额模块只给意图，不建支付单。"""
    logger.info(f"申请提升分角色着陆 | role={tenant_role} product={product}")
    sku = product if product in CHECKOUT_PRODUCTS else DEFAULT_UPGRADE_PRODUCT
    if tenant_role in BUYER_TENANT_ROLES:
        return {
            "action": "checkout", "product": sku,
            "checkout_path": checkout_path_for(sku), "message": "去结账",
        }
    return {
        "action": "contact_admin", "product": sku,
        "checkout_path": None, "message": CONTACT_ADMIN_UPGRADE,
    }

# 免费档默认配额（tenants.quota 缺失时兜底；平台级默认，运营台可改行级）
DEFAULT_QUOTA = {
    "task_concurrency": 5,
    "result_storage": 10000,
    "llm_tokens_month": 200000,
}


class QuotaExceededException(BusinessException):
    """租户配额超限（业务码 QUOTA_EXCEEDED，文案给出可行动建议）"""

    def __init__(self, message: str, dimension: str = "unknown"):
        super().__init__(message=message, code="QUOTA_EXCEEDED", status_code=429)
        self.dimension = dimension


# 租户配额：行级 quota JSON 与平台默认逐键合并（部分覆盖生效）
def quota_of(tenant: Tenant) -> dict:
    logger.debug(f"读取配额 | tenant={getattr(tenant, 'id', None)}")
    merged = dict(DEFAULT_QUOTA)
    if tenant and tenant.quota:
        merged.update({k: v for k, v in tenant.quota.items() if v is not None})
    return merged


# B4：计数缓存 TTL——结果回流逐行检查不再每行 COUNT 全表（60s 窗口内复用；
# 配额语义容忍短窗滞后，Redis 故障自动回退 DB COUNT）
_COUNT_CACHE_TTL = 60
_QUOTA_COUNT_PREFIX = "quota:count:"


class QuotaService:
    """配额检查点（session 注入；调用方在写入路径前置调用）"""

    async def _emit_quota(self, tenant_id: int, dimension: str) -> None:
        logger.info(f"配额拒绝事件 | tenant={tenant_id} dim={dimension}")
        from backend.services.product_event_service import emit_product_event
        await emit_product_event(
            self.session, "quota_exceeded", tenant_id=tenant_id,
            props={"dimension": dimension},
        )

    async def _cached_count(self, key: str, count_fn) -> int:
        """Redis TTL 缓存的计数（B4）：命中免 COUNT；miss/故障回源 DB"""
        try:
            redis = get_async_redis()
            cached = await redis.get(f"{_QUOTA_COUNT_PREFIX}{key}")
            if cached is not None:
                return int(cached)
            value = int(await count_fn())
            await redis.set(f"{_QUOTA_COUNT_PREFIX}{key}", value, ex=_COUNT_CACHE_TTL)
            return value
        except Exception:  # noqa: BLE001 Redis 故障回源 DB（配额不可因缓存故障失效）
            return int(await count_fn())

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _tenant(self, tenant_id: int) -> Tenant:
        tenant = (await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        if tenant is None:
            raise BusinessException(message=f"租户不存在: {tenant_id}")
        return tenant

    async def check_task_concurrency(self, tenant_id: int) -> None:
        """任务入队前：本租户 running/pending 任务数 < task_concurrency"""
        tenant = await self._tenant(tenant_id)
        limit = int(quota_of(tenant)["task_concurrency"])
        async def _count_active() -> int:
            return int((await self.session.execute(
                select(func.count()).select_from(SpiderTask).where(
                    SpiderTask.tenant_id == tenant_id,
                    SpiderTask.status.in_(("pending", "running")),
                )
            )).scalar_one())

        active = await self._cached_count(f"active_tasks:{tenant_id}", _count_active)
        if active >= limit:
            await self._emit_quota(tenant_id, "concurrency")
            raise QuotaExceededException(
                f"任务并发{PLAN_FULL_USER}（{active}/{limit}）：请等待运行中任务完成，"
                f"或{PLAN_FULL_CTA}",
                dimension="concurrency",
            )
        logger.debug(f"配额检查·任务并发 | tenant={tenant_id} {active}/{limit}")

    async def check_result_storage(self, tenant_id: int) -> None:
        """结果回流前：本租户非候选 spider_results 行数 < result_storage"""
        logger.info(f"配额检查·结果存储 | tenant={tenant_id}")
        tenant = await self._tenant(tenant_id)
        limit = int(quota_of(tenant)["result_storage"])
        repo = SpiderResultRepository(self.session)

        async def _count_results() -> int:
            return await repo.count_owned_by_tenant(tenant_id)

        stored = await self._cached_count(f"results_owned:{tenant_id}", _count_results)
        if stored >= limit:
            await self._emit_quota(tenant_id, "storage")
            raise QuotaExceededException(
                f"结果存储{PLAN_FULL_USER}（{stored}/{limit}）：请{STORAGE_CLEANUP_CTA}清理历史结果",
                dimension="storage",
            )
        logger.debug(f"配额检查·结果存储 | tenant={tenant_id} {stored}/{limit}")

    async def check_llm_tokens_month(self, tenant_id: int, year_month: str) -> None:
        """LLM 调用前：本租户当月 total_tokens 合计 < llm_tokens_month"""
        tenant = await self._tenant(tenant_id)
        limit = int(quota_of(tenant)["llm_tokens_month"])
        month_prefix = f"{year_month}-"
        used = (await self.session.execute(
            select(func.coalesce(func.sum(LlmTokenUsage.total_tokens), 0)).where(
                LlmTokenUsage.tenant_id == tenant_id,
                func.cast(LlmTokenUsage.stat_date, String).like(month_prefix + "%"),
            )
        )).scalar_one()
        if int(used) >= limit:
            await self._emit_quota(tenant_id, "llm_tokens")
            raise QuotaExceededException(
                f"本月 LLM token 用量{PLAN_FULL_USER}（{used}/{limit}）。{PLAN_FULL_CTA}",
                dimension="llm_tokens",
            )
        logger.debug(f"配额检查·LLM 月度 | tenant={tenant_id} {used}/{limit}")

    async def usage_by_member(self, tenant_id: int) -> list[dict]:
        """成员维度用量分摊（B6 工单 91）：spider_tasks 按 created_by 聚合

        LLM token 用量暂无操作人维度（llm_token_usage 按 provider/model 聚合），
        先落任务创建分摊；created_by 为 AuditMixin 用户名（NULL 归系统/调度触发）。
        """
        logger.debug(f"用量成员分摊 | tenant={tenant_id}")
        rows = (await self.session.execute(
            select(
                SpiderTask.created_by.label("member"),
                func.count().label("tasks"),
                func.max(SpiderTask.created_at).label("last_active_at"),
            ).where(
                SpiderTask.tenant_id == tenant_id,
            ).group_by(SpiderTask.created_by)
        )).all()
        return [
            {
                "member": r.member or "（系统/调度）",
                "tasks": int(r.tasks),
                "last_active_at": r.last_active_at.isoformat() if r.last_active_at else None,
            }
            for r in rows
        ]

    async def usage_overview(self, tenant_id: int, year_month: str) -> dict:
        """用量看板数据（S3-2 消费）：三指标当前值 vs 配额 + 成员分摊"""
        tenant = await self._tenant(tenant_id)
        quota = quota_of(tenant)
        active_tasks = (await self.session.execute(
            select(func.count()).select_from(SpiderTask).where(
                SpiderTask.tenant_id == tenant_id,
                SpiderTask.status.in_(("pending", "running")),
            )
        )).scalar_one()
        stored_results = await SpiderResultRepository(self.session).count_owned_by_tenant(
            tenant_id
        )
        month_prefix = f"{year_month}-"
        tokens_row = (await self.session.execute(
            select(LlmTokenUsage.provider_name,
                   func.sum(LlmTokenUsage.total_tokens).label("tokens"))
            .where(
                LlmTokenUsage.tenant_id == tenant_id,
                func.cast(LlmTokenUsage.stat_date, String).like(month_prefix + "%"),
            )
            .group_by(LlmTokenUsage.provider_name)
        )).all()
        tokens_total = sum(int(r.tokens or 0) for r in tokens_row)
        usage = {
            "task_concurrency": int(active_tasks),
            "result_storage": int(stored_results),
            "llm_tokens_month": tokens_total,
        }
        return {
            "tenant_id": tenant_id,
            "quota": quota,
            "usage": usage,
            "llm_by_provider": {r.provider_name: int(r.tokens or 0) for r in tokens_row},
            "timezone": SHANGHAI_TZ,
            "year_month": year_month,
            "alerts": build_usage_alerts(usage, quota),
        }
