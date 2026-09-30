"""出站请求守卫：SSRF 统一防线（审计 BUG-22 / P0-8；P1-6 收敛点）

所有「按用户/租户/外部数据给出的 URL 发起请求」的入口都应经过本模块：
- check_url / assert_public_url：协议、端口、主机白名单、DNS 解析后逐个 IP 拒绝
  私网 / 环回 / 链路本地（含云元数据 169.254.169.254）/ 保留 / 组播 / CGNAT，
  以及 IPv4-mapped / NAT64 内嵌的上述地址；纯数字主机（整数编码 IP）直接拒绝
- guarded_get：禁用自动重定向，逐跳复检后再发请求（公网开放重定向跳内网零请求）

已知边界：解析与建连之间存在 DNS rebinding 窗口（TOCTOU）；需要更强保证的入口
应在出口网络层（egress 代理 / 安全组）兜底，本守卫是应用层第一道防线。

依赖方向：platform_core → config（单向）；httpx 仅在 guarded_get 内延迟导入，
scrapy 侧只用同步 check_url。
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("platform.outbound_guard")

DEFAULT_ALLOWED_PORTS: tuple[int, ...] = (80, 443)
MAX_REDIRECT_HOPS = 5

_BLOCKED_NETS = tuple(ipaddress.ip_network(n) for n in (
    # IPv4
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
    # IPv6
    "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
))
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class OutboundBlocked(BusinessException):
    """出站目标被守卫拒绝（400 OUTBOUND_BLOCKED；消息不回显解析结果）"""

    def __init__(self, message: str = "目标地址不允许访问（仅允许公网地址）"):
        super().__init__(message=message, code="OUTBOUND_BLOCKED", status_code=400)


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """私网/环回/链路本地/保留/组播/未指定地址判定（显式网段 + 标准库属性双保险）"""
    if ip.version == 6:
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return is_blocked_ip(mapped)
        if ip in _NAT64:
            return is_blocked_ip(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return any(ip in net for net in _BLOCKED_NETS if net.version == ip.version) or bool(
        ip.is_loopback or ip.is_link_local or ip.is_private
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def resolve_host_ips(host: str) -> list[str]:
    """DNS 解析（阻塞；异步上下文经 assert_public_url 走 to_thread）"""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def host_allowed(host: str, allowed_hosts: Iterable[str]) -> bool:
    """主机白名单：精确匹配，或 `*.example.com` 形式匹配其子域（不含裸域）"""
    host = host.lower().rstrip(".")
    for pattern in allowed_hosts:
        p = str(pattern).lower().strip().rstrip(".")
        if not p:
            continue
        if p.startswith("*."):
            if host.endswith(p[1:]):
                return True
        elif host == p:
            return True
    return False


def _outbound_list(key: str) -> list[str]:
    """读 OUTBOUND.<key> 名单（配置即代码；缺省空）"""
    from config import settings

    section = settings.get("OUTBOUND") or {}
    raw = section.get(key) if hasattr(section, "get") else None
    return [str(x) for x in (raw or []) if str(x).strip()]


def robots_exempt(host: str) -> bool:
    """决策 D8：站点级豁免 robots.txt（OUTBOUND.ROBOTS_EXEMPT_DOMAINS，精确或 *.后缀）"""
    exempt = _outbound_list("ROBOTS_EXEMPT_DOMAINS")
    return bool(exempt) and host_allowed(host, exempt)


def check_url(
    url: str,
    *,
    allowed_ports: Optional[Iterable[int]] = DEFAULT_ALLOWED_PORTS,
    allowed_hosts: Optional[Iterable[str]] = None,
    require_https: bool = False,
    resolve: bool = True,
) -> None:
    """同步校验出站 URL；不合规抛 OutboundBlocked

    allowed_ports=None 表示不限端口（LLM 供应商等自定义端口场景）；
    allowed_hosts 给出时先做白名单，再做 IP 校验（白名单不豁免私网判定）。
    """
    parsed = urlparse(str(url or "").strip())
    schemes = ("https",) if require_https else ("http", "https")
    if parsed.scheme not in schemes:
        raise OutboundBlocked(f"目标地址协议不允许（仅 {'/'.join(schemes)}）")
    host = (parsed.hostname or "").strip()
    if not host:
        raise OutboundBlocked("目标地址缺少主机名")
    try:
        port = parsed.port
    except ValueError as exc:
        raise OutboundBlocked("目标地址端口不合法") from exc
    if allowed_ports is not None and port is not None and port not in tuple(allowed_ports):
        raise OutboundBlocked("目标地址端口不允许")
    if allowed_hosts is not None and not host_allowed(host, allowed_hosts):
        logger.warning(f"出站主机不在白名单 | host={host}")
        raise OutboundBlocked("目标主机不在允许列表内")
    # 决策 D7：平台可配置的禁采域名（OUTBOUND.BLOCKED_DOMAINS，精确或 *.后缀）；所有出站路径统一生效
    blocked = _outbound_list("BLOCKED_DOMAINS")
    if blocked and host_allowed(host, blocked):
        logger.warning(f"出站主机在平台禁采名单 | host={host}")
        raise OutboundBlocked("目标站点不在平台允许的采集范围内")
    if host.isdigit() or host.lower().startswith("0x"):
        # glibc 解析语义下整数 / 十六进制编码命中 IP（2130706433 → 127.0.0.1）
        raise OutboundBlocked()
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if is_blocked_ip(literal):
            logger.warning(f"出站目标为内网字面量 IP | host={host}")
            raise OutboundBlocked()
        return
    if not resolve:
        return
    try:
        raw_ips = resolve_host_ips(host)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise OutboundBlocked("目标主机无法解析") from exc
    if not raw_ips:
        raise OutboundBlocked("目标主机无法解析")
    for raw in raw_ips:
        try:
            ip = ipaddress.ip_address(raw.split("%", 1)[0])
        except ValueError:
            continue
        if is_blocked_ip(ip):
            logger.warning(f"出站域名解析到内网 | host={host}")
            raise OutboundBlocked()


async def assert_public_url(url: str, **kwargs) -> None:
    """check_url 的异步版（DNS 解析放线程池，不阻塞事件循环）"""
    await asyncio.to_thread(check_url, url, **kwargs)


async def guarded_get(client, url: str, *, max_hops: int = MAX_REDIRECT_HOPS, **check_kwargs):
    """逐跳校验的 GET：每一跳先过 assert_public_url 再发请求，返回最终响应

    client 为 httpx.AsyncClient（调用方持有生命周期）；本函数对每次请求显式
    follow_redirects=False，注入的客户端即便开了自动跟随也不会越过校验。
    """
    current = url
    for _ in range(max_hops + 1):
        await assert_public_url(current, **check_kwargs)
        resp = await client.get(current, follow_redirects=False)
        location = resp.headers.get("location") if 300 <= resp.status_code < 400 else None
        if not location:
            return resp
        current = urljoin(current, location)
    raise OutboundBlocked(f"重定向次数超过上限 {max_hops}")
