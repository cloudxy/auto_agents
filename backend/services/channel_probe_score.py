"""探针 10 维评分（阈值不改）。T-19 只换采集 HTTP，判定口径冻结。"""
import difflib
import json
import re

from platform_core.logger import get_logger

logger = get_logger("api")

# 有参考渠道时，同题答案平均相似度低于该阈值判 spoofed（正品同模型应高度一致）
_REF_SIMILARITY_SPOOF_THRESHOLD = 0.15

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

_REFUSAL_MARKERS = (
    "我不知道", "无法提供", "无法访问", "作为一个 ai", "as an ai", "i don't know", "i cannot",
)

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
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _is_substantive(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    lowered = t.lower()
    return not any(marker in lowered for marker in _REFUSAL_MARKERS)


def _model_family(model: str) -> str | None:
    lowered = (model or "").lower()
    for family, tokens in _KNOWN_MODEL_FAMILIES.items():
        if any(token in lowered for token in tokens):
            return family
    return None


def _identity_mentions(content: str, family: str | None) -> tuple[bool, bool]:
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
    """内置默认问题集 + 可选 JSON 文件覆盖；失败回退默认。"""
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
    """10 维评分 + verdict（阈值冻结，T-19 不改）。"""
    calls = list(results.values())
    ok_calls = [c for c in calls if c.get("ok")]
    if not calls or len(ok_calls) * 2 < len(calls):
        return "offline", {"total_calls": len(calls), "ok_calls": len(ok_calls)}
    scores: dict = {}
    family = _model_family(requested_model)
    zh_q = _first_by_category(questions, "identity", lang="zh") or _first_by_category(
        questions, "identity",
    )
    zh_ident = (results.get(zh_q["id"]) or {}) if zh_q else {}
    en_q = _first_by_category(questions, "identity", lang="en")
    en_ident = (results.get(en_q["id"]) or {}) if en_q else {}
    own, other = _identity_mentions(zh_ident.get("content"), family)
    scores["identity"] = 1.0 if own else 0.0
    en_own, en_other = _identity_mentions(en_ident.get("content"), family)
    scores["zh_en_consistency"] = 1.0 if (own and en_own) else (0.5 if (own or en_own) else 0.0)
    cutoff_q = _first_by_category(questions, "knowledge_cutoff")
    cutoff_content = ((results.get(cutoff_q["id"]) or {}).get("content") or "") if cutoff_q else ""
    scores["knowledge_cutoff"] = 1.0 if _is_substantive(cutoff_content) else 0.0
    math_q = _first_by_category(questions, "math_reasoning")
    math_content = ((results.get(math_q["id"]) or {}).get("content") or "") if math_q else ""
    expected = (math_q or {}).get("expected")
    digits = re.findall(r"-?\d+", str(math_content).replace(",", ""))
    scores["math_reasoning"] = 1.0 if expected is not None and str(expected) in digits else 0.0
    inst_q = _first_by_category(questions, "instruction_following")
    inst_content = ((results.get(inst_q["id"]) or {}).get("content") or "") if inst_q else ""
    expected_lines = (inst_q or {}).get("expected_lines") or []
    lines = [ln.strip() for ln in inst_content.strip().splitlines() if ln.strip()]
    scores["instruction_following"] = 1.0 if expected_lines and lines == expected_lines else 0.0
    _fill_latency_price(scores, requested_model, zh_ident, family, ref_results, zh_q)
    if cutoff_q:
        repeat = results.get(f"{cutoff_q['id']}:repeat") or {}
        verbatim = bool(cutoff_content) and cutoff_content == (repeat.get("content") or "")
        scores["verbatim_repeat"] = 0.0 if verbatim else 1.0
    if inst_q:
        r1 = (results.get(f"{inst_q['id']}:repeat1") or {}).get("content") or ""
        r2 = (results.get(f"{inst_q['id']}:repeat2") or {}).get("content") or ""
        sims = [_text_sim(inst_content, r1), _text_sim(inst_content, r2), _text_sim(r1, r2)]
        scores["format_stability"] = 1.0 if all(s >= 0.6 for s in sims) else 0.5
    ref_sim = _ref_similarity(results, questions, ref_results, scores)
    identity_contradiction = family is not None and (other or en_other)
    if (
        identity_contradiction
        or scores.get("verbatim_repeat") == 0.0
        or (ref_sim is not None and ref_sim < _REF_SIMILARITY_SPOOF_THRESHOLD)
    ):
        return "spoofed", scores
    return "original", scores


def _fill_latency_price(
    scores: dict, requested_model: str, zh_ident: dict, family: str | None,
    ref_results: dict | None, zh_q: dict | None,
) -> None:
    scores["latency"] = 1.0
    if ref_results and zh_q:
        ref_lat = int(((ref_results.get(zh_q["id"]) or {}).get("latency_ms")) or 0)
        latency = int(zh_ident.get("latency_ms") or 0)
        if ref_lat > 0 and latency > 0:
            ratio = latency / ref_lat
            scores["latency_ratio"] = round(ratio, 3)
            scores["latency"] = 1.0 if 0.2 <= ratio <= 5.0 else 0.5
    reasoning_tokens = int(zh_ident.get("reasoning_tokens") or 0)
    is_o_series = re.match(r"^o[134]([-.\b]|$)", requested_model.lower()) is not None
    scores["reasoning_tokens_anomaly"] = 0.0 if (reasoning_tokens > 0 and not is_o_series) else 1.0
    usage = zh_ident.get("usage") or {}
    total_tokens = int(usage.get("total_tokens") or 0)
    resp_family = _model_family(str(zh_ident.get("model") or ""))
    family_match = family is None or resp_family is None or resp_family == family
    scores["price_anomaly"] = 1.0 if (total_tokens > 0 and family_match) else 0.5


def _ref_similarity(
    results: dict, questions: list[dict], ref_results: dict | None, scores: dict,
) -> float | None:
    if not ref_results:
        return None
    sims = []
    for q in questions:
        mine = (results.get(q["id"]) or {}).get("content") or ""
        theirs = (ref_results.get(q["id"]) or {}).get("content") or ""
        if mine and theirs:
            sims.append(_text_sim(mine, theirs))
    if not sims:
        return None
    ref_sim = sum(sims) / len(sims)
    scores["ref_similarity"] = round(ref_sim, 4)
    return ref_sim
