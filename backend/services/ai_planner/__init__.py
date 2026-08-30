"""AI 采集规划包（期4 结构治理：原 ai_planner_service.py 六职责拆分）

模块边界（依赖只向包内单向，跨模块可变引用统一经门面查找）：
- llm_client.py    LLM 客户端缓存 / 运行时配置解析 / chat completions / token 预算
- url_guard.py     SSRF 防护（M6）/ HTML 清洗 / 目标页单页抓取
- prompting.py     Prompt 构造 / LLM 响应解析 / 参数组装 / 注册命名推导（纯函数）
- state.py         后台任务启动 / 试采终态快照 / 失败兜底 / 启动对账
- orchestrator.py  AiPlannerService（规划/试采/修复/注册状态机 + CRUD）

Patch 兼容（_facade 模式）：历史路径 backend.services.ai_planner_service 保留为
薄 shim（本包符号的 re-export）；存量单测 patch("backend.services.ai_planner_service.
<name>") 的目标是门面命名空间，因此包内模块对可 patch 符号（settings / _TOKEN_USAGE /
_resolve_llm_runtime_config / _resolve_host_ips / _read_task_snapshot / SpiderService /
SpiderDefinitionRepository / _spawn / get_manager / AsyncSession / AiPlanRepository /
httpx.AsyncClient）一律经门面模块属性查找——各子模块文件末行
`import backend.services.ai_planner_service as _facade`（sys.modules 绑定部分初始化
的门面，Python 3.7+ 语义；置于末尾保证 shim ↔ 包双向初始化入口均安全）。
"""
from backend.services.ai_planner.llm_client import (
    _CLIENT_CONNECT_TIMEOUT,
    _CLIENT_KEEPALIVE_EXPIRY,
    _CLIENT_MAX_CONNECTIONS,
    _CLIENT_MAX_KEEPALIVE_CONNECTIONS,
    _RETRY_BASE_DELAY,
    _TOKEN_USAGE,
    _client_cache_key,
    _HTTP_CLIENTS,
    _HTTP_CLIENT_OWNER,
    _resolve_llm_runtime_config,
    get_shared_client,
    invalidate_client_cache,
    llm_chat,
    resolve_config_from_settings,
)
from backend.services.ai_planner.url_guard import (
    _ALLOWED_PORTS,
    _BLOCKED_V4_NETS,
    _BLOCKED_V6_NETS,
    _FETCH_TIMEOUT,
    _HTML_COMMENT,
    _MAX_HTML_CHARS,
    _MAX_REDIRECT_HOPS,
    _MULTI_NEWLINE,
    _SCRIPT_BLOCK,
    _SPIDER_UA,
    _TAB_SPACES,
    _assert_public_url,
    _clean_html_sync,
    _fetch_html,
    _is_blocked_ip,
    _resolve_host_ips,
)
from backend.services.ai_planner.prompting import (
    _CONSTRAINTS,
    _MD_FENCE,
    _PLAN_SYSTEM_PROMPT,
    _SCHEMA_HINT,
    _build_generated_params,
    _build_plan_messages,
    _build_repair_messages,
    _derive_spider_name,
    _domain_of,
    _parse_llm_json,
)
from backend.services.ai_planner.state import (
    _BACKGROUND_TASKS,
    _BUSY_STATUSES,
    _WAIT_INTERVAL_SECONDS,
    _WAIT_TIMEOUT_SECONDS,
    _TaskSnapshot,
    _force_fail_status,
    _read_task_snapshot,
    _run_plan_bg,
    _run_test_bg,
    _spawn,
    reconcile_interrupted_plans,
)
from backend.services.ai_planner.orchestrator import AiPlannerService

# ----------------------------------------------------------------------
# 旧单文件命名空间的依赖绑定（兼容层）：存量单测 patch 目标 + 历史路径
# from-import 的第三方符号。置于子模块 re-export 之后（包自身初始化完成后
# 再拉外部依赖，避免潜在的包外反向依赖被拖入初始化环）。
# ----------------------------------------------------------------------
import asyncio  # noqa: F401
import hashlib  # noqa: F401
import httpx  # noqa: F401
import ipaddress  # noqa: F401
import json  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import socket  # noqa: F401
import time  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from urllib.parse import urljoin, urlparse  # noqa: F401

