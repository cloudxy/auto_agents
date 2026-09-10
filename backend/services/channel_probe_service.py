"""渠道真伪探针（T-19）：采集走平台网关 chat 适配叶，列表走 admin HTTP。

10 维指纹与阈值不改。伪装只落库+通知：不关渠道、不改窗口/额度（GWT-07.6）。
禁止 DSN / new-api 方言。
"""
import asyncio
import time
import uuid

from backend.config_consts import (
    RELAY_PROBE_ENABLED,
    RELAY_PROBE_INTERVAL_SECONDS,
    RELAY_PROBE_LOCK_RENEWAL_SECONDS,
    RELAY_PROBE_LOCK_TTL_SECONDS,
)
from backend.repositories.newapi_repository import ChannelProbeResultRepository
from backend.services import channel_probe_score as _score_mod

DEFAULT_PROBE_QUESTIONS = _score_mod.DEFAULT_PROBE_QUESTIONS
_REF_SIMILARITY_SPOOF_THRESHOLD = _score_mod._REF_SIMILARITY_SPOOF_THRESHOLD
_first_by_category = _score_mod._first_by_category
_load_questions = _score_mod._load_questions
_score_probe_batch = _score_mod._score_probe_batch
from backend.services.gateway_models import items_from_payload, map_gateway_model
from backend.services.llm_gateway import admin as gw_admin
from backend.services.llm_gateway.chat import chat_completions
from backend.services.newapi_api import (
    NEWAPI_PROBE_LOCK_KEY,
    _cfg_manual_disabled,
    _channel_id_from_ref,
    _main_async_session,
    read_cfg_hash,
)
from backend.services.notify_service import NotifyService
from config import settings
from platform_core.logger import get_logger
from platform_core.queues import distributed_lock

logger = get_logger("api")


def _first_model(channel: dict | None) -> str:
    """目标模型名：优先 model_name，否则 models 逗号串首个。"""
    if not channel:
        return ""
    named = str(channel.get("model_name") or channel.get("model") or "").strip()
    if named:
        return named.split(",")[0].strip()
    models = str(channel.get("models") or "")
    return models.split(",")[0].strip() if models else ""


