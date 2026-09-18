"""公开读模型投影（feat-agents-market AD-5/AD-11，自 service.py 迁出）。

职责：行 → 公开 dict 的字段白名单投影 + 媒体 href + md 正文读取分流。
新增投影位：persona_md（agent 侧行，WIP 缺陷 B）、gate_open（CTA 闸语义）。
_read_skill_md 分流（WIP 缺陷 A 修复）：file_path 以 `.agents/` 开头 → 仓库根
相对读取；否则 LIBRARY_ROOT 兜底（legacy 行）。
"""
from pathlib import Path
from typing import Optional

from platform_core.models.capability import CapabilityAsset, CapabilityCommand

from backend.services.power_market.installs import hosts_for_asset
from backend.services.power_market.types import _to_public_asset_type

_PUBLIC_FIELDS = (
    "name", "title", "description", "category", "tier", "score",
    "status", "source_url", "source_author", "updated_at", "asset_type",
    "listing_state", "license",
    "featured",  # AD-6：综合序权重，随 items 外发（contract §4 #7）
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _project(
    row: CapabilityAsset, *, command: Optional[CapabilityCommand] = None,
) -> dict:
    item = {f: getattr(row, f) for f in _PUBLIC_FIELDS if hasattr(row, f)}
    item["asset_type"] = _to_public_asset_type(row.asset_type)
    item["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
    item["score"] = float(row.score) if row.score is not None else None
    # QA-13：featured 列随 050 迁移落地，`select(CapabilityAsset)` 在迁移前的
    # 库上本就会因未知列直接炸 SQL 错误——getattr 防御不到它声称保护的场景
    # （防御发生在 Python 属性访问阶段，SQL 报错发生在这之前），只留一份
    # ORM 侧真实存在时的类型归一化。
    item["featured"] = int(row.featured or 0)
    item["subscribable"] = row.listing_state == "listed"
    item["hosts"] = hosts_for_asset(row)
    pub = item["asset_type"]
    item["logo"] = _media_href(pub, row.name, "logo") if row.logo else None
    item["background"] = (
        _media_href(pub, row.name, "background") if row.background else None
    )
    if command is not None:
        item["slash"] = command.slash
    return item


def _media_href(asset_type: str, name: str, kind: str) -> str:
    from urllib.parse import quote

    return (
        f"/api/v1/public/capabilities/{quote(asset_type, safe='')}/"
        f"{quote(name, safe='')}/media/{kind}"
    )


def _read_skill_md(row: CapabilityAsset) -> str:
    rel = (row.file_path or row.name or "").strip()
    if not rel:
        return ""
    md = _md_path(rel) / "SKILL.md"
    try:
        return md.read_text(encoding="utf-8") if md.exists() else ""
    except OSError:
        return ""


def _md_path(rel: str) -> Path:
    if rel.startswith(".agents/"):
        return _REPO_ROOT / rel  # .agents 真相源：仓库根相对
    from backend.config_consts import SKILLS_LIBRARY_ROOT
    from config import settings

    library = Path(str(settings.get("SKILLS.LIBRARY_ROOT", SKILLS_LIBRARY_ROOT)))
    # QA-5（相对 HEAD 回归）：HEAD 原式 `Path(LIBRARY_ROOT) / rel` 天然对
    # 绝对/相对两种配置都正确；迁出时误把"绝对/相对归一化"与"拼 rel"糅在
    # 一起，绝对分支整个丢了 rel——默认配置是相对路径，回归静默通过零覆盖。
    return (library if library.is_absolute() else Path.cwd() / library) / rel
