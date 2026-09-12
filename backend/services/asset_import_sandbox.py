r"""导入沙箱收容与条目解析（FR-100 / ADR-0023 决策 2，asset_import_service 配套）

- _EntryGuard：条目路径收容（`../`、绝对路径、symlink 拒绝且失败原因列名称，
  GWT-100.7/NFR-04/SEC-11）+ 大小/条目数上限执法（单条目超限=条目失败且原因含
  上限数字 GWT-100.5；批累计/条目数超限=整批拒绝，压缩炸弹防线）。
- zip 符号链接识别 + 流式限长解压（头标说谎的炸弹条目不进内存）。
- frontmatter/名称解析：名称层再设一道禁路径段防线（frontmatter/manifest
  的 name 不得携带 `/`、`\`、`..`——资产名是落盘目录名）。
"""
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from backend.services.plugin_service import _MANIFEST_CANDIDATES
from platform_core.exceptions import ValidationException
from platform_core.logger import get_logger

logger = get_logger("service.asset_import")

_NAME_MAX = 128
_DESC_MAX = 1024


@dataclass
class EntryFailure:
    """条目级拒绝（逃逸/超大）。group=顶层分组名；空=无归属（仅拒绝+日志）"""

    group: str
    reason: str


class EntryGuard:
    """沙箱收容 + 上限执法（GWT-100.5/100.7；NFR-04/SEC-11）"""

    def __init__(self, file_bytes: int, batch_bytes: int, max_entries: int):
        self.file_bytes = file_bytes
        self.batch_bytes = batch_bytes
        self.max_entries = max_entries
        self.entries = 0
        self.decompressed = 0
        self.failures: list[EntryFailure] = []

    def check_path(self, name: str) -> "str | None":
        """路径收容：绝对路径 / `..` / 空段 → 条目拒绝（GWT-100.7）"""
        pure = PurePosixPath(name)
        if not pure.parts or pure.is_absolute() or ".." in pure.parts:
            self._reject(name)
            return None
        return pure.as_posix()

    def count_entry(self) -> None:
        self.entries += 1
        if self.entries > self.max_entries:
            raise ValidationException(
                message=f"条目数量超过上限（{self.max_entries}），整批拒绝", field="import")

    def reject_size(self, name: str, group: str) -> None:
        """单条目超限：该资产失败，原因含上限数字（GWT-100.5），同批其余继续"""
        self.failures.append(EntryFailure(group=group, reason=(
            f"文件超过大小上限（{self.file_bytes} 字节）：{name}，已拒绝")[:512]))
        logger.warning(f"导入条目超限拒绝 | entry={name}")

    def account_total(self, size: int) -> None:
        """解包累计上限：超限=压缩炸弹口径，整批失败（直接 raise）"""
        self.decompressed += size
        if self.decompressed > self.batch_bytes:
            raise ValidationException(
                message=f"解包总量超过大小上限（{self.batch_bytes} 字节），整批拒绝",
                field="import")

    def symlink_reject(self, name: str) -> None:
        self._reject(name)

    def _reject(self, name: str) -> None:
        """记失败条目并归属顶层分组（使携带资产整体失败）；无分组=仅拒绝+日志"""
        pure = PurePosixPath(name)
        parts = pure.parts
        if pure.is_absolute():
            group = parts[1] if len(parts) > 2 else ""  # ("/","pkg","f")→pkg
        elif parts and parts[0] not in ("..", ""):
            group = parts[0]
        else:
            group = ""
        self.failures.append(EntryFailure(
            group=group, reason=f"路径指向资产目录之外：{name}，已拒绝"))
        logger.warning(f"导入条目路径逃逸拒绝 | entry={name}")


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    """zip 内符号链接条目（unix mode 存于 external_attr 高 16 位）"""
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def _read_capped(zf: "zipfile.ZipFile", info: zipfile.ZipInfo, limit: int) -> "bytes | None":
    """流式解压单条目，超限即停（内存上限=limit+64KB）；None=超限"""
    chunks: list[bytes] = []
    total = 0
    with zf.open(info) as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                return None
            chunks.append(chunk)
    return b"".join(chunks)


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    for idx in range(1, min(len(lines), 80)):
        if lines[idx].strip() == "---":
            data = yaml.safe_load("\n".join(lines[1:idx]))
            return data if isinstance(data, dict) else {}
    raise ValueError("frontmatter 未闭合")


