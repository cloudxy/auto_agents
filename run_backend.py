#!/usr/bin/env python3
"""
Backend 后端服务启动入口

使用方式：
    ./run_backend.py                           # 推荐（自动使用 .venv）
    python3 run_backend.py                     # 直接运行
    python3 run_backend.py --no-reload         # 生产模式
"""
import sys
import os

# 自动检测并使用 backend/.venv 的 Python
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(PROJECT_ROOT, 'backend', '.venv', 'bin', 'python3')

if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    # 重新使用 .venv 的 Python 执行
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

# 将项目根目录添加到 Python 路径
sys.path.insert(0, PROJECT_ROOT)


def main():
    """启动 Backend API 服务"""
    import argparse
    from config import settings
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Auto Agents Backend API")
    parser.add_argument(
        "--host", 
        type=str, 
        default=settings.API.HOST,
        help=f"监听地址 (默认: {settings.API.HOST})"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=settings.API.PORT,
        help=f"监听端口 (默认: {settings.API.PORT})"
    )
    parser.add_argument(
        "--reload", 
        action="store_true",
        default=settings.API.DEBUG,
        help="启用热重载（开发模式）"
    )
    parser.add_argument(
        "--no-reload", 
        action="store_true",
        help="禁用热重载（生产模式）"
    )
    
    args = parser.parse_args()
    
    # --no-reload 优先于 --reload
    reload_mode = args.reload if not args.no_reload else False
    
    # 导入依赖（在解析参数后，避免不必要的导入开销）
    import uvicorn
    from core import initialize_app
    from backend.app import create_app
    
    # 1. 初始化基础设施（日志、数据库、存储）
    initialize_app()
    
    # 2. 创建 FastAPI 应用
    app = create_app()
    
    # 3. 打印启动信息
    print("\n" + "=" * 60)
    print("🚀 Auto Agents Backend API 已启动")
    print("=" * 60)
    print(f"📍 服务地址: http://{args.host}:{args.port}")
    print(f"📖 API 文档: http://{args.host}:{args.port}/api/docs")
    print(f"🔧 调试模式: {'✅ 开启' if reload_mode else '❌ 关闭'}")
    print(f"📊 环境配置: {'Development' if settings.API.DEBUG else 'Production'}")
    print("=" * 60 + "\n")
    
    # 4. 启动 Uvicorn 服务器
    uvicorn.run(
        app=app,
        host=args.host,
        port=args.port,
        reload=reload_mode,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
