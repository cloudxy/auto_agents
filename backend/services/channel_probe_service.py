"""new-api 渠道真伪探针服务（阶段三）

职责（独立 asyncio task，与调度器各自间隔、同 Redis 锁命名空间不同锁名）：
- 10 维行为指纹体检：身份提问 / 知识截止 / 数值推理 / 指令遵循 / 延迟测量 /
  reasoning_tokens 异常 / 价格异常 / 同题逐字重复（缓存指纹）/ 格式稳定性 / 中英一致性
- 同批边界输入分别打参考渠道（PROBE_REFERENCE_CHANNEL）与待检渠道：
  difflib 答案相似度 + 启发式（延迟比 / 逐字重复 / 身份回答矛盾）
  → verdict original / spoofed / offline → 写 channel_probe_results（batch_id=uuid hex）
- 采集：httpx POST {BASE_URL}/v1/chat/completions（model=待检渠道模型，PROBE_API_KEY 优先）

问题集：内置默认 + 可选 NEWAPI.PROBE_QUESTIONS_FILE JSON 覆盖（格式见 _load_questions）。
"""
import asyncio
import difflib
import json
import re
import uuid

import redis.asyncio as aioredis

from backend.repositories.newapi_repository import ChannelProbeResultRepository
from backend.services.newapi_api import (
    CHANNEL_STATUS_ENABLED,
    NEWAPI_PROBE_LOCK_KEY,
    NewapiApiClient,
    _main_async_session,
)
from backend.services.notify_service import NotifyService
from config import settings
from backend.config_consts import (NEWAPI_ENABLED)
from platform_core.logger import get_logger
from platform_core.queues import distributed_lock

logger = get_logger("api")

# 有参考渠道时，同题答案平均相似度低于该阈值判 spoofed（正品同模型应高度一致）
_REF_SIMILARITY_SPOOF_THRESHOLD = 0.15

# 探针巡检间隔默认值（秒，1 天）：start() 日志与 _tick_loop() 两处共用
_PROBE_INTERVAL_DEFAULT = 86400

# 常见模型家族关键词（身份矛盾启发式：答案提及他族模型名即视为矛盾信号）
_KNOWN_MODEL_FAMILIES: dict[str, tuple[str, ...]] = {
    "gpt": ("gpt", "chatgpt", "o1", "o3", "o4"),
    "claude": ("claude",),
    "gemini": ("gemini",),
    "glm": ("glm", "chatglm", "智谱"),
    "qwen": ("qwen", "通义", "千问"),
    "deepseek": ("deepseek",),
    "llama": ("llama",),
    "mistral": ("mistral", "mixtral"),
    "kimi": ("kimi", "moonshot"),
    "doubao": ("doubao", "豆包"),
    "ernie": ("ernie", "文心"),
    "hunyuan": ("hunyuan",),
}

# 知识截止题的拒答特征（拒答 → 该维 0 分，作为伪装信号之一记录）
_REFUSAL_MARKERS = ("我不知道", "无法提供", "无法访问", "作为一个 ai", "as an ai", "i don't know", "i cannot")

# 内置默认探针问题集（PROBE_QUESTIONS_FILE 可整体覆盖，字段契约一致）
DEFAULT_PROBE_QUESTIONS: list[dict] = [
    {"id": "identity_zh", "category": "identity", "lang": "zh",
     "text": "你是什么模型？请只回答你的模型名称。"},
    {"id": "identity_en", "category": "identity", "lang": "en",
     "text": "What model are you? Reply with the model name only."},
    {"id": "knowledge_cutoff_zh", "category": "knowledge_cutoff", "lang": "zh",
     "text": "请说出一件 2025 年发生的具体事件（包含月份）。如果你不了解 2025 年的事件，请直接说明。"},
    {"id": "knowledge_cutoff_en", "category": "knowledge_cutoff", "lang": "en",
     "text": "Name one specific event that happened in 2025 (include the month). "
             "If you do not know about 2025 events, say so."},
    {"id": "math_reasoning", "category": "math_reasoning", "lang": "zh",
     "text": "请计算 137 × 89 - 2048 的值，只输出最终数字。", "expected": 10145},
    {"id": "instruction_following", "category": "instruction_following", "lang": "zh",
     "text": "请严格按照以下格式输出，共两行，不要输出任何其他内容：\nRED\nBLUE",
     "expected_lines": ["RED", "BLUE"]},
]


