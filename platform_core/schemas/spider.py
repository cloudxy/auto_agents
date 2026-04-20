"""爬虫任务 Schema —— API 层与 Service 层之间的数据契约"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from platform_core.schemas.base import QueryParams, RequestBody


class SpiderTaskResponse(BaseModel):
    """单条爬虫任务的对外响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    spider_name: str
    status: str
    result_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SpiderTaskListResponse(BaseModel):
    """分页列表响应"""
    total: int
    items: List[SpiderTaskResponse]


class SpiderTaskQuery(QueryParams):
    """任务列表查询参数"""
    skip: int = Field(0, ge=0, description="偏移")
    limit: int = Field(20, ge=1, le=100, description="每页大小")
    status: Optional[str] = Field(None, description="按状态过滤：pending/running/completed/failed")


class RunSpiderRequest(RequestBody):
    """触发一次爬虫任务"""
    spider_name: str = Field(..., min_length=1, max_length=100)
    params: Optional[str] = Field(None, description="透传给爬虫的 JSON 字符串")


class SpiderStatsResponse(BaseModel):
    """爬虫维度的统计数据"""
    total_tasks: int
    pending: int
    running: int
    completed: int
    failed: int
