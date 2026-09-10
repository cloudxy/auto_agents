"""LiteLLM 值班面：模型 / 部署 / spend / budget HTTP（httpx）。

仅管理 HTTP。backend 不持网关库连接。值班/探针（T-18/T-19）只 import 本模块，不走 chat。
"""
from typing import Any, Optional

import httpx

from backend.services.llm_gateway._settings import _http_json
from platform_core.logger import get_logger

logger = get_logger("api")


async def list_models(
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM GET /model/info")
    return await _http_json("GET", "/model/info", transport=transport)


async def list_deployments(
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM GET /v2/model/info")
    return await _http_json("GET", "/v2/model/info", transport=transport)


async def get_spend_logs(
    params: Optional[dict[str, Any]] = None,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM GET /spend/logs")
    return await _http_json("GET", "/spend/logs", params=params, transport=transport)


async def get_global_spend(
    params: Optional[dict[str, Any]] = None,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM GET /global/spend")
    return await _http_json("GET", "/global/spend", params=params, transport=transport)


async def list_budgets(
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM GET /budget/list")
    return await _http_json("GET", "/budget/list", transport=transport)


async def create_budget(
    body: dict[str, Any],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM POST /budget/new")
    return await _http_json("POST", "/budget/new", json_body=body, transport=transport)


async def get_budget_info(
    budget_id: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM GET /budget/info")
    return await _http_json(
        "GET", "/budget/info", params={"budget_id": budget_id}, transport=transport,
    )


async def update_budget(
    body: dict[str, Any],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM POST /budget/update")
    return await _http_json("POST", "/budget/update", json_body=body, transport=transport)


async def create_model(
    body: dict[str, Any],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM POST /model/new")
    return await _http_json("POST", "/model/new", json_body=body, transport=transport)


async def update_model(
    body: dict[str, Any],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    logger.info("LiteLLM POST /model/update")
    return await _http_json("POST", "/model/update", json_body=body, transport=transport)
