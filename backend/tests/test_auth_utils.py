"""JWT 认证工具单元测试 - token 生成/验证/过期/无效场景

说明：backend/utils/auth.py 在导入时强制校验 JWT.SECRET_KEY 已配置
（否则抛 ValueError），这本身就是一条安全红线，故导入成功即通过。
"""
from datetime import timedelta

import jwt as pyjwt
from backend.utils.auth import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    """bcrypt 密码哈希与校验"""

    def test_hash_and_verify_roundtrip(self):
        hashed = get_password_hash("correct-horse-battery")
        assert hashed != "correct-horse-battery"
        assert verify_password("correct-horse-battery", hashed) is True

    def test_wrong_password_rejected(self):
        hashed = get_password_hash("correct-horse-battery")
        assert verify_password("wrong-password", hashed) is False

    def test_hash_is_salted(self):
        """同一密码两次哈希结果应不同（盐值随机）"""
        assert get_password_hash("same-password") != get_password_hash("same-password")


class TestAccessToken:
    """JWT Token 生成与解码"""

    def test_create_and_decode_roundtrip(self):
        token = create_access_token(data={"sub": "tester", "user_id": 42})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "tester"
        assert payload["user_id"] == 42
        assert "exp" in payload

    def test_expired_token_returns_none(self):
        token = create_access_token(
            data={"sub": "tester"},
            expires_delta=timedelta(minutes=-5),
        )
        assert decode_access_token(token) is None

    def test_invalid_token_returns_none(self):
        assert decode_access_token("not-a-valid-jwt") is None

    def test_token_signed_with_wrong_key_rejected(self):
        """用其他密钥签名的 token 必须被拒绝"""
        forged = pyjwt.encode(
            {"sub": "attacker"},
            "attacker-forged-key-not-the-real-one",
            algorithm=ALGORITHM,
        )
        assert decode_access_token(forged) is None


class TestSecretKeyGuard:
    """SECRET_KEY 强制校验红线"""

    def test_secret_key_is_configured(self):
        """导入 auth 模块成功即证明 SECRET_KEY 已通过强制校验"""
        assert SECRET_KEY
        assert SECRET_KEY != "change-me-in-production"
        assert ALGORITHM == "HS256"
