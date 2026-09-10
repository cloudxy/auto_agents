"""爬虫定时调度模型 - Cron 计划登记

一条记录 = 一个爬虫的定时触发计划。调度器（backend/services/schedule_service.py）
每轮 tick 扫描 enabled 且 next_run_at 已到期的记录，触发一次任务入队后推进
last_run_at / next_run_at（由 croniter 基于当前时间计算）。

约定：
- cron_expr 为标准 5 段 cron 表达式，创建/修改时由 croniter 校验合法性
- params 与手动任务一致：JSON 字符串（{"urls": [...]}），透传给消费者
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func
from .base import Base
from .mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class SpiderSchedule(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "spider_schedules"

    id = Column(Integer, primary_key=True, index=True)
    spider_name = Column(String(100), nullable=False, index=True)
    cron_expr = Column(String(100), nullable=False)  # 5 段 cron 表达式
    params = Column(Text)  # JSON 字符串，透传任务参数
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True))  # 上次触发时刻
    next_run_at = Column(DateTime(timezone=True), index=True)  # 下次触发时刻（调度器扫描依据）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
