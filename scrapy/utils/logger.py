"""Scrapy 日志配置"""
import logging
from loguru import logger
import sys
import os

# 从项目配置读取日志级别
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def setup_logger():
    """配置 Loguru 日志"""
    # 移除默认 handler
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stderr,
        level=settings.get("LOG_LEVEL", "INFO"),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )
    
    # 文件输出 - 按天轮转
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "spider")
    os.makedirs(log_dir, exist_ok=True)
    
    logger.add(
        os.path.join(log_dir, "spider_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="30 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8"
    )
    
    logger.add(
        os.path.join(log_dir, "error_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="90 days",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8"
    )
    
    return logger

# 导出全局 logger 实例
spider_logger = setup_logger()
