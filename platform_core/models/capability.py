"""能力资产域模型（P6：capability hub）

统一目录层（capability_assets）+ 类型化细节表（plugin/expert/team）。
skills 三表保留为 skill 类型细节（D10），治理字段经 asset 层收口。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import AuditMixin, SoftDeleteMixin

ASSET_TYPES = ("skill", "plugin", "expert", "expert_team")


class CapabilityAsset(SoftDeleteMixin, AuditMixin, Base):
    """统一资产目录（治理真相源，四类共用；平台级公共资产 tenant_id 恒 NULL）"""

    __tablename__ = "capability_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_type = Column(String(16), nullable=False, index=True,
                        comment="skill/plugin/expert/expert_team")
    name = Column(String(128), nullable=False, comment="目录名（类型内唯一）")
    title = Column(String(256), default="")
    description = Column(String(1024))
    category = Column(String(64), nullable=False, default="uncategorized", index=True)
    status = Column(String(16), nullable=False, default="experimental", index=True,
                    comment="experimental/testing/stable/recommended/deprecated/blacklist")
    source_type = Column(String(16), nullable=False, default="self_built")
    source_url = Column(String(512), default="")
    source_author = Column(String(128), default="")
    content_hash = Column(String(64), default="")
    score = Column(Numeric(3, 1))
    ai_suggested_score = Column(Numeric(3, 1))
    tier = Column(String(2))
    reviewed_by = Column(String(64))
    reviewed_at = Column(DateTime)
    similar_to = Column(JSON)
    file_path = Column(String(512))
    sync_state = Column(String(16), nullable=False, default="ok")
    tenant_id = Column(Integer, comment="平台级恒 NULL（豁免白名单）")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    # 细节表外键（skill 类型关联 skills.id）
    detail_id = Column(Integer, comment="类型化细节表行 id")
    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("asset_type", "name", name="uq_asset_type_name"),
    )


class CapabilityPlugin(Base):
    """插件细节（plugin.json 解析产物；hooks/commands 只登记不执行）"""

    __tablename__ = "capability_plugins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("capability_assets.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    version = Column(String(32), default="")
    author = Column(String(128), default="")
    license = Column(String(64), default="")
    manifest = Column(JSON, comment="plugin.json 原文")
    bundled_skills = Column(JSON, comment="内嵌技能名数组")
    mcp_servers = Column(JSON, comment="MCP servers 配置（登记）")
    hooks = Column(JSON, comment="hooks 配置（登记不执行）")
    commands = Column(JSON, comment="commands 配置（登记不执行）")
    health_status = Column(String(16), nullable=False, default="unknown",
                           comment="unknown/healthy/degraded/down")
    last_verified_at = Column(DateTime)
    verify_detail = Column(JSON, comment="验证管线结果")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CapabilityExpert(Base):
    """专家细节（subagent canonical：frontmatter tools + 正文 system prompt）"""

    __tablename__ = "capability_experts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("capability_assets.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    persona_md = Column(Text, comment="正文 = system prompt")
    tools = Column(JSON, comment="frontmatter tools 数组")
    bundled_skills = Column(JSON, comment="捆绑技能资产名")
    mcp_refs = Column(JSON, comment="引用的 MCP（插件名或 server 名）")
    model_pref = Column(String(64), comment="偏好模型（可选）")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CapabilityTeam(Base):
    """专家团定义（一期无执行态）"""

    __tablename__ = "capability_teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("capability_assets.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    leader_expert = Column(String(128), comment="团长专家资产名")
    members = Column(JSON, comment="成员专家资产名数组")
    workflow_md = Column(Text, comment="协作流程描述")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
