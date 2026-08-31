"""Webhook 密钥启动守卫单测（P0-2：默认占位符/空密钥拒绝启动）

防线对齐 JWT 守卫（backend/utils/auth.py 对同款占位符导入即抛错）。
lifespan 内调用（测试不进入 TestClient 上下文，不影响既有测试）。
"""
from unittest.mock import patch

import pytest

import backend.app as app_mod
from backend.app import _validate_runtime_secrets
from stubs import fake_settings


def test_guard_rejects_placeholder_secret():
    with patch.object(app_mod, "settings", fake_settings(**{
            "WEBHOOK.SECRET_KEY": "change-me-in-production"})):
        with pytest.raises(RuntimeError) as exc:
            _validate_runtime_secrets()
    # 报错必须给出可操作的配置指引
    assert "AUTO_AGENTS_WEBHOOK__SECRET_KEY" in str(exc.value)


def test_guard_rejects_empty_or_missing_secret():
    for secret in ("", "   ", None):
        with patch.object(app_mod, "settings", fake_settings(**{
                "WEBHOOK.SECRET_KEY": secret})):
            with pytest.raises(RuntimeError):
                _validate_runtime_secrets()


def test_guard_passes_with_real_secret():
    with patch.object(app_mod, "settings", fake_settings(**{
            "WEBHOOK.SECRET_KEY": "real-random-secret-from-dotenv-48chars"})):
        _validate_runtime_secrets()  # 不抛即通过
