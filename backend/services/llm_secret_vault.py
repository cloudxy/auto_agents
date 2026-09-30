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
from platform_core.outbound_guard import OutboundBlocked, assert_public_url, host_allowed
from platform_core.schemas.llm_provider import is_private_base_url

MSG_URL_BLOCKED = "连接失败：目标地址不允许访问"

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
    def private_url_blocked() -> bool:
        """私网 base_url 是否拦截：prod 恒拦（不受配置影响，审计 P0-8）；其余环境按
        LLM.PROVIDER_BLOCK_PRIVATE_URL（本地 new-api / ollama 属合法开发路径）"""
        if os.getenv("APP_ENV", "local") == "prod":
            return True
        return bool(settings.get("LLM.PROVIDER_BLOCK_PRIVATE_URL", False))

    @staticmethod
    def ensure_public_base_url(base_url: str) -> None:
        """拦截开启时拒绝私网/环回 base_url（静态判定；DNS 级校验见 assert_outbound_base_url）"""
        if not LlmSecretVault.private_url_blocked():
            return
        if is_private_base_url(base_url):
            raise BusinessException(MSG_URL_BLOCKED, code="LLM_PROVIDER_URL_BLOCKED")

    @staticmethod
    async def assert_outbound_base_url(base_url: str) -> None:
        """保存 / 探测 / 测试前的出站复检（审计 BUG-22 / P0-8）

        拦截开启时：DNS 解析后逐 IP 拒绝私网 / 环回 / 链路本地（127.0.0.1.nip.io 这类
        域名静态判定挡不住）；LLM.PROVIDER_PRIVATE_HOSTS_ALLOWED 可显式豁免运维信任的
        内网主机（如自建 ollama）。对外错误统一「连接失败」，不回显解析结果。
        """
        if not LlmSecretVault.private_url_blocked():
            return
        allowed = settings.get("LLM.PROVIDER_PRIVATE_HOSTS_ALLOWED", []) or []
        host = LlmSecretVault.host_of(base_url)
        if host and allowed and host_allowed(host, allowed):
            return
        try:
            await assert_public_url(base_url, allowed_ports=None)
        except OutboundBlocked as exc:
            logger.warning(f"LLM 供应商地址被出站守卫拒绝 | host={host}")
            raise BusinessException(MSG_URL_BLOCKED, code="LLM_PROVIDER_URL_BLOCKED") from exc

    @staticmethod
    def validated_probe_base_url(base_url: str) -> str:
        """探测地址过 schema 同款校验（恒拒云元数据；格式合法）"""
        from platform_core.schemas.llm_provider import _validate_base_url

        return _validate_base_url(base_url)