from pydantic import ValidationError  # noqa: F401
from sqlalchemy import select, update  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from config import settings  # noqa: F401
from platform_core.db import get_manager  # noqa: F401
from platform_core.exceptions import BusinessException, NotFoundException  # noqa: F401
from platform_core.logger import get_logger  # noqa: F401
from platform_core.models.ai_plan import AiPlan  # noqa: F401
from platform_core.models.spider_task import SpiderTask  # noqa: F401
from platform_core.schemas.ai_plan import (  # noqa: F401
    AiPlanCreate,
    AiPlanListResponse,
    AiPlanResponse,
    FlowConfig,
)
from platform_core.schemas.spider import DefinitionCreateRequest  # noqa: F401
from backend.repositories.ai_plan_repository import AiPlanRepository  # noqa: F401
from backend.repositories.spider_definition_repository import (  # noqa: F401
    SpiderDefinitionRepository,
)
from backend.services.llm_provider_service import (  # noqa: F401
    LlmProviderService,
    LlmRuntimeConfig,
)
from backend.services.spider_service import SpiderService  # noqa: F401

logger = get_logger("api")  # noqa: F401  兼容旧命名空间 logger 绑定

__all__ = [
    # orchestrator
    "AiPlannerService",
    # llm_client
    "_CLIENT_CONNECT_TIMEOUT", "_CLIENT_KEEPALIVE_EXPIRY", "_CLIENT_MAX_CONNECTIONS",
    "_CLIENT_MAX_KEEPALIVE_CONNECTIONS", "_RETRY_BASE_DELAY", "_TOKEN_USAGE",
    "_HTTP_CLIENTS", "_HTTP_CLIENT_OWNER", "_client_cache_key",
    "_resolve_llm_runtime_config", "get_shared_client", "invalidate_client_cache",
    "llm_chat", "resolve_config_from_settings",
    # url_guard
    "_ALLOWED_PORTS", "_BLOCKED_V4_NETS", "_BLOCKED_V6_NETS", "_FETCH_TIMEOUT",
    "_HTML_COMMENT", "_MAX_HTML_CHARS", "_MAX_REDIRECT_HOPS", "_MULTI_NEWLINE",
    "_SCRIPT_BLOCK", "_SPIDER_UA", "_TAB_SPACES", "_assert_public_url",
    "_clean_html_sync", "_fetch_html", "_is_blocked_ip", "_resolve_host_ips",
    # prompting
    "_CONSTRAINTS", "_MD_FENCE", "_PLAN_SYSTEM_PROMPT", "_SCHEMA_HINT",
    "_build_generated_params", "_build_plan_messages", "_build_repair_messages",
    "_derive_spider_name", "_domain_of", "_parse_llm_json",
    # state
    "_BACKGROUND_TASKS", "_BUSY_STATUSES", "_WAIT_INTERVAL_SECONDS",
    "_WAIT_TIMEOUT_SECONDS", "_TaskSnapshot", "_force_fail_status",
    "_read_task_snapshot", "_run_plan_bg", "_run_test_bg", "_spawn",
    "reconcile_interrupted_plans",
    # 兼容绑定（旧命名空间第三方符号）
    "asyncio", "hashlib", "httpx", "ipaddress", "json", "os", "re", "socket",
    "time", "dataclass", "urljoin", "urlparse", "ValidationError", "select",
    "update", "AsyncSession", "settings", "get_manager", "BusinessException",
    "NotFoundException", "get_logger", "logger", "AiPlan", "SpiderTask",
    "AiPlanCreate", "AiPlanListResponse", "AiPlanResponse", "FlowConfig",
    "DefinitionCreateRequest", "AiPlanRepository", "SpiderDefinitionRepository",
    "LlmProviderService", "LlmRuntimeConfig", "SpiderService",
]
