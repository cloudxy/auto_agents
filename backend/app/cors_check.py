"""CORS 启动自检：只告警、不拒绝启动。

前端与 API 经同一域名反代时 CORS 根本不生效，空来源是合法的生产形态，所以这里不像
Webhook / JWT 密钥那样 fail-fast；但占位域名、生产放行 localhost、"*" 配凭据这类配置
一旦生效就是真实风险或真实故障，启动日志必须能一眼看到。
"""
from __future__ import annotations

import os
from typing import Any, Iterable
from urllib.parse import urlsplit

from platform_core.logger import get_logger

# 仓库里出现过的占位 / 文档示例域名：留在生产配置里等于没配
_PLACEHOLDER_HOSTS = ("your-domain.com", "example.com", "example.org")
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def _hosts_matching(origins: Iterable[str], hosts: tuple[str, ...]) -> list[str]:
    """来源的主机名等于或是 hosts 中某项的子域（按主机名比较，不做子串匹配）"""
    out = []
    for origin in origins:
        name = (urlsplit(str(origin)).hostname or "").lower()
        if any(name == h or name.endswith("." + h) for h in hosts):
            out.append(origin)
    return out


def cors_config_warnings(cors: Any, app_env: str) -> list[str]:
    """按环境检查 CORS 配置，返回告警文案列表（空 = 无问题）"""
    origins = [str(o) for o in (cors.get("ORIGINS") or [])]
    credentials = bool(cors.get("ALLOW_CREDENTIALS", False))
    warnings: list[str] = []
    if "*" in origins and credentials:
        warnings.append("CORS.ORIGINS 含 \"*\" 且 ALLOW_CREDENTIALS=true：任意站点可带凭据跨域调用 API")
    placeholders = _hosts_matching(origins, _PLACEHOLDER_HOSTS)
    if placeholders:
        warnings.append(f"CORS.ORIGINS 仍是占位域名 {placeholders}：真实前端域名会被浏览器拦截")
    loopback = _hosts_matching(origins, _LOOPBACK_HOSTS)
    if app_env == "prod" and loopback:
        warnings.append(f"生产 CORS.ORIGINS 放行本机来源 {loopback}：本机任意页面可带凭据调用生产 API")
    return warnings


def warn_cors_config(settings: Any) -> list[str]:
    """读取当前配置并把告警写进 global 日志；返回告警列表（测试用）"""
    logger = get_logger("global")
    app_env = (os.environ.get("APP_ENV") or "local").strip().lower()
    cors = settings.get("CORS", {}) or {}
    warnings = cors_config_warnings(cors, app_env)
    for text in warnings:
        logger.warning(f"CORS 配置自检: {text}")
    if app_env == "prod" and not cors.get("ORIGINS"):
        logger.info(
            "CORS 自检: 生产未配置跨域来源，只允许同源访问；前后端分域部署须注入 "
            "AUTO_AGENTS_CORS__ORIGINS='[\"https://admin.<你的域名>\"]'"
        )
    return warnings