def _first_by_category(questions: list[dict], category: str, lang: str | None = None) -> dict | None:
    """取指定类别（可选语言）的第一道题"""
    for q in questions:
        if q.get("category") != category:
            continue
        if lang is not None and str(q.get("lang") or "") != lang:
            continue
        return q
    return None


def _text_sim(a: str, b: str) -> float:
    """difflib 相似度（空串记 0）"""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _is_substantive(text: str) -> bool:
    """非空且非拒答"""
    t = (text or "").strip()
    if not t:
        return False
    lowered = t.lower()
    return not any(marker in lowered for marker in _REFUSAL_MARKERS)


def _model_family(model: str) -> str | None:
    """模型名 → 已知家族（未知模型返回 None）"""
    lowered = (model or "").lower()
    for family, tokens in _KNOWN_MODEL_FAMILIES.items():
        if any(token in lowered for token in tokens):
            return family
    return None


def _identity_mentions(content: str, family: str | None) -> tuple[bool, bool]:
    """身份回答分析：返回（提及本族模型, 提及他族模型）"""
    lowered = (content or "").lower()
    own = bool(family) and any(
        token in lowered for token in _KNOWN_MODEL_FAMILIES.get(family, ())
    )
    other = any(
        token in lowered
        for fam, tokens in _KNOWN_MODEL_FAMILIES.items()
        if fam != family
        for token in tokens
    )
    return own, other


def _load_questions(path: str) -> list[dict]:
    """内置默认问题集 + 可选 JSON 文件覆盖

    文件契约（数组或 {"questions": [...]}）：每项必填 id/category/text，
    可选 lang/expected（数值推理期望值）/expected_lines（指令遵循期望行）。
    加载或校验失败回退内置默认（不中断巡检）。
    """
    defaults = [dict(q) for q in DEFAULT_PROBE_QUESTIONS]
    if not path:
        return defaults
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(items, list) or not items:
            raise ValueError("问题集为空或格式非数组")
        for item in items:
            if not item.get("id") or not item.get("category") or not item.get("text"):
                raise ValueError(f"问题缺少必填字段: {item}")
        logger.info(f"探针问题集已从文件加载: path={path}, count={len(items)}")
        return items
    except Exception as e:  # noqa: BLE001
        logger.warning(f"探针问题文件加载失败，回退内置默认: path={path}, error={e}")
        return defaults


