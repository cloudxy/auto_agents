"""技能域 Pydantic Schema（方案 A）——与 ORM 模型配对且互不 import（模型即契约红线）

状态映射（总方案 3.2-A-4）：存量 active→testing、experimental→experimental、deprecated→deprecated。
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from platform_core.schemas.base import PaginationQuery

SKILL_STATUSES = ("experimental", "testing", "stable", "recommended", "deprecated", "blacklist")
SKILL_SOURCE_TYPES = ("self_built", "network_imported", "marketplace_crawled")


class SkillQuery(PaginationQuery):
    """技能列表查询参数"""

    q: Optional[str] = Field(None, max_length=100, description="name/title/description 模糊")
    category: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, max_length=16)
    tier: Optional[str] = Field(None, max_length=2, pattern=r"^[SABC]$")
    source_type: Optional[str] = Field(None, max_length=16)
    industry: Optional[str] = Field(None, max_length=64, description="行业标签过滤")
    sort: str = Field("updated_at", pattern=r"^(score|tier|updated_at|name)$")


class SkillReviewResponse(BaseModel):
    """评分历史条目"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reviewer_type: str
    reviewer: str
    score: Optional[float] = None
    rubric: Optional[dict] = None
    notes: Optional[str] = None
    content_hash: Optional[str] = None
    prompt_version: Optional[str] = None
    created_at: Optional[datetime] = None


class SkillResponse(BaseModel):
    """技能列表条目（治理字段投影）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str = ""
    description: Optional[str] = None
    category: str
    industries: Optional[List[str]] = None
    status: str
    source_type: str
    source_url: str = ""
    source_author: str = ""
    imported_at: Optional[datetime] = None
    score: Optional[float] = None
    ai_suggested_score: Optional[float] = None
    tier: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    similar_to: Optional[List[str]] = None
    sync_state: str = "ok"
    updated_at: Optional[datetime] = None


class SkillDetailResponse(SkillResponse):
    """技能详情（追加内部治理字段与文件镜像，仅管理端）"""

    rubric_human: Optional[dict] = None
    rubric_ai: Optional[dict] = None
    review_notes: Optional[str] = None
    content_hash: str = ""
    file_path: str = ""
    raw_meta: Optional[dict] = None
    skill_md: Optional[str] = None
    meta_yaml: Optional[str] = None
    reviews: List[SkillReviewResponse] = Field(default_factory=list)


class SkillListResponse(BaseModel):
    """技能列表信封（对齐 UserListResponse 形态）"""

    total: int
    items: List[SkillResponse]


class SkillJobResponse(BaseModel):
    """任务运行记录"""

    id: int
    job_type: str
    status: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    detail: Optional[dict] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class SkillScoringRationale(BaseModel):
    """AI 评分每维一句话理由（四维必填）"""

    completeness: str = Field(..., min_length=1)
    doc_quality: str = Field(..., min_length=1)
    maintenance: str = Field(..., min_length=1)
    real_world_effect: str = Field(..., min_length=1)


class SkillScoringResult(BaseModel):
    """AI 评分结果契约（A-P2-1）：LLM 输出入口校验——非法结构在落库前即拒

    维度 1-10 整数；rationale 每维必填（拒绝"只给分不讲理由"的退化输出）。
    期望样例见 tests/test_skill_scoring_plumbing.py 的 VALID_SAMPLE（独立事实源）。
    """

    completeness: int = Field(..., ge=1, le=10)
    doc_quality: int = Field(..., ge=1, le=10)
    maintenance: int = Field(..., ge=1, le=10)
    real_world_effect: int = Field(..., ge=1, le=10)
    overall: int = Field(..., ge=1, le=10)
    rationale: SkillScoringRationale
    notes: str = Field("", max_length=2000)
