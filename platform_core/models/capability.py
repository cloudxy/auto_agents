"""能力资产域模型（P6：capability hub）

统一目录层（capability_assets）+ 类型化细节表（plugin/expert/team）。
skills 三表保留为 skill 类型细节（D10），治理字段经 asset 层收口。
"""
from sqlalchemy import (
    Column, Computed, DateTime, ForeignKey, Index, Integer, Numeric,
    SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME, JSON
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin

# 公开五类 skill/plugin/command/agent/team；expert/expert_team 一周期可读。
# 公开 JSON 只出新五类（power_market.types）。不改 uq_asset_type_name_alive。
ASSET_TYPES = (
    "skill", "plugin", "command", "agent", "team", "expert", "expert_team",
)


class CapabilityAsset(SoftDeleteMixin, AuditMixin, Base):
    """统一资产目录（治理真相源，五类共用；平台级公共资产 tenant_id 恒 NULL）

    唯一键含生成列 alive_flag（迁移 025）：软删行脱离唯一约束，删后 harvester
    周期扫描可重建同名资产（content_hash 判重走内容维度，不受影响）。
    """

    __tablename__ = "capability_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_type = Column(String(16), nullable=False, index=True,
                        comment="skill/plugin/command/agent/team + 一周期 expert/expert_team")
    name = Column(String(128), nullable=False, comment="目录名（类型内唯一）")
    title = Column(String(256), default="")
    description = Column(String(1024))
    category = Column(String(64), nullable=False, default="uncategorized", index=True)
    status = Column(String(16), nullable=False, default="experimental", index=True,
                    comment="experimental/testing/stable/recommended/deprecated/blacklist")
    source_type = Column(String(32), nullable=False, default="self_built")
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
    alive_flag = Column(SmallInteger, Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
                        comment="存活标记（生成列，025）：唯一键组件，软删行 NULL 脱离唯一约束")
    listing_state = Column(
        String(16), nullable=False, default="unlisted", server_default="unlisted",
        comment="unlisted/listed/coming_soon；与 status / 许可 / 黑名单独立",
    )
    license = Column(String(64), nullable=True, comment="同步拷贝的许可标识（现在）。NULL=未声明")
    public_license_override = Column(
        SmallInteger, nullable=False, default=0, server_default="0",
        comment="超管特例放行（现在）。0=未放行",
    )
    host_compat = Column(
        JSON, nullable=True,
        comment="NULL=四宿主可订；[]=都不可订；非空数组=仅名单",
    )
    listed_at = Column(
        MYSQL_DATETIME(fsp=6), nullable=True,
        comment="最近一次 listed；unlist 不清空；NULL=从未 listed",
    )
    source_id = Column(
        Integer, ForeignKey("capability_sources.id", ondelete="RESTRICT"),
        nullable=True, comment="NULL=尚未 attach 源（第一方窗口）",
    )
    origin_ref = Column(String(256), nullable=True, comment="源内路径。NULL=无源路径")
    origin_local_name = Column(String(128), nullable=True, comment="插件内短名")
    origin_plugin_name = Column(
        String(128), nullable=True, comment="父插件目录名；第一方无父插件则 NULL",
    )
    alias_origin_refs = Column(JSON, nullable=True, comment="被折叠的路径集，非查询列")
    writable = Column(
        SmallInteger, nullable=False, default=1, server_default="1",
        comment="1=第一方可写库+源树；0=第三方。attach 源时改 0",
    )
    __table_args__ = (
        UniqueConstraint("asset_type", "name", "alive_flag", name="uq_asset_type_name_alive"),
        Index(
            "idx_assets_listing_status_type_cat",
            "listing_state", "status", "asset_type", "category",
        ),
        Index(
            "idx_assets_source_origin_alive",
            "source_id", "origin_ref", "alive_flag",
        ),
    )


