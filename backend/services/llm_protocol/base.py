"""协议适配层基座（方案 B · B-M1-1）：数据结构 + 共享外呼 + 错误脱敏"""
import httpx

from typing import Optional, Protocol, runtime_checkable

PROBE_TIMEOUT = 10.0


class ProtocolError(Exception):
    """协议外呼失败——只携带状态码与 reason，绝不携带响应体（脱敏沿用 llm_provider 约定）"""


class ModelInfo:
    """归一化模型标识"""

    __slots__ = ("id", "owned_by", "raw_name")

    def __init__(self, model_id: str, owned_by: str = "", raw_name: str = ""):
        self.id = model_id
        self.owned_by = owned_by
        self.raw_name = raw_name


class ModelList:
    """模型列表 + 对话模型过滤视图（可迭代）"""

    def __init__(self, models: list[ModelInfo], chat_filter):
        self._models = models
        self._chat_filter = chat_filter

    def __iter__(self):
        return iter(self._models)

    def __len__(self) -> int:
        return len(self._models)

    def all(self) -> list[ModelInfo]:
        return list(self._models)

    def chat_only(self) -> "ModelList":
        return ModelList([m for m in self._models if self._chat_filter(m.id)], self._chat_filter)

    def ids(self) -> list[str]:
        return [m.id for m in self._models]


class ChatRequest:
    """归一化对话请求（探测与业务调用共用同一构造器）"""

    __slots__ = ("url", "headers", "json_payload")

    def __init__(self, url: str, headers: dict, json_payload: dict):
        self.url = url
        self.headers = headers
        self.json_payload = json_payload


async def execute_json(
    client: Optional[httpx.AsyncClient], method: str, url: str, headers: dict,
    json_payload: Optional[dict] = None,
) -> dict:
    """统一外呼：trust_env=False（防本机代理劫持）；非 2xx 抛脱敏 ProtocolError"""
    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=PROBE_TIMEOUT, trust_env=False)
    try:
        resp = await client.request(method, url, headers=headers, json=json_payload)
        if resp.status_code >= 400:
            raise ProtocolError(f"HTTP {resp.status_code} {resp.reason_phrase}")
        return resp.json()
    except ProtocolError:
        raise
    except httpx.HTTPError as exc:
        raise ProtocolError(f"网络错误: {exc}") from exc
    except ValueError as exc:
        raise ProtocolError(f"响应不是合法 JSON: {exc}") from exc
    finally:
        if own:
            await client.aclose()


@runtime_checkable
class LlmProtocolAdapter(Protocol):
    """协议适配器接口：模型列表 / 对话构造 / 响应解析 / 对话模型过滤"""

    type_id: str
    display_name: str

    async def list_models(
        self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None
    ) -> ModelList: ...

    def build_chat(
        self, base_url: str, api_key: str, model: str,
        messages: list[dict], max_tokens: int = 1,
    ) -> ChatRequest: ...

    def parse_chat(self, resp_json: dict) -> str: ...

    def is_chat_model(self, model_id: str) -> bool: ...
