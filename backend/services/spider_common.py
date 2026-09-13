"""爬虫域共享工具与常量（期 4 Facade 退役：原 spider_service.py 公共部分迁出）

职责：
- 共享常量：_PROJECT_ROOT / _SPIDERS_DIR / FLOW_SPIDER_NAME / _STORE_TARGET_ENUM
- 共享工具：resolve_spider_log_path / extract_store_targets / extract_flow /
  _read_task_log_sync（供 task / query 子 Service 与 tasks/consumer.py 复用）

约束（遵循 AuthService 范式）：
- 不直接写 SQL、不直接 session.execute，所有数据操作通过 Repository
- 存量 from-import 路径 backend.services.spider_service.<工具> 由该模块 re-export 兼容
"""
import json
import os
from typing import Optional

from config import settings
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("api")

__all__ = [
    "logger",
    "settings",
    "_PROJECT_ROOT",
    "_SPIDERS_DIR",
    "FLOW_SPIDER_NAME",
    "_FLOW_KEYS",
    "_INTERNAL_SPIDERS",
    "_STORE_TARGET_ENUM",
    "resolve_spider_log_path",
    "extract_store_targets",
    "extract_flow",
    "_read_task_log_sync",
    "require_enqueue_tenant",
    "NO_TENANT_ENQUEUE_MESSAGE",
]

NO_TENANT_ENQUEUE_MESSAGE = "没有企业身份，无法入队"
# FR-87 / GWT-87.3：只读提交入队拒绝句（同族中文；「无提交入口」的前端面归 T-18/T-20）。
READONLY_ENQUEUE_MESSAGE = "当前账号不能提交采集任务，请联系企业管理员"
# FR-U01 / NFR-U01：点提交后 3 秒内用户可见入队句（禁止「创建成功」顶替）。
ENQUEUE_ACCEPTED_COPY = "已入队"


def require_enqueue_tenant(tenant_id: int | None) -> int:
    logger.info(f"入队租户校验 | tenant={tenant_id}")
    if tenant_id is None:
        raise BusinessException(NO_TENANT_ENQUEUE_MESSAGE)
    try:
        tid = int(tenant_id)
    except (TypeError, ValueError):
        raise BusinessException(NO_TENANT_ENQUEUE_MESSAGE)
    if tid <= 0:
        raise BusinessException(NO_TENANT_ENQUEUE_MESSAGE)
    return tid


# 项目根目录（与 platform_core.logger 的日志根解析保持一致）
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 代码爬虫目录（4.4 文件清单只读扫描，不读文件内容，B2 边界）
_SPIDERS_DIR = os.path.join(_PROJECT_ROOT, "scrapy", "spiders")

# 阶段 5.1 流程化采集
FLOW_SPIDER_NAME = "flow_generic"
_FLOW_KEYS = ("pagination", "detail", "filters")

# T-41 / FR-104 方案视图内部项清单：demo 爬虫（example/openweather）、能力资产
# 收割器（skill_harvester）、flow 引擎伪爬虫（flow_generic 源码文件/引擎登记行）。
# 仅作用于 registry / files 两个读面（方案视图数据源，只滤视图）；DB 定义行、
# 启停、入队校验（_ensure_spider_available 走 DB 直查）与源码文件本身不受影响。
_INTERNAL_SPIDERS = frozenset({"example", "openweather", "skill_harvester", FLOW_SPIDER_NAME})

# 已实现的额外存储目标枚举
_STORE_TARGET_ENUM = ("redis", "csv")


def resolve_spider_log_path() -> Optional[str]:
    logger.debug("解析爬虫日志文件路径")
    spider_cfg = getattr(settings, "LOGGERS", {}).get("spider", {}) if hasattr(settings, "LOGGERS") else {}
    rel = "logs/spider/spider.log"
    if spider_cfg:
        rel = spider_cfg.get("FILE", spider_cfg.get("file", rel))
    if os.path.isabs(rel):
        candidate = os.path.abspath(rel)
    else:
        candidate = os.path.abspath(os.path.join(_PROJECT_ROOT, rel))
    log_root = os.path.join(_PROJECT_ROOT, "logs")
    if not candidate.startswith(log_root + os.sep):
        logger.warning(f"非法的爬虫日志路径，已拒绝: {candidate}")
        return None
    return candidate


def extract_store_targets(params: Optional[str]) -> list[str]:
    logger.debug(f"解析任务存储目标: params={params!r}" if params else "解析任务存储目标: 无 params")
    if not params:
        return []
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return []
    raw = data.get("store_to") if isinstance(data, dict) else None
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [t for t in raw if t in _STORE_TARGET_ENUM]


def extract_flow(params: Optional[str]) -> Optional[dict]:
    logger.debug(f"识别流程采集参数: params={params!r}" if params else "识别流程采集参数: 无 params")
    if not params:
        return None
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    flow = {}
    selectors = data.get("selectors")
    if isinstance(selectors, list):
        flow["selectors"] = [s for s in selectors if isinstance(s, dict)]
    for key in _FLOW_KEYS:
        section = data.get(key)
        if isinstance(section, dict) and section:
            flow[key] = section
        elif key == "filters" and isinstance(section, list):
            rules = [r for r in section if isinstance(r, dict)]
            if rules:
                flow[key] = rules
    has_section = any(k in flow for k in _FLOW_KEYS)
    return flow if has_section else None


def _read_task_log_sync(
    log_path: str,
    offset: int | None,
    tail: int,
    keyword: str | None = None,
    level: str | None = None,
) -> list[str]:
    """同步读取并过滤任务日志（供 asyncio.to_thread 调用）"""
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        size = os.fstat(f.fileno()).st_size
        if offset is not None and 0 < offset <= size:
            f.seek(offset)
        lines = f.read().splitlines()

    if not keyword and not level:
        return lines[-tail:]

    kw_lower = keyword.lower() if keyword else None
    level_upper = level.upper() if level else None
    filtered: list[str] = []
    for line in lines:
        if level_upper:
            parts = line.split("|")
            if len(parts) >= 2:
                line_level = parts[1].strip().upper()
                if line_level != level_upper:
                    continue
            else:
                continue
        if kw_lower and kw_lower not in line.lower():
            continue
        filtered.append(line)
    return filtered[-tail:]
