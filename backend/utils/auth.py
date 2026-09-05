"""JWT 认证工具 - 强制验证 SECRET_KEY"""
from datetime import datetime, timedelta, timezone
from typing import Optional
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


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT Token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    # 脱敏：只记录用户标识，不记录 token 内容
    user_id = data.get("user_id", "unknown")
    logger.info(f"创建 Token | user_id={user_id} | exp={expire.isoformat()}")
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"无效 Token: {e}")
        return None
