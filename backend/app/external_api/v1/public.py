"""外部 API - 公开查询接口

职责：
- 提供 API Key 认证的采集结果数据查询
- 支持第三方系统按爬虫名称分页拉取结果
- 任务状态 / 任务结果 / 聚合统计的真实数据查询（API Key 认证）
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.external_api.v1.webhooks import validate_api_key
from backend.repositories.spider_result_repository import SpiderResultRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_service import SpiderService
from platform_core.db import get_async_db
from platform_core.exceptions import NotFoundException
from platform_core.schemas.spider import SpiderTaskResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# 公开数据查询端点（API Key 认证）
# ---------------------------------------------------------------------------

def _require_api_key(request: Request) -> None:
    """公开查询端点统一鉴权（唯一入口，/data/{spider_name} 也走此函数）

    X-API-Key 须命中 EXTERNAL_API.API_KEYS（或过渡期旧单 key EXTERNAL_API.API_KEY，
    见 webhooks.validate_api_key）；均未配置（空）时一律 401，杜绝默认密钥。
    """
    api_key = request.headers.get("X-API-Key", "")
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API Key")


@router.get("/data/{spider_name}")
async def get_spider_data(
    spider_name: str,
    request: Request,
    page: int = 1,
    page_size: int = 20,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    fields: Optional[str] = None,
    session: AsyncSession = Depends(get_async_db),
):
    """公开数据查询端点 — 按爬虫名称分页查询采集结果

    认证：X-API-Key Header，统一走 _require_api_key（与 status/results/stats
    同一鉴权逻辑）；未配置 API Key 或密钥不匹配时一律 401。
    可选参数：
      - page / page_size：分页
      - start_time / end_time：时间范围过滤（ISO 8601）
      - fields：逗号分隔的字段名，如 "url,title,content"（响应字段裁剪）
    """
    # 1. 验证 API Key（统一鉴权入口，与新列表/旧单 key 双轨配置兼容）
    _require_api_key(request)

    # 2. 参数约束
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

    # 3. 查询结果
    repo = SpiderResultRepository(session)
    items, total = await repo.query_by_spider(
        spider_name=spider_name,
        page=page,
        page_size=page_size,
        start_time=start_time,
        end_time=end_time,
    )

    # 4. 字段过滤
    if fields:
        field_list = {f.strip() for f in fields.split(",") if f.strip()}
        if field_list:
            items = [{k: v for k, v in item.items() if k in field_list} for item in items]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 任务状态 / 结果 / 统计（真实数据，API Key 认证）
# ---------------------------------------------------------------------------

@router.get("/spider/status/{task_id}", response_model=SpiderTaskResponse)
async def get_spider_status(
    task_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_db),
):
    """查询爬虫任务状态（公开接口，API Key 认证；任务不存在返回 404）"""
    _require_api_key(request)
    task = await SpiderTaskRepository(session).get_by_id(task_id)
    if task is None:
        raise NotFoundException("爬虫任务")
    return SpiderTaskResponse.model_validate(task)


@router.get("/spider/results/{task_id}")
async def get_spider_results(
    task_id: int,
    request: Request,
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_async_db),
):
    """获取任务采集结果（公开接口，API Key 认证；分页；任务不存在返回 404）"""
    _require_api_key(request)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    if page_size > 100:
        page_size = 100

    resp = await SpiderService(session).list_results(
        task_id=task_id, skip=(page - 1) * page_size, limit=page_size
    )
    return {
        "task_id": task_id,
        "page": page,
        "page_size": page_size,
        "total": resp.total,
        "data": [item.model_dump(mode="json") for item in resp.items],
    }


@router.get("/stats")
async def get_public_stats(
    request: Request,
    session: AsyncSession = Depends(get_async_db),
):
    """系统公开统计（真实聚合数据：任务状态分布/成功率/近 7 日趋势；API Key 认证）"""
    _require_api_key(request)
    return (await SpiderService(session).stats()).model_dump(mode="json")
