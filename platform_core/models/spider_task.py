"""爬虫任务模型

status 状态流转图（合法值 4 个；DB 层 VARCHAR(20)，枚举校验在应用层——迁移 027 起）：

    (创建) ──▶ pending ──▶ running ──▶ completed（终态）
                 │  ▲          │
                 │  │          └──▶ failed（终态；执行异常/超时回收）
                 │  │
                 │  └── failed 且 retry_count < SPIDER_MAX_RETRIES
                 │      时自动重投（webhook finish_task，ZSET 延迟退避 1s→5s→15s）
                 └───▶ failed（投递失败，终态、不重试）

    - 终态幂等：completed/failed 再收 finish_task 直接返回（spider_task_service）
    - running 不可删除/编辑；仅 pending/queued 可编辑（queued 为历史防御值，
      当前无写入点）
    - 非法流转（如 completed → 任意、running → pending）在服务层守卫；
      新增状态值（cancelled/timeout 等）先更新本图 + 服务层守卫，DDL 无需变更
"""
from sqlalchemy import Column, DateTime, Integer, String, Text, Index
from sqlalchemy.sql import func
from .base import Base
from .mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class SpiderTask(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "spider_tasks"
    __table_args__ = (
        # 管理页/配额查询：tenant_id + status 等值（+可选 priority 等值）
        # 026 由 (tenant_id, status) 升级——ESR 全等值，基数降序
        Index("ix_spider_tasks_tenant_status_priority", "tenant_id", "status", "priority"),
    )

    id = Column(Integer, primary_key=True, index=True)
    spider_name = Column(String(100), nullable=False, index=True)
    status = Column(String(20), default="pending",
                    comment="任务状态（合法值/流转图见模块 docstring）")  # pending/running/completed/failed
    params = Column(Text)  # JSON 字符串
    # priority 单列索引已于 026 删除（基数=3，等值过滤由上方复合索引承接）
    priority = Column(String(10), default="normal")  # high/normal/low（阶段 4.1）
    result_count = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)  # 失败自动重试已用次数（上限见 SPIDER_MAX_RETRIES）
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))  # 消费者置 running 的时刻（统计时长用）
    completed_at = Column(DateTime(timezone=True))
