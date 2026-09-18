"""扫描 .agents：skill / plugin / command / agent + icon/background 路径。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from backend.services.plugin_service import _plugin_manifest_path
from backend.services.power_market.walk import (
    _fold_commands, _fold_skills, _parse_frontmatter, _read_manifest,
)
from platform_core.logger import get_logger

_SKIP_PLUGIN = {"README.md"}
_ICON_FILES = ("icon.png", "icon.webp", "icon.svg", "icon.jpg")
_BG_FILES = ("background.png", "background.webp", "background.jpg", "background.svg")
_IMG_EXT = {".png", ".webp", ".svg", ".jpg", ".jpeg", ".gif"}

logger = get_logger("service.power_market")


@dataclass
class HubItem:
    asset_type: str
    name: str
    title: str
    description: str
    category: str
    origin_ref: str
    origin_local_name: str
    origin_plugin_name: str | None
    file_path: str
    content_hash: str
    logo: str | None
    background: str | None
    license: str = "MIT"
    extra: dict = field(default_factory=dict)


def collect_agents_hub(agents_root: Path) -> list[HubItem]:
    logger.info(f"agents_hub.collect | root={agents_root}")
    root = agents_root.resolve() if agents_root.exists() else agents_root
    items: list[HubItem] = []
    items.extend(_scan_repo_skills(root))
    for pkg in _plugin_dirs(root):
        items.extend(_scan_plugin(pkg, root))
    items.extend(_scan_loose(root))
    return items


def _scan_loose(root: Path) -> list[HubItem]:
    """AD-4g：顶层 agents/*.md 与 commands/*.md（目录导入落盘的游离资产）。

    目录不存在即零行为变化——老仓库无这两个目录时本函数返回空列表，
    同步/对账口径与扩展前完全一致。游离资产 origin_plugin_name=None、
    name 不带 `plugin__` 前缀（它不属于任何插件）。
    """
    items: list[HubItem] = []
    items.extend(_scan_agents(root, root, None))
    if (root / "commands").is_dir():
        for raw in _fold_commands(root, {}):
            items.append(_command_item(root, root, None, raw))
    # QA-15：游离资产没有 plugin__ 前缀这层唯一性保护，任何未来改动都可能
    # 重新引入 slug 撞车——遍历式兜底：同 (asset_type, name) 出现第二次就
    # 警告，不吞掉、不去重（去重会让某一份文件的内容悄悄消失，交给同步
    # upsert 层的唯一键报错，这里只负责让人能第一时间发现是撞车不是别的）。
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.asset_type, item.name)
        if key in seen:
            logger.warning(f"游离资产 slug 撞车 | type={item.asset_type} name={item.name}")
        seen.add(key)
    return items


def _repo_rel(path: Path, agents_root: Path) -> str:
    repo = agents_root.parent
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        try:
            return f".agents/{path.relative_to(agents_root).as_posix()}"
        except ValueError:
            return path.as_posix()


def _pick_file(candidates: list[Path]) -> Path | None:
    for path in candidates:
        if path.is_file() and path.suffix.lower() in _IMG_EXT:
            return path
    return None


def _dir_icon(folder: Path, stem: str | None = None) -> Path | None:
    names: list[Path] = []
    if stem:
        names.extend(folder / f"{stem}.{kind}" for kind in ("icon.png", "icon.webp", "icon.svg"))
        names.extend(folder / "profiles" / stem / name for name in _ICON_FILES)
    names.extend(folder / name for name in _ICON_FILES)
    return _pick_file(names)


def _dir_background(folder: Path, stem: str | None = None) -> Path | None:
    names: list[Path] = []
    if stem:
        names.extend(
            folder / f"{stem}.{kind}"
            for kind in ("background.png", "background.webp", "background.jpg")
        )
        names.extend(folder / "profiles" / stem / name for name in _BG_FILES)
    names.extend(folder / name for name in _BG_FILES)
    return _pick_file(names)


def _digest(paths: list[Path | None]) -> str:
    hasher = hashlib.sha256()
    for path in paths:
        if path is not None and path.is_file():
            hasher.update(path.read_bytes())
        else:
            hasher.update(b"\0")
    return hasher.hexdigest()


def _plugin_dirs(agents_root: Path) -> list[Path]:
    plugins = agents_root / "plugins"
    if not plugins.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(plugins.iterdir()):
        if child.name in _SKIP_PLUGIN or child.name.startswith("."):
            continue
        if child.is_symlink() and not child.exists():
            # GWT-01.4：失效符号链接跳过原因入日志（同步不报错、不软删已有 live 行）
            logger.info(f"agents_hub 跳过失效符号链接 | plugins/{child.name}")
            continue
        if child.is_dir():
            out.append(child)
    return out


def _scan_repo_skills(agents_root: Path) -> list[HubItem]:
    skills_root = agents_root / "skills"
    if not skills_root.is_dir():
        return []
    items: list[HubItem] = []
    for folder in sorted(skills_root.iterdir()):
        md = folder / "SKILL.md"
        if not folder.is_dir() or not md.is_file():
            continue
        items.append(_skill_item(folder, md, agents_root, plugin=None, slug=folder.name))
    return items


def _skill_item(
    folder: Path, md: Path, agents_root: Path, *, plugin: str | None, slug: str,
) -> HubItem:
    meta = _parse_frontmatter(md.read_text(encoding="utf-8"))
    logo = _dir_icon(folder)
    bg = _dir_background(folder)
    title = (meta.get("name") or folder.name).strip()
    desc = (meta.get("description") or "")[:1024]
    return HubItem(
        asset_type="skill", name=slug[:128], title=title[:256], description=desc,
        category="skill", origin_ref=_repo_rel(folder, agents_root),
        origin_local_name=folder.name, origin_plugin_name=plugin,
        file_path=_repo_rel(folder, agents_root),
        content_hash=_digest([md, logo, bg]),
        logo=_repo_rel(logo, agents_root) if logo else None,
        background=_repo_rel(bg, agents_root) if bg else None,
    )


def _scan_plugin(pkg: Path, agents_root: Path) -> list[HubItem]:
    try:
        manifest = _read_manifest(pkg)
    except ValueError:
        return []
    folded = _fold_skills(pkg)
    items = [_plugin_item(pkg, agents_root, manifest, bundled=folded)]
    plugin = pkg.name
    for raw in folded:
        folder = Path(raw["file_path"]) if raw.get("file_path") else pkg / raw["origin_ref"]
        md = folder / "SKILL.md"
        if not md.is_file():
            continue
        slug = f"{plugin}__{raw['origin_local_name']}"
        items.append(_skill_item(folder, md, agents_root, plugin=plugin, slug=slug))
    for raw in _fold_commands(pkg, manifest):
        items.append(_command_item(pkg, agents_root, plugin, raw))
    items.extend(_scan_agents(pkg, agents_root, plugin))
    return items


def _plugin_item(pkg: Path, agents_root: Path, manifest: dict, *, bundled: list[dict]) -> HubItem:
    logo = _dir_icon(pkg)
    bg = _dir_background(pkg)
    man_path = _plugin_manifest_path(pkg) or pkg / "plugin.json"
    desc = str(manifest.get("description") or pkg.name)[:1024]
    license_id = str(manifest.get("license") or "MIT") or "MIT"
    return HubItem(
        asset_type="plugin", name=pkg.name[:128], title=pkg.name[:256],
        description=desc, category="plugin",
        origin_ref=_repo_rel(pkg, agents_root), origin_local_name=pkg.name,
        origin_plugin_name=None, file_path=_repo_rel(pkg, agents_root),
        content_hash=_digest([man_path, logo, bg]),
        logo=_repo_rel(logo, agents_root) if logo else None,
        background=_repo_rel(bg, agents_root) if bg else None,
        license=license_id[:64],
        extra={
            "manifest": manifest,
            "bundled_skills": sorted({r["origin_local_name"] for r in bundled}),
        },
    )


def _command_item(pkg: Path, agents_root: Path, plugin: str | None, raw: dict) -> HubItem:
    md = Path(raw["file_path"]) if raw.get("file_path") else pkg / raw["origin_ref"]
    folder = md.parent if md.suffix == ".md" else md
    stem = md.stem if md.suffix == ".md" else raw["origin_local_name"]
    logo = _dir_icon(folder, stem)
    bg = _dir_background(folder, stem)
    slug = (
        f"{plugin}__{raw['origin_local_name']}" if plugin else raw["origin_local_name"]
    )
    return HubItem(
        asset_type="command", name=slug[:128], title=str(raw.get("title") or stem)[:256],
        description=str(raw.get("description") or "")[:1024], category="command",
        origin_ref=str(raw.get("origin_ref") or ""), origin_local_name=raw["origin_local_name"],
        origin_plugin_name=plugin, file_path=_repo_rel(md if md.exists() else folder, agents_root),
        content_hash=_digest([md if md.exists() else None, logo, bg]),
        logo=_repo_rel(logo, agents_root) if logo else None,
        background=_repo_rel(bg, agents_root) if bg else None,
        extra={
            "slash": raw.get("slash") or raw["origin_local_name"],
            "body_md": raw.get("body_md") or "",
        },
    )


def _scan_agents(pkg: Path, agents_root: Path, plugin: str | None) -> list[HubItem]:
    agents_dir = pkg / "agents"
    if not agents_dir.is_dir():
        return []
    items: list[HubItem] = []
    for md in sorted(agents_dir.glob("*.md")):
        if md.name.startswith(".") or md.name.lower() == "readme.md":
            continue
        items.append(_agent_item(md, agents_dir, agents_root, plugin))
    return items


def _agent_item(md: Path, agents_dir: Path, agents_root: Path, plugin: str | None) -> HubItem:
    text = md.read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
    stem = md.stem
    logo = _dir_icon(agents_dir, stem)
    bg = _dir_background(agents_dir, stem)
    local = (meta.get("name") or stem).strip()
    # QA-15：游离资产（plugin=None）的 slug 之前直接用 frontmatter name——
    # 两份游离 .md 若 frontmatter 里 name 撞了，第二个 upsert 会更新到第一
    # 个刚 flush 的行（同 (asset_type, name) 唯一键），磁盘两份文件对应一行，
    # 一份资产静默不可见，prune 对账也少算。插件内 agent 靠 `plugin__` 前缀
    # 保证唯一，游离资产没有这层保护——改用磁盘文件名（stem，同目录内天然
    # 唯一，操作系统不允许重名文件）当 slug，frontmatter name 只做展示用途
    # （title 字段仍取 local，不受影响）。
    slug = f"{plugin}__{local}" if plugin else stem
    tools = _tools_list(meta.get("tools") or "")
    return HubItem(
        asset_type="agent", name=slug[:128], title=local[:256],
        description=str(meta.get("description") or "")[:1024], category="agent",
        origin_ref=_repo_rel(md, agents_root), origin_local_name=local,
        origin_plugin_name=plugin, file_path=_repo_rel(md, agents_root),
        content_hash=_digest([md, logo, bg]),
        logo=_repo_rel(logo, agents_root) if logo else None,
        background=_repo_rel(bg, agents_root) if bg else None,
        extra={"persona_md": body, "tools": tools},
    )


def _tools_list(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        inner = text.strip("[]")
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
    return [p.strip() for p in text.split(",") if p.strip()]
