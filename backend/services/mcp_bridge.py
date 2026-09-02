"""MCP 工具桥（P6 C4，ADR-0001）

平台消费插件的运行时：MCP client（stdio/HTTP）→ tools/list 登记 + tools/call 调用。
双重用途：① 插件验证管线（connect → list → 抽样 call → health 落库）；
② 平台 LLM 工具面（专家/规划器可调插件工具，二期消费）。

安全边界（ADR-0001）：
- stdio 可执行文件白名单（config LLM.MCP_ALLOWED_EXECUTABLES，缺省 node/npx/python3/uvx）；
- 全程超时（连接 5s / 调用 10s）；不 shell；hooks/commands 只登记不执行。
"""
from typing import Optional

from platform_core.logger import get_logger

logger = get_logger("service.mcp_bridge")

CONNECT_TIMEOUT = 5.0
CALL_TIMEOUT = 10.0

# stdio 可执行文件白名单（防任意命令执行；配置可扩）
_DEFAULT_ALLOWED = ("node", "npx", "python3", "python", "uvx", "uv")


def _allowed_executables() -> set[str]:
    from config import settings

    extra = settings.get("LLM.MCP_ALLOWED_EXECUTABLES", []) or []
    return set(_DEFAULT_ALLOWED) | {str(x) for x in extra}


async def list_tools(server_config: dict) -> dict:
    logger.debug(f"MCP tools/list | cmd={server_config.get('command')}")
    """连接 MCP server → tools/list → 关闭。返回 {ok, tools[], error}"""
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        import asyncio

        params = _stdio_params(server_config)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.list_tools(), CALL_TIMEOUT)
                return {
                    "ok": True,
                    "tools": [
                        {"name": t.name, "description": (t.description or "")[:200]}
                        for t in result.tools
                    ],
                    "error": "",
                }
    except Exception as exc:  # noqa: BLE001 桥失败结构化返回
        logger.warning(f"MCP tools/list 失败: {type(exc).__name__}: {exc}")
        return {"ok": False, "tools": [], "error": f"{type(exc).__name__}: {exc}"}


async def call_tool(server_config: dict, tool_name: str, arguments: Optional[dict] = None) -> dict:
    logger.debug(f"MCP tools/call | tool={tool_name}")
    """连接 → tools/call → 关闭。返回 {ok, content, error}"""
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        import asyncio

        params = _stdio_params(server_config)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), CONNECT_TIMEOUT)
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments or {}), CALL_TIMEOUT
                )
                content = "".join(
                    getattr(c, "text", "") for c in (result.content or [])
                )
                return {"ok": not result.isError, "content": content[:2000], "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "content": "", "error": f"{type(exc).__name__}: {exc}"}


def _stdio_params(server_config: dict) -> "StdioServerParameters":
    """构造 stdio 启动参数——可执行文件白名单校验（ADR-0001 安全边界）"""
    from mcp import StdioServerParameters

    command = str(server_config.get("command") or "")
    executable = command.rsplit("/", 1)[-1]
    if executable not in _allowed_executables():
        raise ValueError(
            f"MCP stdio 可执行文件不在白名单: {command!r}（允许: {sorted(_allowed_executables())}）"
        )
    return StdioServerParameters(
        command=command,
        args=[str(a) for a in (server_config.get("args") or [])],
        env={str(k): str(v) for k, v in (server_config.get("env") or {}).items()} or None,
    )


async def verify_plugin_server(server_config: dict) -> dict:
    logger.debug(f"MCP 验证管线 | cmd={server_config.get('command')}")
    """插件验证管线（ADR-0001）：connect → tools/list → 抽样 call（首个工具空参）。

    判定：list ok 且有工具 = healthy；list ok 但零工具 = degraded；
    连接失败 = down。
    """
    listing = await list_tools(server_config)
    if not listing["ok"]:
        return {"health": "down", "tools": 0, "detail": listing["error"]}
    tools = listing["tools"]
    if not tools:
        return {"health": "degraded", "tools": 0, "detail": "连接成功但零工具注册"}

    # 抽样：首个工具空参调用（预期多数工具会报参数错误——但这证明了管道通）
    sample = await call_tool(server_config, tools[0]["name"], {})
    # 调用返回（无论工具层错误）= 管道连通
    return {
        "health": "healthy",
        "tools": len(tools),
        "detail": f"listed {len(tools)} tools; sample call ok={sample['ok']}",
        "tool_names": [t["name"] for t in tools[:20]],
    }
