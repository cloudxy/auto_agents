"""LiteLLM 值班面：模型 / 部署 / spend / budget / Key 管理 HTTP（httpx）。

仅管理 HTTP。backend 不持网关库连接。值班/探针（T-18/T-19）只 import 本模块，不走 chat。
渠道组令牌（ADR-0019，T-08）经 generate_key/delete_key 登记与作废虚拟 Key。
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


async def generate_key(
    body: dict[str, Any],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    """POST /key/generate：登记虚拟 Key（ADR-0019 渠道组令牌）。

    响应含明文 key——只由签发路径回传一次，调用方禁止落库/入日志。
    """
    logger.info("LiteLLM POST /key/generate")
    return await _http_json("POST", "/key/generate", json_body=body, transport=transport)


async def delete_key(
    body: dict[str, Any],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    """POST /key/delete：作废虚拟 Key（吊销路径）。

    v1.100.0 KeyRequest 只收 keys / key_aliases；明文不落库 → 按 key_aliases
    引用作废（OpenAPI 实读核对，ADR-0019）。
    """
    logger.info("LiteLLM POST /key/delete")
    return await _http_json("POST", "/key/delete", json_body=body, transport=transport)


async def get_key_info(
    key: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    """GET /key/info：单 Key 行（用量观察点之一，ADR-0019 决策 3 / T-09）。

    v1.100.0 实读：query 参数 ``key`` 收 **明文或其 sha256 hash**（网关侧
    token 列即 hash）。调用方只持本地 ``key_hash``（== sha256(明文)），
    明文永不出库。响应 ``info`` 含 spend / last_active / key_alias；
    Key 已作废时网关 404。
    """
    logger.info("LiteLLM GET /key/info")
    return await _http_json("GET", "/key/info", params={"key": key}, transport=transport)


async def list_key_spend_logs(
    key_alias: str,
    *,
    page: int = 1,
    page_size: int = 100,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    """GET /spend/logs/v2：按 key_alias 过滤的分页 spend 日志（T-09 用量观察）。

    v1.100.0 实读：rows（``data``）含 ``total_tokens``（int）——是按 Key 累计
    token 用量的可得口径（key/info 行只有 USD spend，无 token 计数）。
    响应：``{data, total, page, page_size, total_pages, total_is_capped}``。
    """
    logger.info("LiteLLM GET /spend/logs/v2")
    return await _http_json(
        "GET", "/spend/logs/v2",
        params={"key_alias": key_alias, "page": int(page), "page_size": int(page_size)},
        transport=transport,
    )
