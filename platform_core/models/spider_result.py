"""爬虫采集结果模型 - 数据闭环的落库终点

与 SpiderTask 的关系：一次任务（spider_tasks）产出多条结果（spider_results）。
字段与 scrapy/items 的 BaseItem 及其子类对齐，未映射字段进 extra（JSON）。
"""
from sqlalchemy import Column, Float, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from .base import Base
from .mixins import TenantMixin


class SpiderResult(TenantMixin, Base):
    __tablename__ = "spider_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)  # 关联 spider_tasks.id
    spider_name = Column(String(100), nullable=False, index=True)
    url = Column(String(500))
    title = Column(Text)
    content = Column(Text)
    source = Column(String(50))
    item_type = Column(String(100))  # Item 类名（BaseItem/HotSearchItem/...）
    extra = Column(Text)             # 未映射字段的 JSON 字符串
    quality_score = Column(Float, nullable=True)  # 数据质量评分（0-100）
    content_hash = Column(String(32), nullable=True, index=True)  # md5(url + title + content)，增量去重
    created_at = Column(DateTime(timezone=True), server_default=func.now())
