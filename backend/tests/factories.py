"""测试模型工厂（E0.1b 工单 02）：高频模型的一行构造 builder

约定：
- 默认值满足列约束可直接 flush；唯一键（username/email/name）默认值带自增序号，
  连续多次默认调用互不冲突；
- overrides 覆盖任意列（setattr），用于定向定制测试场景；
- 不引入新依赖（区别于 factory_boy），保持零新依赖原则。
"""
import itertools
from typing import Any, TypeVar

from platform_core.models.base import Base
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.models.user import User

_seq = itertools.count(1)

M = TypeVar("M", bound=Base)


def _apply(model: M, overrides: dict[str, Any]) -> M:
    """应用字段覆盖（未知列名由 SQLAlchemy flush 阶段暴露）"""
    for key, value in overrides.items():
        setattr(model, key, value)
    return model


def build_user(**overrides: Any) -> User:
    """最小可入库用户（viewer，激活）

    T5 后 users.tenant_id NOT NULL：默认归属 id=1 租户（无 FK 强制，测试库
    无需预建租户行；需要租户语义的用例经 overrides 显式覆盖）。
    """
    n = next(_seq)
    return _apply(
        User(
            username=f"user-{n}",
            email=f"user-{n}@test.local",
            password_hash="not-a-real-hash",
            role="viewer",
            is_active=True,
            tenant_id=1,
        ),
        overrides,
    )


def build_spider_task(**overrides: Any) -> SpiderTask:
    """最小可入库爬虫任务（pending/normal 优先级）"""
    n = next(_seq)
    return _apply(
        SpiderTask(
            spider_name=f"spider-{n}",
            status="pending",
            priority="normal",
            params="{}",
        ),
        overrides,
    )


def build_llm_provider(**overrides: Any) -> LlmProvider:
    """最小可入库 LLM 供应商（openai_compatible，未激活；api_key 留空=走兜底路径）"""
    n = next(_seq)
    return _apply(
        LlmProvider(
            name=f"provider-{n}",
            provider_type="openai_compatible",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        ),
        overrides,
    )


def build_spider_definition(**overrides: Any) -> SpiderDefinition:
    """最小可入库爬虫定义（web 类型，手动登记来源）"""
    n = next(_seq)
    return _apply(
        SpiderDefinition(
            name=f"demo_spider_{n}",
            title=f"演示爬虫 {n}",
            type="web",
            source="manual",
        ),
        overrides,
    )
