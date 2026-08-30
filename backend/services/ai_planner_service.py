"""AI 采集规划服务 - LLM 规划 flow 流程 → 试采验证 → 注册爬虫定义（阶段二）

职责：
- _llm_chat：OpenAI 兼容 chat completions（httpx 直连，不引 openai SDK），
  含超时 / 指数退避重试 / token 预算熔断；LLM.ENABLED=false 时直接抛业务异常
- _execute_plan：规划状态机 planning → 抓取/复用 HTML → 清洗截断（to_thread）→
  LLM 产出严格 JSON → FlowConfig 校验 → 落 plan_json 与 generated_params
- _execute_test：flow_generic 低优先级试采 → 终态轮询 + 质量判定 →
  未通过且未达 LLM.MAX_ITERATIONS 时把失败原因 + 样本 HTML 回喂 LLM 修正后重新试采
- register：校验最近试采通过后调 SpiderService.create_definition（source=ai_generated）

设计约束：
- 后台任务（规划/试采）自开独立 AsyncSession（端点请求 session 在响应后关闭），
  服务内所有状态变更落 DB，状态机可查询进度
- 试采终态轮询用独立短事务 session（_read_task_snapshot）：长生命周期 session 的
  identity map 会遮蔽 webhook 并发推进的终态（已加载未过期实体不刷新）
- DOM/HTML 清洗等 CPU 操作走 asyncio.to_thread，不阻塞事件循环
- commit 后不再读 ORM 属性（防 expire 惰性加载 MissingGreenlet），全部用本地变量
"""
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.ai_plan_repository import AiPlanRepository
from backend.repositories.spider_definition_repository import SpiderDefinitionRepository
from backend.services.llm_provider_service import LlmProviderService, LlmRuntimeConfig
from backend.services.spider_service import SpiderService
from config import settings
from platform_core.db import get_manager
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.ai_plan import AiPlan
from platform_core.models.spider_task import SpiderTask
from platform_core.schemas.ai_plan import AiPlanCreate, AiPlanListResponse, AiPlanResponse, FlowConfig
from platform_core.schemas.spider import DefinitionCreateRequest

logger = get_logger("api")

# 试采等待参数（终态轮询）
_WAIT_INTERVAL_SECONDS = 5.0
_WAIT_TIMEOUT_SECONDS = 600.0
# LLM 重试退避基数（指数：1s/2s/4s...）
_RETRY_BASE_DELAY = 1.0
# 目标页抓取：单页 10s 超时 + UA 伪装（单次轻量请求，非爬虫队列任务）
_FETCH_TIMEOUT = 10.0
_SPIDER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# HTML 清洗后截断上限（LLM 上下文预算）
_MAX_HTML_CHARS = 15000
# M6 SSRF 防护：单页抓取仅允许公网 http(s) 目标（80/443），重定向逐跳校验
_ALLOWED_PORTS = (80, 443)
_MAX_REDIRECT_HOPS = 5
_BLOCKED_V4_NETS = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16",
))
_BLOCKED_V6_NETS = tuple(ipaddress.ip_network(n) for n in (
    "::/128", "::1/128", "fc00::/7", "fe80::/10",
))
# M5：规划/试采/注册互斥的占用态（条件 UPDATE 原子抢断的状态守卫集合）
_BUSY_STATUSES = ("planning", "testing", "registered")

# 进程级 token 用量累计（跨请求熔断；按 provider 维度计数，兜底路径统一记在
# "config" 名下；单实例假设：多副本部署时预算无法跨进程聚合，需外部聚合方案）
_TOKEN_USAGE: dict[str, int] = {}

# ----------------------------------------------------------------------
# 共享 AsyncClient 缓存（provider 路径专用；兜底路径保持现状的一次性 client）
# ----------------------------------------------------------------------
# key=(base_url, sha256(api_key)[:12])：Authorization 头在创建时固化，密钥轮换
# 自然产生新条目；owner 记录归属供应商，热切换/变更/删除时由 invalidate 定向关闭
_HTTP_CLIENTS: dict[tuple[str, str], httpx.AsyncClient] = {}
_HTTP_CLIENT_OWNER: dict[tuple[str, str], int] = {}
# 连接池与超时拆分：connect 上限 10s，读/写/取池跟随调用方超时
_CLIENT_MAX_CONNECTIONS = 20
_CLIENT_MAX_KEEPALIVE_CONNECTIONS = 10
_CLIENT_KEEPALIVE_EXPIRY = 30.0
_CLIENT_CONNECT_TIMEOUT = 10.0

# 后台任务强引用集（防 asyncio.Task 被 GC），完成后自动清理
_BACKGROUND_TASKS: set = set()


# ----------------------------------------------------------------------
# 后台任务启动（自开独立 session）
# ----------------------------------------------------------------------
def _spawn(coro) -> None:
    """创建后台任务并持有引用（防 GC），完成后自动清理"""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _client_cache_key(base_url: str, api_key: str) -> tuple[str, str]:
    """共享 client 缓存键：base_url + 密钥指纹（明文/完整哈希均不落内存键）"""
    return (base_url.rstrip("/"), hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:12])


