"""目录导入（FR-07 / AD-4）：无状态两段式 preview→confirm，落盘统一 .agents。

设计要点（contract AD-4）：

- **a 上传形态**：每个 part 的 filename = 前端 `webkitRelativePath`。相对路径是
  前端可控输入，服务端在判型/落盘**之前**强制清洗（QA-8）：`..` 分量、绝对路径
  形态（前导 `/` 或盘符）、任何反斜杠分量一律判非法路径入跳过清单。
- **b 判型不另写一套**：把清洗后的树铺成 `.agents` 形状的暂存根，再交给
  `collect_agents_hub` 判型——与同步通道同一份实现（禁止两份）。暂存根就叫
  `.agents`，于是 `_repo_rel` 算出的 `file_path/origin_ref/logo/background`
  天然等于落盘后的真实相对路径，confirm 不需要二次改写。
- **d 无状态**：preview 与 confirm 各自上传同一棵树，判型确定性 → 结果一致；
  服务端不存暂存态，取消 = 不发 confirm（GWT-07.2 天然成立）。
- **e upsert**：同 asset_type+name 走 update（不是 legacy 的 skipped）；新建行
  `listing_state='unlisted'`（导入不自动上架）。
- **f 限额**：≤500 文件整批拒；单文件 ≤5MB；SKILL.md ≤1MB；扩展名白名单外
  入跳过清单不落盘（GWT-07.9）。
"""
from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from backend.services.power_market.agents_hub import _upsert_item_listing
from backend.services.power_market.agents_hub_scan import HubItem, collect_agents_hub
from backend.services.plugin_service import _plugin_manifest_path
from platform_core.exceptions import ValidationException
from platform_core.fs_guard import PathEscapeError, assert_contained
from platform_core.logger import get_logger

logger = get_logger("service.power_market")

MAX_FILES = 500
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_SKILL_MD_BYTES = 1024 * 1024
ALLOWED_EXT = {".md", ".json", ".png", ".webp", ".svg", ".jpg", ".jpeg", ".gif"}

MSG_TOO_MANY_FILES = f"单次最多导入 {MAX_FILES} 个文件，请改用服务器路径导入"
MSG_NO_ASSET = "未识别到可导入资产"
REASON_BAD_PATH = "非法路径"
REASON_EXT = "非白名单扩展名"
REASON_TOO_BIG = f"单文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 上限"
REASON_SKILL_MD_BIG = "SKILL.md 超过 1MB 上限"
REASON_DUP = "同名资产已在本批次出现，跳过"

_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass
class UploadedFile:
    """API 层读完的一个 part（服务层不依赖 FastAPI 类型）。"""

    filename: str
    content: bytes


def _clean_rel(raw: str) -> str | None:
    """相对路径清洗：非法返回 None（调用方入跳过清单）。"""
    text = (raw or "").strip()
    if not text or "\\" in text or text.startswith("/") or _DRIVE.match(text):
        return None
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _accept(rel: str, content: bytes) -> str | None:
    """返回拒收原因；None = 收下。"""
    suffix = Path(rel).suffix.lower()
    if suffix not in ALLOWED_EXT:
        return REASON_EXT
    if len(content) > MAX_FILE_BYTES:
        return REASON_TOO_BIG
    if Path(rel).name == "SKILL.md" and len(content) > MAX_SKILL_MD_BYTES:
        return REASON_SKILL_MD_BIG
    return None


def _materialize(files: list[UploadedFile], raw_root: Path) -> list[dict]:
    """把通过清洗与限额的 part 写进 raw_root；返回跳过清单。"""
    skipped: list[dict] = []
    for item in files:
        rel = _clean_rel(item.filename)
        if rel is None:
            skipped.append({"path": item.filename, "reason": REASON_BAD_PATH})
            continue
        reason = _accept(rel, item.content)
        if reason is not None:
            skipped.append({"path": rel, "reason": reason})
            continue
        target = raw_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
    return skipped


def _is_under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _plugin_roots(raw_root: Path) -> list[Path]:
    """含 plugin.json（或 _MANIFEST_CANDIDATES 嵌套位）的目录，去掉相互嵌套者。"""
    found = [
        d for d in sorted(raw_root.rglob("*")) if d.is_dir()
        and _plugin_manifest_path(d) is not None
    ]
    return [d for d in found if not any(_is_under(d, o) for o in found if o != d)]


