"""Backend 进程入口：python -m scripts.runlib.backend"""
from __future__ import annotations

import argparse
import logging
import sys

from .detect import port_in_use
from .venv import apply_env, reexec_with_venv


def _bridge_uvicorn_logging() -> None:
    from platform_core.logger import get_logger

    class _UvicornToLoguru(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                level: str | int = get_logger("api").level(record.levelname).name
            except ValueError:
                level = record.levelno
            frame, depth = logging.currentframe(), 0
            while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
                frame = frame.f_back
                depth += 1
            get_logger("api").opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []
    uv = logging.getLogger("uvicorn")
    uv.handlers = [_UvicornToLoguru()]
    uv.propagate = False


def create_app_for_reload():
    from platform_core import init_db, init_log, init_storage

    init_log()
    init_db()
    init_storage()
    _bridge_uvicorn_logging()
    from backend.app import create_app
    return create_app()


def main() -> None:
    reexec_with_venv()
    parser = argparse.ArgumentParser(description="Auto Agents Backend API")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    apply_env(args.env)

    from config import APP_ENV, settings
    from platform_core import init_db, init_log, init_storage

    host = args.host or settings.API.HOST
    port = args.port or settings.API.PORT
    reload_mode = False if args.no_reload else (args.reload or bool(settings.API.DEBUG))
    if args.no_reload:
        reload_mode = False

    if port_in_use(port, host if host != "0.0.0.0" else "127.0.0.1"):
        print(f"端口 {host}:{port} 已被占用，启动终止")
        sys.exit(1)

    print("Initializing Backend Core...")
    init_log()
    init_db()
    init_storage()
    _bridge_uvicorn_logging()

    if reload_mode:
        app_target = "scripts.runlib.backend:create_app_for_reload"
        factory_mode = True
    else:
        from backend.app import create_app
        app_target = create_app()
        factory_mode = False

    print(f"Backend  {host}:{port}  env={APP_ENV}  reload={reload_mode}")
    import uvicorn
    uvicorn.run(
        app=app_target, host=host, port=port, reload=reload_mode,
        factory=factory_mode, log_level="info", access_log=True, log_config=None,
        proxy_headers=settings.API.PROXY_HEADERS,
        forwarded_allow_ips=settings.API.FORWARDED_ALLOW_IPS,
    )


if __name__ == "__main__":
    main()
