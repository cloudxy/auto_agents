from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import sys
import os

# 添加项目路径（仓库根目录，保证 platform_core / backend / config 可导入）
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# 导入模型
from platform_core.models import Base  # noqa

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 动态注入数据库连接串（配置即代码；密码取法与 platform_core.db.DBManager 对齐）
from config import settings  # noqa: E402

mysql_conf = settings.MYSQL.DEFAULT
_password = os.getenv('MYSQL_DEFAULT_PASSWORD') or str(settings.get('MYSQL_DEFAULT_PASSWORD', ''))
_db_url = (
    f"mysql+pymysql://{mysql_conf.USER}:{_password}@{mysql_conf.HOST}:"
    f"{mysql_conf.PORT}/{mysql_conf.DB_NAME}?charset=utf8mb4"
)
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
