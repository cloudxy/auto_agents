"""爬虫相关接口"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class SpiderTask(BaseModel):
    spider_name: str
    params: Optional[dict] = None

@router.post("/run")
async def run_spider(task: SpiderTask):
    """运行爬虫任务"""
    return {"message": f"Spider {task.spider_name} started", "task_id": "todo"}

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    return {"task_id": task_id, "status": "pending"}
