"""JWT 认证工具 - 强制验证 SECRET_KEY"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import jwt
import bcrypt
from platform_core.logger import get_logger
from config import settings

logger = get_logger("api")

# JWT 配置（强制验证）
SECRET_KEY = settings.JWT.SECRET_KEY
if not SECRET_KEY or SECRET_KEY == "change-me-in-production":
    raise ValueError(
        "⚠️ 严重安全漏洞：JWT.SECRET_KEY 未配置或使用了默认值！\n"
        "请在环境变量中设置 AUTO_AGENTS_JWT__SECRET_KEY，或在 config/{env}/jwt.yml 中覆盖。"
    )

ALGORITHM = getattr(settings.JWT, "ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings.JWT, "ACCESS_TOKEN_EXPIRE_MINUTES", 30)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def _bcrypt_rounds() -> int:
    raw = os.environ.get("BCRYPT_ROUNDS") or str(settings.get("AUTH.BCRYPT_ROUNDS", 12))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 12
    return max(4, min(n, 14))


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    salt = bcrypt.gensalt(rounds=_bcrypt_rounds())
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT Token"""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    # typ 区分访问 / 刷新令牌（决策 D10）：refresh 令牌不能拿来当访问令牌
    to_encode.setdefault("typ", "access")
    to_encode.update({"exp": expire, "iat": int(now.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    # 脱敏：只记录用户标识，不记录 token 内容
    user_id = data.get("user_id", "unknown")
    logger.info(f"创建 Token | user_id={user_id} | exp={expire.isoformat()}")
    return encoded_jwt


def decode_token_any(token: str, *, verify_exp: bool = True) -> Optional[dict]:
    """解码并验签任意类型的本站令牌（访问 / 刷新）；失败返回 None"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                          options={"verify_exp": verify_exp})
    except jwt.InvalidTokenError:
        return None


def decode_access_token(token: str) -> Optional[dict]:
    """解码访问令牌；刷新令牌（typ=refresh）一律拒绝"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ", "access") != "access":
            logger.warning("拒绝非访问令牌用于鉴权")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"无效 Token: {e}")
        return None
