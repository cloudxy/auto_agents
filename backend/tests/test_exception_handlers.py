"""异常处理器测试 - 统一异常响应格式与注册完整性"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from platform_core.exceptions import (
    BusinessException,
    NotFoundException,
    register_exception_handlers,
)


def _make_test_app() -> FastAPI:
    """构建最小测试应用（仅注册异常处理器 + 触发路由）"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-business")
    async def raise_business():
        raise BusinessException(message="测试业务异常", code="TEST_BUSINESS", status_code=400)

    @app.get("/raise-not-found")
    async def raise_not_found():
        raise NotFoundException(resource="用户")

    @app.get("/raise-http")
    async def raise_http():
        raise HTTPException(status_code=418, detail="teapot")

    @app.get("/raise-unhandled")
    async def raise_unhandled():
        raise RuntimeError("boom")

    return app


class TestHandlerRegistration:
    """异常处理器注册完整性"""

    def test_all_handlers_registered(self, app):
        """create_app 应注册 4 类异常处理器（验证/应用/HTTP/兜底）"""
        from fastapi.exceptions import RequestValidationError
        from platform_core.exceptions.base import AppException

        handlers = app.exception_handlers
        assert RequestValidationError in handlers
        assert AppException in handlers
        assert HTTPException in handlers
        assert Exception in handlers


class TestAppExceptionResponse:
    """AppException 统一响应格式"""

    def test_business_exception_response_shape(self):
        client = TestClient(_make_test_app())
        resp = client.get("/raise-business")
        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "TEST_BUSINESS"
        assert body["message"] == "测试业务异常"
        assert body["data"] == {}
        assert "request_id" in body

    def test_not_found_exception_uses_404(self):
        client = TestClient(_make_test_app())
        resp = client.get("/raise-not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert "用户" in body["message"]


class TestHttpExceptionResponse:
    """FastAPI HTTPException 统一响应格式"""

    def test_http_exception_response_shape(self):
        client = TestClient(_make_test_app())
        resp = client.get("/raise-http")
        assert resp.status_code == 418
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "HTTP_418"
        assert body["message"] == "teapot"

    def test_unknown_route_returns_json_404(self, client):
        """未注册路由应返回 JSON 404（Starlette 默认形态）

        行为边界：路由未命中的 404 由 Starlette router 直接抛出，
        不经过统一 HTTPException handler，故格式为 {"detail": ...}
        而非 success/code 统一形态；路由内显式 raise 的 HTTPException
        才走统一 handler（见 test_http_exception_response_shape）。
        """
        resp = client.get("/api/v1/this-route-does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body


class TestUnhandledExceptionResponse:
    """未捕获异常兜底响应"""

    def test_unhandled_exception_returns_500_json(self):
        test_app = _make_test_app()
        # raise_server_exceptions=False 让兜底 handler 接管 500
        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.get("/raise-unhandled")
        assert resp.status_code == 500
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "INTERNAL_SERVER_ERROR"
        assert "request_id" in body
