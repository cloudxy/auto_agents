"""日志初始化模块 - 数据驱动，支持动态配置"""
import os
import sys
from datetime import datetime

from loguru import logger
from config import settings


def _make_rotation_func(max_size_mb: int):
    """创建轮转函数：按天 + 按大小轮转"""
    max_size_bytes = max_size_mb * 1024 * 1024

    def should_rotate(message, file):
        try:
            last_mtime = os.stat(file.name).st_mtime
            file_date = datetime.fromtimestamp(last_mtime).date()
            today = datetime.now().date()
            if file_date < today:
                return True
        except Exception:
            pass
        
        try:
            file.seek(0, 2)
            current_size = file.tell()
            if current_size > max_size_bytes:
                return True
        except Exception:
            pass
        
        return False
    
    return should_rotate


def init_log():
    """初始化所有日志处理器（数据驱动）"""
    logger.remove()

    # 日志根目录：项目根 / logs
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    log_root = os.path.join(project_root, 'logs')

    loggers_cfg = getattr(settings, "LOGGERS", {})
    if not hasattr(loggers_cfg, "keys"):
        return logger

    for name, cfg in loggers_cfg.items():
        if name.startswith("_"):
            continue

        file_path = getattr(cfg, "FILE", getattr(cfg, "file", f"logs/{name}/{name}.log"))
        
        # 如果是相对路径，强制转换为基于项目根目录 logs/ 的绝对路径
        if not os.path.isabs(file_path):
            # 确保路径格式为 logs/xxx/xxx.log
            if not file_path.startswith('logs/'):
                file_path = f"logs/{file_path}" if not file_path.startswith('/') else file_path.lstrip('/')
            file_path = os.path.join(project_root, file_path)
        
        level = getattr(cfg, "LEVEL", getattr(cfg, "level", "INFO"))
        max_size = getattr(cfg, "MAX_SIZE", getattr(cfg, "max_size", 100))
        retention = getattr(cfg, "RETENTION", getattr(cfg, "retention", 30))
        console = getattr(cfg, "CONSOLE", getattr(cfg, "console", False))

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        logger.add(
            file_path,
            level=level,
            format=settings.LOG_FORMAT,
            rotation=_make_rotation_func(max_size),
            retention=f"{retention} days",
            compression=None,
            enqueue=True,
            backtrace=True,
            diagnose=True,
            filter=lambda r, n=name: (
                (n == "error" and r["level"].no >= 40) or
                (n == "global" and (not r["extra"].get("name") or r["extra"].get("name") == "global")) or
                (n != "global" and n != "error" and r["extra"].get("name") == n)
            ),
        )

        if console:
            logger.add(
                sys.stderr,
                level=level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                filter=lambda r, n=name: (
                    (n == "global" and (not r["extra"].get("name") or r["extra"].get("name") == "global")) or
                    (n != "global" and r["extra"].get("name") == n)
                ),
            )

    return logger


def get_logger(name: str):
    """获取指定名称的日志记录器"""
    return logger.bind(name=name)
