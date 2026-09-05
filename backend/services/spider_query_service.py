"""爬虫结果查询与统计服务 - 结果/导出/质量/日志/存储状态/聚合统计

职责：
- list_results：任务采集结果分页查询
- export_results：结果导出（csv/json）
- get_task_quality：数据质量报告（平均分/四档分布）
- task_logs：任务运行日志（尾部 N 行 + 关键词/级别过滤）
- store_status：多存储目标状态查询
- stats：聚合运行统计（供 /admin/stats）

设计说明（期 4 Facade 退役后独立化）：
- 自持 session / repo / result_repo；模块级直引 settings / get_async_redis /
  共享工具（测试 patch 目标：backend.services.spider_query_service.<name>）。
- 期 4 R11 收口：_task_log_offset / store_status 的同步 redis_client 直调
  全部改 get_async_redis + await，check-arch 文件级豁免同步移除。
"""
import asyncio
import csv
import io
import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_result_repository import SpiderResultRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_common import (
    _PROJECT_ROOT,
    _STORE_TARGET_ENUM,
    _read_task_log_sync,
    extract_store_targets,
    resolve_spider_log_path,
)
from config import settings
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import TASK_LOG_OFFSET_KEY, TASK_RESULTS_KEY
from platform_core.redis_async import get_async_redis
from platform_core.schemas.spider import (
    DailyPoint,
    SpiderResultListResponse,
    SpiderResultResponse,
    SpiderStatsResponse,
    TaskLogResponse,
    TaskQualityReportResponse,
    TaskStoreStatusResponse,
    TopSpider,
)

logger = get_logger("api")


