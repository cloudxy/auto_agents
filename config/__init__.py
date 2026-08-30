"""
Dynaconf 配置管理 - 根目录统一配置入口

服务对象：
- backend（FastAPI 应用）
- scrapy（爬虫项目）
- 任何需要统一配置的子项目

加载顺序（后者覆盖前者）：
1. default/*.yml            —— 通用默认
2. scrapy/default/*.yml     —— 爬虫默认
3. <env>/*.yml              —— 环境覆盖
4. scrapy/<env>/*.yml       —— 爬虫环境覆盖
5. <env>/.env               —— 敏感变量（密码、密钥）
6. 环境变量 AUTO_AGENTS_*    —— 最高优先级
"""
from dynaconf import Dynaconf
from pathlib import Path
import os
import glob

current_env = os.getenv("APP_ENV", "local")

_config_dir = Path(__file__).resolve().parent


def _collect_yaml(*relative_dirs):
    """按给定子目录顺序收集所有 yml 文件，稳定排序后返回绝对路径列表。"""
    files = []
    for rel in relative_dirs:
        d = _config_dir / rel
        if d.is_dir():
            files.extend(sorted(str(p) for p in d.glob("*.yml")))
    return files


settings_files = (
    _collect_yaml("default")
    + _collect_yaml("scrapy/default")
    + _collect_yaml(current_env)
    + _collect_yaml(f"scrapy/{current_env}")
)

settings = Dynaconf(
    envvar_prefix="AUTO_AGENTS",
    environments=False,
    settings_files=settings_files,
    dotenv_path=str(_config_dir / current_env / ".env"),
    load_dotenv=True,
    merge_enabled=True,
    dotenv_override=True,
)

# 动态注入 Redis URL（供 scrapy-redis、aioredis 等直接用）
# 密码取法与 platform_core.db.DBManager._get_password 对齐：
# 环境变量 REDIS_<KEY>_PASSWORD > .env 扁平键（AUTO_AGENTS_ 前缀剥离后）> yml 嵌套占位值
# 注入后每个 Redis 实例可通过 REDIS.<instance>.URL 直接获取完整连接串
for instance_key in settings.get("REDIS", {}).keys():
    cfg = settings.get(f"REDIS.{instance_key}", {})
    host = cfg.get("HOST", "127.0.0.1")
    port = cfg.get("PORT", 6379)
    db = cfg.get("DB", 0)
    password = (
        os.getenv(f"REDIS_{instance_key}_PASSWORD")
        or str(settings.get(f"REDIS_{instance_key}_PASSWORD", ""))
        or cfg.get("PASSWORD", "")
    )

    auth = f":{password}@" if password else ""
    settings.set(f"REDIS.{instance_key}.URL", f"redis://{auth}{host}:{port}/{db}")

APP_ENV = current_env
CONFIG_DIR = str(_config_dir)

__all__ = ["settings", "APP_ENV", "CONFIG_DIR"]
