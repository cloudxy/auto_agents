"""爬虫结果数据访问层 - 封装所有 SpiderResult 相关的数据库操作"""
from collections.abc import AsyncIterator
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import and_, case, delete as sa_delete, or_
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.repository import BaseRepository

# FR-11 / ADR-0013：候选与成果同表；租户配额/数据中心/导出/出站排除 marketplace。
CANDIDATE_SOURCE = "marketplace"


def owned_source_clause(exclude_source: str = CANDIDATE_SOURCE):
    """source <> exclude_source；NULL source 视为非该值（可导出、计配额）。"""
    return or_(
        SpiderResult.source.is_(None),
        SpiderResult.source != exclude_source,
    )


def pending_marketplace_clause():
    """待审候选：source=marketplace 且 extra.review 缺省 pending。

    extra 是 TEXT JSON。json_extract 在 SQLite 返回无引号标量，MySQL 可能带引号。
    """
    extra = SpiderResult.extra
    review = func.json_extract(extra, "$.review")
    return and_(
        SpiderResult.source == CANDIDATE_SOURCE,
        or_(
            extra.is_(None),
            extra == "",
            review.is_(None),
            review.in_(("pending", '"pending"')),
        ),
    )


# keyword LIKE '%kw%' 检索护栏：前导通配符无法命中任何索引，行数上百万后
# 深翻页会退化为全表扫描 + filesort。开启 keyword 过滤时，单次检索最多允许
# 访问前 KEYWORD_SEARCH_MAX_ROWS 行（与分页参数冲突时取 min）；超出窗口的
# 翻页直接返回空列表（total 仍为真实计数），防止深分页拖垮数据库。
KEYWORD_SEARCH_MAX_ROWS = 200

# 导出流式分批大小：export 按主键 id 游标逐批拉取，单批行数上限，
# 将导出过程的内存峰值从「全表行数」压到单批常量级。
EXPORT_BATCH_SIZE = 5000


