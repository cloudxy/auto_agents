"""任务标记日志格式器（审计 BUG-16）

同一个 Scrapy 进程并发处理多个租户的任务，日志落在同一个文件里。原先日志行不带任务标识，
后端「运行日志」只能按文件偏移切窗口，窗口内并发任务的行（含其他租户的 URL）会一起返回。

本格式器给引擎产出的逐请求日志（抓取 / 产出 / 丢弃 / 条目错误 / 爬虫错误 / 下载错误）
加上 `[task=N]` 前缀（N 来自 request.meta / response.meta / item 的 task_id），
后端据此只把本任务的行返回给租户。没有 task_id 的行保持原样。
"""
from __future__ import annotations

from typing import Any, Optional

from scrapy.logformatter import LogFormatter


def _task_id_of(*sources: Any) -> Optional[int]:
    for src in sources:
        if src is None:
            continue
        meta = getattr(src, "meta", None)
        if isinstance(meta, dict) and meta.get("task_id"):
            return _as_int(meta.get("task_id"))
        try:
            value = src.get("task_id") if hasattr(src, "get") else None
        except Exception:  # noqa: BLE001 Item 取值失败按无标记处理
            value = None
        if value:
            return _as_int(value)
    return None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tag(entry: dict, task_id: Optional[int]) -> dict:
    if task_id is None or not isinstance(entry, dict):
        return entry
    args = entry.get("args")
    if isinstance(args, dict):
        tagged = dict(entry)
        tagged["msg"] = "[task=%(task_id)s] " + str(entry.get("msg", ""))
        tagged["args"] = {**args, "task_id": task_id}
        return tagged
    return entry


class TaskLogFormatter(LogFormatter):
    def crawled(self, request, response, spider):
        return _tag(super().crawled(request, response, spider), _task_id_of(request, response))

    def scraped(self, item, response, spider):
        return _tag(super().scraped(item, response, spider), _task_id_of(response, item))

    def dropped(self, item, exception, response, spider):
        return _tag(super().dropped(item, exception, response, spider), _task_id_of(response, item))

    def item_error(self, item, exception, response, spider):
        return _tag(super().item_error(item, exception, response, spider), _task_id_of(response, item))

    def spider_error(self, failure, request, response, spider):
        return _tag(super().spider_error(failure, request, response, spider), _task_id_of(request, response))

    def download_error(self, failure, request, spider, errmsg=None):
        return _tag(super().download_error(failure, request, spider, errmsg), _task_id_of(request))
