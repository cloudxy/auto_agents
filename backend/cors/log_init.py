"""日志初始化模块 - 数据驱动，支持动态配置"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from loguru import logger
from config import settings


def _make_rotation_func(max_size_mb: int):
    """创建轮转函数：按天 + 按大小轮转"""
    max_size_bytes = max_size_mb * 1024 * 1024

    def should_rotate(message, file):
        # 1. 按天轮转（通过文件修改时间判断）
        try:
            # 获取文件的最后修改时间
            last_mtime = os.stat(file.name).st_mtime
            file_date = datetime.fromtimestamp(last_mtime).date()
            today = datetime.now().date()
            
            # 如果文件是昨天或更早创建的，需要轮转
            if file_date < today:
                return True
        except Exception:
            pass
        
        # 2. 按大小轮转（防止单文件过大）
        try:
            file.seek(0, 2)  # 移动到文件末尾
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

    # 获取项目根目录（backend/cors 的上两级目录）
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    loggers_cfg = getattr(settings, "LOGGERS", {})
    if not hasattr(loggers_cfg, "keys"):
        return logger

    for name, cfg in loggers_cfg.items():
        if name.startswith("_"):
            continue

        # 兼容大小写配置键
        file_path = getattr(cfg, "FILE", getattr(cfg, "file", f"logs/{name}/{name}.log"))
        
        # 如果是相对路径，转换为基于项目根目录的绝对路径
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_root, file_path)
        
        level = getattr(cfg, "LEVEL", getattr(cfg, "level", "INFO"))
        max_size = getattr(cfg, "MAX_SIZE", getattr(cfg, "max_size", 100))
        retention = getattr(cfg, "RETENTION", getattr(cfg, "retention", 30))
        console = getattr(cfg, "CONSOLE", getattr(cfg, "console", False))
        rotate_hour = getattr(cfg, "ROTATE_HOUR", getattr(cfg, "rotate_hour", 3))

        # 确保日志目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # 文件处理器：按天 + 按大小轮转，不压缩
        # 关键：通过 filter 实现日志隔离
        # - global/error: 接收所有未指定 name 的日志（extra 为空）
        # - api/admin/spider: 仅接收 name 匹配的日志
        logger.add(
            file_path,
            level=level,
            format=settings.LOG_FORMAT,
            rotation=_make_rotation_func(max_size),  # 使用自定义轮转函数
            retention=f"{retention} days",
            compression=None,  # 不压缩
            enqueue=True,
            backtrace=True,
            diagnose=True,
            filter=lambda r, n=name: (
                # error 日志：接收所有 ERROR 级别及以上
                (n == "error" and r["level"].no >= 40) or
                # global 日志：接收未指定 name 的日志 + 明确绑定 name="global" 的日志
                (n == "global" and (not r["extra"].get("name") or r["extra"].get("name") == "global")) or
                # 其他模块日志：严格匹配 name
                (n != "global" and n != "error" and r["extra"].get("name") == n)
            ),
        )

        # 控制台处理器（仅 global）
        if console:
            logger.add(
                sys.stderr,
                level=level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                filter=lambda r, n=name: (
                    # 控制台仅显示 global 日志（包括未绑定和明确绑定的）
                    (n == "global" and (not r["extra"].get("name") or r["extra"].get("name") == "global")) or
                    # 或其他模块明确绑定的日志
                    (n != "global" and r["extra"].get("name") == n)
                ),
            )

    return logger


def get_logger(name: str):
    """获取指定名称的日志记录器"""
    return logger.bind(name=name)


# 动态生成便捷函数（基于 LOGGERS 配置）
def _build_convenience_funcs():
    loggers_cfg = getattr(settings, "LOGGERS", {})
    if not hasattr(loggers_cfg, "keys"):
        return

    module = sys.modules[__name__]
    for name in loggers_cfg.keys():
        if name.startswith("_"):
            continue
        func_name = f"{name}_logger"
        setattr(module, func_name, lambda n=name: get_logger(n))


_build_convenience_funcs()
