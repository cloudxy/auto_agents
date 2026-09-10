"""ADR-0012 目录身份：bundled slug、第一方规则、禁止改 uq。"""
from platform_core.models.capability import CapabilityAsset

BUNDLED_SEP = "__"
SOURCE_INDEXED = "source_indexed"
FIRST_PARTY_FIXTURE = "example-pdf-extractor"
FIRST_PARTY_STATUSES = ("stable", "recommended")
SKIP_DIR_NAMES = {
    "deprecated", "in-progress", "node_modules", ".git", "tests", "docs",
    "scripts", "references", "evals", "agents", "examples", "maintainers",
}


def _bundled_slug(plugin: str, origin_local_name: str) -> str:
    return f"{plugin}{BUNDLED_SEP}{origin_local_name}"


def _path_slug(plugin: str, origin_ref: str) -> str:
    parts = [p for p in origin_ref.replace("\\", "/").split("/") if p and p != "skills"]
    return _bundled_slug(plugin, BUNDLED_SEP.join(parts))


def _display_title(origin_local_name: str, frontmatter_name: str = "") -> str:
    text = (frontmatter_name or origin_local_name or "").strip()
    return text or origin_local_name


def _is_third_party(row: CapabilityAsset) -> bool:
    if getattr(row, "source_id", None) is not None:
        return True
    if int(getattr(row, "writable", 1) or 1) == 0:
        return True
    return (row.source_type or "self_built") != "self_built"


def _is_first_party_backfill(row: CapabilityAsset) -> bool:
    if row.source_id is not None:
        return False
    if row.origin_plugin_name:
        return False
    if (row.source_type or "self_built") != "self_built":
        return False
    if (row.status or "") not in FIRST_PARTY_STATUSES:
        return False
    return row.deleted_at is None
