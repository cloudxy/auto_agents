"""AI 采集规划包（期4 结构治理：原 ai_planner_service.py 六职责拆分；T6 解环修订）

模块边界（依赖只向包内/向下单向，包内模块互不经 import 引用）：
- llm_client.py    LLM 客户端缓存 / 运行时配置解析入口 / chat completions / token 预算
- url_guard.py     SSRF 防护（M6）/ HTML 清洗 / 目标页单页抓取
- prompting.py     Prompt 构造 / LLM 响应解析 / 参数组装 / 注册命名推导（纯函数）
- state.py         后台任务启动 / 试采终态快照 / 失败兜底 / 启动对账
- orchestrator.py  AiPlannerService（规划/试采/修复/注册状态机 + CRUD）

T6 解环后的两条硬约束：
1. 包内模块对可 patch 的可变依赖（settings / _TOKEN_USAGE /
   _resolve_llm_runtime_config / _resolve_host_ips / _read_task_snapshot /
   SpiderService / SpiderDefinitionRepository / _spawn / get_manager /
   AsyncSession / AiPlanRepository / httpx.AsyncClient）以及跨模块符号
   一律经 llm_common.seam() 调用期取值（存量单测 patch
   backend.services.ai_planner_service.<name> 的晚绑定语义不变）；
   包内模块禁止 import 门面 ai_planner_service（无文件末尾反向 import）。
2. LLM 运行时配置形状与解析（LlmRuntimeConfig / resolve_config_from_settings）
   下沉至 backend.services.llm_common（叶子），本包与 llm_provider_service
   均单向依赖之；本包不再回引 llm_provider_service。
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
)
from backend.services.llm_common import (  # noqa: F401 — 下沉层 re-export（T6）
    LlmRuntimeConfig,
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
# 再拉外部依赖；均为向下/无环依赖）。
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
    "llm_chat",
    # llm_common（T6 下沉层 re-export）
    "LlmRuntimeConfig", "resolve_config_from_settings",
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
    "SpiderService",
]
