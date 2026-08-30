"""爬虫结果查询与统计服务 - 结果/导出/质量/日志/存储状态/聚合统计

职责：
- list_results：任务采集结果分页查询
- export_results：结果导出（csv/json）
- get_task_quality：数据质量报告（平均分/四档分布）
- task_logs：任务运行日志（尾部 N 行 + 关键词/级别过滤）
- store_status：多存储目标状态查询
- stats：聚合运行统计（供 /admin/stats）

设计说明：
- 子 Service 通过 __getattr__ 将未知属性委托给父 Facade（SpiderService），
  确保测试 patch backend.services.spider_service.<name> 能正确生效。
"""
import asyncio
import csv
import io
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import TASK_RESULTS_KEY
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

# 从 spider_service 导入共享工具（不会被测试 patch）
from backend.services.spider_service import (
    _PROJECT_ROOT,
    _read_task_log_sync,
)

logger = get_logger("api")


class SpiderQueryService:
    """结果查询 / 统计 / 日志 / 质量 / 存储状态"""

    def __init__(self, parent):
        """parent: SpiderService Facade 实例"""
        self._parent = parent

    def __getattr__(self, name):
        """委托未知属性到父 Facade"""
        return getattr(self._parent, name)

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

    # 导出列定义
    _EXPORT_COLUMNS = (
        "id", "task_id", "spider_name", "url", "title", "content",
        "source", "item_type", "extra", "created_at",
    )

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

    async def export_results(self, task_id: int, fmt: str) -> Tuple[bytes, str, str]:
        """导出任务全部采集结果（csv / json）"""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if fmt not in ("csv", "json"):
            raise BusinessException("导出格式仅支持 csv/json")

        items = await self.result_repo.all_by_task(task_id)
        rows = []
        for r in items:
            rows.append(
                {
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
            )

        filename = f"task_{task_id}_results.{fmt}"
        if fmt == "json":
            content = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            media_type = "application/json"
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=self._EXPORT_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            content = buf.getvalue().encode("utf-8-sig")
            media_type = "text/csv"

        logger.info(f"导出任务结果: task_id={task_id}, fmt={fmt}, rows={len(rows)}")
        return content, filename, media_type

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

        log_path = self.resolve_spider_log_path()
        content_lines: list[str] = []
        if log_path and os.path.isfile(log_path):
            offset = self._task_log_offset(task_id)
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

    def _task_log_offset(self, task_id: int) -> Optional[int]:
        """读取任务日志起始偏移量（通过委托访问）"""
        return self._parent._task_log_offset(task_id)

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
                redis_count = self.redis_client().llen(TASK_RESULTS_KEY.format(task_id=task_id))
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
        rel = self.settings.get("STORAGE.DIR", "storage/exports") or "storage/exports"
        return rel if os.path.isabs(rel) else os.path.abspath(os.path.join(_PROJECT_ROOT, rel))

    def _store_targets(self, task) -> list[str]:
        """生效的额外存储目标"""
        from backend.services.spider_service import _STORE_TARGET_ENUM, extract_store_targets
        targets = extract_store_targets(getattr(task, "params", None))
        if not targets:
            default = self.settings.get("STORAGE.EXTRA_TARGETS", []) or []
            if isinstance(default, str):
                default = [default]
            targets = [t for t in default if t in _STORE_TARGET_ENUM]
        return targets
