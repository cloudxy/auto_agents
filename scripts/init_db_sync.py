"""
数据库表初始化脚本（同步版本）
用于在开发环境中快速同步所有模型到数据库
"""
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

import os
os.environ.setdefault("APP_ENV", "local")

from sqlalchemy import create_engine
from config import settings
from platform_core.models.base import Base

def init_tables():
    """初始化所有数据库表"""
    try:
        # 构造 MySQL URL
        mysql_conf = settings.MYSQL.DEFAULT
        password = os.getenv('MYSQL_DEFAULT_PASSWORD') or str(mysql_conf.PASSWORD)
        db_url = f"mysql+aiomysql://{mysql_conf.USER}:{password}@{mysql_conf.HOST}:{mysql_conf.PORT}/{mysql_conf.DB_NAME}?charset=utf8mb4"
        
        # 使用同步引擎进行建表（避开异步上下文管理器问题）
        sync_url = db_url.replace("mysql+aiomysql", "mysql+pymysql")
        engine = create_engine(sync_url, echo=True)
        
        print(f"正在连接数据库: {mysql_conf.HOST}:{mysql_conf.PORT}/{mysql_conf.DB_NAME}")
        print(f"密码长度: {len(mysql_conf.PASSWORD) if mysql_conf.PASSWORD else 0}")
        print(f"环境变量 MYSQL_DEFAULT_PASSWORD: {os.getenv('MYSQL_DEFAULT_PASSWORD')}")
        print("开始同步表结构...")
        
        # 导入所有模型以确保它们被注册到 Base.metadata
        from platform_core.models.user import User
        from platform_core.models.spider_task import SpiderTask
        from platform_core.models.system_config import SystemConfig
        
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        
        print("✅ 数据库表结构同步成功！")
        print("已创建的表:", list(Base.metadata.tables.keys()))
        
    except Exception as e:
        print(f"❌ 数据库表结构同步失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    init_tables()