class SpiderQueryService:
    """结果查询 / 统计 / 日志 / 质量 / 存储状态"""

    def __init__(self, session: AsyncSession):
        """独立 Service：自持会话与仓储（期 4 Facade 退役）"""
        self.session = session
        self.repo = SpiderTaskRepository(session)
        self.result_repo = SpiderResultRepository(session)

    async def list_results(
        self,
        task_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> SpiderResultListResponse:
        """查询任务采集结果（数据闭环出口）"""
        logger.info(f"查询任务结果: task_id={task_id}, skip={skip}, limit={limit}")
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        total = await self.result_repo.count_by_task(task_id)
        items = await self.result_repo.list_by_task(task_id, skip=skip, limit=limit)
        return SpiderResultListResponse(
            total=total,
            items=[SpiderResultResponse.model_validate(r) for r in items],
        )

    async def get_task(self, task_id: int):
        """按主键取任务行（miss 抛 404）——T7 跳层收口：external_api 状态查询改道本层"""
        logger.info(f"查询任务 | task_id={task_id}")
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        return task

    async def query_public_results(
        self,
        spider_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[list, int]:
        """按爬虫名称分页查询结果（返回 dict 行列表，非 ORM）——外部公开查询通道

        T7 跳层收口：external_api /data/{spider_name} 的 repository 直连改道本层；
        字段裁剪（fields 参数）属协议层职责，归调用方。
        """
        logger.info(
            f"公开结果查询: spider={spider_name}, page={page}, "
            f"start={start_time}, end={end_time}"
        )
        return await self.result_repo.query_by_spider(
            spider_name=spider_name,
            page=page,
            page_size=page_size,
            start_time=start_time,
            end_time=end_time,
        )

    # 导出列定义
    _EXPORT_COLUMNS = (
        "id", "task_id", "spider_name", "url", "title", "content",
        "source", "item_type", "extra", "created_at",
    )

    @staticmethod
    def _export_row(r) -> dict:
        """ORM 结果行 -> 导出字典（列与全量导出保持一致）"""
        return {
            "id": r.id,
            "task_id": r.task_id,
            "spider_name": r.spider_name,
            "url": r.url,
            "title": r.title,
            "content": r.content,
            "source": r.source,
            "item_type": r.item_type,
            "extra": r.extra,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    async def export_results(
        self, task_id: int, fmt: str
    ) -> Tuple[AsyncIterator[bytes], str, str]:
        """导出任务全部采集结果（csv / json）—— 流式分批产出

        任务存在性与格式校验在返回前同步完成；正文按 id 游标分批拉取
        （iter_by_task）并增量编码为字节块，内存峰值恒为单批常量级，
        避免大任务导出全量载入。返回 (字节块异步迭代器, 文件名, media_type)，
        由 API 层以 StreamingResponse 下发，导出格式与列与全量导出逐字节一致。
        """
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if fmt not in ("csv", "json"):
            raise BusinessException("导出格式仅支持 csv/json")

        filename = f"task_{task_id}_results.{fmt}"
        media_type = "application/json" if fmt == "json" else "text/csv"
        logger.info(f"导出任务结果(流式): task_id={task_id}, fmt={fmt}")
        return self._iter_export_chunks(task_id, fmt), filename, media_type

    async def _iter_export_chunks(
        self, task_id: int, fmt: str
    ) -> AsyncIterator[bytes]:
        """按 id 游标分批拉取结果并增量编码（csv 带 BOM 头；json 保持 indent=2 数组格式）"""
        if fmt == "csv":
            yield b"\xef\xbb\xbf"  # utf-8-sig BOM（Excel 兼容）
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=self._EXPORT_COLUMNS)
            writer.writeheader()
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)
        else:
            yield b"["
            first = True

        async for r in self.result_repo.iter_by_task(task_id):
            row = self._export_row(r)
            if fmt == "csv":
                writer.writerow(row)
                yield buf.getvalue().encode("utf-8")
                buf.seek(0)
                buf.truncate(0)
            else:
                part = json.dumps(row, ensure_ascii=False, indent=2)
                yield (b"\n" if first else b",\n")
                first = False
                # 与 json.dumps(rows, indent=2) 逐字节对齐：元素整体缩进 2 空格
                yield ("  " + part.replace("\n", "\n  ")).encode("utf-8")

        if fmt == "json":
            yield b"\n]" if not first else b"]"  # 空结果：与 json.dumps([], indent=2) 对齐

    async def search_results(
        self,
        spider_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ) -> SpiderResultListResponse:
        """跨任务分页查询采集结果（数据中心：爬虫/时间范围/关键词过滤）"""
        logger.info(
            f"跨任务查询采集结果: spider={spider_name}, page={page}, "
            f"start={start_time}, end={end_time}, keyword={keyword}"
        )
        items, total = await self.result_repo.query_by_spider(
            spider_name=spider_name,
            page=page,
            page_size=page_size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
        )
        return SpiderResultListResponse(
            total=total,
            items=[SpiderResultResponse.model_validate(item) for item in items],
        )

    async def delete_result(self, result_id: int) -> dict:
        """删除单条采集结果（数据中心清理，仅 admin）"""
        logger.info(f"删除采集结果: result_id={result_id}")
        result = await self.result_repo.get_by_id(result_id)
        if result is None:
            raise NotFoundException("采集结果")
        await self.result_repo.delete(result_id)
        await self.session.commit()
        return {"id": result_id, "deleted": True}

    async def get_task_quality(self, task_id: int) -> TaskQualityReportResponse:
        """查询任务的质量报告：平均分/最低分/最高分/四档分布"""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")

        data = await self.result_repo.quality_report(task_id)
        return TaskQualityReportResponse(
            task_id=task_id,
            avg_score=data["avg_score"],
            min_score=data["min_score"],
            max_score=data["max_score"],
            total_items=data["total_items"],
            score_distribution={
                "excellent(80-100)": data["excellent"],
                "good(60-80)": data["good"],
                "fair(40-60)": data["fair"],
                "poor(0-40)": data["poor"],
            },
        )

    async def task_logs(
        self,
        task_id: int,
        lines: int = 200,
        keyword: str | None = None,
        level: str | None = None,
    ) -> TaskLogResponse:
        """读取任务运行日志（按任务隔离，从分发偏移量到文件尾，取尾部 N 行）"""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        await self.session.refresh(task)

        log_path = resolve_spider_log_path()
        content_lines: list[str] = []
        if log_path and os.path.isfile(log_path):
            offset = await self._task_log_offset(task_id)
            tail = max(1, min(lines, 500))
            content_lines = await asyncio.to_thread(
                _read_task_log_sync, log_path, offset, tail, keyword, level
            )
        return TaskLogResponse(
            task_id=task_id,
            spider_name=task.spider_name,
            status=task.status,
            lines=content_lines,
        )

    async def _task_log_offset(self, task_id: int) -> Optional[int]:
        """读取任务日志起始偏移量（期 4 R11 收口：同步 redis_client 改异步门面）

        原为 Facade 静态方法（同步 redis_client 直调 .get，行内豁免 allow-sync-redis）；
        调用方 task_logs 本就在 async 上下文，改 get_async_redis + await 后
        连同 check-arch R11 的行内豁免与文件级豁免一并清零。
        """
        try:
            raw = await get_async_redis().get(TASK_LOG_OFFSET_KEY.format(task_id=task_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取任务日志偏移量失败: task_id={task_id}, error={e}")
            return None
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def store_status(self, task_id: int) -> TaskStoreStatusResponse:
        """查询任务的额外存储目标状态"""
        logger.info(f"查询任务存储状态: task_id={task_id}")
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        targets = self._store_targets(task)
        redis_count: Optional[int] = None
        if targets:
            try:
                # 期 4 R11 收口：原同步 redis_client 直调 llen 阻塞事件循环，改异步门面
                redis_count = await get_async_redis().llen(TASK_RESULTS_KEY.format(task_id=task_id))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"读取结果缓存条数失败: task_id={task_id}, error={e}")
        csv_path: Optional[str] = None
        if "csv" in targets:
            candidate = os.path.join(self._store_dir(), f"task_{task_id}.csv")
            csv_path = candidate if os.path.isfile(candidate) else None
        return TaskStoreStatusResponse(
            task_id=task_id, targets=targets, redis_count=redis_count, csv_path=csv_path
        )

    async def stats(self) -> SpiderStatsResponse:
        """供 /admin/stats 使用的聚合统计"""
        logger.info("聚合爬虫运行统计")
        counts = await self.repo.count_by_status()
        total = sum(counts.values())

        finished = counts["completed"] + counts["failed"]
        success_rate = round(counts["completed"] / finished, 4) if finished else None

        since = datetime.now() - timedelta(days=6)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_tasks = [
            DailyPoint(date=d, count=n) for d, n in await self.repo.daily_task_counts(since)
        ]
        daily_results = [
            DailyPoint(date=d, count=n) for d, n in await self.result_repo.daily_result_counts(since)
        ]
        top_spiders = [
            TopSpider(spider_name=name, result_count=n)
            for name, n in await self.repo.top_spiders_by_results(limit=5)
        ]

        return SpiderStatsResponse(
            total_tasks=total,
            pending=counts["pending"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            avg_duration_seconds=await self.repo.avg_duration_seconds(),
            success_rate=success_rate,
            total_results=sum(p.count for p in daily_results),
            daily_tasks=daily_tasks,
            daily_results=daily_results,
            top_spiders=top_spiders,
        )

    def _store_dir(self) -> str:
        """csv 落盘目录"""
        rel = settings.get("STORAGE.DIR", "storage/exports") or "storage/exports"
        return rel if os.path.isabs(rel) else os.path.abspath(os.path.join(_PROJECT_ROOT, rel))

    def _store_targets(self, task) -> list[str]:
        """生效的额外存储目标"""
        targets = extract_store_targets(getattr(task, "params", None))
        if not targets:
            default = settings.get("STORAGE.EXTRA_TARGETS", []) or []
            if isinstance(default, str):
                default = [default]
            targets = [t for t in default if t in _STORE_TARGET_ENUM]
        return targets
