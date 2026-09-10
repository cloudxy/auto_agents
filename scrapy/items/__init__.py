"""Scrapy Items - 数据项定义"""
import scrapy


class BaseItem(scrapy.Item):
    """基础数据项"""
    # 内部归属字段（阶段 4.1）：由 TaskAttribution 中间件从响应 meta 注入，
    # StorePipeline 读取后弹出，不进入业务字段序列化
    task_id = scrapy.Field()
    # 唯一标识
    id = scrapy.Field()
    # 标题
    title = scrapy.Field()
    # URL
    url = scrapy.Field()
    # 内容
    content = scrapy.Field()
    # 来源
    source = scrapy.Field()
    # 创建时间
    created_at = scrapy.Field()
    # 更新时间
    updated_at = scrapy.Field()
    # 额外数据（JSON）
    extra = scrapy.Field()
    # 数据质量评分（B1）：QualityCheckPipeline 写入（0-100），随 StorePipeline 推送队列，
    # Backend 消费者弹出后落库 spider_results.quality_score。
    # 必须声明于此：scrapy.Item 只允许写入已声明字段，未声明会在 __setitem__ 抛 KeyError，
    # 导致 item 被丢弃 → item_scraped 不触发 → 爬虫永不收尾（任务卡 running）。
    # 声明在 BaseItem 上使所有 Item 子类（含 flow_generic 经 build_item 产出的实例）可安全写入。
    _quality_score = scrapy.Field()


class HotSearchItem(BaseItem):
    """热搜榜单数据项（百度/微博）"""
    rank = scrapy.Field()      # 排名
    heat_value = scrapy.Field() # 热度值
    tag = scrapy.Field()       # 标签（如：新、热、爆）


class WeatherItem(BaseItem):
    """天气数据项"""
    city = scrapy.Field()
    temperature = scrapy.Field()
    humidity = scrapy.Field()
    description = scrapy.Field()
    wind_speed = scrapy.Field()


class ZhihuFeedItem(BaseItem):
    """知乎推荐流数据项"""
    author = scrapy.Field()
    vote_count = scrapy.Field()
    comment_count = scrapy.Field()
    content_type = scrapy.Field() # answer/article


class ProductItem(BaseItem):
    """商品数据项"""
    # 价格
    price = scrapy.Field()
    # 原价
    original_price = scrapy.Field()
    # 库存
    stock = scrapy.Field()
    # 图片列表
    images = scrapy.Field()
    # 评分
    rating = scrapy.Field()
