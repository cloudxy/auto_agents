"""ORM 数据模型 —— 声明式 Base + 所有业务表

约定（红线）：
- 只定义结构，不操作 Session
- 禁止 import Pydantic schema
- 所有业务模型继承 platform_core.models.base.Base
"""
from platform_core.models.base import Base
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

__all__ = [
    "Base", "SpiderTask", "SpiderResult", "SpiderSchedule", "SpiderDefinition",
    "User", "OperationLog", "SystemConfig", "AlertRule", "TaskTemplate", "AiPlan",
    "LlmProvider", "ChannelEvent", "ChannelProbeResult", "LlmTokenUsage",
    "Skill", "SkillReview", "SkillJob",
]
