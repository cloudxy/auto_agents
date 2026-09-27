"""把微信 Native 支付的 code_url 渲染成可直接 <img src> 的 SVG data URI。

用 `qrcode` 的 SVG 路径工厂（不依赖 Pillow，纯矢量），服务端渲染一次随
支付意图响应一起返回——避免前端引入新的二维码渲染依赖，也避免二维码单独
开一个可被反复请求的端点（code_url 一次性、不该被缓存/重复拉取）。
"""
from __future__ import annotations

import base64
import io

import qrcode
import qrcode.image.svg

from platform_core.logger import get_logger

logger = get_logger("service.payment.qr")


def code_url_to_svg_data_uri(code_url: str) -> str:
    logger.debug("渲染微信支付二维码 SVG")
    img = qrcode.make(code_url, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