def _skill_roots(raw_root: Path, plugins: list[Path]) -> list[Path]:
    """含 SKILL.md 且不在任何插件目录内的目录（插件内 skill 由插件展开负责）。"""
    return [
        d for d in sorted(raw_root.rglob("*")) if d.is_dir()
        and (d / "SKILL.md").is_file()
        and not any(_is_under(d, p) for p in plugins)
    ]


def _loose_md(raw_root: Path, folder: str, plugins: list[Path]) -> list[Path]:
    """游离 agents/*.md 或 commands/*.md（不在插件目录内）。"""
    return [
        md for md in sorted(raw_root.rglob(f"{folder}/*.md"))
        if md.is_file() and not any(_is_under(md, p) for p in plugins)
    ]


def _copy_into(src: Path, dst: Path, skipped: list[dict], raw_root: Path) -> bool:
    """同名已铺则记跳过（同批重名不静默覆盖）。"""
    if dst.exists():
        skipped.append({
            "path": src.relative_to(raw_root).as_posix(), "reason": REASON_DUP,
        })
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return True


def _stage(raw_root: Path, stage_root: Path, skipped: list[dict]) -> Path:
    """把 raw 树铺成 `.agents` 形状（判型与落盘共用同一形状）。"""
    agents = stage_root / ".agents"
    agents.mkdir(parents=True, exist_ok=True)
    plugins = _plugin_roots(raw_root)
    for pkg in plugins:
        _copy_into(pkg, agents / "plugins" / pkg.name, skipped, raw_root)
    for folder in _skill_roots(raw_root, plugins):
        _copy_into(folder, agents / "skills" / folder.name, skipped, raw_root)
    for md in _loose_md(raw_root, "agents", plugins):
        _copy_into(md, agents / "agents" / md.name, skipped, raw_root)
    for md in _loose_md(raw_root, "commands", plugins):
        _copy_into(md, agents / "commands" / md.name, skipped, raw_root)
    return agents


def _bundle(items: list[HubItem]) -> list[dict]:
    """插件把它展开出来的 bundled 资产挂在自己名下，供向导折叠展示。"""
    by_plugin: dict[str, list[dict]] = {}
    top: list[dict] = []
    for item in items:
        node = {
            "asset_type": item.asset_type, "name": item.name,
            "origin_path": item.file_path,
        }
        if item.origin_plugin_name:
            by_plugin.setdefault(item.origin_plugin_name, []).append(node)
        else:
            top.append(node)
    for node in top:
        if node["asset_type"] == "plugin":
            node["bundled"] = by_plugin.pop(node["name"], [])
    for orphans in by_plugin.values():  # 插件行缺失时不吞掉子项
        top.extend(orphans)
    return top


def _guard_count(files: list[UploadedFile]) -> None:
    if len(files) > MAX_FILES:
        raise ValidationException(MSG_TOO_MANY_FILES, field="files")


async def preview_tree_import(session, files: list[UploadedFile]) -> dict:
    """预览（不写库不落盘）：判型清单 + 跳过清单 + 四类计数。"""
    logger.info(f"hub_import.preview | parts={len(files)}")
    _guard_count(files)
    with tempfile.TemporaryDirectory(prefix="hub-import-") as tmp:
        items, skipped = _collect(Path(tmp), files)
        actions = await _actions(session, items)
        assets = _bundle(items)
        for node in assets:
            node["action"] = actions.get((node["asset_type"], node["name"]), "create")
            for child in node.get("bundled") or []:
                child["action"] = actions.get(
                    (child["asset_type"], child["name"]), "create",
                )
        counts = {t: 0 for t in ("skill", "plugin", "command", "agent")}
        for item in items:
            counts[item.asset_type] = counts.get(item.asset_type, 0) + 1
        return {
            "assets": assets, "skipped": skipped, "counts": counts,
            "files_total": len(files),
        }


