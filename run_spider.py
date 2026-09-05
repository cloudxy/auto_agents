#!/usr/bin/env python3
from __future__ import annotations
"""
Scrapy 爬虫服务启动入口

使用方式：
    ./run_spider.py --list                     # 列出所有可用爬虫
    ./run_spider.py --spider example           # 运行指定爬虫
    ./run_spider.py --env prod --spider example
    ./run_spider.py                            # 运行所有爬虫

特性：
- 自动检测根 .venv（workspace 统一环境）并以它重启
- --env 透传为 APP_ENV，config 层与 backend 一致
- 本地 scrapy/ 目录加入 sys.path，不与 pip 的 scrapy 库冲突
- SCRAPY_SETTINGS_MODULE=settings → scrapy/settings.py
"""
import os
import sys
import uuid
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRAPY_DIR = os.path.join(PROJECT_ROOT, "scrapy")
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")

# Worker 进程标识（心跳键后缀，进程生命周期内不变）
WORKER_ID = uuid.uuid4().hex[:12]
# 各爬虫重生次数（心跳上报，运营可观察重启频率）
RESPAWN_COUNTS: dict[str, int] = {}


def _reexec_with_venv():
    if os.path.exists(VENV_PYTHON) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PYTHON):
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)


def _setup_paths():
    """
    设置 sys.path 顺序：
    1. PROJECT_ROOT  → `from config import settings`、`from platform_core.xxx`
    2. SCRAPY_DIR    → `import settings`（scrapy 入口）、`spiders`/`middlewares`/`pipelines`/`utils`
    """
    for p in (SCRAPY_DIR, PROJECT_ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.environ["SCRAPY_SETTINGS_MODULE"] = "settings"


def _resolve_worker_log_file() -> str:
    """解析 worker 日志文件路径（与 Backend 日志 API 同一约定）

    数据源 config LOGGERS.SPIDER.FILE（默认 logs/spider/spider.log）：
    backend/services/spider_service.py::resolve_spider_log_path 读同一配置做
    「任务日志按偏移量切分」的读取端，本函数是写入端，两端必须指向同一文件。
    """
    from config import settings as project_settings

    rel = project_settings.get("LOGGERS.SPIDER.FILE", "logs/spider/spider.log")
    return rel if os.path.isabs(rel) else os.path.join(PROJECT_ROOT, rel)


def _configure_worker_logging(settings) -> None:
    """worker 日志落盘（最小目标：先让日志落盘、偏移机制可用，不动日志架构）

    - loguru（platform_core）：init_log() 按 config LOGGERS 段挂 sink，
      pipelines/extensions 的日志落到 logs/spider/spider.log
    - scrapy 引擎日志：设置 LOG_FILE 指向同一文件（默认 append 模式，
      不破坏 Backend 分发时刻记录的字节偏移）；LOG_FORMAT 的
      '时间 | 级别 | logger | 消息' 与日志 API 的级别过滤约定对齐
    常驻重生模式下多爬虫共享同一文件（允许交错，偏移按字节区间切分仍可用）。
    """
    from platform_core.logger import init_log

    log_file = _resolve_worker_log_file()
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    init_log()
    settings.set("LOG_FILE", log_file, priority="cmdline")
    settings.set(
        "LOG_FORMAT", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        priority="cmdline",
    )


def list_spiders():
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader

    settings = get_project_settings()
    spiders = sorted(SpiderLoader.from_settings(settings).list())
    print("\n" + "=" * 60)
    print("可用爬虫列表")
    print("=" * 60)
    if not spiders:
        print(" 未发现任何爬虫")
    else:
        for name in spiders:
            print(f"  • {name}")
    print("=" * 60 + "\n")
    return spiders


def run(spider_name: str | None, **kwargs):
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader
    from scrapy.utils.log import configure_logging
    # 先装 asyncio reactor 再导入 reactor：Scrapy 2.13+ 默认要求 asyncio，
    # 直接 import twisted.internet.reactor 会装上 select reactor 导致校验失败
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    from twisted.internet import defer, reactor, task as twisted_task  # noqa: E402

    settings = get_project_settings()
    _configure_worker_logging(settings)
    configure_logging(settings)
    runner = CrawlerRunner(settings)

    loader = SpiderLoader.from_settings(settings)
    available = set(loader.list())

    if spider_name:
        if spider_name not in available:
            print(f"爬虫 '{spider_name}' 不存在")
            print("用 --list 查看可用爬虫")
            sys.exit(1)
        names = [spider_name]
        print(f"运行爬虫: {spider_name}")
    else:
        if not available:
            print("未发现任何爬虫")
            return
        names = sorted(available)
        print(f"运行所有爬虫 ({len(names)} 个)")
        for name in names:
            print(f"  • 加载: {name}")

    print("\n" + "=" * 60)
    print("爬虫开始运行... (Ctrl+C 停止)")
    print("=" * 60 + "\n")

    # 常驻模式：单轮结束（空闲自动收尾/异常退出）后延迟重生同名爬虫，
    # 保证新任务随时可被消费；shutdown 类结束不重生（优雅停机）。
    # 背景：IdleAutoClose 收尾会关闭爬虫，若不重生则 Worker 空转、新任务卡死。
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
            print(f"[常驻] 爬虫 {name} 本轮结束(reason={reason})，{respawn_delay}s 后重生")
            yield twisted_task.deferLater(reactor, respawn_delay, lambda: None)

    # ---------------- Worker 节点心跳（2.2） ----------------
    # 写 spider:worker:{id} Hash（pid/spiders/started_at/respawn_count），EX 到期未续约即离线；
    # Backend 只读该键展示节点页，符合 B2 边界（仅经 Redis 通信）
    from twisted.internet.task import LoopingCall

    from config import settings as project_settings
    from platform_core.db import redis_client
    from platform_core.queues import WORKER_HEARTBEAT_KEY

    hb_cfg = project_settings.get("WORKER_HEARTBEAT", {}) or {}
    hb_interval = int(getattr(hb_cfg, "INTERVAL_SECONDS", 10) or 10)
    hb_ttl = int(getattr(hb_cfg, "TTL_SECONDS", 30) or 30)
    worker_started_at = datetime.now().isoformat(timespec="seconds")

    def _beat():
        try:
            client = redis_client()
            key = WORKER_HEARTBEAT_KEY.format(worker_id=WORKER_ID)
            client.hset(key, mapping={
                "pid": str(os.getpid()),
                "spiders": ",".join(sorted(names)),
                "started_at": worker_started_at,
                "respawn_count": str(sum(RESPAWN_COUNTS.values())),
            })
            client.expire(key, hb_ttl)
        except Exception as e:  # noqa: BLE001 心跳失败不能影响爬虫主流程
            print(f"[心跳] 写入失败（忽略）: {e}")

    _beat()
    LoopingCall(_beat).start(hb_interval, now=False)

    for name in names:
        run_forever(name)

    reactor.run()


def main():
    _reexec_with_venv()

    import argparse
    parser = argparse.ArgumentParser(description="Auto Agents Scrapy 爬虫启动器")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None,
                        help="运行环境（透传为 APP_ENV）")
    parser.add_argument("--spider", type=str, default=None, help="指定爬虫名称")
    parser.add_argument("--list", action="store_true", help="列出可用爬虫")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径（透传给爬虫）")
    args = parser.parse_args()

    if args.env:
        os.environ["APP_ENV"] = args.env

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
