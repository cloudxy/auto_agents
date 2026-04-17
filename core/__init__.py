"""核心基础设施层 - 统一管理日志、数据库与存储初始化"""
from core.log_init import init_log, get_logger
from core.db_init import init_db, redis_client, get_async_db
from core.storage_init import init_storage


def initialize_app():
    """初始化应用所需的所有组件"""
    print("=" * 60)
    print("初始化 Auto Agents 基础设施...")
    print("=" * 60)
    
    # 1. 初始化日志系统
    init_log()
    log = get_logger("global")
    
    # 2. 初始化数据库连接
    log.info("开始初始化数据库连接...")
    try:
        init_db()
        log.success("数据库初始化成功")
    except Exception as e:
        log.error(f"数据库初始化失败: {e}")
        raise
    
    # 3. 初始化存储系统
    log.info("开始初始化存储系统...")
    try:
        init_storage()
        log.success("存储系统初始化成功")
    except Exception as e:
        log.error(f"存储系统初始化失败: {e}")
        raise
    
    log.success("基础设施初始化完成！")
    print("=" * 60)
