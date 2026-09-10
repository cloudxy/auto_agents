"""源树遍历：包目录 + 插件内 SKILL.md（按 content_hash 折叠）。"""
import hashlib
import json
from pathlib import Path

from backend.services.plugin_service import _plugin_manifest_path
from backend.services.power_market.identity import SKIP_DIR_NAMES

_SKILL_MD = "SKILL.md"


def _iter_packages(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if _is_package(root):
        return [root]
    return sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name not in SKIP_DIR_NAMES
        and _is_package(d)
    )


def _is_package(path: Path) -> bool:
    return _plugin_manifest_path(path) is not None


def _read_manifest(plugin_dir: Path) -> dict:
    path = _plugin_manifest_path(plugin_dir)
    if path is None:
        return {"name": plugin_dir.name, "description": plugin_dir.name, "license": ""}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("name"):
        raise ValueError("plugin.json 缺 name")
    return data


def _iter_skill_files(plugin_dir: Path) -> list[Path]:
    skills_root = plugin_dir / "skills"
    if not skills_root.is_dir():
        return []
    found: list[Path] = []
    for md in sorted(skills_root.rglob(_SKILL_MD)):
        if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in md.relative_to(plugin_dir).parts):
            continue
        found.append(md)
    return found


def _skill_hash(md_path: Path) -> str:
    return hashlib.sha256(md_path.read_bytes()).hexdigest()


def _frontmatter_name(md_path: Path) -> str:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return md_path.parent.name
    lines = text.splitlines()
    for idx in range(1, min(len(lines), 40)):
        if lines[idx].strip() == "---":
            block = "\n".join(lines[1:idx])
            for line in block.splitlines():
                if line.startswith("name:"):
                    return line.split(":", 1)[1].strip().strip("\"'")
            break
    return md_path.parent.name


def _fold_skills(plugin_dir: Path) -> list[dict]:
    """同一 content_hash 折叠为一条；hash 不同走路径段。"""
    by_hash: dict[str, dict] = {}
    for md in _iter_skill_files(plugin_dir):
        rel = md.parent.relative_to(plugin_dir).as_posix()
        local = md.parent.name
        digest = _skill_hash(md)
        item = {
            "origin_ref": rel,
            "origin_local_name": local,
            "content_hash": digest,
            "title": _frontmatter_name(md),
            "file_path": md.parent.as_posix(),
            "alias_origin_refs": [],
        }
        hit = by_hash.get(digest)
        if hit is None:
            by_hash[digest] = item
            continue
        hit["alias_origin_refs"].append(rel)
    return list(by_hash.values())


def _bare_slash(value: str) -> str:
    return (value or "").strip().lstrip("/")[:64]


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    out: dict[str, str] = {}
    for idx in range(1, min(len(lines), 40)):
        if lines[idx].strip() != "---":
            continue
        for line in lines[1:idx]:
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            out[key.strip()] = val.strip().strip("\"'")
        break
    return out


def _command_item(
    *, local: str, slash: str, title: str, description: str,
    body_md: str, origin_ref: str, digest: str, file_path: str,
) -> dict:
    local = _bare_slash(local) or "command"
    title_text = (title or local).strip().lstrip("/") or local
    return {
        "origin_local_name": local[:128],
        "origin_ref": origin_ref,
        "slash": _bare_slash(slash) or local[:64],
        "title": title_text,
        "description": (description or "")[:512],
        "body_md": body_md or "",
        "content_hash": digest,
        "file_path": file_path or "",
    }


def _command_dirs(plugin_dir: Path, manifest: dict) -> list[Path]:
    raw = manifest.get("commands")
    candidates = []
    if isinstance(raw, str) and raw.strip():
        candidates.append(plugin_dir / raw.strip())
    candidates.append(plugin_dir / "commands")
    found: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if not path.is_dir():
            continue
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        found.append(path)
    return found


def _commands_from_files(plugin_dir: Path, manifest: dict) -> list[dict]:
    items: list[dict] = []
    for cmd_dir in _command_dirs(plugin_dir, manifest):
        for md in sorted(cmd_dir.glob("*.md")):
            if md.name.startswith("."):
                continue
            text = md.read_text(encoding="utf-8")
            meta = _parse_frontmatter(text)
            stem = md.stem
            local = meta.get("name") or stem
            items.append(_command_item(
                local=local, slash=meta.get("slash") or local, title=meta.get("name") or stem,
                description=meta.get("description") or "", body_md=text,
                origin_ref=md.relative_to(plugin_dir).as_posix(),
                digest=hashlib.sha256(md.read_bytes()).hexdigest(),
                file_path=md.as_posix(),
            ))
    return items


def _command_from_mapping(key: str, value) -> dict | None:
    if isinstance(value, dict):
        local = str(value.get("name") or key)
        title = str(value.get("title") or value.get("name") or key)
        desc = str(value.get("description") or "")
        body = str(value.get("prompt") or value.get("body") or value.get("body_md") or "")
        slash = str(value.get("slash") or local)
    elif isinstance(value, str):
        local, title, desc, body, slash = key, key, value, "", key
    else:
        return None
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""
    return _command_item(
        local=local, slash=slash, title=title, description=desc, body_md=body,
        origin_ref=f"commands/{_bare_slash(local) or 'command'}",
        digest=digest, file_path="",
    )


def _commands_from_manifest(manifest: dict) -> list[dict]:
    raw = manifest.get("commands")
    items: list[dict] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            parsed = _command_from_mapping(str(key), value)
            if parsed:
                items.append(parsed)
        return items
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                parsed = _command_from_mapping(str(entry.get("name") or ""), entry)
            elif isinstance(entry, str):
                parsed = _command_from_mapping(entry, {})
            else:
                parsed = None
            if parsed:
                items.append(parsed)
    return items


def _merge_command_file(prev: dict, item: dict) -> None:
    if item.get("body_md"):
        prev["body_md"] = item["body_md"]
    if item.get("content_hash"):
        prev["content_hash"] = item["content_hash"]
    if item.get("file_path"):
        prev["file_path"] = item["file_path"]
        prev["origin_ref"] = item.get("origin_ref") or prev.get("origin_ref")
    if item.get("slash"):
        prev["slash"] = item["slash"]
    if item.get("description") and not prev.get("description"):
        prev["description"] = item["description"]
    if item.get("title") and not prev.get("title"):
        prev["title"] = item["title"]


def _fold_commands(plugin_dir: Path, manifest: dict) -> list[dict]:
    """plugin.json commands + commands/*.md；同 origin_local_name 合并，文件正文优先。不执行 slash。"""
    by_local: dict[str, dict] = {}
    for item in _commands_from_manifest(manifest):
        by_local[item["origin_local_name"]] = item
    for item in _commands_from_files(plugin_dir, manifest):
        local = item["origin_local_name"]
        prev = by_local.get(local)
        if prev is None:
            by_local[local] = item
            continue
        _merge_command_file(prev, item)
    return list(by_local.values())