class SpiderResultRepository(BaseRepository[SpiderResult]):
    """SpiderResult Repository —— 在 BaseRepository 之上扩展按任务查询/计数"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=SpiderResult, session=session)

    async def list_by_task(
        self,
        task_id: int,
        skip: int = 0,
        limit: int = 50,
        *,
        exclude_source: Optional[str] = CANDIDATE_SOURCE,
    ) -> List[SpiderResult]:
        """按任务分页查询非候选结果（最新优先；「我的结果」）"""
        conds = [SpiderResult.task_id == task_id]
        if exclude_source is not None:
            conds.append(owned_source_clause(exclude_source))
        stmt = (
            select(SpiderResult)
            .where(*conds)
            .order_by(SpiderResult.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_task(
        self, task_id: int, *, exclude_source: Optional[str] = CANDIDATE_SOURCE,
    ) -> int:
        """按任务计数非候选结果条数"""
        conds = [SpiderResult.task_id == task_id]
        if exclude_source is not None:
            conds.append(owned_source_clause(exclude_source))
        stmt = select(func.count(SpiderResult.id)).where(*conds)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def count_owned_by_tenant(self, tenant_id: int) -> int:
        """本企业非候选结果条数（配额 / 用量；不计 marketplace）"""
        stmt = select(func.count(SpiderResult.id)).where(
            SpiderResult.tenant_id == tenant_id,
            owned_source_clause(),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_pending_marketplace_candidates(
        self, page: int = 1, page_size: int = 20,
    ) -> Tuple[List[SpiderResult], int]:
        """待审候选 SQL 分页（禁止全表进内存再切片）"""
        cond = pending_marketplace_clause()
        total = int((await self.session.execute(
            select(func.count()).select_from(SpiderResult).where(cond)
        )).scalar() or 0)
        offset = (page - 1) * page_size
        rows = (await self.session.execute(
            select(SpiderResult).where(cond)
            .order_by(SpiderResult.id.desc())
            .offset(offset).limit(page_size)
        )).scalars().all()
        return list(rows), total

    async def all_by_task(self, task_id: int) -> List[SpiderResult]:
        """按任务查询全部结果（一次性载入，仅限小任务场景；导出请用 iter_by_task）"""
        stmt = (
            select(SpiderResult)
            .where(SpiderResult.task_id == task_id)
            .order_by(SpiderResult.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def iter_by_task(
        self,
        task_id: int,
        batch_size: int = EXPORT_BATCH_SIZE,
        *,
        exclude_source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[SpiderResult]:
        """按 id 游标分批产出任务结果（导出流式用，避免 all() 全量载入内存）

        以 (task_id, id > last_id) 为游标逐批 ORDER BY id ASC 拉取。
        exclude_source 在 SQL 侧排除该 source（NULL 视为非该值，可导出）。
        limit 为窗口上限（导出单次 100）；单批不超过 remaining。
        """
        last_id = 0
        yielded = 0
        while True:
            remaining = None if limit is None else limit - yielded
            if remaining is not None and remaining <= 0:
                break
            fetch = batch_size if remaining is None else min(batch_size, remaining)
            conds = [
                SpiderResult.task_id == task_id,
                SpiderResult.id > last_id,
            ]
            if exclude_source is not None:
                conds.append(owned_source_clause(exclude_source))
            stmt = (
                select(SpiderResult)
                .where(*conds)
                .order_by(SpiderResult.id.asc())
                .limit(fetch)
            )
            rows = (await self.session.execute(stmt)).scalars().all()
            if not rows:
                break
            for row in rows:
                yield row
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            last_id = rows[-1].id

    async def create_for_task(self, **kwargs) -> SpiderResult:
        """落库一条结果并原子累加任务的 result_count"""
        instance = await self.create(**kwargs)
        await self.session.execute(
            update(SpiderTask)
            .where(SpiderTask.id == kwargs["task_id"])
            .values(result_count=SpiderTask.result_count + 1)
        )
        return instance

    async def delete_by_task(self, task_id: int) -> int:
        """删除指定任务的全部结果（任务删除时级联清理）"""
        result = await self.session.execute(
            sa_delete(SpiderResult).where(SpiderResult.task_id == task_id)
        )
        return int(result.rowcount or 0)

    async def daily_result_counts(self, since: datetime) -> List[Tuple[str, int]]:
        """按日统计采集结果条数（created_at >= since），返回 [(yyyy-mm-dd, count)] 升序"""
        day = func.date(SpiderResult.created_at)
        stmt = (
            select(day, func.count(SpiderResult.id))
            .where(SpiderResult.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        result = await self.session.execute(stmt)
        return [(str(d), int(n)) for d, n in result.all()]

    async def find_by_content_hash(
        self,
        content_hash: str,
        tenant_id: Optional[int] = None,
        spider_name: Optional[str] = None,
    ) -> Optional[SpiderResult]:
        """按 (tenant_id, spider_name, content_hash) 查重（B6；跨租户互不可见）"""
        stmt = select(SpiderResult).where(SpiderResult.content_hash == content_hash)
        if tenant_id is not None:
            stmt = stmt.where(SpiderResult.tenant_id == tenant_id)
        if spider_name:
            stmt = stmt.where(SpiderResult.spider_name == spider_name)
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def query_by_spider(
        self,
        spider_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keyword: Optional[str] = None,
        exclude_source: Optional[str] = CANDIDATE_SOURCE,
        tenant_id: Optional[int] = None,
    ) -> Tuple[List[dict], int]:
        """按爬虫名称分页查询结果（返回 dict 列表，非 ORM 对象）

        阶段 6 扩展：spider_name 可选（跨任务全量查询），keyword 模糊匹配 title/url/content。
        默认排除 marketplace 候选（数据中心 / 出站；FR-11）。
        出站拉数须传 tenant_id（FR-13）；数据中心可省略（JWT tenant_scope 注入）。

        keyword 深翻页护栏：LIKE '%kw%' 无法命中索引，检索窗口硬上限为
        KEYWORD_SEARCH_MAX_ROWS（与分页参数冲突时取 min）；超出窗口的翻页
        返回空列表（total 仍为真实计数），防止深分页全表扫描。
        """
        filters = []
        if tenant_id is not None:
            filters.append(SpiderResult.tenant_id == tenant_id)
        if spider_name:
            filters.append(SpiderResult.spider_name == spider_name)
        if keyword:
            kw = f"%{keyword}%"
            filters.append(
                SpiderResult.title.like(kw)
                | SpiderResult.url.like(kw)
                | SpiderResult.content.like(kw)
            )
        if exclude_source is not None:
            filters.append(owned_source_clause(exclude_source))
        query = select(SpiderResult)
        count_query = select(func.count()).select_from(SpiderResult)
        for cond in filters:
            query = query.where(cond)
            count_query = count_query.where(cond)

        if start_time:
            query = query.where(SpiderResult.created_at >= start_time)
            count_query = count_query.where(SpiderResult.created_at >= start_time)
        if end_time:
            query = query.where(SpiderResult.created_at <= end_time)
            count_query = count_query.where(SpiderResult.created_at <= end_time)

        total = (
            await self.session.execute(count_query)
        ).scalar() or 0

        offset = (page - 1) * page_size
        limit = page_size
        if keyword:
            # 深翻页护栏：检索窗口整体限制在 KEYWORD_SEARCH_MAX_ROWS 行内
            if offset >= KEYWORD_SEARCH_MAX_ROWS:
                return [], total
            limit = min(limit, KEYWORD_SEARCH_MAX_ROWS - offset)

        query = (
            query.order_by(SpiderResult.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        rows = result.scalars().all()

        items = [
            {
                "id": r.id,
                "task_id": r.task_id,
                "spider_name": r.spider_name,
                "url": r.url,
                "title": r.title,
                "content": r.content,
                "source": r.source,
                "item_type": r.item_type,
                "quality_score": r.quality_score,
                "content_hash": r.content_hash,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return items, total

    async def quality_report(self, task_id: int) -> dict:
        """任务级数据质量原始聚合数据（供 Service 层构造响应）"""
        # 聚合查询
        stmt = (
            select(
                func.avg(SpiderResult.quality_score),
                func.min(SpiderResult.quality_score),
                func.max(SpiderResult.quality_score),
                func.count(SpiderResult.id),
            )
            .where(SpiderResult.task_id == task_id)
            .where(SpiderResult.quality_score.isnot(None))
        )
        result = await self.session.execute(stmt)
        row = result.one()
        avg_score, min_score, max_score, total = row

        # 四档分布
        dist_stmt = (
            select(
                func.sum(
                    case(
                        (SpiderResult.quality_score >= 80, 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            (SpiderResult.quality_score >= 60)
                            & (SpiderResult.quality_score < 80),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            (SpiderResult.quality_score >= 40)
                            & (SpiderResult.quality_score < 60),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (SpiderResult.quality_score < 40, 1),
                        else_=0,
                    )
                ),
            )
            .where(SpiderResult.task_id == task_id)
            .where(SpiderResult.quality_score.isnot(None))
        )
        dist_result = await self.session.execute(dist_stmt)
        dist_row = dist_result.one()
        excellent, good, fair, poor = dist_row

        return {
            "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
            "min_score": round(float(min_score), 1) if min_score is not None else None,
            "max_score": round(float(max_score), 1) if max_score is not None else None,
            "total_items": int(total),
            "excellent": int(excellent or 0),
            "good": int(good or 0),
            "fair": int(fair or 0),
            "poor": int(poor or 0),
        }
