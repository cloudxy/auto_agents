"""数据质量检查管道 - 字段完整性、空值率、重复率、质量评分"""
import hashlib

from platform_core.logger import get_logger

logger = get_logger("spider")


class QualityCheckPipeline:
    """数据质量评估管道

    在 StorePipeline 之前执行（优先级 350 < 400），为每个 Item 计算质量评分。
    评分写入 item['_quality_score']（下划线前缀，StorePipeline 序列化时会包含它）。

    评分公式（0-100）：
    - 字段完整率 × 50：所有声明字段中非空的比例
    - 非空率 × 30：核心字段（url/title/content）非空比例
    - 去重分 × 20：基于 url+title 指纹，首次出现 1.0，重复 0.0
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

    def process_item(self, item, spider):
        if not self.enabled:
            return item

        # 1. 字段完整率
        all_fields = (
            list(item.fields.keys()) if hasattr(item, "fields") else list(item.keys())
        )
        non_empty = sum(1 for f in all_fields if item.get(f))
        field_completeness = non_empty / max(len(all_fields), 1)

        # 2. 核心字段非空率
        core_non_empty = sum(1 for f in self.core_fields if item.get(f))
        core_rate = core_non_empty / max(len(self.core_fields), 1)

        # 3. 去重分（基于 url+title 指纹）
        fingerprint = hashlib.md5(
            f"{item.get('url', '')}|{item.get('title', '')}".encode()
        ).hexdigest()
        is_dup = fingerprint in self._seen
        self._seen.add(fingerprint)
        dup_score = 0.0 if is_dup else 1.0

        # 4. 综合评分
        score = round(field_completeness * 50 + core_rate * 30 + dup_score * 20, 1)
        item["_quality_score"] = score

        if is_dup:
            logger.debug(f"重复数据（质量评分降低）: url={item.get('url')}")

        return item