async def get_shared_client(base_url: str, api_key: str, timeout: float, provider_id: Optional[int] = None) -> httpx.AsyncClient:
    logger.debug(f"获取共享 LLM client: provider_id={provider_id}, timeout={timeout}")
    # 取（或建）共享 AsyncClient：连接池复用，Limits + connect/read 超时拆分
    key = _client_cache_key(base_url, api_key)
    client = _HTTP_CLIENTS.get(key)
    if client is not None and not client.is_closed:
        return client
    if client is not None:  # 已被外部关闭的残留条目
        _HTTP_CLIENTS.pop(key, None)
        _HTTP_CLIENT_OWNER.pop(key, None)
    limits = httpx.Limits(
        max_connections=_CLIENT_MAX_CONNECTIONS,
        max_keepalive_connections=_CLIENT_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=_CLIENT_KEEPALIVE_EXPIRY,
    )
    timeout_cfg = httpx.Timeout(
        timeout,
        connect=min(_CLIENT_CONNECT_TIMEOUT, timeout),
        read=timeout, write=timeout, pool=timeout,
    )
    client = httpx.AsyncClient(timeout=timeout_cfg, limits=limits, follow_redirects=False)
    _HTTP_CLIENTS[key] = client
    if provider_id is not None:
        _HTTP_CLIENT_OWNER[key] = provider_id
    return client


async def invalidate_client_cache(provider_id: Optional[int] = None) -> None:
    logger.debug(f"失效共享 LLM client 缓存: provider_id={provider_id}")
    # 失效共享 client 缓存：provider_id 定向清理该供应商的连接，None 全清。
    # 须在事件循环内 await 调用（供应商变更/热切换/删除后由 Service 层触发）；
    # 飞行中的请求不受影响，下次重试自动建新 client。
    keys = [k for k, owner in _HTTP_CLIENT_OWNER.items()
            if provider_id is None or owner == provider_id]
    for key in keys:
        client = _HTTP_CLIENTS.pop(key, None)
        _HTTP_CLIENT_OWNER.pop(key, None)
        if client is None:
            continue
        try:
            await client.aclose()
        except Exception as e:  # noqa: BLE001 关闭失败仅记日志，不影响主流程
            logger.warning(f"共享 LLM client 关闭失败（忽略）: {e}")


# ----------------------------------------------------------------------
# 运行时配置解析（provider 优先 / yml+env 兜底）
# ----------------------------------------------------------------------
def resolve_config_from_settings() -> LlmRuntimeConfig:
    logger.debug("解析 yml/env 兜底 LLM 配置")
    # yml/env 兜底配置：读取顺序与阶段一 _llm_chat 完全一致（零回归保证）。
    # 本函数必须留在本模块（而非 llm_provider_service）：test_ai_planner.py 对
    # backend.services.ai_planner_service.settings 的 monkeypatch 只对本模块
    # 命名空间的 settings 读取生效，兜底路径行为契约与现状完全一致。
    return LlmRuntimeConfig(
        base_url=str(settings.get("LLM.BASE_URL", "") or "").rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY") or str(settings.get("LLM.API_KEY", "") or ""),
        model=str(settings.get("LLM.MODEL", "") or ""),
        temperature=float(settings.get("LLM.TEMPERATURE", 0.2)),
        timeout=float(settings.get("LLM.TIMEOUT", 120)),
        max_retries=max(1, int(settings.get("LLM.MAX_RETRIES", 3))),
        enabled=bool(settings.get("LLM.ENABLED", False)),
        source="config",
        provider_id=None,
    )


async def _resolve_llm_runtime_config() -> LlmRuntimeConfig:
    """独立短事务 session 解析 LLM 运行时配置（激活供应商优先）

    短事务模式同 _read_task_snapshot（每轮新建、查完即关）；任何异常
    （DB 不可用/表未建/单测无库）都降级为 yml/env 兜底，不阻断 LLM 调用。
    """
    try:
        manager = get_manager()
        async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
            return await LlmProviderService(session).resolve_runtime_config()
    except Exception as e:  # noqa: BLE001 无库/异常场景一律回退兜底路径
        logger.warning(f"LLM 供应商配置解析失败，回退 yml/env 兜底: {e}")
        return resolve_config_from_settings()


@dataclass(frozen=True)
class _TaskSnapshot:
    """试采任务状态快照（独立短事务读取的纯标量，脱离 ORM session，无懒加载风险）"""

    task_id: int
    status: str
    result_count: int
    error_message: Optional[str]


