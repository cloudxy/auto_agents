"""参数验证器 - 通用字段验证函数

提供可复用的验证逻辑，供 Schema 类通过 @field_validator 调用
"""
import re


def validate_string_length(value: str, min_len: int = 1, max_len: int = 255) -> str:
    """验证字符串长度"""
    if not value or len(value.strip()) == 0:
        raise ValueError("字段不能为空")
    if len(value) < min_len:
        raise ValueError(f"字段长度不能少于 {min_len} 个字符")
    if len(value) > max_len:
        raise ValueError(f"字段长度不能超过 {max_len} 个字符")
    return value.strip()


def validate_email(value: str) -> str:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, value):
        raise ValueError("邮箱格式不正确")
    return value.lower()


def validate_phone(value: str) -> str:
    """验证手机号格式（中国大陆）"""
    pattern = r'^1[3-9]\d{9}$'
    if not re.match(pattern, value):
        raise ValueError("手机号格式不正确")
    return value


def sanitize_input(value: str) -> str:
    """清理输入，防止 XSS 攻击"""
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>.*?</iframe>',
    ]
    
    cleaned = value
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    return cleaned
