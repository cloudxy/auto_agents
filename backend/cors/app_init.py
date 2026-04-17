"""应用初始化模块 - 负责所有基础设施的初始化（日志、数据库、存储）"""
from backend.cors.log_init import init_log, get_logger
from backend.cors.db_init import init_db
from backend.cors.storage_init import init_storage


def initialize_app():
    """初始化应用所需的所有组件
    
    日志策略：
    - 初始化过程日志 -> global_logger（仅初始化阶段）
    - 初始化错误日志 -> error_logger + global_logger（双写）
    - 各模块运行时日志 -> 按需动态获取（不预加载）
    """
    print("=" * 60)
    print("初始化 Auto Agents 应用...")
    print("=" * 60)
    
    # 1. 初始化日志系统
    init_log()
    
    # 2. 初始化数据库连接（使用临时 logger）
    global_log = get_logger("global")
    error_log = get_logger("error")
    
    global_log.info("开始初始化数据库连接...")
    try:
        init_db()
        global_log.success("数据库初始化成功")
    except Exception as e:
        error_msg = f"数据库初始化失败: {e}"
        error_log.error(error_msg)  # 同步到 error 日志
        raise
    
    # 3. 初始化存储系统
    global_log.info("开始初始化存储系统...")
    try:
        init_storage()
        global_log.success("存储系统初始化成功")
    except Exception as e:
        error_msg = f"存储系统初始化失败: {e}"
        error_log.error(error_msg)  # 同步到 error 日志
        raise
    
    global_log.success("应用初始化完成！")
    print("=" * 60)