async def confirm_tree_import(session, files: list[UploadedFile], *, agents_root) -> dict:
    """确认：落盘到真实 .agents 根 + upsert 入库（单项失败不整批回滚，GWT-07.5）。

    QA-10：contract §4 #4 要求响应带 batch_id 但实现之前没给——回执号不入库
    （db-spec §10 裁定），只是一次导入批次的关联令牌，随 import_completed
    事件一起发（emit_import_completed 的 batch_id 形参此前一直存在但从未被
    传值）。用 uuid4 而不是自增 id：这批资产本身不建表，没有天然的行 id 可用。
    """
    logger.info(f"hub_import.confirm | parts={len(files)} root={agents_root}")
    _guard_count(files)
    batch_id = uuid4().hex[:12]
    created = updated = 0
    failed: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="hub-import-") as tmp:
        items, skipped = _collect(Path(tmp), files)
        staged = Path(tmp) / "stage" / ".agents"
        for item in items:
            try:
                _land(staged, Path(agents_root), item)
                action = await _upsert_item_listing(session, item, listing="unlisted")
            except Exception as exc:  # noqa: BLE001 单项失败入清单，不中断整批
                failed.append({"name": item.name, "reason": str(exc)})
                logger.warning(
                    f"hub_import 单项失败 | type={item.asset_type} "
                    f"name={item.name} err={exc}"
                )
                continue
            if action == "inserted":
                created += 1
            elif action == "updated":
                updated += 1
        await session.flush()
    return {
        "created": created, "updated": updated, "failed": failed, "skipped": skipped,
        "batch_id": batch_id,
    }


def _collect(tmp: Path, files: list[UploadedFile]) -> tuple[list[HubItem], list[dict]]:
    """清洗 → 铺 .agents 形状 → 复用同步通道判型。空批次 422（GWT-07.4）。"""
    raw_root = tmp / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    skipped = _materialize(files, raw_root)
    staged = _stage(raw_root, tmp / "stage", skipped)
    items = collect_agents_hub(staged)
    if not items:
        raise ValidationException(MSG_NO_ASSET, field="files")
    return items, skipped


def _land(staged_agents: Path, real_agents: Path, item: HubItem) -> None:
    """把该资产在暂存 .agents 下的产物复制到真实 .agents 同名位置（update 语义）。

    QA-1 修复：落盘前经 `assert_contained` 做出口路径收容——`.agents/plugins/*`
    在本仓库全部是指向仓外真实目录的符号链接（指针农场，"禁止复制内容"），入口
    清洗（QA-8 的 `_clean_rel`）只保证相对路径字面量合法，不保证它落盘时不会
    穿过既有符号链接写到仓库外；出口必须单独收容，两者不能互相替代。
    QA-9 修复：不再 `rmtree` 后 `copytree`（会把真实 `.agents/<type>/<name>`
    下不在本次上传树里的文件，例如 049 迁移引入的 icon.png/background.png，
    一并静默删除）——改用 `dirs_exist_ok=True` 做增量合并式更新，只覆盖上传
    树里出现的文件。
    """
    rel = (item.file_path or "").strip()
    if not rel.startswith(".agents/"):
        raise ValueError(f"落盘路径非法：{rel}")
    tail = rel[len(".agents/"):]
    src = staged_agents / tail
    dst = real_agents / tail
    if not src.exists():
        raise ValueError(f"暂存产物缺失：{rel}")
    try:
        dst = assert_contained(dst, real_agents)
    except PathEscapeError as exc:
        raise ValueError(f"落盘路径逃逸收容根：{rel}") from exc
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


async def _actions(session, items: list[HubItem]) -> dict[tuple[str, str], str]:
    """预览的 create/update 标注：库里已有同类同名 live 行即 update。"""
    from sqlalchemy import select

    from platform_core.models.capability import CapabilityAsset

    pairs = {(i.asset_type, i.name) for i in items}
    if not pairs:
        return {}
    rows = (await session.execute(
        select(CapabilityAsset.asset_type, CapabilityAsset.name).where(
            CapabilityAsset.deleted_at.is_(None),
            CapabilityAsset.name.in_({n for _t, n in pairs}),
        )
    )).all()
    live = {(t, n) for t, n in rows}
    return {p: ("update" if p in live else "create") for p in pairs}
