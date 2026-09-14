"""LiteLLM Proxy 配置导出 CLI（L1 影子接入）

读 llm_providers（enabled 且未软删）→ 生成 LiteLLM Proxy 静态 config.yaml。

用法：
  uv run python backend/scripts/export_litellm_config.py                    # 缺省 deploy/litellm/config.gen.yaml
  uv run python backend/scripts/export_litellm_config.py --out /tmp/c.yaml  # 指定输出
  uv run python backend/scripts/export_litellm_config.py --redacted-sample  # 追加脱敏样例（key 掩码，可入日志/工单）

退出码：0 = 导出含模型条目；1 = 无可用供应商（空 model_list，失败可回退语义）；
        2 = 环境问题（如 LLM_ENCRYPTION_KEY 缺失导致解密失败由异常栈呈现）。

安全：生成文件含明文 api_key（gitignore 已登记 deploy/litellm/config.gen.yaml），
stdout 只输出统计与脱敏样例，绝不输出完整 key。
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.services.litellm import export_litellm_config  # noqa: E402
from config import settings  # noqa: E402
from platform_core.db import get_manager, init_db  # noqa: E402
from platform_core.logger import get_logger  # noqa: E402

logger = get_logger("scripts.litellm_export")


def _redact(key: str) -> str:
    """密钥掩码（首 4 + 尾 4，中间 ***；短密钥全掩）"""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


async def _run(args: argparse.Namespace) -> int:
    init_db()
    async for session in get_manager().get_async_session("DEFAULT"):
        result = await export_litellm_config(session, out_path=args.out)
        break
    print(
        f"provider_count={result.provider_count} model_count={result.model_count} "
        f"empty={result.empty} out={result.out_path}"
    )
    if args.redacted_sample and not result.empty:
        with open(result.out_path, encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith("api_key:"):
                    key = line.split("api_key:", 1)[1].strip().strip('"')
                    print("api_key: " + _redact(key))
                else:
                    print(line, end="")
    if result.empty:
        print("WARNING: 无可用 LLM 供应商，已生成空 model_list（影子对比将全量 missing_in_litellm）")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 LiteLLM Proxy 静态 config.yaml")
    default_out = str(settings.get("LITELLM.EXPORT.DEFAULT_OUT", "deploy/litellm/config.gen.yaml"))
    parser.add_argument("--out", default=default_out, help=f"输出路径（缺省 {default_out}）")
    parser.add_argument(
        "--redacted-sample", action="store_true",
        help="输出脱敏样例到 stdout（api_key 掩码，用于日志/工单留证）",
    )
    args = parser.parse_args()
    logger.info(f"CLI 导出启动: out={args.out}")
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
