"""LLM 密钥保险库 + base_url 安全守卫（B2，工单 82 拆分自 llm_provider_service.py）

两个安全关注点一处收口（深模块，静态方法组）：
- Fernet 加解密：主密钥读 LLM_ENCRYPTION_KEY（env 优先，其次 settings），
  未配置时加密拒绝（不降级明文入库）、解密按密钥缺失处理
- SSRF 守卫：私网 base_url 受 LLM.PROVIDER_BLOCK_PRIVATE_URL 开关控制
  （默认 false：本地 ollama/new-api 属文档化合法路径；云元数据端点在
  schema 层恒拒绝，与本开关无关）
"""
import os
from typing import Optional
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from config import settings
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.schemas.llm_provider import is_private_base_url

logger = get_logger("service.llm_vault")

_ENCRYPTION_ENV_KEY = "LLM_ENCRYPTION_KEY"


class LlmSecretVault:
    """密钥保管 + SSRF 守卫（无实例状态）"""

    @staticmethod
    def encryption_key() -> str:
        """主密钥：环境变量（含 .env 注入）优先，其次 settings 顶层/LLM 嵌套"""
        key = (
            os.environ.get(_ENCRYPTION_ENV_KEY)
            or settings.get("LLM_ENCRYPTION_KEY", "")
            or settings.get("LLM.ENCRYPTION_KEY", "")
        )
        return str(key).strip() if key else ""

    @staticmethod
    def fernet(key_material: str) -> Fernet:
        """由主密钥构造 Fernet（非法密钥抛业务异常，含生成命令提示）"""
        try:
            return Fernet(key_material.encode("utf-8"))
        except (ValueError, TypeError) as e:
            raise BusinessException(
                "LLM_ENCRYPTION_KEY 格式非法（需 Fernet 密钥，"
                "生成命令: python -c \"from cryptography.fernet import Fernet; "
                f"print(Fernet.generate_key().decode())\"）: {e}"
            )

    @staticmethod
    def encrypt_api_key(plain: Optional[str]) -> str:
        """明文 → Fernet 密文；未配置主密钥时直接拒绝（不降级明文入库）"""
        if not plain:
            return ""
        master = LlmSecretVault.encryption_key()
        if not master:
            raise BusinessException(
                "未配置 LLM_ENCRYPTION_KEY（Fernet 主密钥）：为避免明文入库已拒绝保存 API Key，"
                "请先在 .env 配置 LLM_ENCRYPTION_KEY 后重试"
            )
        return LlmSecretVault.fernet(master).encrypt(plain.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decrypt_api_key(encrypted: Optional[str]) -> str:
        """密文 → 明文；主密钥缺失/解密失败按密钥缺失处理（log warning，返回空串）"""
        if not encrypted:
            return ""
        master = LlmSecretVault.encryption_key()
        if not master:
            logger.warning("读取 LLM 供应商密钥失败：未配置 LLM_ENCRYPTION_KEY，按密钥缺失处理")
            return ""
        try:
            return LlmSecretVault.fernet(master).decrypt(encrypted.encode("utf-8")).decode("utf-8")
        except Exception as e:  # noqa: BLE001 密文损坏/主密钥轮换等一律按缺失处理
            logger.warning(f"LLM 供应商密钥解密失败，按密钥缺失处理: {e}")
            return ""

    @staticmethod
    def host_of(base_url: str) -> str:
        return urlparse(base_url).hostname or ""

    @staticmethod
    def ensure_public_base_url(base_url: str) -> None:
        """LLM.PROVIDER_BLOCK_PRIVATE_URL=true 时拒绝私网/环回 base_url（M6 式静态判定）"""
        if not bool(settings.get("LLM.PROVIDER_BLOCK_PRIVATE_URL", False)):
            return
        if is_private_base_url(base_url):
            raise BusinessException(
                "base_url 指向私网/环回地址，当前部署已禁用"
                "（LLM.PROVIDER_BLOCK_PRIVATE_URL=true）"
            )

    @staticmethod
    def validated_probe_base_url(base_url: str) -> str:
        """探测地址过 schema 同款校验（恒拒云元数据；格式合法）"""
        from platform_core.schemas.llm_provider import _validate_base_url

        return _validate_base_url(base_url)
