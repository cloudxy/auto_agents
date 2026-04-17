"""外部 API - 公开查询接口

职责：
- 提供无需认证的公开数据查询
- 支持第三方系统获取爬虫状态
- 限流保护（未来实现）
"""
from fastapi import APIRouter, HTTPException
from backend.cors.log_init import get_logger
import time

router = APIRouter()

@router.get("/spider/status/{task_id}")
async def get_spider_status(task_id: str):
    """
    查询爬虫任务状态（公开接口）
    
    第三方系统可以通过此接口查询任务进度
    """
    logger = get_logger("api")
    try:
        # TODO: 从数据库查询任务状态
        # task = await get_task_from_db(task_id)
        
        # 模拟返回
        return {
            "task_id": task_id,
            "status": "running",  # pending, running, completed, failed
            "progress": 65,
            "started_at": int(time.time()) - 300,
            "estimated_completion": int(time.time()) + 120
        }
        
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/spider/results/{task_id}")
async def get_spider_results(
    task_id: str,
    page: int = 1,
    page_size: int = 50
):
    """
    获取爬虫结果（公开接口，支持分页）
    """
    logger = get_logger("api")
    try:
        # TODO: 从数据库查询结果
        # results = await get_results_from_db(task_id, page, page_size)
        
        # 模拟返回
        return {
            "task_id": task_id,
            "page": page,
            "page_size": page_size,
            "total": 1000,
            "data": [
                {"id": i, "title": f"Result {i}", "url": f"https://example.com/{i}"}
                for i in range((page-1)*page_size, min(page*page_size, 1000))
            ]
        }
        
    except Exception as e:
        logger.error(f"获取结果失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_public_stats():
    """
    获取系统公开统计信息
    """
    return {
        "total_tasks_today": 156,
        "completed_tasks": 142,
        "failed_tasks": 14,
        "avg_completion_time_seconds": 45,
        "active_spiders": 8
    }
