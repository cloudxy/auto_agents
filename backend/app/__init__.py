"""
FastAPI 应用核心模块 - 应用级初始化和全局配置

职责：
- 创建 FastAPI 实例
- 配置全局中间件（CORS等）
- 注册 API 路由（不关心具体业务实现）

注意：
- 不包含任何业务逻辑
- 不直接定义路由
- 通过 app/api/ 聚合器注册路由
- 初始化逻辑已移至 cors/app_init.py
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

def create_app():
    """创建 FastAPI 应用实例（不含初始化逻辑）"""
    app = FastAPI(
        title="Auto Agents API",
        description="自动化代理系统 API",
        version="1.0.0"
    )

    # CORS 配置（从 web.yml 配置文件读取）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS.ORIGINS,
        allow_credentials=settings.CORS.ALLOW_CREDENTIALS,
        allow_methods=settings.CORS.ALLOW_METHODS,
        allow_headers=settings.CORS.ALLOW_HEADERS,
    )

    # 请求 ID 中间件（链路追踪）
    from backend.app.middleware import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)

    # 注册统一异常处理器
    from platform_core.exceptions import register_exception_handlers
    register_exception_handlers(app)

    # 注册内部 API 路由（用于管理后台、前端、内部服务）
    from backend.app.api import api_router
    app.include_router(api_router, prefix="/api")

    # 注册外部 API 路由（用于第三方集成、开放平台、Webhook）
    from backend.app.external_api import external_api_router
    app.include_router(external_api_router, prefix="/external")
    
    return app