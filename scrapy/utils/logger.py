"""
Scrapy 侧日志 —— 复用 platform_core.logger

不重复实现：init_log / get_logger 完全来自 platform_core，
只是把 scrapy 侧的导入做一个稳定别名。
"""
from platform_core.logger import init_log, get_logger

__all__ = ["init_log", "get_logger"]
