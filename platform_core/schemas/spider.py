"""爬虫任务 Schema —— API 层与 Service 层之间的数据契约"""
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from platform_core.schemas.base import QueryParams, RequestBody


class SpiderTaskResponse(BaseModel):
    """单条爬虫任务的对外响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    spider_name: str
    status: str
    priority: str = "normal"
    result_count: int = 0
    retry_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SpiderTaskListResponse(BaseModel):
    """分页列表响应"""
    total: int
    items: List[SpiderTaskResponse]


class SpiderTaskQuery(QueryParams):
    """任务列表查询参数"""
    skip: int = Field(0, ge=0, description="偏移")
    limit: int = Field(20, ge=1, le=100, description="每页大小")
    status: Optional[str] = Field(None, description="按状态过滤：pending/running/completed/failed")
    priority: Optional[str] = Field(None, pattern="^(high|normal|low)$", description="按优先级过滤")


class RunSpiderRequest(RequestBody):
    """触发一次爬虫任务"""
    spider_name: str = Field(..., min_length=1, max_length=100)
    params: Optional[str] = Field(None, description="透传给爬虫的 JSON 字符串")
    priority: str = Field("normal", pattern="^(high|normal|low)$", description="任务优先级（高/普通/低）")


class SpiderParamField(BaseModel):
    """任务参数字段定义（驱动前端动态表单）"""
    name: str
    label: str
    kind: str = Field(..., description="urls/text/json/select/selectors")
    required: bool = False
    default: Optional[str] = None
    help: Optional[str] = None
    options: Optional[List[Dict[str, str]]] = None
    render_js: bool = Field(False, description="是否启用 Playwright JS 渲染")
    wait_for: Optional[str] = Field(None, description="CSS 选择器，等待元素出现后再提取")
    wait_timeout: Optional[int] = Field(None, description="等待元素超时秒数（默认取 PLAYWRIGHT_TIMEOUT）")


class SpiderTypeInfo(BaseModel):
    """爬虫类型定义（api 接口 / web 网页）"""
    type: str
    label: str
    fields: List[SpiderParamField] = []


class SpiderInfo(BaseModel):
    """单个可调度爬虫的注册信息"""
    name: str
    title: str
    type: str
    description: str = ""


class SpiderRegistryResponse(BaseModel):
    """爬虫注册表响应：类型表单定义 + 爬虫清单"""
    types: List[SpiderTypeInfo]
    spiders: List[SpiderInfo]


class TaskLogResponse(BaseModel):
    """任务运行日志响应（尾部 N 行）"""
    task_id: int
    spider_name: str
    status: str
    lines: List[str]


class SpiderResultResponse(BaseModel):
    """单条采集结果的对外响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    spider_name: str
    url: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    item_type: Optional[str] = None
    extra: Optional[str] = None
    quality_score: Optional[float] = None
    content_hash: Optional[str] = None
    created_at: Optional[datetime] = None


class SpiderResultListResponse(BaseModel):
    """任务结果分页响应"""
    total: int
    items: List[SpiderResultResponse]


class DailyPoint(BaseModel):
    """按日统计点（趋势图数据）"""
    date: str
    count: int


class TopSpider(BaseModel):
    """爬虫结果量排行项"""
    spider_name: str
    result_count: int


class WorkerActiveTask(BaseModel):
    """节点上爬虫的当前活跃任务"""
    spider_name: str
    task_id: Optional[int] = None
    status: Optional[str] = None


class WorkerNodeResponse(BaseModel):
    """Worker 节点心跳信息（/spiders/nodes 列表项）"""
    worker_id: str
    pid: Optional[int] = None
    spiders: List[str] = []
    started_at: Optional[str] = None
    respawn_count: int = 0
    online: bool = True
    active_tasks: List[WorkerActiveTask] = []


class WorkerNodeListResponse(BaseModel):
    """Worker 节点列表响应"""
    total: int
    items: List[WorkerNodeResponse]


class SpiderStatsResponse(BaseModel):
    """爬虫维度的统计数据"""
    total_tasks: int
    pending: int
    running: int
    completed: int
    failed: int
    # 阶段 2.1 运行统计扩展（无数据时为 None / 空）
    avg_duration_seconds: Optional[float] = None
    success_rate: Optional[float] = None
    total_results: int = 0
    daily_tasks: List[DailyPoint] = []
    daily_results: List[DailyPoint] = []
    top_spiders: List[TopSpider] = []


# ----------------------------------------------------------------------
# 定时调度契约（1.1）
# ----------------------------------------------------------------------
class ScheduleRequest(RequestBody):
    """创建/修改定时调度计划"""
    spider_name: str = Field(..., min_length=1, max_length=100)
    cron_expr: str = Field(..., min_length=9, max_length=100, description="5 段 cron 表达式，如 */5 * * * *")
    params: Optional[str] = Field(None, description="透传给爬虫的 JSON 字符串")
    enabled: bool = Field(True, description="是否启用")


class ScheduleUpdateRequest(RequestBody):
    """局部更新调度计划（启停/改表达式/改参数）"""
    cron_expr: Optional[str] = Field(None, min_length=9, max_length=100)
    params: Optional[str] = None
    enabled: Optional[bool] = None


