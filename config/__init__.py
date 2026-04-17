"""
Dynaconf 配置管理 - 合并配置文件以简化目录结构
"""
from dynaconf import Dynaconf
import os

# 获取当前环境（默认本地开发环境）
current_env = os.getenv("APP_ENV", "local")

# 配置目录
config_dir = os.path.dirname(os.path.abspath(__file__))
default_config_dir = os.path.join(config_dir, "default")
env_config_dir = os.path.join(config_dir, current_env)

# 配置文件
settings_files = [
    # === 默认配置 (Default) ===
    os.path.join(default_config_dir, "settings.yml"),  # 全局通用配置
    os.path.join(default_config_dir, "api.yml"),       # API 服务配置
    os.path.join(default_config_dir, "web.yml"),       # Web 服务配置
    os.path.join(default_config_dir, "log.yml"),       # 日志配置
    os.path.join(default_config_dir, "jwt.yml"),       # JWT 认证配置
    os.path.join(default_config_dir, "storage.yml"),   # 存储配置
    os.path.join(default_config_dir, "admin.yml"),     # 管理后台配置
    os.path.join(default_config_dir, "official.yml"),  # 官方网站配置
    
    # === Scrapy 爬虫专用配置 ===
    os.path.join(config_dir, "scrapy", "default", "settings.yml"), # 爬虫基础配置
    os.path.join(config_dir, "scrapy", "default", "sites.yml"),    # 站点采集规则
    
    # === 环境特定覆盖 (Environment Overrides) ===
    os.path.join(env_config_dir, "settings.yml"),
    os.path.join(env_config_dir, "mysql.yml"),
    os.path.join(env_config_dir, "redis.yml"),
    os.path.join(env_config_dir, "web.yml"),
    os.path.join(env_config_dir, "log.yml"),
    
    # === Scrapy 环境特定覆盖 ===
    os.path.join(config_dir, "scrapy", current_env, "settings.yml"),
]

# 初始化 Dynaconf
settings = Dynaconf(
    envvar_prefix="AUTO_AGENTS",
    environments=False,
    settings_files=settings_files,
    dotenv_path=os.path.join(env_config_dir, ".env"),
    load_dotenv=True,
    merge_enabled=True,
    dotenv_override=True,
)

# 动态注入 Redis URL
for instance_key in settings.get("REDIS", {}).keys():
    cfg = settings.get(f"REDIS.{instance_key}", {})
    host = cfg.get("HOST", "127.0.0.1")
    port = cfg.get("PORT", 6379)
    db = cfg.get("DB", 0)
    password = cfg.get("PASSWORD", "")
    
    if password:
        url = f"redis://:{password}@{host}:{port}/{db}"
    else:
        url = f"redis://{host}:{port}/{db}"
    
    settings.set(f"REDIS.{instance_key}.URL", url)

__all__ = ["settings"]
