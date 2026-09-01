"""AI 采集计划模型（阶段二：AI 智能采集核心）

记录"目标 URL → LLM 规划 flow 流程 → 试采验证 → 注册爬虫定义"全链路状态机：
draft（初始/规划完成）→ planning（规划中）→ testing（试采中）→ registered（已注册）
任一环节失败置 failed（error_message 可追溯），failed 后可重新规划。

plan_json 内约定键（与 scrapy/spiders/flow_generic.py 的 flow JSON 契约对齐）：
- flow：FlowConfig 序列化（selectors/pagination/detail/filters/render_js）
- test_history：[{iteration, task_id, status, result_count, passed, reason}]
- html_sample：清洗后的样本 HTML（自动修复迭代回喂 LLM）
- html_snippet：创建时用户可选预置 HTML（有则跳过抓取）
"""
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class AiPlan(TenantMixin, Base):
    """AI 采集计划表（LLM 规划状态机，可查询进度）"""

    __tablename__ = "ai_plans"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    target_url = Column(String(500), nullable=False, index=True, comment="目标页面 URL")
    status = Column(String(20), nullable=False, default="draft", server_default="draft",
                    comment="状态：draft/planning/testing/registered/failed")
    plan_json = Column(JSON, nullable=True,
                       comment="LLM 产出（flow 流程定义 + test_history + html_sample 等元数据）")
    generated_params = Column(JSON, nullable=True,
                              comment="组装后的 flow_generic 任务参数（enqueue 时序列化为 JSON 串）")
    test_task_id = Column(Integer, nullable=True, comment="最近一次试采的爬虫任务 ID")
    iteration_count = Column(Integer, nullable=False, default=0, server_default="0",
                             comment="自动修复迭代次数（上限 LLM.MAX_ITERATIONS）")
    error_message = Column(Text, nullable=True, comment="失败原因（failed 状态可追溯）")
    created_by = Column(String(64), nullable=True, comment="创建人用户名")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="更新时间")

    def __repr__(self) -> str:
        return f"<AiPlan #{self.id} {self.status} {self.target_url}>"