def _parse_probe_chat(data: object, model: str, latency_ms: int) -> dict:
    """适配叶 chat_completions 回包 → 探针统一结构。"""
    if not isinstance(data, dict):
        return _failed_probe_chat(model, latency_ms, "empty payload")
    choice = (data.get("choices") or [{}])[0] if isinstance(data.get("choices"), list) else {}
    content = str(((choice.get("message") or {}).get("content") or "")).strip()
    usage = data.get("usage") or {}
    reasoning = int(
        (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    )
    return {
        "ok": bool(content),
        "content": content,
        "latency_ms": latency_ms,
        "usage": usage if isinstance(usage, dict) else {},
        "model": str(data.get("model") or model),
        "reasoning_tokens": reasoning,
        "error": None if content else "empty content",
    }


def _failed_probe_chat(model: str, latency_ms: int, error: str) -> dict:
    return {
        "ok": False, "content": "", "latency_ms": latency_ms, "usage": {},
        "model": model, "reasoning_tokens": 0, "error": error,
    }


class ChannelProbeService:
    """网关模型真伪探针：chat 适配叶采集 + 三态判定落库；伪装不熔断。"""

    def __init__(self):
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._redis = None

    async def start(self) -> None:
        """启动探针循环（幂等；无 DSN / 无 new-api 客户端）。"""
        if self._running:
            return
        if not settings.get("RELAY.PROBE_ENABLED", RELAY_PROBE_ENABLED):
            logger.info("渠道真伪探针已禁用（RELAY.PROBE_ENABLED=false），不启动")
            return
        from platform_core.redis_async import get_async_redis as _get_async_redis

        self._redis = _get_async_redis()
        self._running = True
        self._loop_task = asyncio.create_task(
            self._tick_loop(), name="gateway-channel-probe",
        )
        interval = int(
            settings.get("RELAY.PROBE_INTERVAL_SECONDS", RELAY_PROBE_INTERVAL_SECONDS)
            or RELAY_PROBE_INTERVAL_SECONDS
        )
        logger.info(f"渠道真伪探针已启动（网关 chat 适配叶）: interval={interval}s")

    async def stop(self) -> None:
        """优雅停止（不关闭共享 Redis）。"""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._loop_task = None
        self._redis = None
        logger.info("渠道真伪探针已停止")

    async def _tick_loop(self) -> None:
        interval = int(
            settings.get("RELAY.PROBE_INTERVAL_SECONDS", RELAY_PROBE_INTERVAL_SECONDS)
            or RELAY_PROBE_INTERVAL_SECONDS
        )
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(f"渠道探针轮次失败: {e}")
            await asyncio.sleep(interval)

    async def _tick_once(self) -> None:
        """抢锁 → 网关模型列表 → 参考基线 → 逐目标探针（隔离）。"""
        lock_ttl = int(
            settings.get("RELAY.PROBE_LOCK_TTL_SECONDS", RELAY_PROBE_LOCK_TTL_SECONDS)
            or RELAY_PROBE_LOCK_TTL_SECONDS
        )
        lock_renewal = int(
            settings.get(
                "RELAY.PROBE_LOCK_RENEWAL_SECONDS", RELAY_PROBE_LOCK_RENEWAL_SECONDS,
            )
            or RELAY_PROBE_LOCK_RENEWAL_SECONDS
        )
        async with distributed_lock(
            self._redis, NEWAPI_PROBE_LOCK_KEY, ttl=lock_ttl, renewal=lock_renewal,
        ) as lock:
            if lock is None:
                return
            questions = _load_questions(
                str(settings.get("RELAY.PROBE_QUESTIONS_FILE", "") or "")
            )
            models = await self._list_mapped()
            if not models:
                logger.debug("网关模型列表为空，探针本轮跳过")
                return
            await self._run_batch(models, questions)

    async def _run_batch(self, models: list[dict], questions: list[dict]) -> None:
        ref = self._resolve_reference(models)
        ref_results = await self._collect_reference(ref, questions)
        batch_id = uuid.uuid4().hex
        ref_key = str((ref or {}).get("gateway_ref") or "")
        targets = await self._select_targets(models, ref_key)
        logger.info(
            f"渠道探针批次开始: batch_id={batch_id}, targets={len(targets)}, "
            f"ref={ref_key or '无'}"
        )
        for target in targets:
            try:
                await self._probe_channel(target, ref_results, questions, batch_id)
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"渠道探针失败（已隔离）: ref={target.get('gateway_ref')}, error={e}"
                )

    async def _list_mapped(self) -> list[dict]:
        try:
            payload = await gw_admin.list_models()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"网关模型列表不可达，探针本轮跳过: error={e}")
            return []
        out: list[dict] = []
        for raw in items_from_payload(payload):
            mapped = map_gateway_model(raw)
            if mapped is None:
                continue
            out.append({
                "gateway_ref": mapped.gateway_ref,
                "model_name": mapped.model_name,
                "name": mapped.model_name,
            })
        return out

    async def _select_targets(self, models: list[dict], ref_key: str) -> list[dict]:
        targets: list[dict] = []
        for item in models:
            if ref_key and str(item.get("gateway_ref") or "") == ref_key:
                continue
            raw = {}
            try:
                raw = await read_cfg_hash(
                    self._redis, gateway_ref=str(item.get("gateway_ref") or ""),
                ) or {}
            except Exception as e:  # noqa: BLE001
                logger.warning(f"探针读配置失败（仍探测）: error={e}")
            if _cfg_manual_disabled(raw):
                continue
            targets.append(item)
        return targets

    def _resolve_reference(self, models: list[dict]) -> dict | None:
        """PROBE_REFERENCE_CHANNEL 匹配 gateway_ref / model_name。"""
        spec = str(settings.get("RELAY.PROBE_REFERENCE_CHANNEL", "") or "").strip()
        if not spec:
            return None
        for item in models:
            if spec in (
                str(item.get("gateway_ref") or ""),
                str(item.get("model_name") or ""),
                str(item.get("name") or ""),
            ):
                return item
        logger.warning(f"参考模型未在网关列表找到: {spec}（本批无参考对比）")
        return None

    async def _collect_reference(
        self, ref: dict | None, questions: list[dict],
    ) -> dict | None:
        model = _first_model(ref) if ref else ""
        if not model:
            return None
        results = await self._collect_responses(model, questions)
        if results and all(not r.get("ok") for r in results.values()):
            logger.warning(f"参考模型探针全部失败（model={model}），本批无参考对比")
            return None
        return results

    async def _probe_chat(self, model: str, prompt: str) -> dict:
        """POST 平台网关 /v1/chat/completions（chat 适配叶，非 new-api）。"""
        started = time.monotonic()
        try:
            data = await chat_completions({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            })
            latency_ms = int((time.monotonic() - started) * 1000)
            return _parse_probe_chat(data, model, latency_ms)
        except Exception as e:  # noqa: BLE001
            latency_ms = int((time.monotonic() - started) * 1000)
            return _failed_probe_chat(model, latency_ms, str(e))

    async def _collect_responses(self, model: str, questions: list[dict]) -> dict:
        """按问题集逐题采集；知识截止题 +1 次复测，指令题 +2 次。"""
        results: dict = {}
        for item in questions:
            results[item["id"]] = await self._probe_chat(model, item["text"])
        cutoff_q = _first_by_category(questions, "knowledge_cutoff")
        if cutoff_q:
            results[f"{cutoff_q['id']}:repeat"] = await self._probe_chat(
                model, cutoff_q["text"],
            )
        inst_q = _first_by_category(questions, "instruction_following")
        if inst_q:
            results[f"{inst_q['id']}:repeat1"] = await self._probe_chat(
                model, inst_q["text"],
            )
            results[f"{inst_q['id']}:repeat2"] = await self._probe_chat(
                model, inst_q["text"],
            )
        return results

    async def _probe_channel(
        self, target: dict, ref_results: dict | None, questions: list[dict], batch_id: str,
    ) -> None:
        """采集 → 评分 → 落库。spoofed 不关渠道、不改窗口/额度（GWT-07.6）。"""
        ref = str(target.get("gateway_ref") or target.get("id") or "")
        model = _first_model(target)
        if not model:
            logger.warning(f"模型无可用名，跳过探针: ref={ref}")
            return
        cid = _channel_id_from_ref(ref or model)
        results = await self._collect_responses(model, questions)
        verdict, scores = _score_probe_batch(model, results, questions, ref_results)
        scores = dict(scores)
        scores["_gateway_ref"] = ref or model
        zh_q = _first_by_category(questions, "identity", lang="zh") or _first_by_category(
            questions, "identity",
        )
        latency = None
        if zh_q is not None:
            raw_lat = (results.get(zh_q["id"]) or {}).get("latency_ms")
            if raw_lat is not None:
                latency = int(raw_lat)
        await self._record_probe_result(
            channel_id=cid, model=model, verdict=verdict, scores=scores,
            latency_ms=latency, batch_id=batch_id,
        )
        logger.info(f"渠道探针完成: ref={ref}, model={model}, verdict={verdict}")
        if verdict == "spoofed":
            await NotifyService().notify_text(
                "channel.probe.spoofed",
                f"⚠ 模型 {ref}（{target.get('name', '')}）真伪探针判定 spoofed（model={model}）",
            )

    async def _record_probe_result(
        self,
        *,
        channel_id: int,
        model: str,
        verdict: str,
        scores: dict,
        latency_ms: int | None,
        batch_id: str,
    ) -> None:
        """channel_probe_results 落本库；失败仅告警。"""
        try:
            async with _main_async_session() as session:
                await ChannelProbeResultRepository(session).create_result(
                    channel_id=channel_id, model=model, verdict=verdict, scores=scores,
                    latency_ms=latency_ms, batch_id=batch_id,
                )
                await session.commit()
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"探针结果落库失败: channel_id={channel_id}, verdict={verdict}, error={e}"
            )
