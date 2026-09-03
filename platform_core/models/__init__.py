"""ORM 数据模型 —— 声明式 Base + 所有业务表

约定（红线）：
- 只定义结构，不操作 Session
- 禁止 import Pydantic schema
- 所有业务模型继承 platform_core.models.base.Base
"""
from platform_core.models.base import Base
from platform_core.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin
from platform_core.models.tenant import Tenant
from platform_core.models.capability import (
    CapabilityAsset, CapabilityExpert, CapabilityPlugin, CapabilityTeam,
)
from platform_core.models.spider_task import SpiderTask
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_schedule import SpiderSchedule
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.user import User
from platform_core.models.operation_log import OperationLog
from platform_core.models.system_config import SystemConfig
from platform_core.models.alert_rule import AlertRule
from platform_core.models.task_template import TaskTemplate
from platform_core.models.ai_plan import AiPlan
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.channel_event import ChannelEvent
from platform_core.models.channel_probe_result import ChannelProbeResult
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.skill import Skill, SkillJob, SkillReview
from platform_core.models.llm_provider_model import LlmProviderModel
from platform_core.models.tag import Tag, Tagging
from platform_core.models.attachment import Attachment
from platform_core.models.notification import Notification
from platform_core.models.resource_version import ResourceVersion
from platform_core.models.workflow import (
    WorkflowDefinition, WorkflowInstance, WorkflowStep, WorkflowTransition,
)
from platform_core.models.archive import ArchiveRecord
from platform_core.models.i18n import I18nLocale, I18nTranslation
from platform_core.models.system_cache import SystemCache
from platform_core.models.role import Role
from platform_core.models.department import Department
from platform_core.models.menu import Menu
from platform_core.models.permission import Permission

__all__ = [
    "Base", "SpiderTask", "SpiderResult", "SpiderSchedule", "SpiderDefinition",
    "User", "OperationLog", "SystemConfig", "AlertRule", "TaskTemplate", "AiPlan",
    "LlmProvider", "ChannelEvent", "ChannelProbeResult", "LlmTokenUsage",
    "Skill", "SkillReview", "SkillJob", "LlmProviderModel", "Tenant", "TenantMixin", "CapabilityAsset", "CapabilityPlugin",
    "CapabilityExpert", "CapabilityTeam", "SoftDeleteMixin", "AuditMixin",
    # DB 升级 2026-09 Phase B/C 横切功能表
    "Tag", "Tagging", "Attachment", "Notification", "ResourceVersion",
    "WorkflowDefinition", "WorkflowInstance", "WorkflowStep", "WorkflowTransition",
    "ArchiveRecord", "I18nLocale", "I18nTranslation", "SystemCache",
    "Role", "Department", "Menu", "Permission",
]
