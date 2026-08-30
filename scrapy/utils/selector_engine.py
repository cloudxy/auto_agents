"""选择器执行引擎 - 统一的 xpath/css/regex 字段提取逻辑

消除 generic.py 与 flow_generic.py 之间的选择器提取代码重复。
所有选择器相关的提取、构建操作均通过本模块完成。
"""
import json
import re
from typing import Any

from items import BaseItem
from platform_core.logger import get_logger

logger = get_logger("spider")

_SELECTOR_TYPES = ("xpath", "css", "regex")


def extract_fields(response, fields: list[dict[str, Any]]) -> dict[str, list[str]]:
    """按选择器规则逐字段提取（xpath / css / regex 三分支）。

    Args:
        response: Scrapy Response 对象。
        fields: 字段规则列表，每项需含 ``name`` / ``type`` / ``expr`` 键。

    Returns:
        ``{field_name: [value, ...]}`` 字典；非法规则或执行失败的字段会被跳过并记录警告。
    """
    result: dict[str, list[str]] = {}
    for rule in fields:
        name = rule.get("name")
        stype = rule.get("type")
        expr = rule.get("expr")
        if not name or not expr or stype not in _SELECTOR_TYPES:
            logger.warning(f"非法选择器规则已跳过: {rule!r}")
            continue
        try:
            if stype == "xpath":
                values = response.xpath(expr).getall()
            elif stype == "css":
                values = response.css(expr).getall()
            else:  # regex
                values = re.findall(expr, response.text)
        except Exception as e:  # noqa: BLE001 单条规则失败不中断整页采集
            logger.warning(f"选择器执行失败: name={name}, error={e}")
            continue
        result[name] = [str(v).strip() for v in values if v is not None]
    return result


def build_item(
    response,
    fields: dict[str, list[str]],
    source: str = "generic",
    extra: dict[str, Any] | None = None,
) -> BaseItem:
    """将提取结果字典构造为 BaseItem。

    Args:
        response: Scrapy Response 对象（取 ``response.url`` 及兜底 title）。
        fields: ``extract_fields`` 返回的字段字典。
        source: Item 的 ``source`` 字段值（如 ``"custom"`` / ``"flow"``）。
        extra: 可选的额外信息字典，序列化后写入 ``item["extra"]``。

    Returns:
        填充完毕的 BaseItem 实例。
    """
    item = BaseItem()
    item["url"] = response.url
    title_values = fields.get("title") or []
    item["title"] = title_values[0] if title_values else (response.css("title::text").get() or response.url)
    item["content"] = json.dumps(fields, ensure_ascii=False)
    item["source"] = source
    if extra is not None:
        item["extra"] = json.dumps(extra, ensure_ascii=False)
    return item
