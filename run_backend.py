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
- --reload 走 import string 工厂（create_app_for_reload）：uvicorn 对 app 对象 +
  reload 直接 exit 1；且 reloader 子进程是 spawn 出的全新解释器，工厂内需重做
  日志/DB/存储初始化与 uvicorn→loguru 日志接管
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


def _bridge_uvicorn_logging() -> None:
    """uvicorn 三类日志改投 loguru（enqueue 文件 sink）：默认 StreamHandler 同步写
    stdout/stderr，若 stdout 是无人排水的管道（IDE 终端 `| head`、排水线程死亡），
    每请求一行的 access log 写满管道后会永久阻塞事件循环，整进程僵死。

    幂等：父进程（main）与 --reload 子进程（create_app_for_reload）各调一次。
    挂单一 handler 于 "uvicorn" 父 logger：access/error 清空自有 handler 后
    经 propagate 上浮单次落地（若三者都挂 handler，每条记录父子各触发一次，日志翻倍；
    子级 propagate=False 则记录直接丢弃）。
    """
    import logging

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
    """--reload 子进程内的 app 工厂（uvicorn 经 import string 调用）。

    uvicorn reloader 用 multiprocessing spawn 拉起全新解释器执行本函数：父进程
    main() 已做的 init_log/init_db/init_storage 与 uvicorn→loguru 日志接管均不随
    进程继承，必须在此重做——否则子进程日志退化为 loguru 默认 stderr sink（裸
    stdout/stderr），且 access log 因 "uvicorn" logger 无 handler 而整批丢失。
    （uvicorn 侧 subprocess_started 仅调 config.configure_logging()；log_config=None
    不会重挂 StreamHandler，故此处预设的接管不会被重置。）
    """
    from platform_core import init_log, init_db, init_storage

    init_log()
    init_db()
    init_storage()
    _bridge_uvicorn_logging()

    from backend.app import create_app
    return create_app()


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
        print(f"端口 {host}:{port} 已被占用，启动终止")
        sys.exit(1)

    # 初始化基础设施
    print("Initializing Backend Core...")
    from platform_core import init_log, init_db, init_storage
    init_log()
    init_db()
    init_storage()

    # uvicorn→loguru 日志接管：须在 uvicorn.run 之前挂好（父进程侧；
    # reload 子进程侧由 create_app_for_reload 自行挂）
    _bridge_uvicorn_logging()

    if reload_mode:
        # reload 模式：uvicorn 对非 import string 的 app 对象 + reload 直接
        # exit 1（uvicorn/main.py: "You must pass the application as an import
        # string to enable 'reload' or 'workers'."），必须传工厂字符串；
        # 父进程不装配 app（服务进程是 reloader spawn 出的子进程）
        app_target = "run_backend:create_app_for_reload"
        factory_mode = True
    else:
        # 非 reload（compose/生产）：沿用 app 对象路径，行为不变
        from backend.app import create_app
        app_target = create_app()
        factory_mode = False

    print("\n" + "=" * 60)
    print("Auto Agents Backend API 已启动")
    print("=" * 60)
    print(f"服务地址: http://{host}:{port}")
    print(f"API 文档: http://{host}:{port}/api/docs")
    print(f"热重载:   {'开启' if reload_mode else '关闭'}")
    print(f"环境:     {APP_ENV}")
    print("=" * 60 + "\n")

    import uvicorn

    uvicorn.run(
        app=app_target, host=host, port=port, reload=reload_mode,
        factory=factory_mode,
        log_level="info", access_log=True,
        # 跳过 uvicorn 自带 dictConfig（其 StreamHandler 会重置上面预置的接管，
        # 恢复对 stdout 的同步写；reload 子进程内同样只设 level 不重挂 handler）；
        # 日志统一经 loguru enqueue 落盘
        log_config=None,
        # 反代信任头：仅 FORWARDED_ALLOW_IPS 内的反代可改写 X-Forwarded-For
        # （按 IP 限流的来源 IP 依赖此头；配置见 config/default/api.yml）
        proxy_headers=settings.API.PROXY_HEADERS,
        forwarded_allow_ips=settings.API.FORWARDED_ALLOW_IPS,
    )


if __name__ == "__main__":
    main()
