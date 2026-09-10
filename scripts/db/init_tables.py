"""开发环境 create_all 基线表（已存在则跳过）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "local")

from sqlalchemy import create_engine  # noqa: E402

from config import settings  # noqa: E402
import platform_core.models  # noqa: F401,E402  注册全部模型到 Base.metadata
from platform_core.models.base import Base  # noqa: E402


def main() -> None:
    conf = settings.MYSQL.DEFAULT
    password = os.getenv("MYSQL_DEFAULT_PASSWORD") or str(settings.get("MYSQL_DEFAULT_PASSWORD", ""))
    url = (
        f"mysql+pymysql://{conf.USER}:{password}@{conf.HOST}:{conf.PORT}/{conf.DB_NAME}"
        "?charset=utf8mb4"
    )
    engine = create_engine(url)
    print(f"同步表结构 {conf.HOST}:{conf.PORT}/{conf.DB_NAME}")
    Base.metadata.create_all(bind=engine)
    print("已创建/已存在:", ", ".join(Base.metadata.tables))


if __name__ == "__main__":
    main()