def _score_probe_batch(
    requested_model: str,
    results: dict,
    questions: list[dict],
    ref_results: dict | None = None,
) -> tuple[str, dict]:
    """10 维评分 + verdict 判定（纯函数，便于单测三分支）

    - offline：无采集结果或过半调用失败（渠道不可用）
    - spoofed：身份回答提及他族模型（身份矛盾）/ 知识截止题逐字重复（缓存指纹）/
      有参考渠道且同题相似度均值 < _REF_SIMILARITY_SPOOF_THRESHOLD
    - original：其余情形（个别维度低分仅记录于 scores，供人工复核）
    """
    calls = list(results.values())
    ok_calls = [c for c in calls if c.get("ok")]
    if not calls or len(ok_calls) * 2 < len(calls):
        return "offline", {"total_calls": len(calls), "ok_calls": len(ok_calls)}

    scores: dict = {}
    family = _model_family(requested_model)
    zh_q = _first_by_category(questions, "identity", lang="zh") or _first_by_category(questions, "identity")
    zh_ident = (results.get(zh_q["id"]) or {}) if zh_q else {}
    en_q = _first_by_category(questions, "identity", lang="en")
    en_ident = (results.get(en_q["id"]) or {}) if en_q else {}

    # 1) 身份提问：回答应提及请求模型所属家族，且不出现他族模型名
    own, other = _identity_mentions(zh_ident.get("content"), family)
    scores["identity"] = 1.0 if own else 0.0

    # 10) 中英一致性：zh/en 身份回答方向一致（都同族且都不矛盾）
    en_own, en_other = _identity_mentions(en_ident.get("content"), family)
    scores["zh_en_consistency"] = 1.0 if (own and en_own) else (0.5 if (own or en_own) else 0.0)

    # 2) 知识截止：非空且非拒答
    cutoff_q = _first_by_category(questions, "knowledge_cutoff")
    cutoff_content = ((results.get(cutoff_q["id"]) or {}).get("content") or "") if cutoff_q else ""
    scores["knowledge_cutoff"] = 1.0 if _is_substantive(cutoff_content) else 0.0

    # 3) 数值推理：确定性算术命中（expected 由问题集提供）
    math_q = _first_by_category(questions, "math_reasoning")
    math_content = ((results.get(math_q["id"]) or {}).get("content") or "") if math_q else ""
    expected = (math_q or {}).get("expected")
    digits = re.findall(r"-?\d+", str(math_content).replace(",", ""))
    scores["math_reasoning"] = 1.0 if expected is not None and str(expected) in digits else 0.0

    # 4) 指令遵循：精确多行格式
    inst_q = _first_by_category(questions, "instruction_following")
    inst_content = ((results.get(inst_q["id"]) or {}).get("content") or "") if inst_q else ""
    expected_lines = (inst_q or {}).get("expected_lines") or []
    lines = [ln.strip() for ln in inst_content.strip().splitlines() if ln.strip()]
    scores["instruction_following"] = 1.0 if expected_lines and lines == expected_lines else 0.0

    # 5) 延迟测量：相对参考渠道的延迟比（异常过快/过慢降分；无参考只记录不判罚）
    scores["latency"] = 1.0
    if ref_results and zh_q:
        ref_lat = int(((ref_results.get(zh_q["id"]) or {}).get("latency_ms")) or 0)
        latency = int(zh_ident.get("latency_ms") or 0)
        if ref_lat > 0 and latency > 0:
            ratio = latency / ref_lat
            scores["latency_ratio"] = round(ratio, 3)
            scores["latency"] = 1.0 if 0.2 <= ratio <= 5.0 else 0.5

    # 6) reasoning_tokens 异常：非 o 系模型却返回 reasoning_tokens 字段
    reasoning_tokens = int(zh_ident.get("reasoning_tokens") or 0)
    is_o_series = re.match(r"^o[134]([-.\b]|$)", requested_model.lower()) is not None
    scores["reasoning_tokens_anomaly"] = 0.0 if (reasoning_tokens > 0 and not is_o_series) else 1.0

    # 7) 价格异常（退化口径，无价目表）：usage 缺失/为零，或回包模型家族与请求不符
    usage = zh_ident.get("usage") or {}
    total_tokens = int(usage.get("total_tokens") or 0)
    resp_family = _model_family(str(zh_ident.get("model") or ""))
    family_match = family is None or resp_family is None or resp_family == family
    scores["price_anomaly"] = 1.0 if (total_tokens > 0 and family_match) else 0.5

    # 8) 同题逐字重复（缓存指纹）：知识截止题原样复问，逐字相同即可疑
    if cutoff_q:
        repeat = results.get(f"{cutoff_q['id']}:repeat") or {}
        verbatim = bool(cutoff_content) and cutoff_content == (repeat.get("content") or "")
        scores["verbatim_repeat"] = 0.0 if verbatim else 1.0

    # 9) 格式稳定性：指令题三连答非空且两两相似
    if inst_q:
        r1 = (results.get(f"{inst_q['id']}:repeat1") or {}).get("content") or ""
        r2 = (results.get(f"{inst_q['id']}:repeat2") or {}).get("content") or ""
        sims = [_text_sim(inst_content, r1), _text_sim(inst_content, r2), _text_sim(r1, r2)]
        scores["format_stability"] = 1.0 if all(s >= 0.6 for s in sims) else 0.5

    # 参考相似度：同题答案与参考渠道的平均 difflib 相似度
    ref_sim: float | None = None
    if ref_results:
        sims = []
        for q in questions:
            mine = (results.get(q["id"]) or {}).get("content") or ""
            theirs = (ref_results.get(q["id"]) or {}).get("content") or ""
            if mine and theirs:
                sims.append(_text_sim(mine, theirs))
        if sims:
            ref_sim = sum(sims) / len(sims)
            scores["ref_similarity"] = round(ref_sim, 4)

    # 评审 m-6：请求模型家族无法识别（family=None）时，任何已知家族词出现在
    # 身份回答中都会被 _identity_mentions 记为 other——正品渠道会被误判
    # spoofed，此时「身份矛盾」不参与 verdict（scores 保留记录，供人工复核）
    identity_contradiction = family is not None and (other or en_other)
    if (
        identity_contradiction
        or scores.get("verbatim_repeat") == 0.0
        or (ref_sim is not None and ref_sim < _REF_SIMILARITY_SPOOF_THRESHOLD)
    ):
        return "spoofed", scores
    return "original", scores