async def _read_task_snapshot(task_id: int) -> Optional[_TaskSnapshot]:
    """独立短事务 session 读任务标量快照（每轮新建、查完即关）

    缺陷背景：后台试采协程曾复用长生命周期 session 轮询 repo.get_by_id，
    identity map 中已加载未过期实体即使 SELECT 到新行也不刷新属性（默认无
    populate_existing）→ worker webhook 推进的终态永不可见 → 600s 必超时。
    独立 session 每轮新建连接/事务，读到的永远是 DB 最新已提交行（与事务
    隔离级别无关）；且只取标量列，连 ORM 实体都不进 identity map（双保险）。
    """
    manager = get_manager()
    async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
        row = await session.execute(
            select(
                SpiderTask.id,
                SpiderTask.status,
                SpiderTask.result_count,
                SpiderTask.error_message,
            ).where(SpiderTask.id == task_id)
        )
        data = row.first()
    if data is None:
        return None
    return _TaskSnapshot(
        task_id=int(data.id),
        status=str(data.status),
        result_count=int(data.result_count or 0),
        error_message=data.error_message,
    )


async def _force_fail_status(plan_id: int, message: str) -> None:
    """m3 最后防线：_fail 自身失败（如 DB 异常卡死）时用全新 session 落 failed；
    新 session 也失败则仅记日志，不再抛（避免掩盖原始异常/无限递归）。"""
    try:
        manager = get_manager()
        async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
            await AiPlanRepository(session).update_status(
                plan_id, "failed", error_message=message[:2000], test_task_id=None
            )
            await session.commit()
        logger.warning(f"AI 计划兜底置 failed 完成: plan_id={plan_id}")
    except Exception as e:  # noqa: BLE001 兜底失败只记日志
        logger.error(f"AI 计划兜底置 failed 失败: plan_id={plan_id}, error={e}")


async def reconcile_interrupted_plans() -> int:
    logger.info("启动对账开始：无条件清理中断遗留的 planning/testing AI 计划（评审 M-2）")
    # 后台规划/试采任务不跨进程持久：进程重启后这些行会永久滞留占用态
    # （_BUSY_STATUSES 抢断锁），阻塞重新触发。lifespan 启动阶段为单实例
    # 语义，进行中的后台任务必然已随进程消亡，故不再按 updated_at 宽限
    # （评审 M-2：原 10 分钟窗口会让启动前 10 分钟内的滞留行逃过对账）
    # ——无条件全部置 failed("进程中断，请重新发起")，单语句批量 UPDATE。
    # 多副本部署会误伤其他副本正在执行的任务，故仅在单实例语义的
    # lifespan 启动阶段调用。
    stmt = (
        update(AiPlan)
        .where(AiPlan.status.in_(("planning", "testing")))
        .values(status="failed", error_message="进程中断，请重新发起", test_task_id=None)
        .execution_options(synchronize_session=False)
    )
    manager = get_manager()
    async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
        result = await session.execute(stmt)
        await session.commit()
    affected = int(result.rowcount or 0)
    if affected:
        logger.warning(f"启动对账：{affected} 个中断遗留的 AI 计划已置 failed")
    return affected


async def _run_plan_bg(plan_id: int) -> None:
    """后台规划协程：自开独立 AsyncSession（端点请求 session 已随响应关闭）"""
    try:
        manager = get_manager()
        async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
            await AiPlannerService(session)._execute_plan(plan_id)
    except Exception as e:  # noqa: BLE001 兜底：后台异常记日志 + 新 session 落失败态
        logger.error(f"AI 规划后台任务异常: plan_id={plan_id}, error={e}")
        await _force_fail_status(plan_id, f"规划后台异常: {e}")


async def _run_test_bg(plan_id: int) -> None:
    """后台试采协程：自开独立 AsyncSession"""
    try:
        manager = get_manager()
        async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
            await AiPlannerService(session)._execute_test(plan_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"AI 试采后台任务异常: plan_id={plan_id}, error={e}")
        await _force_fail_status(plan_id, f"试采后台异常: {e}")


# ----------------------------------------------------------------------
# HTML 抓取 / 清洗 / LLM 响应解析（纯函数，供 to_thread 调用）
# ----------------------------------------------------------------------
_SCRIPT_BLOCK = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAB_SPACES = re.compile(r"[ \t\r\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n\s*\n+")
_MD_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _clean_html_sync(html: str) -> str:
    """清洗 HTML：去脚本/样式/注释、压缩空白，保留标签结构并截断（CPU 密集，走 to_thread）"""
    text = _SCRIPT_BLOCK.sub(" ", html)
    text = _HTML_COMMENT.sub(" ", text)
    text = _TAB_SPACES.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n", text)
    text = text.strip()
    if len(text) > _MAX_HTML_CHARS:
        text = text[:_MAX_HTML_CHARS]
    return text


