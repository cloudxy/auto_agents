"""目标页抓取防护层：SSRF 校验（M6）/ HTML 清洗 / 单页抓取（重定向逐跳校验）

拆分自 ai_planner_service.py（期4 结构治理），职责边界：
- HTML 清洗（去脚本/样式/注释、压缩空白、截断）：_clean_html_sync（CPU 密集，走 to_thread）
- SSRF 防护：_resolve_host_ips / _is_blocked_ip / _assert_public_url
  （仅允许 80/443 公网 http(s) 目标，逐跳校验重定向）
- 单页抓取：_fetch_html（UA 伪装 + 10s 超时 + 禁自动重定向逐跳 SSRF 校验）

Patch 兼容约定：_resolve_host_ips / _assert_public_url 等可 patch 符号经
llm_common.seam() 命名空间调用期取值（T6 解环：门面初始化完成后注入 seam，
无文件末尾反向 import；test_ai_planner.py patch
backend.services.ai_planner_service._resolve_host_ips 需在运行时生效）；
httpx 为全局共享模块对象（patch httpx.AsyncClient 即全局生效），保留本地引用。
"""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from backend.services.llm_common.seam import seam as _seam
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("api")

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

# ----------------------------------------------------------------------
# HTML 清洗（纯函数，供 to_thread 调用）
# ----------------------------------------------------------------------
_SCRIPT_BLOCK = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAB_SPACES = re.compile(r"[ \t\r\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n\s*\n+")


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


# ----------------------------------------------------------------------
# SSRF 防护（M6）
# ----------------------------------------------------------------------
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
    字面量 IP（含十进制整数编码）直接判定不发 DNS；域名目标解析后全部校验。
    DNS 解析经门面查找（_seam()._resolve_host_ips）：存量单测 patch 旧路径
    backend.services.ai_planner_service._resolve_host_ips 在运行时生效。
    """
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
        raw_ips = await asyncio.to_thread(_seam()._resolve_host_ips, host)
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
    不再每跳新建；拒绝型 URL 仍零请求零建连（SSRF 零请求断言依赖此语义）。
    """
    current = url
    client_ctx: httpx.AsyncClient | None = None
    client: httpx.AsyncClient | None = None
    try:
        for _ in range(_MAX_REDIRECT_HOPS):
            await _seam()._assert_public_url(current)
            if client is None:
                # trust_env=False：抓取请求不走系统代理（本机代理劫持陷阱，同上约定）
                client_ctx = httpx.AsyncClient(
                    timeout=_FETCH_TIMEOUT, follow_redirects=False, trust_env=False,
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