def _first_model(channel: dict | None) -> str:
    """渠道 models 逗号串的首个模型（探针按模型路由采集）"""
    if not channel:
        return ""
    models = str(channel.get("models") or channel.get("model") or "")
    return models.split(",")[0].strip() if models else ""


class ChannelProbeService:
    """new-api 渠道真伪探针：周期批次巡检 + 三态判定落库"""

    def __init__(self):
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._redis: aioredis.Redis | None = None
        self._api: NewapiApiClient | None = None

    # ── 生命周期 ──────────────────────────────────────────────
    async def start(self) -> None:
        """启动探针循环（幂等；NEWAPI.ENABLED / PROBE_ENABLED 分层开关，关闭时 log 一行）"""
        if self._running:
            return
        if not settings.get("NEWAPI.ENABLED", NEWAPI_ENABLED):
            logger.info("new-api 集成总开关关闭（NEWAPI.ENABLED=false），渠道探针不启动")
            return
        if not settings.get("NEWAPI.PROBE_ENABLED", False):
            logger.info("渠道真伪探针已禁用（NEWAPI.PROBE_ENABLED=false），不启动")
            return
        from platform_core.redis_async import get_async_redis as _get_async_redis

        self._redis = _get_async_redis()  # B3 归一门面
        self._api = NewapiApiClient()
        self._running = True
        self._loop_task = asyncio.create_task(self._tick_loop(), name="newapi-channel-probe")
        interval = int(
            settings.get("NEWAPI.PROBE_INTERVAL_SECONDS", _PROBE_INTERVAL_DEFAULT)
            or _PROBE_INTERVAL_DEFAULT
        )
        logger.info(f"渠道真伪探针已启动: interval={interval}s")

    async def stop(self) -> None:
        """优雅停止"""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 退出路径兜底
                pass
            self._loop_task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("渠道真伪探针已停止")

    async def _tick_loop(self) -> None:
        interval = int(
            settings.get("NEWAPI.PROBE_INTERVAL_SECONDS", _PROBE_INTERVAL_DEFAULT)
            or _PROBE_INTERVAL_DEFAULT
        )
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单轮失败不中断循环
                logger.error(f"渠道探针轮次失败: {e}")
            await asyncio.sleep(interval)

    # ── 单批巡检 ──────────────────────────────────────────────
    async def _tick_once(self) -> None:
        """单批：抢锁 → 载问题集 → 参考渠道基线 → 逐目标渠道探针（隔离）

        锁走 platform_core.queues.distributed_lock 共享设施（唯一 token +
        finally 原子释放，早退/异常路径同样释放，评审 m-1）；
        TTL 仅作进程崩溃兑底，正常运行靠主动释放。
        """
        lock_ttl = int(settings.get("NEWAPI.PROBE_LOCK_TTL_SECONDS", 21600) or 21600)
        # C4 修复：批次串行耗时可能超过 TTL（9 题 × N 渠道 × 60s 超时），
        # 启用周期续期防止锁过期后双实例并发批次（TTL 仅作进程崩溃兜底）
        lock_renewal = int(settings.get("NEWAPI.PROBE_LOCK_RENEWAL_SECONDS", 600) or 600)
        async with distributed_lock(
            self._redis, NEWAPI_PROBE_LOCK_KEY, ttl=lock_ttl, renewal=lock_renewal
        ) as lock:
            if lock is None:
                return  # 其他实例已在执行本批
            questions = _load_questions(
                str(settings.get("NEWAPI.PROBE_QUESTIONS_FILE", "") or "")
            )
            channels = await self._api.list_channels()
            if not channels:
                logger.debug("new-api 渠道列表为空，探针本轮跳过")
                return

            ref_channel = self._resolve_reference(channels)
            ref_results: dict | None = None
            ref_model = _first_model(ref_channel) if ref_channel else None
            if ref_model:
                ref_results = await self._collect_responses(ref_model, questions)
                if ref_results and all(not r.get("ok") for r in ref_results.values()):
                    logger.warning(f"参考渠道探针全部失败（model={ref_model}），本批无参考对比")
                    ref_results = None

            batch_id = uuid.uuid4().hex
            ref_id = int(ref_channel["id"]) if ref_channel else None
            targets = [
                ch for ch in channels
                if int(ch.get("status") or 0) == CHANNEL_STATUS_ENABLED
                and int(ch.get("id") or 0) != (ref_id or -1)
            ]
            logger.info(
                f"渠道探针批次开始: batch_id={batch_id}, targets={len(targets)}, "
                f"ref={'#' + str(ref_id) if ref_id else '无'}"
            )
            for target in targets:
                try:
                    await self._probe_channel(target, ref_results, questions, batch_id)
                except Exception as e:  # noqa: BLE001 单渠道隔离，不中断本批
                    logger.error(
                        f"渠道探针失败（已隔离）: channel_id={target.get('id')}, error={e}"
                    )

    def _resolve_reference(self, channels: list[dict]) -> dict | None:
        """解析参考渠道（PROBE_REFERENCE_CHANNEL 支持渠道 id 或名称）"""
        spec = str(settings.get("NEWAPI.PROBE_REFERENCE_CHANNEL", "") or "").strip()
        if not spec:
            return None
        for ch in channels:
            if spec in (str(ch.get("id")), str(ch.get("name") or "")):
                return ch
        logger.warning(f"参考渠道未在渠道列表找到: {spec}（本批无参考对比）")
        return None

    async def _collect_responses(self, model: str, questions: list[dict]) -> dict:
        """按问题集逐题采集；知识截止题 +1 次复测（缓存指纹），指令题 +2 次（格式稳定性）"""
        results: dict = {}
        for item in questions:
            results[item["id"]] = await self._api.chat_completion(model, item["text"])
        cutoff_q = _first_by_category(questions, "knowledge_cutoff")
        if cutoff_q:
            results[f"{cutoff_q['id']}:repeat"] = await self._api.chat_completion(
                model, cutoff_q["text"]
            )
        inst_q = _first_by_category(questions, "instruction_following")
        if inst_q:
            results[f"{inst_q['id']}:repeat1"] = await self._api.chat_completion(
                model, inst_q["text"]
            )
            results[f"{inst_q['id']}:repeat2"] = await self._api.chat_completion(
                model, inst_q["text"]
            )
        return results

    async def _probe_channel(
        self, target: dict, ref_results: dict | None, questions: list[dict], batch_id: str
    ) -> None:
        """单渠道探针：采集 → 评分判定 → 落库（spoofed 追加通知）"""
        cid = int(target["id"])
        model = _first_model(target)
        if not model:
            logger.warning(f"渠道无可用模型，跳过探针: channel_id={cid}")
            return
        results = await self._collect_responses(model, questions)
        verdict, scores = _score_probe_batch(model, results, questions, ref_results)
        zh_q = _first_by_category(questions, "identity", lang="zh") or _first_by_category(
            questions, "identity"
        )
        # 评审 m-5：问题集可能缺失 identity 题（zh_q 为 None），不取下标防 KeyError
        # （与 _score_probe_batch 的同款守卫对齐）
        latency = None
        if zh_q is not None:
            latency = int(((results.get(zh_q["id"]) or {}).get("latency_ms")) or 0) or None
        await self._record_probe_result(
            channel_id=cid, model=model, verdict=verdict, scores=scores,
            latency_ms=latency, batch_id=batch_id,
        )
        logger.info(f"渠道探针完成: channel_id={cid}, model={model}, verdict={verdict}")
        if verdict == "spoofed":
            await NotifyService().notify_text(
                "channel.probe.spoofed",
                f"⚠ 渠道 #{cid}（{target.get('name', '')}）真伪探针判定 spoofed（model={model}）",
            )

    # ── 结果落库（主库） ──────────────────────────────────────
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
        """channel_probe_results 落库（主库独立提交；失败仅告警，不影响探针批次）"""
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
