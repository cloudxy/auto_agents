"""Scrapy 任务标记日志格式器（审计 BUG-16）：逐请求日志带 [task=N]，无 task_id 保持原样"""
import importlib
import logging
import os
import sys
from pathlib import Path

_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _render(entry: dict) -> str:
    return entry["msg"] % entry["args"]


def _fmt():
    return importlib.import_module("utils.task_log_formatter").TaskLogFormatter()


def test_crawled_line_carries_task_marker():
    http = importlib.import_module("scrapy.http")
    req = http.Request("https://a.example/1", meta={"task_id": 42})
    resp = http.HtmlResponse(url=req.url, body=b"<html></html>", request=req)
    entry = _fmt().crawled(req, resp, spider=None)
    assert _render(entry).startswith("[task=42] Crawled (200)")
    assert entry["level"] == logging.DEBUG


def test_download_error_carries_task_marker():
    http = importlib.import_module("scrapy.http")
    req = http.Request("https://a.example/2", meta={"task_id": 7})

    class _F:
        def getErrorMessage(self):
            return "boom"

    entry = _fmt().download_error(_F(), req, spider=None, errmsg="timeout")
    assert _render(entry).startswith("[task=7] ")


def test_line_without_task_id_unchanged():
    http = importlib.import_module("scrapy.http")
    req = http.Request("https://a.example/3")
    resp = http.HtmlResponse(url=req.url, body=b"", request=req)
    entry = _fmt().crawled(req, resp, spider=None)
    assert not _render(entry).startswith("[task=")


def test_settings_wire_formatter():
    settings = importlib.import_module("settings")
    assert settings.LOG_FORMATTER == "utils.task_log_formatter.TaskLogFormatter"
