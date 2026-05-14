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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRAPY_DIR = os.path.join(PROJECT_ROOT, "scrapy")
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")


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


def list_spiders():
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader

    settings = get_project_settings()
    spiders = sorted(SpiderLoader.from_settings(settings).list())
    print("\n" + "=" * 60)
    print("🕷️  可用爬虫列表")
    print("=" * 60)
    if not spiders:
        print("  ⚠️  未发现任何爬虫")
    else:
        for name in spiders:
            print(f"  • {name}")
    print("=" * 60 + "\n")
    return spiders


def run(spider_name: str | None, **kwargs):
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader

    settings = get_project_settings()
    process = CrawlerProcess(settings)

    loader = SpiderLoader.from_settings(settings)
    available = set(loader.list())

    if spider_name:
        if spider_name not in available:
            print(f"❌ 爬虫 '{spider_name}' 不存在")
            print("💡 用 --list 查看可用爬虫")
            sys.exit(1)
        print(f"🎯 运行爬虫: {spider_name}")
        process.crawl(spider_name, **kwargs)
    else:
        if not available:
            print("⚠️  未发现任何爬虫")
            return
        print(f"🎯 运行所有爬虫 ({len(available)} 个)")
        for name in sorted(available):
            print(f"  • 加载: {name}")
            process.crawl(name, **kwargs)

    print("\n" + "=" * 60)
    print("🚀 爬虫开始运行... (Ctrl+C 停止)")
    print("=" * 60 + "\n")
    process.start()


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