class SpiderScheduleResponse(BaseModel):
    """单条调度计划的对外响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    spider_name: str
    cron_expr: str
    params: Optional[str] = None
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SpiderScheduleListResponse(BaseModel):
    """调度计划列表响应"""
    total: int
    items: List[SpiderScheduleResponse]


# ----------------------------------------------------------------------
# 数据源多存储契约（4.2）
# ----------------------------------------------------------------------
class TaskStoreStatusResponse(BaseModel):
    """任务的额外存储目标状态（除 MySQL 外的 redis/csv）"""
    task_id: int
    targets: List[str] = []  # 生效的存储目标（任务 params.store_to 优先，其次配置默认）
    redis_count: Optional[int] = None  # redis 缓存条数（目标含 redis/csv 时有值）
    csv_path: Optional[str] = None  # csv 落盘路径（未落盘为 None）


# ----------------------------------------------------------------------
# 代码爬虫文件管理契约（4.4）
# ----------------------------------------------------------------------
class SpiderFileResponse(BaseModel):
    """代码爬虫文件清单项（只读文件元数据 + 关联启停状态）"""
    name: str  # 文件名去后缀（约定与 spider name 一致）
    file: str  # 相对路径，如 scrapy/spiders/example.py
    size_bytes: int
    registered: bool  # 是否已登记到 spider_definitions
    enabled: Optional[bool] = None  # 启停状态（未登记为 None，视为未启用）
    title: Optional[str] = None


class SpiderFileListResponse(BaseModel):
    """代码爬虫文件清单响应"""
    total: int
    items: List[SpiderFileResponse]


class DefinitionUpdateRequest(RequestBody):
    """爬虫定义启停更新（仅 admin）"""
    enabled: bool


class DefinitionCreateRequest(RequestBody):
    """新建爬虫定义（仅 admin，来源标记为 manual）"""
    name: str = Field(..., min_length=1, max_length=50, description="爬虫名（与 scrapy spider name 一致）")
    title: str = Field(..., min_length=1, max_length=100, description="展示标题")
    type: str = Field("web", pattern="^(api|web|custom|flow)$", description="类型：api/web/custom/flow")
    description: Optional[str] = Field(None, max_length=2000, description="描述")


class DefinitionUpdateMetaRequest(RequestBody):
    """爬虫定义元信息局部更新（仅 admin，不含启停/名称）"""
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)


class TaskUpdateRequest(RequestBody):
    """待执行任务编辑（params/优先级，仅 pending/queued 可改）"""
    params: Optional[str] = Field(None, description="透传给爬虫的 JSON 字符串")
    priority: Optional[str] = Field(None, pattern="^(high|normal|low)$", description="任务优先级（高/普通/低）")


class TaskControlRequest(RequestBody):
    """任务控制请求（暂停/恢复/终止）"""
    action: str = Field(..., pattern="^(pause|resume|stop)$", description="控制动作：pause/resume/stop")


class SpiderDefinitionResponse(BaseModel):
    """爬虫定义的对外响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str
    type: str
    description: Optional[str] = None
    enabled: bool
    source: str = "yml_seed"


# ----------------------------------------------------------------------
# 数据质量监控（B1）
# ----------------------------------------------------------------------
class TaskQualityReportResponse(BaseModel):
    """任务数据质量报告"""
    task_id: int
    avg_score: Optional[float] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    total_items: int = 0
    score_distribution: Dict[str, int] = {
        "excellent(80-100)": 0,
        "good(60-80)": 0,
        "fair(40-60)": 0,
        "poor(0-40)": 0,
    }


# ----------------------------------------------------------------------
# 告警规则契约（B2）
# ----------------------------------------------------------------------
class AlertRuleRequest(BaseModel):
    """创建告警规则请求"""
    name: str
    spider_name: Optional[str] = None
    rule_type: str  # consecutive_failures / result_drop / task_timeout / queue_depth
    threshold: float
    window_minutes: int = 60
    severity: str = "warning"
    channels: Optional[List[str]] = None
    enabled: bool = True


class AlertRuleUpdateRequest(BaseModel):
    """更新告警规则请求"""
    name: Optional[str] = None
    threshold: Optional[float] = None
    window_minutes: Optional[int] = None
    severity: Optional[str] = None
    channels: Optional[List[str]] = None
    enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    """告警规则响应"""
    id: int
    name: str
    spider_name: Optional[str] = None
    rule_type: str
    threshold: float
    window_minutes: int = 60
    severity: str = "warning"
    channels: Optional[List] = None
    enabled: bool = True
    last_triggered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# 任务模板契约（C1）
# ----------------------------------------------------------------------
class TaskTemplateRequest(BaseModel):
    """创建任务模板请求"""
    name: str = Field(..., min_length=1, max_length=200)
    spider_name: str = Field(..., min_length=1, max_length=100)
    params: Optional[str] = None
    priority: str = Field("normal", pattern="^(high|normal|low)$")


class TaskTemplateUpdateRequest(BaseModel):
    """更新任务模板请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    spider_name: Optional[str] = Field(None, min_length=1, max_length=100)
    params: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(high|normal|low)$")


class TaskTemplateResponse(BaseModel):
    """任务模板响应"""
    id: int
    name: str
    spider_name: str
    params: Optional[str] = None
    priority: str = "normal"
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
