"""能力市场 hub 根与 file_path 存储格式（D2：产品运行时根与开发中枢 `.agents/` 分离）。

- **根**：`SKILLS.AGENTS_ROOT`（键名沿用，语义 = 产品运行时 hub 根），默认
  `runtime/agents-hub`（`runtime/` 已 gitignore）；相对路径按进程 cwd 解析
  （run.py / uvicorn 均在仓库根启动）。同步 / 目录导入 / legacy 导入 / 失源清理只认这个根；
  开发中枢 `.agents/` 只有运维显式把根指过去才会被扫描。根不存在 = 空：
  同步按零项完成、导入落盘时逐级建目录、失源清理拒绝剪除（见 agents_hub）。
- **存储格式**：hub 来源行的 `file_path` / `origin_ref` / `logo` / `background` 一律写
  `agents-hub/<相对 hub 根的 posix 路径>`——逻辑前缀，与根的物理位置无关，挪根不用改库。
- **读兼容**：D2 前写入的 `.agents/<...>`（仓库根相对）仍认作 hub 来源行；解析时先找
  hub 根下同一相对位置（已迁移），不存在再回落仓库 `.agents/`（未迁移）。一次性迁移
  `scripts/db/migrate_agents_hub_root.py` 把产品内容挪进新根并改写前缀。
"""
from __future__ import annotations

from pathlib import Path

from backend.config_consts import SKILLS_AGENTS_ROOT
from platform_core.logger import get_logger

logger = get_logger("service.power_market")

HUB_PATH_PREFIX = "agents-hub/"
LEGACY_HUB_PREFIX = ".agents/"
HUB_PATH_PREFIXES = (HUB_PATH_PREFIX, LEGACY_HUB_PREFIX)
LEGACY_HUB_DIR = Path(__file__).resolve().parents[3] / ".agents"


def hub_root() -> Path:
    """产品运行时 hub 根（SKILLS.AGENTS_ROOT；相对路径按 cwd 解析）。"""
    logger.info("agents_hub.agents_root | resolve")
    return _configured_root()


def _configured_root() -> Path:
    """hub_root 的无日志版（公开详情 / 媒体每次请求都要解析，避免刷日志）。"""
    from config import settings

    raw = str(settings.get("SKILLS.AGENTS_ROOT", SKILLS_AGENTS_ROOT) or SKILLS_AGENTS_ROOT)
    root = Path(raw)
    return root if root.is_absolute() else Path.cwd() / root


def _to_stored(path: Path, root: Path) -> str:
    """磁盘路径 → 入库格式（hub 根内 = `agents-hub/<rel>`；根外兜底存绝对 posix）。"""
    try:
        return f"{HUB_PATH_PREFIX}{path.relative_to(root).as_posix()}"
    except ValueError:
        return path.as_posix()


def _is_hub_path(stored: str | None) -> bool:
    """是否 hub 来源行路径（新前缀或 D2 前的 `.agents/` 前缀）。"""
    text = (stored or "").strip()
    return any(text.startswith(prefix) for prefix in HUB_PATH_PREFIXES)


def _hub_tail(stored: str | None) -> str | None:
    """剥掉 hub 前缀后的相对路径；非 hub 路径、含 `..` 分量或剥完仍是绝对路径返回 None。"""
    text = (stored or "").strip()
    for prefix in HUB_PATH_PREFIXES:
        if text.startswith(prefix):
            tail = text[len(prefix):]
            if tail.startswith("/") or ".." in tail.split("/"):
                return None
            return tail
    return None


def _resolve_hub_path(stored: str | None, root: Path | None = None) -> Path | None:
    """入库路径 → 磁盘路径；非 hub 路径返回 None（调用方走各自的 legacy 分支）。

    legacy `.agents/` 前缀：hub 根下同位置存在即用（已迁移），否则回落仓库 `.agents/`
    （未迁移）；两处都没有时返回 hub 根下的位置（调用方按「不存在」处理）。
    """
    tail = _hub_tail(stored)
    if tail is None:
        return None
    primary = (root if root is not None else _configured_root()) / tail
    if (stored or "").strip().startswith(LEGACY_HUB_PREFIX) and not primary.exists():
        legacy = LEGACY_HUB_DIR / tail
        if legacy.exists():
            return legacy
    return primary
