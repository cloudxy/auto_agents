"""技能域模型（方案 A：技能管理中心）

三表职责（总方案 §5.1）：
- Skill          治理真相源 + 文件镜像索引（内容真相源在 skills-library/skills/<name>/ 文件）
- SkillReview    AI 与人工评审全留痕（矫正可追溯；AI 永不写人工权威分）
- SkillJob       扫描/评分批/导入 运行记录（轻量观测，不做通用 job 框架）

tenant_id 预留恒 NULL（D3：平台级统一技能库，进 S1 豁免白名单）。
"""
from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func

from platform_core.models.base import Base


class Skill(Base):
    """技能主表（治理真相源）"""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(128), nullable=False, unique=True, index=True, comment="目录名，全局唯一（唯一取值源）")
    title = Column(String(256), default="", comment="SKILL.md frontmatter 显示名")
    description = Column(Text, comment="frontmatter description")
    category = Column(String(64), nullable=False, default="uncategorized", index=True,
                      comment="一级分类（受控枚举）")
    industries = Column(JSON, comment='行业标签数组，对齐 taxonomy/industries.yaml')
    status = Column(String(16), nullable=False, default="experimental", index=True,
                    comment="experimental/testing/stable/recommended/deprecated/blacklist")
    source_type = Column(String(16), nullable=False, default="self_built",
                         comment="self_built/network_imported/marketplace_crawled")
    source_url = Column(String(512), default="", comment="来源地址")
    source_author = Column(String(128), default="", comment="来源作者")
    imported_at = Column(DateTime, comment="导入时间")
    content_hash = Column(String(64), default="", comment="目录内容 sha256，变更检测锚点")
    score = Column(Numeric(3, 1), comment="人工终评综合分（NULL=未复核；AI 永不写）")
    ai_suggested_score = Column(Numeric(3, 1), comment="AI 建议分（仅参考）")
    rubric_human = Column(JSON, comment="人工四维评分 {completeness,doc_quality,maintenance,real_world_effect}")
    rubric_ai = Column(JSON, comment="AI 四维评分")
    tier = Column(String(2), comment="派生列：S/A/B/C（人工分优先，缺省按 AI 分）")
    reviewed_by = Column(String(64), comment="终评人")
    reviewed_at = Column(DateTime, comment="终评时间")
    review_notes = Column(Text, comment="终评笔记")
    similar_to = Column(JSON, comment="同类技能 name 数组（已确认）")
    file_path = Column(String(512), nullable=False, comment="skills-library 内相对路径")
    sync_state = Column(String(16), nullable=False, default="ok",
                        comment="ok/hash_changed/missing/parse_error")
    tenant_id = Column(Integer, comment="D3 预留：平台级恒 NULL")
    raw_meta = Column(JSON, comment="meta.yaml 原文快照（导出对账用）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class SkillReview(Base):
    """评分历史（AI 与人工评审全留痕）"""

    __tablename__ = "skill_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    skill_id = Column(Integer, nullable=False, index=True, comment="技能 ID")
    reviewer_type = Column(String(8), nullable=False, comment="ai/human")
    reviewer = Column(String(64), nullable=False, comment="模型名 / 用户名")
    score = Column(Numeric(3, 1), comment="综合分")
    rubric = Column(JSON, comment="四维评分")
    notes = Column(Text, comment="AI 评语（各维理由）/ 人工笔记")
    content_hash = Column(String(64), comment="评的是哪个版本")
    prompt_version = Column(String(8), comment="AI 评审时的 prompt 版本")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")


class SkillJob(Base):
    """任务运行记录（scan/score_batch/export_meta/import）"""

    __tablename__ = "skill_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    job_type = Column(String(16), nullable=False, comment="scan/score_batch/export_meta/import")
    status = Column(String(16), nullable=False, comment="running/done/failed")
    total = Column(Integer, default=0, comment="总数")
    succeeded = Column(Integer, default=0, comment="成功数")
    failed = Column(Integer, default=0, comment="失败数")
    detail = Column(JSON, comment="失败清单等")
    started_at = Column(DateTime, server_default=func.now(), comment="开始时间")
    finished_at = Column(DateTime, comment="结束时间")