def _frontmatter_name(text: str, fallback: str) -> str:
    try:
        return str(_parse_frontmatter(text).get("name") or fallback).strip()[:_NAME_MAX]
    except ValueError:
        raise


def _marker_title(text: str, fallback: str) -> str:
    try:
        return str((_parse_frontmatter(text) or {}).get("description") or fallback)
    except ValueError:
        return fallback


def _valid_skill_name(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[a-z0-9][a-z0-9\-_]{1,127}", name))


def _valid_generic_name(name: str) -> bool:
    r"""agent/command/plugin 名：禁路径段（`/`、`\`、`..`）——防名称层逃逸"""
    import re

    return bool(name) and bool(re.fullmatch(r"[^/\\]+", name)) and name not in (".", "..")


def _first_segment(rel: str) -> str:
    return PurePosixPath(rel).parts[0] if PurePosixPath(rel).parts else ""


def _sandbox_dest(sandbox: Path, rel: str) -> Path:
    return sandbox.joinpath(*PurePosixPath(rel).parts)


@dataclass
class PendingAsset:
    """分类产物：一个可判定类型的候选（或带解析错误的候选）"""

    asset_type: str
    name: str
    title: str
    group: str
    files: list[tuple[str, Path]] = field(default_factory=list)  # (目标相对路径, 沙箱源)
    single_file: bool = False  # command：单 .md 落 commands/<name>.md
    error: str | None = None  # 解析/命名失败（failed item 原因）


def _dir_files(pkg: Path) -> list[tuple[str, Path]]:
    return sorted((p.relative_to(pkg).as_posix(), p) for p in pkg.rglob("*") if p.is_file())


def _entry_failure_for(p: PendingAsset, guard: EntryGuard) -> "str | None":
    """条目级拒绝归属：本分组第一条失败原因（使携带资产整体失败，不写半份）"""
    for f in guard.failures:
        if f.group and f.group == p.group:
            return f.reason
    return None


def _unmatched_entry_failures(pendings: list[PendingAsset], guard: EntryGuard) -> list[PendingAsset]:
    """无候选承载的条目拒绝 → 合成 failed 项（仅独立 .md：类型可由文件名判定；
    非 md 杂项的拒绝只留日志——GWT-100.3 的不可导入语义，evidence §8 记边界）"""
    matched = {p.group for p in pendings}
    out: list[PendingAsset] = []
    seen: set[str] = set()
    for f in guard.failures:
        fname = f.group or ""
        if (not fname or fname in matched or fname in seen
                or not fname.lower().endswith(".md")):
            continue
        seen.add(fname)
        kind = "skill" if fname.lower() == "skill.md" else (
            "agent" if fname.lower() == "agent.md" else "command")
        out.append(PendingAsset(
            asset_type=kind, name=Path(fname).stem, title="", group=fname,
            error=f.reason))
    return out


# ---------- 四类分类（GWT-100.4；类型由导入过程判定） ----------


def _collect_candidates(sandbox: Path) -> list[PendingAsset]:
    pendings: list[PendingAsset] = []
    for entry in sorted(sandbox.iterdir()):
        if entry.is_dir():
            pendings.extend(_classify_dir(entry))
        elif entry.is_file() and entry.suffix.lower() == ".md":
            pend = _classify_md(entry.name, entry.read_text(encoding="utf-8"), entry)
            if pend is not None:
                pendings.append(pend)
        else:
            logger.info(f"导入跳过不可识别条目 | entry={entry.name}")
    return pendings


def _classify_dir(pkg: Path) -> list[PendingAsset]:
    manifest = next((pkg / c for c in _MANIFEST_CANDIDATES if (pkg / c).is_file()), None)
    if manifest is not None:
        return [_plugin_pending(pkg, manifest)]
    for marker, kind in (("AGENT.md", "agent"), ("SKILL.md", "skill")):
        if (pkg / marker).is_file():
            return [_md_dir_pending(pkg, pkg / marker, kind)]
    cmds = pkg / "commands"
    if cmds.is_dir():
        out = []
        for md in sorted(cmds.glob("*.md")):
            pend = _classify_md(md.name, md.read_text(encoding="utf-8"), md)
            if pend is not None:
                pend.group = pkg.name  # 条目失败归属整包
                out.append(pend)
        return out
    return []


def _plugin_pending(pkg: Path, manifest: Path) -> PendingAsset:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not str(data.get("name") or "").strip():
            raise ValueError("plugin.json 缺 name")
    except ValueError as exc:
        return PendingAsset(
            asset_type="plugin", name=pkg.name, title="", group=pkg.name,
            error=f"plugin.json 非法: {exc}",
        )
    name = str(data["name"]).strip()[:_NAME_MAX]
    if not _valid_generic_name(name):
        return PendingAsset(
            asset_type="plugin", name=pkg.name, title="", group=pkg.name,
            error=f"插件名不合法（不得含路径段）: {name}",
        )
    return PendingAsset(
        asset_type="plugin", name=name, group=pkg.name,
        title=str(data.get("description") or "")[:_DESC_MAX],
        files=_dir_files(pkg),
    )


def _md_dir_pending(pkg: Path, marker: Path, kind: str) -> PendingAsset:
    text = marker.read_text(encoding="utf-8")
    title = _marker_title(text, pkg.name)[:_DESC_MAX]
    try:
        name = _frontmatter_name(text, pkg.name)
    except ValueError as exc:
        return PendingAsset(
            asset_type=kind, name=pkg.name, title=title, group=pkg.name,
            error=f"{marker.name} {exc}",
        )
    if kind == "skill" and not _valid_skill_name(name):
        return PendingAsset(
            asset_type=kind, name=name, title=title, group=pkg.name,
            error=f"技能名不合法（目录名规范）: {name}",
        )
    if kind != "skill" and not _valid_generic_name(name):
        return PendingAsset(
            asset_type=kind, name=pkg.name, title=title, group=pkg.name,
            error=f"资产名不合法（不得含路径段）: {name}",
        )
    return PendingAsset(
        asset_type=kind, name=name, group=pkg.name, title=title,
        files=_dir_files(pkg),
    )


def _classify_md(fname: str, text: str, src: Path) -> "PendingAsset | None":
    """独立 .md：SKILL.md→skill / AGENT.md→agent / 其余→command"""
    kind = "skill" if fname.lower() == "skill.md" else (
        "agent" if fname.lower() == "agent.md" else "command")
    stem = Path(fname).stem
    title = _marker_title(text, stem)[:_DESC_MAX]
    try:
        name = _frontmatter_name(text, stem)
    except ValueError as exc:
        return PendingAsset(
            asset_type=kind, name=stem, title="", group=fname, files=[(fname, src)],
            single_file=True, error=f"{fname} {exc}",
        )
    bad_name = (
        (kind == "skill" and not _valid_skill_name(name))
        or (kind != "skill" and not _valid_generic_name(name))
    )
    if bad_name:
        label = "技能名不合法（目录名规范）" if kind == "skill" else "资产名不合法（不得含路径段）"
        return PendingAsset(
            asset_type=kind, name=stem, title=title, group=fname, files=[(fname, src)],
            single_file=True, error=f"{label}: {name}",
        )
    return PendingAsset(
        asset_type=kind, name=name, title=title, group=fname,
        files=[(fname, src)], single_file=True,
    )
