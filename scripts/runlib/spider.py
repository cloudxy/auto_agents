"""Scrapy Worker 入口：python -m scripts.runlib.spider"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from .paths import ROOT
from .venv import apply_env, reexec_with_venv

SCRAPY_DIR = ROOT / "scrapy"
WORKER_ID = uuid.uuid4().hex[:12]
RESPAWN_COUNTS: dict[str, int] = {}


def _setup_paths() -> None:
    for path in (str(SCRAPY_DIR), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.environ["SCRAPY_SETTINGS_MODULE"] = "settings"


def _worker_log_file() -> str:
    from config import settings as project_settings
    rel = project_settings.get("LOGGERS.SPIDER.FILE", "logs/spider/spider.log")
    return rel if os.path.isabs(rel) else str(ROOT / rel)


def _configure_worker_logging(settings) -> None:
    from platform_core.logger import init_log
    log_file = _worker_log_file()
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    init_log()
    settings.set("LOG_FILE", log_file, priority="cmdline")
    settings.set(
        "LOG_FORMAT", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        priority="cmdline",
    )


def list_spiders() -> list[str]:
    from scrapy.spiderloader import SpiderLoader
    from scrapy.utils.project import get_project_settings
    names = sorted(SpiderLoader.from_settings(get_project_settings()).list())
    print("可用爬虫:")
    for name in names or ["(无)"]:
        print(f"  • {name}")
    return names


def run(spider_name: str | None, **kwargs) -> None:
    from scrapy.crawler import CrawlerRunner
    from scrapy.spiderloader import SpiderLoader
    from scrapy.utils.log import configure_logging
    from scrapy.utils.project import get_project_settings
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    from twisted.internet import defer, reactor, task as twisted_task

    settings = get_project_settings()
    _configure_worker_logging(settings)
    configure_logging(settings)
    runner = CrawlerRunner(settings)
    available = set(SpiderLoader.from_settings(settings).list())
    if spider_name:
        if spider_name not in available:
            print(f"爬虫 '{spider_name}' 不存在")
            sys.exit(1)
        names = [spider_name]
    else:
        names = sorted(available)
        if not names:
            print("未发现任何爬虫")
            return
    print(f"运行爬虫: {', '.join(names)}  (Ctrl+C 停止)")

    respawn_delay = 5

    @defer.inlineCallbacks
    def run_forever(name):
        while True:
            crawler = runner.create_crawler(name)
            yield crawler.crawl(**kwargs)
            reason = crawler.stats.get_value("finish_reason") if crawler.stats else None
            if reason in ("shutdown", "ctrl_c", "cancel"):
                break
            RESPAWN_COUNTS[name] = RESPAWN_COUNTS.get(name, 0) + 1
            print(f"[常驻] {name} 结束({reason})，{respawn_delay}s 后重生")
            yield twisted_task.deferLater(reactor, respawn_delay, lambda: None)

    _start_heartbeat(names)
    for name in names:
        run_forever(name)
    reactor.run()


def _start_heartbeat(names: list[str]) -> None:
    from datetime import datetime as dt

    from twisted.internet.task import LoopingCall

    from config import settings as project_settings
    from platform_core.db import redis_client
    from platform_core.queues import WORKER_HEARTBEAT_KEY

    hb_cfg = project_settings.get("WORKER_HEARTBEAT", {}) or {}
    interval = int(getattr(hb_cfg, "INTERVAL_SECONDS", 10) or 10)
    ttl = int(getattr(hb_cfg, "TTL_SECONDS", 30) or 30)
    started = dt.now().isoformat(timespec="seconds")

    def beat() -> None:
        try:
            client = redis_client()
            key = WORKER_HEARTBEAT_KEY.format(worker_id=WORKER_ID)
            client.hset(key, mapping={
                "pid": str(os.getpid()),
                "spiders": ",".join(sorted(names)),
                "started_at": started,
                "respawn_count": str(sum(RESPAWN_COUNTS.values())),
            })
            client.expire(key, ttl)
        except Exception as exc:  # noqa: BLE001
            print(f"[心跳] 写入失败（忽略）: {exc}")

    beat()
    LoopingCall(beat).start(interval, now=False)


def main() -> None:
    reexec_with_venv()
    parser = argparse.ArgumentParser(description="Auto Agents Scrapy Worker")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--spider", type=str, default=None)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()
    apply_env(args.env)
    _setup_paths()
    if args.list:
        list_spiders()
        return
    kwargs = {}
    if args.output:
        kwargs["output"] = args.output
    run(args.spider, **kwargs)


if __name__ == "__main__":
    main()
