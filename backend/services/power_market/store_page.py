"""商店不存在句：仅约束公开详情 GET，与官网真 404 文案同形。"""
from backend.services.power_market.types import (
    STORE_NOT_FOUND_COPY,
    STORE_NOT_FOUND_HOME,
)

# 固定字节：未上架 / 黑名单 / 从不存在短名的 GET 详情共用。禁止「已下架」。
STORE_NOT_FOUND_HTML = (
    "<!DOCTYPE html>\n"
    '<html lang="zh-CN">\n'
    "<head>\n"
    '<meta charset="utf-8"/>\n'
    "<title>404</title>\n"
    "</head>\n"
    "<body>\n"
    "<h1>404</h1>\n"
    f"<p>{STORE_NOT_FOUND_COPY}</p>\n"
    f'<p><a href="/">{STORE_NOT_FOUND_HOME}</a></p>\n'
    "</body>\n"
    "</html>\n"
)
