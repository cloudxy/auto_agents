"""数据质量检查管道 - 按抽取结果评分（审计 BUG-21 / F4 QA-2，评分口径 v2）"""
import hashlib
import json

from platform_core.logger import get_logger

logger = get_logger("spider")

# 管道 / 中间件写入的内部字段，不代表抽取质量（原先计入完整率分母，任何 Item 都拿到固定分）
_INTERNAL_FIELDS = frozenset({
    "task_id", "id", "created_at", "updated_at", "_quality_score", "source", "extra",
    "spider_name", "tenant_id", "item_type",
})
_DUP_FACTOR = 0.6


def _fields_payload(item) -> dict | None:
    """flow / generic 爬虫的 content 是 {选择器名: [值...]} 的 JSON；其它爬虫返回 None"""
    raw = item.get("content")
    if not isinstance(raw, str) or not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(data, dict) and data and all(isinstance(v, list) for v in data.values()):
        return data
    return None


def _valid_value(value, url: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and text != url


class QualityCheckPipeline:
    """数据质量评估管道（在 StorePipeline 之前执行，优先级 350 < 400）

    评分写入 item['_quality_score']（0-100），口径 v2：

    - 选择器型 Item（flow / generic：content 为「选择器名 → 值列表」）：
      分数 = 100 × 声明选择器命中率 × 命中值有效率 × 去重系数
      （值等于页面 URL、空白视为无效；同指纹重复出现乘 0.6）。
      例：声明 3 个选择器只命中 title → 33 分，低于试采闸 40。
    - 其它 Item：分数 = 100 × 业务字段完整率 × 去重系数（排除 task_id / id / 时间戳 /
      source 等内部字段；title 等于 URL 视为缺失）。

    原口径（完整率×50 + 核心字段×30 + 去重×20）的分母包含内部字段、title 缺失时回退
    页面标题或 URL、content 恒非空，最低 50 分，试采「< 40 判失败」永远触发不了。
    """

    def open_spider(self, spider):
        # 从 spider.settings 读取平铺键（scrapy/settings.py 已把 config QUALITY_CHECK 段
        # 映射为 QUALITY_CHECK_*；Scrapy Settings 不支持嵌套 dict 点号读取，勿改回点号路径）
        self.required_fields = spider.settings.getlist(
            "QUALITY_CHECK_REQUIRED_FIELDS", ["url"]
        )
        self.core_fields = spider.settings.getlist(
            "QUALITY_CHECK_CORE_FIELDS", ["url", "title", "content"]
        )
        self.enabled = spider.settings.getbool("QUALITY_CHECK_ENABLED", True)
        # 内存去重（单 spider 生命周期内）
        self._seen: set[str] = set()

    def _dup_factor(self, item) -> float:
        fingerprint = hashlib.md5(
            f"{item.get('url', '')}|{item.get('title', '')}|{item.get('content', '')}".encode()
        ).hexdigest()
        is_dup = fingerprint in self._seen
        self._seen.add(fingerprint)
        if is_dup:
            logger.debug(f"重复数据（质量评分降低）: url={item.get('url')}")
        return _DUP_FACTOR if is_dup else 1.0

    @staticmethod
    def _selector_score(fields: dict, url: str) -> float:
        declared = len(fields)
        hit = [name for name, values in fields.items() if any(str(v or "").strip() for v in values)]
        if not declared or not hit:
            return 0.0
        valid = [name for name in hit if any(_valid_value(v, url) for v in fields[name])]
        return (len(hit) / declared) * (len(valid) / len(hit))

    @staticmethod
    def _completeness(item) -> float:
        url = str(item.get("url") or "")
        names = list(item.fields.keys()) if hasattr(item, "fields") else list(item.keys())
        business = [n for n in names if n not in _INTERNAL_FIELDS]
        if not business:
            return 0.0
        filled = sum(1 for n in business if _valid_value(item.get(n), url) or (n == "url" and url))
        return filled / len(business)

    def process_item(self, item, spider):
        if not self.enabled:
            return item
        url = str(item.get("url") or "")
        fields = _fields_payload(item)
        base = self._selector_score(fields, url) if fields is not None else self._completeness(item)
        item["_quality_score"] = round(100 * base * self._dup_factor(item), 1)
        return item
