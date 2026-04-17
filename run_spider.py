#!/usr/bin/env python3
"""
Scrapy 爬虫服务启动入口

使用方式：
    python run_spider.py                    # 运行所有爬虫
    python run_spider.py --spider example   # 运行指定爬虫
    python run_spider.py --list             # 列出所有可用爬虫
"""
import sys
import os

# 将项目根目录和 Scrapy 目录添加到 Python 路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRAPY_DIR = os.path.join(PROJECT_ROOT, 'scrapy')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRAPY_DIR)


def list_available_spiders():
    """列出所有可用的爬虫"""
    print("\n" + "=" * 60)
    print("🕷️  可用爬虫列表")
    print("=" * 60)
    
    try:
        from scrapy.utils.misc import load_object
        from scrapy.spiderloader import SpiderLoader
        from scrapy.settings import Settings
        
        settings = Settings()
        settings.set('SPIDER_MODULES', ['spiders'])
        
        spider_loader = SpiderLoader.from_settings(settings)
        spiders = spider_loader.list()
        
        if not spiders:
            print("⚠️  未找到任何爬虫")
        else:
            for spider_name in sorted(spiders):
                print(f"  • {spider_name}")
        
        print("=" * 60 + "\n")
        return spiders
    except Exception as e:
        print(f"❌ 加载爬虫失败: {e}\n")
        return []


def run_spider(spider_name=None, **kwargs):
    """运行指定的爬虫"""
    print("\n" + "=" * 60)
    print("🕷️  启动 Scrapy 爬虫服务")
    print("=" * 60)
    
    # 设置 Scrapy 环境变量
    os.environ['SCRAPY_SETTINGS_MODULE'] = 'settings'
    
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    
    # 获取 Scrapy 项目设置
    settings = get_project_settings()
    
    # 确保日志目录存在
    log_file = settings.get('LOG_FILE', '')
    if log_file:
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)
    
    # 创建爬虫进程
    process = CrawlerProcess(settings)
    
    # 如果指定了爬虫名称，运行特定爬虫
    if spider_name:
        print(f"🎯 运行爬虫: {spider_name}")
        try:
            process.crawl(spider_name, **kwargs)
        except KeyError:
            print(f"❌ 错误: 爬虫 '{spider_name}' 不存在")
            print("💡 使用 --list 查看可用爬虫\n")
            return
    else:
        # 运行所有爬虫
        print("🎯 运行所有爬虫")
        try:
            from scrapy.utils.misc import load_object
            from scrapy.spiderloader import SpiderLoader
            from scrapy.settings import Settings
            
            settings_obj = Settings()
            settings_obj.set('SPIDER_MODULES', ['spiders'])
            spider_loader = SpiderLoader.from_settings(settings_obj)
            spiders = spider_loader.list()
            
            if not spiders:
                print("⚠️  未找到任何爬虫\n")
                return
            
            for spider_name in spiders:
                print(f"  • 加载: {spider_name}")
                process.crawl(spider_name, **kwargs)
        except Exception as e:
            print(f"❌ 加载爬虫失败: {e}\n")
            return
    
    # 启动爬虫
    print("\n" + "=" * 60)
    print("🚀 爬虫开始运行...")
    print("=" * 60 + "\n")
    process.start()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto Agents Scrapy 爬虫启动器")
    parser.add_argument(
        "--spider", 
        type=str, 
        help="指定要运行的爬虫名称"
    )
    parser.add_argument(
        "--list", 
        action="store_true",
        help="列出所有可用爬虫"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default=None,
        help="输出文件路径（可选）"
    )
    
    args = parser.parse_args()
    
    # 如果请求列出爬虫
    if args.list:
        list_available_spiders()
        return
    
    # 运行爬虫
    kwargs = {}
    if args.output:
        kwargs['output'] = args.output
    
    run_spider(
        spider_name=args.spider,
        **kwargs
    )


if __name__ == "__main__":
    main()
