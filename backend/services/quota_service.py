"""租户配额与用量服务（SaaS S3-1）

tenants.quota JSON 契约：{task_concurrency, result_storage, llm_tokens_month}
三类检查点：
- 任务并发：enqueue 时统计本租户 running/pending 任务数，超并发拒绝；
- 结果存储：结果回流时统计本租户 spider_results 行数，超存储拒绝；
- LLM token：月度用量（llm_token_usage 聚合）超配额拒绝 LLM 调用。
超限统一抛 QuotaExceededException（业务码 QUOTA_EXCEEDED，文案可行动）。
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.redis_async import get_async_redis

logger = get_logger("service.quota")

# 免费档默认配额（tenants.quota 缺失时兜底；平台级默认，运营台可改行级）
DEFAULT_QUOTA = {
    "task_concurrency": 5,
    "result_storage": 10000,
    "llm_tokens_month": 200000,
}


class QuotaExceededException(BusinessException):
    """租户配额超限（业务码 QUOTA_EXCEEDED，文案给出可行动建议）"""

    def __init__(self, message: str):
        super().__init__(message=message, code="QUOTA_EXCEEDED", status_code=429)


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
            raise QuotaExceededException(
                f"任务并发已达配额上限（{active}/{limit}）：请等待运行中任务完成，"
                "或联系平台管理员提升套餐"
            )
        logger.debug(f"配额检查·任务并发 | tenant={tenant_id} {active}/{limit}")

    async def check_result_storage(self, tenant_id: int) -> None:
        """结果回流前：本租户 spider_results 行数 < result_storage"""
        tenant = await self._tenant(tenant_id)
        limit = int(quota_of(tenant)["result_storage"])
        async def _count_results() -> int:
            return int((await self.session.execute(
                select(func.count()).select_from(SpiderResult).where(
                    SpiderResult.tenant_id == tenant_id
                )
            )).scalar_one())

        stored = await self._cached_count(f"results:{tenant_id}", _count_results)
        if stored >= limit:
            raise QuotaExceededException(
                f"结果存储已达配额上限（{stored}/{limit}）：请清理历史结果，"
                "或联系平台管理员提升套餐"
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
                func.cast(LlmTokenUsage.stat_date, String_).like(month_prefix + "%"),
            )
        )).scalar_one()
        if int(used) >= limit:
            raise QuotaExceededException(
                f"本月 LLM token 用量已达配额上限（{used}/{limit}）：请配置自有供应商 Key，"
                "或联系平台管理员提升套餐"
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
        stored_results = (await self.session.execute(
            select(func.count()).select_from(SpiderResult).where(
                SpiderResult.tenant_id == tenant_id
            )
        )).scalar_one()
        month_prefix = f"{year_month}-"
        tokens_row = (await self.session.execute(
            select(LlmTokenUsage.provider_name,
                   func.sum(LlmTokenUsage.total_tokens).label("tokens"))
            .where(
                LlmTokenUsage.tenant_id == tenant_id,
                func.cast(LlmTokenUsage.stat_date, String_).like(month_prefix + "%"),
            )
            .group_by(LlmTokenUsage.provider_name)
        )).all()
        tokens_total = sum(int(r.tokens or 0) for r in tokens_row)
        return {
            "tenant_id": tenant_id,
            "quota": quota,
            "usage": {
                "task_concurrency": int(active_tasks),
                "result_storage": int(stored_results),
                "llm_tokens_month": tokens_total,
            },
            "llm_by_provider": {r.provider_name: int(r.tokens or 0) for r in tokens_row},
        }


from sqlalchemy import String as String_  # noqa: E402（usage_overview cast 用）