def _resolve_host_ips(host: str) -> list[str]:
    """DNS 解析（阻塞调用，须放 to_thread）：返回全部解析结果 IP（独立函数便于测试桩替换）"""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """私网/环回/链路本地/保留/组播/未指定地址判定（显式网段 + 标准库属性双保险）"""
    nets = _BLOCKED_V6_NETS if ip.version == 6 else _BLOCKED_V4_NETS
    return any(ip in net for net in nets) or bool(
        ip.is_loopback or ip.is_link_local or ip.is_private
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


async def _assert_public_url(url: str) -> None:
    """M6 SSRF 防护：仅允许 80/443 的公网 http(s) 目标

    host → 解析 IP → 逐个拒绝私网/环回/链路本地/保留段；
    字面量 IP（含十进制整数编码）直接判定不发 DNS；域名目标解析后全部校验。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BusinessException(f"目标地址协议不允许: {url}")
    if parsed.port is not None and parsed.port not in _ALLOWED_PORTS:
        raise BusinessException(f"目标地址端口不允许（仅 80/443）: {url}")
    host = parsed.hostname or ""
    if not host:
        raise BusinessException(f"目标地址缺少主机: {url}")
    if host.isdigit():
        # 纯数字 host：glibc 解析语义下命中整数编码 IP（如 2130706433→127.0.0.1），直接拒绝
        raise BusinessException(f"目标主机为纯数字（整数编码 IP 绕过），已拒绝（SSRF 防护）: {url}")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise BusinessException(f"目标地址指向私网/保留段，已拒绝（SSRF 防护）: {url}")
        return
    try:
        raw_ips = await asyncio.to_thread(_resolve_host_ips, host)
    except (socket.gaierror, UnicodeError) as e:
        raise BusinessException(f"目标主机 DNS 解析失败: {url} ({e})")
    for raw in raw_ips:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise BusinessException(f"目标域名解析到私网/保留段，已拒绝（SSRF 防护）: {url}")


async def _fetch_html(url: str) -> str:
    """抓取目标页单页 HTML（UA 伪装 + 10s 超时 + 禁自动重定向逐跳 SSRF 校验）

    M6：follow_redirects=False 手动跟随，每跳先过 _assert_public_url 再发请求，
    防公网开放重定向跳转内网（event hook 校验时连接已发出，不可靠）。
    client 在整条重定向链内惰性创建一次（首跳校验通过后才建连，多跳复用），
    不再每跳新建；拒绝型 URL 仍零请求零建连（SSRF 零请求断言依赖此语义）。"""
    current = url
    client_ctx: httpx.AsyncClient | None = None
    client: httpx.AsyncClient | None = None
    try:
        for _ in range(_MAX_REDIRECT_HOPS):
            await _assert_public_url(current)
            if client is None:
                client_ctx = httpx.AsyncClient(
                    timeout=_FETCH_TIMEOUT, follow_redirects=False,
                    headers={"User-Agent": _SPIDER_UA},
                )
                client = await client_ctx.__aenter__()
            resp = await client.get(current)
            if 300 <= resp.status_code < 400 and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                continue
            resp.raise_for_status()
            return resp.text
        raise BusinessException(f"重定向次数超过上限 {_MAX_REDIRECT_HOPS}: {url}")
    finally:
        if client is not None:
            await client_ctx.__aexit__(None, None, None)


def _parse_llm_json(raw: str) -> dict:
    """解析 LLM 响应为严格 JSON dict（剥 markdown 围栏 / 提取首尾大括号）"""
    text = (raw or "").strip()
    match = _MD_FENCE.search(text)
    if match:
        text = match.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM 响应中未找到 JSON 对象")
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 响应不是合法 JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("LLM 响应 JSON 顶层必须是对象")
    return data


# ----------------------------------------------------------------------
# Prompt 构造
# ----------------------------------------------------------------------
_PLAN_SYSTEM_PROMPT = (
    "你是网页采集规则生成专家。根据给定的 HTML 片段为流程化爬虫生成采集规则。"
    "只输出一个 JSON 对象，不要任何解释、注释或 markdown 代码块围栏。"
)

_SCHEMA_HINT = (
    '{"selectors": [{"name": "field_name", "type": "xpath|css|regex", "expr": "..."}],'
    ' "pagination": {"selector": "next-page css/xpath selector", "type": "css|xpath",'
    ' "max_pages": 2} | null,'
    ' "detail": {"list_selector": "list-item css", "url_selector": "link xpath (e.g. ./@href)",'
    ' "selectors": [{"name": "...", "type": "...", "expr": "..."}]} | null,'
    ' "filters": [{"field": "field_name", "op": "contains|equals|regex", "value": "..."}]}'
)

_CONSTRAINTS = (
    "约束：selectors 必填且至少 1 条；pagination.selector 与 detail.list_selector 用 css；"
    "detail.url_selector 必须是 xpath；max_pages 固定为 2；只提取页面上真实存在的结构。"
)


def _build_plan_messages(target_url: str, html: str) -> list[dict]:
    """规划 prompt：目标 URL + 清洗后 HTML → 采集规则 JSON"""
    user = (
        f"目标页面: {target_url}\n"
        f"HTML 片段（已清洗截断）:\n{html}\n\n"
        f"请输出符合以下结构的 JSON：\n{_SCHEMA_HINT}\n\n{_CONSTRAINTS}"
    )
    return [
        {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _build_repair_messages(target_url: str, flow_dict: dict, reason: str, html: str) -> list[dict]:
    """自动修复 prompt：失败原因 + 原规则 + 样本 HTML → 修正后的完整 JSON"""
    user = (
        f"目标页面: {target_url}\n"
        f"上一次生成的采集规则（试采失败）:\n{json.dumps(flow_dict, ensure_ascii=False)}\n"
        f"试采失败原因: {reason}\n"
        f"HTML 片段（已清洗截断）:\n{html}\n\n"
        f"请根据失败原因修正采集规则，输出完整 JSON（不是差异补丁）：\n{_SCHEMA_HINT}\n\n{_CONSTRAINTS}"
    )
    return [
        {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _build_generated_params(target_url: str, flow: FlowConfig) -> dict:
    """FlowConfig → flow_generic 任务参数（顶层键与消费者 extract_flow 契约一致）"""
    params: dict = {"urls": [target_url]}
    params["selectors"] = [s.model_dump() for s in flow.selectors]
    if flow.pagination is not None:
        params["pagination"] = flow.pagination.model_dump()
    if flow.detail is not None:
        params["detail"] = flow.detail.model_dump()
    if flow.filters:
        params["filters"] = [f.model_dump() for f in flow.filters]
    if flow.render_js:
        params["render_js"] = True
    if flow.wait_for:
        params["wait_for"] = flow.wait_for
    if flow.wait_timeout:
        params["wait_timeout"] = flow.wait_timeout
    return params


def _domain_of(url: str) -> str:
    """提取 URL 域名（注册表命名用）"""
    host = (urlparse(url).netloc or url).split("@")[-1]
    return host or url


def _derive_spider_name(url: str, plan_id: int) -> str:
    """从目标域名推导注册爬虫名（ai_ 前缀 + plan id 保证唯一，总长 ≤50）"""
    slug = re.sub(r"[^a-z0-9]+", "_", _domain_of(url).lower()).strip("_") or "site"
    # i4：name 列上限 50，slug 截断长度按 plan_id 位数动态计算（固定 40 位在 6 位以上 id 时溢出）
    plan_digits = max(1, len(str(plan_id)))
    slug_cap = 50 - len("ai_") - plan_digits - 1
    return f"ai_{slug[:slug_cap]}_{plan_id}"


class AiPlannerService:
    """AI 采集计划服务：规划 / 试采（含自动修复迭代）/ 注册 / CRUD"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AiPlanRepository(session)

    # ------------------------------------------------------------------
    # CRUD（同步返回，规划/试采走后台任务）
    # ------------------------------------------------------------------
    async def create_plan(
        self, payload: AiPlanCreate, created_by: Optional[str] = None
    ) -> AiPlanResponse:
        """创建计划（draft；html_snippet 预置后规划阶段跳过在线抓取）"""
        logger.info(f"创建 AI 采集计划: target_url={payload.target_url}, by={created_by}")
        plan_json = {"html_snippet": payload.html_snippet} if payload.html_snippet else None
        item = await self.repo.create(
            target_url=payload.target_url, status="draft", plan_json=plan_json,
            created_by=created_by,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return AiPlanResponse.model_validate(item)

    async def list_plans(
        self, skip: int = 0, limit: int = 20, status: Optional[str] = None
    ) -> AiPlanListResponse:
        """分页列表（可按状态过滤）"""
        items = await self.repo.list_plans(skip=skip, limit=limit, status=status)
        total = await self.repo.count(status=status)
        return AiPlanListResponse(
            total=total, items=[AiPlanResponse.model_validate(p) for p in items]
        )

    async def get_plan(self, plan_id: int) -> AiPlanResponse:
        """单条计划快照"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        return AiPlanResponse.model_validate(plan)

    async def delete_plan(self, plan_id: int) -> dict:
        """删除计划（规划/试采进行中拒绝，防后台任务写空）"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status in ("planning", "testing"):
            raise BusinessException("计划正在规划/试采中，无法删除；请等待后台任务结束")
        deleted = await self.repo.delete(plan_id)
        await self.session.commit()
        logger.info(f"AI 采集计划已删除: plan_id={plan_id}")
        return {"id": plan_id, "deleted": deleted}

    # ------------------------------------------------------------------
    # 后台任务触发（API 端点内 create_task，立即返回快照）
    # ------------------------------------------------------------------
    async def launch_plan(self, plan_id: int) -> AiPlanResponse:
        """触发后台规划：原子抢断置 planning → asyncio.create_task 执行，立即返回快照"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status in _BUSY_STATUSES:
            raise BusinessException(f"计划当前状态为 {plan.status}，不允许触发规划")
        # M5：check-then-act 非原子，并发触发会双跑双 LLM 调用；
        # 条件 UPDATE（status NOT IN busy）一次语句抢断，rowcount=0 即已被并发占用。
        claimed = await self.repo.claim_status(
            plan_id, "planning", blocked_statuses=_BUSY_STATUSES,
            error_message=None, test_task_id=None,
        )
        await self.session.commit()
        if not claimed:
            raise BusinessException("计划已进入规划/试采/注册流程，请勿重复触发")
        _spawn(_run_plan_bg(plan_id))
        return await self.get_plan(plan_id)

    async def launch_test(self, plan_id: int) -> AiPlanResponse:
        """触发后台试采：spawn 前原子抢断置 testing，立即返回快照"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status == "planning":
            raise BusinessException("规划进行中，请等待规划完成后再试采")
        if plan.status == "testing":
            raise BusinessException("试采进行中，请勿重复触发")
        if plan.status == "registered":
            raise BusinessException("计划已注册，无需再次试采")
        if not plan.generated_params:
            raise BusinessException("请先完成规划（/plan）再试采")
        # M5：原实现不拦 testing 且 spawn 前不置状态 → testing 期间重复触发即双跑；
        # spawn 前先条件 UPDATE 原子置 testing，抢断失败（并发已占）直接拒绝。
        claimed = await self.repo.claim_status(
            plan_id, "testing", blocked_statuses=_BUSY_STATUSES, error_message=None,
        )
        await self.session.commit()
        if not claimed:
            raise BusinessException("计划已进入规划/试采/注册流程，请勿重复触发")
        _spawn(_run_test_bg(plan_id))
        return await self.get_plan(plan_id)

    # ------------------------------------------------------------------
    # LLM 调用（OpenAI 兼容 chat completions，httpx 直连；供应商优先 / 兜底不变）
    # ------------------------------------------------------------------
    async def _llm_chat(self, messages: list[dict]) -> str:
        """chat completions：超时 / 指数退避重试 / token 预算熔断 / 未启用抛业务异常

        配置来源：激活且 enabled 的供应商优先（provider 路径，共享 client），
        否则 yml/env 兜底（行为与阶段一完全一致，一次性 client）。
        """
        cfg = await _resolve_llm_runtime_config()
        if not cfg.enabled:
            raise BusinessException(
                "LLM 功能未启用（无激活供应商且 LLM.ENABLED=false）："
                "请在 LLM 供应商管理中配置并激活，或开启 LLM.ENABLED 并配置 LLM_API_KEY"
            )
        if not cfg.base_url or not cfg.model:
            raise BusinessException(
                "LLM 配置不完整：请检查 LLM.BASE_URL / LLM.MODEL（或激活供应商的配置）"
            )
        if not cfg.api_key:
            raise BusinessException(
                "缺少 LLM API Key：请在 .env 配置 LLM_API_KEY（或为激活的供应商配置密钥）"
            )

        # token 预算沿用全局 LLM.MAX_TOKENS_BUDGET（供应商表无独立预算列）
        budget = int(settings.get("LLM.MAX_TOKENS_BUDGET", 200000))
        payload = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature}
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        url = f"{cfg.base_url}/chat/completions"
        # token 用量按 provider 维度计数（兜底路径统一记在 "config" 名下）
        usage_dim = f"provider:{cfg.provider_id}" if cfg.provider_id is not None else "config"
        last_error: Exception | None = None

        for attempt in range(cfg.max_retries):
            used_total = _TOKEN_USAGE.get(usage_dim, 0)
            if used_total >= budget:
                raise BusinessException(
                    f"LLM token 预算已耗尽（{usage_dim} 累计 {used_total} >= {budget}），已熔断"
                )
            try:
                if cfg.provider_id is not None:
                    # provider 路径：模块级共享 client（连接池复用，变更时 invalidate 失效）
                    client = await get_shared_client(
                        cfg.base_url, cfg.api_key, cfg.timeout, cfg.provider_id
                    )
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                else:
                    # 兜底路径：与现状完全一致（每调用一次性 client，yml/env 配置）
                    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
                        resp = await client.post(url, json=payload, headers=headers)
                        resp.raise_for_status()
                data = resp.json()
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                if not content:
                    raise ValueError("LLM 响应缺少 content")
                used = int((data.get("usage") or {}).get("total_tokens") or 0)
                if used:
                    _TOKEN_USAGE[usage_dim] = _TOKEN_USAGE.get(usage_dim, 0) + used
                    logger.info(
                        f"LLM token 用量: +{used}（{usage_dim} 累计 "
                        f"{_TOKEN_USAGE[usage_dim]}/{budget}）"
                    )
                return content
            except BusinessException:
                raise
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if 400 <= status < 500 and status != 429:
                    raise BusinessException(f"LLM 请求被拒绝（HTTP {status}），不重试: {e}")
                last_error = e
            except Exception as e:  # noqa: BLE001 超时/网络/解析失败均进入重试
                last_error = e
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"LLM 调用失败（第 {attempt + 1}/{cfg.max_retries} 次），"
                f"{delay:.1f}s 后重试: {last_error}"
            )
            await asyncio.sleep(delay)

        raise BusinessException(f"LLM 调用失败（已重试 {cfg.max_retries} 次）: {last_error}")

    # ------------------------------------------------------------------
    # 规划（后台执行：planning → 抓取/复用 HTML → LLM → FlowConfig → 落库）
    # ------------------------------------------------------------------
    async def _execute_plan(self, plan_id: int) -> None:
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        # commit 会 expire ORM 对象，先提取本地变量再推进状态机
        target_url = plan.target_url
        plan_json = dict(plan.plan_json or {})

        await self.repo.update_status(plan_id, "planning", error_message=None, test_task_id=None)
        await self.session.commit()

        try:
            snippet = plan_json.get("html_snippet")
            if snippet:
                html = snippet
                logger.info(f"AI 规划使用预置 HTML 片段: plan_id={plan_id}")
            else:
                html = await _fetch_html(target_url)
            cleaned = await asyncio.to_thread(_clean_html_sync, html)
            raw = await self._llm_chat(_build_plan_messages(target_url, cleaned))
            flow_dict = await asyncio.to_thread(_parse_llm_json, raw)
            flow = await asyncio.to_thread(FlowConfig.model_validate, flow_dict)
            generated = _build_generated_params(target_url, flow)
            new_plan_json = {"flow": flow.model_dump(), "test_history": [], "html_sample": cleaned}
            await self.repo.update(plan_id, plan_json=new_plan_json, generated_params=generated)
            # 规划成功回 draft（规划产物已落库，等待试采触发）
            await self.repo.update_status(plan_id, "draft", error_message=None, test_task_id=None)
            await self.session.commit()
            logger.info(f"AI 规划完成: plan_id={plan_id}, selectors={len(flow.selectors)}")
        except ValidationError as e:
            await self._fail(plan_id, f"FlowConfig 校验失败: {e}")
        except BusinessException as e:
            await self._fail(plan_id, str(e))
        except Exception as e:  # noqa: BLE001 后台任务兜底置 failed
            await self._fail(plan_id, f"规划异常: {e}")

    # ------------------------------------------------------------------
    # 试采（后台执行：flow_generic 低优先级试采 + 自动修复迭代）
    # ------------------------------------------------------------------
    async def _execute_test(self, plan_id: int) -> None:
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if not plan.generated_params:
            raise BusinessException("计划缺少生成的任务参数，请先执行规划")
        target_url = plan.target_url
        plan_json = dict(plan.plan_json or {})
        params_dict = dict(plan.generated_params)
        iteration = int(plan.iteration_count or 0)
        history = [dict(h) for h in (plan_json.get("test_history") or [])]
        html_sample = str(plan_json.get("html_sample") or "")
        flow_dict = dict(plan_json.get("flow") or {})
        max_iterations = max(0, int(settings.get("LLM.MAX_ITERATIONS", 2)))
        spider_svc = SpiderService(self.session)

        try:
            while True:
                params_str = json.dumps(params_dict, ensure_ascii=False)
                task = await spider_svc.enqueue(
                    spider_name="flow_generic", params=params_str, priority="low"
                )
                await self.repo.update(plan_id, test_task_id=task.id)
                await self.repo.update_status(plan_id, "testing", error_message=None,
                                              test_task_id=task.id)
                await self.session.commit()
                logger.info(
                    f"AI 试采任务已入队: plan_id={plan_id}, task_id={task.id}, iteration={iteration}"
                )

                final_task = await self._wait_task_final(spider_svc, task.id)
                passed, reason = await self._judge_test(spider_svc, final_task)
                history.append({
                    "iteration": iteration,
                    "task_id": task.id,
                    "status": final_task.status,
                    "result_count": int(final_task.result_count or 0),
                    "passed": passed,
                    "reason": reason,
                })
                plan_json["test_history"] = history
                await self.repo.update(plan_id, plan_json=plan_json, test_task_id=task.id)
                await self.session.commit()

                if passed:
                    # 试采通过：保持 testing（可注册），注册时校验最近一次通过
                    logger.info(f"AI 试采通过: plan_id={plan_id}, task_id={task.id}, reason={reason}")
                    return

                if iteration < max_iterations:
                    iteration += 1
                    await self.repo.update(plan_id, iteration_count=iteration)
                    await self.session.commit()
                    logger.warning(
                        f"AI 试采未通过，自动修复迭代 {iteration}/{max_iterations}: "
                        f"plan_id={plan_id}, reason={reason}"
                    )
                    flow = await self._repair_flow(target_url, flow_dict, reason, html_sample)
                    params_dict = _build_generated_params(target_url, flow)
                    plan_json["flow"] = flow.model_dump()
                    await self.repo.update(
                        plan_id, generated_params=params_dict, plan_json=plan_json
                    )
                    await self.session.commit()
                    continue  # 重新入队试采

                await self._fail(
                    plan_id, f"试采未通过（自动修复迭代已达上限 {max_iterations} 次）: {reason}"
                )
                return
        except BusinessException as e:
            await self._fail(plan_id, str(e))
        except Exception as e:  # noqa: BLE001
            await self._fail(plan_id, f"试采异常: {e}")

    async def _repair_flow(
        self, target_url: str, flow_dict: dict, reason: str, html_sample: str
    ) -> FlowConfig:
        """把失败原因 + 样本 HTML 回喂 LLM 修正 selectors（修复失败由调用方置 failed）"""
        html = html_sample
        if not html:
            html = await _fetch_html(target_url)
        cleaned = await asyncio.to_thread(_clean_html_sync, html)
        raw = await self._llm_chat(_build_repair_messages(target_url, flow_dict, reason, cleaned))
        new_flow_dict = await asyncio.to_thread(_parse_llm_json, raw)
        return await asyncio.to_thread(FlowConfig.model_validate, new_flow_dict)

    async def _wait_task_final(self, spider_svc, task_id: int) -> _TaskSnapshot:
        """轮询试采任务至终态（completed/failed），超时抛业务异常

        每轮经 _read_task_snapshot 用独立短事务 session 读最新终态
        （间隔/超时语义不变），规避长生命周期 session identity map 遮蔽；
        返回脱离 ORM session 的纯标量快照。
        """
        deadline = time.monotonic() + _WAIT_TIMEOUT_SECONDS
        while True:
            snapshot = await _read_task_snapshot(task_id)
            if snapshot is not None and snapshot.status in ("completed", "failed"):
                return snapshot
            if time.monotonic() >= deadline:
                raise BusinessException(
                    f"试采任务 {task_id} 超时未结束（>{_WAIT_TIMEOUT_SECONDS:.0f}s）"
                )
            await asyncio.sleep(_WAIT_INTERVAL_SECONDS)

    async def _judge_test(self, spider_svc, task: _TaskSnapshot) -> tuple[bool, str]:
        """试采判定：completed 且 result_count>0，质量分过低（<40）判失败"""
        if task.status != "completed":
            return False, f"试采任务失败: {task.error_message or task.status}"
        result_count = task.result_count
        if result_count <= 0:
            return False, "试采结果为空（result_count=0）"
        quality = await spider_svc.get_task_quality(task.task_id)
        avg = quality.avg_score
        if avg is not None and float(avg) < 40:
            return False, f"试采质量分过低（avg_score={float(avg):.1f} < 40）"
        return True, f"试采通过: {result_count} 条结果"

    # ------------------------------------------------------------------
    # 注册（同步执行：校验最近试采通过 → create_definition(source=ai_generated)）
    # ------------------------------------------------------------------
    async def register(self, plan_id: int) -> AiPlanResponse:
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status == "registered":
            raise BusinessException("该计划已注册过爬虫定义")
        # create_definition 内部会 commit（expire ORM），先提取全部本地变量
        plan_json = dict(plan.plan_json or {})
        history = plan_json.get("test_history") or []
        generated_params = plan.generated_params
        test_task_id = plan.test_task_id
        target_url = plan.target_url

        if not history or not history[-1].get("passed"):
            raise BusinessException("最近一次试采未通过（或尚未试采），不允许注册；请先执行试采并通过")
        if not generated_params:
            raise BusinessException("计划缺少生成的任务参数，请先执行规划")

        name = _derive_spider_name(target_url, plan_id)
        payload = DefinitionCreateRequest(
            name=name,
            title=f"AI 采集 - {_domain_of(target_url)}",
            type="flow",
            description=f"AI 生成的流程化采集（计划 #{plan_id}，目标 {target_url}）",
        )
        spider_svc = SpiderService(self.session)
        try:
            definition = await spider_svc.create_definition(payload, source="ai_generated")
        except BusinessException as e:
            # m4：create_definition 已 commit 但 plan 状态更新失败时，重试会撞「已存在」；
            # 同名且 source=ai_generated 的定义即本次 AI 注册产物 → 幂等续走（不重复建定义）。
            if "已存在" not in str(e):
                raise
            existing = await SpiderDefinitionRepository(self.session).get_by_name(name)
            if existing is None or existing.source != "ai_generated":
                raise
            logger.warning(
                f"AI 计划注册幂等续走（定义已存在且来源为 ai_generated）: "
                f"plan_id={plan_id}, definition={name}"
            )
            definition = existing

        plan_json["registered_definition"] = definition.name
        await self.repo.update(plan_id, plan_json=plan_json)
        await self.repo.update_status(
            plan_id, "registered", error_message=None, test_task_id=test_task_id
        )
        await self.session.commit()
        logger.info(f"AI 计划已注册为爬虫定义: plan_id={plan_id}, definition={definition.name}")
        return await self.get_plan(plan_id)

    # ------------------------------------------------------------------
    # 失败兜底：置 failed + error_message（状态机可追溯）
    # ------------------------------------------------------------------
    async def _fail(self, plan_id: int, message: str) -> None:
        """失败兜底：先回滚（m3：原异常可能让 session 处于待回滚态，直接 update 会连坐失败卡死）
        再置 failed（状态机可追溯）；自身仍失败则由 _run_*_bg 的 _force_fail_status 收尾。"""
        logger.error(f"AI 计划失败: plan_id={plan_id}, error={message}")
        await self.session.rollback()
        await self.repo.update_status(plan_id, "failed", error_message=message[:2000],
                                      test_task_id=None)
        await self.session.commit()

