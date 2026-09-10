"""LiteLLM Proxy HTTP 适配叶（ADR-0010 / ADR-0014）。

从子模块按需导入：
- `llm_gateway.chat`：仅 `POST /v1/chat/completions`
- `llm_gateway.admin`：模型 / 部署 / spend / budget HTTP

禁止把 chat 与 admin 打进同一 ``__all__``（防 ``import *`` 偷渡 admin）。
本包不 re-export 任一子模块。llm_chat 平台出口只 import chat（T-16）。
"""

__all__: list[str] = []