class CapabilityPlugin(Base):
    """插件细节（plugin.json 解析产物；hooks/commands 只登记不执行）"""

    __tablename__ = "capability_plugins"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_capability_plugins_asset"),
    )

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
    """智能体人设细节（表名 capability_experts 不 rename）"""

    __tablename__ = "capability_experts"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_capability_experts_asset"),
    )

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
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_capability_teams_asset"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("capability_assets.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    leader_expert = Column(String(128), comment="团长专家资产名")
    members = Column(JSON, comment="成员专家资产名数组")
    workflow_md = Column(Text, comment="协作流程描述")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CapabilityCommand(Base):
    """slash 命令细节（catalog 行 asset_type=command 的 1:1；T-21 豁免）。"""

    __tablename__ = "capability_commands"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_commands_asset"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(
        Integer, ForeignKey("capability_assets.id", ondelete="CASCADE"), nullable=False,
    )
    slash = Column(String(64), nullable=False, comment="非全局唯一")
    description = Column(String(512), nullable=True)
    body_md = Column(Text, nullable=True, comment="命令正文；本表即侧表")
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())


class CapabilityComponent(Base):
    """出处/引用边（不是安装礼包；T-21 豁免）。"""

    __tablename__ = "capability_components"
    __table_args__ = (
        UniqueConstraint("parent_asset_id", "child_asset_id", name="uq_components_parent_child"),
        Index("idx_components_child", "child_asset_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_asset_id = Column(
        Integer, ForeignKey("capability_assets.id", ondelete="RESTRICT"), nullable=False,
    )
    child_asset_id = Column(
        Integer, ForeignKey("capability_assets.id", ondelete="RESTRICT"), nullable=False,
    )
    role = Column(String(32), nullable=False, comment="bundled_skill/command/agent|uses_skill|team_member")
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())


class CapabilityInstall(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    """一企业 × 一资产 × 一宿主。禁止进 TENANT_EXEMPT_TABLES。"""

    __tablename__ = "capability_installs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "asset_id", "host", "alive_flag",
            name="uq_installs_tenant_asset_host_alive",
        ),
        Index("idx_installs_asset", "asset_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
        comment="隔离列；迁移层 NOT NULL；禁止豁免",
    )
    asset_id = Column(
        Integer, ForeignKey("capability_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    host = Column(String(16), nullable=False, comment="grok/zcode/kimi/claude")
    enabled = Column(
        SmallInteger, nullable=False, default=1, server_default="1",
        comment="我的安装开关；不是 enable-host",
    )
    trusted = Column(
        SmallInteger, nullable=False, default=0, server_default="0",
    )
    alive_flag = Column(
        SmallInteger,
        Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
        comment="存活标记（生成列）：唯一键组件，软删行 NULL 脱离唯一约束",
    )
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
        comment="订阅成功时刻",
    )
    updated_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )


class CapabilitySource(SoftDeleteMixin, AuditMixin, Base):
    """已登记外部树（平台级；tenant_id 恒 NULL）。同步不得 listed。"""

    __tablename__ = "capability_sources"
    __table_args__ = (
        UniqueConstraint("name", "alive_flag", name="uq_sources_name_alive"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, comment="源稳定名；存活唯一")
    source_kind = Column(String(16), nullable=False, comment="local/git/url；禁止列名 type")
    uri = Column(String(512), nullable=False, comment="本地路径或 git URL")
    is_enabled = Column(SmallInteger, nullable=False, default=1, server_default="1")
    last_sync_at = Column(DateTime, nullable=True, comment="NULL=从未同步成功结束")
    last_succeeded = Column(Integer, nullable=False, default=0, server_default="0")
    last_failed = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(String(512), nullable=True)
    tenant_id = Column(Integer, comment="平台级恒 NULL")
    alive_flag = Column(
        SmallInteger,
        Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
        comment="存活标记（生成列）：唯一键组件",
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CapabilityAlias(SoftDeleteMixin, AuditMixin, Base):
    """人工短名。平台级 tenant_id 恒 NULL。禁止 TenantMixin。同步不建。"""

    __tablename__ = "capability_aliases"
    __table_args__ = (
        UniqueConstraint("slug", "alive_flag", name="uq_aliases_slug_alive"),
        UniqueConstraint("asset_id", "alive_flag", name="uq_aliases_asset_alive"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(128), nullable=False, comment="人工短名；存活全局唯一")
    asset_id = Column(
        Integer, ForeignKey("capability_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_type = Column(
        String(16), nullable=False, comment="反规范化，公开路由第一段；D22b 回填须同步",
    )
    tenant_id = Column(Integer, comment="平台级恒 NULL")
    alive_flag = Column(
        SmallInteger,
        Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
        comment="存活标记（生成列）：唯一键组件",
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(),
    )

