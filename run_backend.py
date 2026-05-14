#!/usr/bin/env python3
"""
Backend 后端服务启动入口

使用方式：
    ./run_backend.py                           # 默认本地环境（APP_ENV=local）
    ./run_backend.py --env dev --no-reload     # 开发环境、关闭热重载
    ./run_backend.py --env prod --no-reload    # 生产环境
    ./run_backend.py --port 9200               # 临时覆盖端口

特性：
- 自动检测根 .venv 并以 venv 解释器重启（workspace 统一环境）
- --env 透传为 APP_ENV，驱动 config/<env>/*.yml 加载
- 端口预检：若端口已占用，直接报错退出
- 串行初始化：logger → db → storage → FastAPI app
"""
import os
import socket
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")


def _reexec_with_venv():
    """若存在根 .venv 且当前不是它，切换到 venv Python 再跑。"""
    if os.path.exists(VENV_PYTHON) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PYTHON):
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def main():
    _reexec_with_venv()
    sys.path.insert(0, PROJECT_ROOT)

    import argparse

    parser = argparse.ArgumentParser(description="Auto Agents Backend API")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None,
                        help="运行环境（透传为 APP_ENV，决定 config/<env>/ 层）")
    parser.add_argument("--host", type=str, default=None, help="监听地址")
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="启用热重载")
    parser.add_argument("--no-reload", action="store_true", help="禁用热重载（生产模式）")
    args = parser.parse_args()

    # --env 必须在 import config 之前生效
    if args.env:
        os.environ["APP_ENV"] = args.env

    from config import settings, APP_ENV

    host = args.host or settings.API.HOST
    port = args.port or settings.API.PORT
    reload_mode = args.reload if not args.no_reload else settings.API.DEBUG
    if args.no_reload:
        reload_mode = False

    if _port_in_use(host, port):
        print(f"❌ 端口 {host}:{port} 已被占用，启动终止")
        sys.exit(1)

    # 初始化基础设施
    print("🚀 Initializing Backend Core...")
    from platform_core import init_log, init_db, init_storage
    init_log()
    init_db()
    init_storage()

    from backend.app import create_app
    app = create_app()

    print("\n" + "=" * 60)
    print("🚀 Auto Agents Backend API 已启动")
    print("=" * 60)
    print(f"📍 服务地址: http://{host}:{port}")
    print(f"📖 API 文档: http://{host}:{port}/api/docs")
    print(f"🔧 热重载:   {'✅ 开启' if reload_mode else '❌ 关闭'}")
    print(f"📊 环境:     {APP_ENV}")
    print("=" * 60 + "\n")

    import uvicorn
    uvicorn.run(app=app, host=host, port=port, reload=reload_mode, log_level="info", access_log=True)


if __name__ == "__main__":
    main()
