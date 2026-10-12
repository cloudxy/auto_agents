#!/usr/bin/env python3
"""D2 一次性迁移：产品内容搬出开发中枢 `.agents/`，进产品 hub 根，并改写库内路径前缀。

用法（仓库根目录；**先停后端**，避免迁移期间同步 / 导入并发写）：
    uv run python scripts/db/migrate_agents_hub_root.py            # dry-run（默认）：只打印计划
    uv run python scripts/db/migrate_agents_hub_root.py --apply    # 执行
选项：--env {local,dev,prod}；--target <hub 根>（默认 SKILLS.AGENTS_ROOT，相对路径按 --repo 解析）；
     --repo <仓库根>（默认本脚本所在仓库）；--db-url <SQLAlchemy URL>（默认 MYSQL.DEFAULT）；
     --skip-db（只搬文件，不碰库）。

文件（`.agents/{skills,plugins,agents,commands}/<name>` 逐项判定）：
- keep：git 跟踪的开发内容（`git ls-files` 命中）、plugins-lock.json 登记的插件、任何符号链接
  （插件指针农场）——它们是开发协作资产，留在中枢；
- move：其余（D2 前目录导入 / legacy 导入落进中枢的产品内容）→ `<hub 根>/<kind>/<name>`；
- conflict：hub 根里已有同名项，跳过（人工合并后重跑）。
  注意：本机未 `git add` 的开发中 skill 也会被判 move——dry-run 先核对。
库（capability_assets 的 file_path / origin_ref / logo / background）：
- `.agents/` 前缀且所指项已在（或将搬进）hub 根 → 改写为 `agents-hub/`；
- 所指项是 keep（开发内容被同步当成产品上架）且行存活、listed / coming_soon → 下架为 unlisted
  （不删行，超管可再上架）；
- 其余（磁盘哪里都没有的孤儿）不动，交给失源清理（prune）。
顺序：先搬文件、后改库（单事务）。库事务失败时 legacy 前缀仍按「hub 根优先」解析到搬后的位置，
读不断；重复执行幂等（搬过的不再出现在中枢，改过的前缀不再匹配）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.power_market.hub_paths import (  # noqa: E402
    HUB_PATH_PREFIX,
    LEGACY_HUB_PREFIX,
)

DEV_HUB = LEGACY_HUB_PREFIX.rstrip("/")  # 开发中枢目录名（仓库根下）
KINDS = ("skills", "plugins", "agents", "commands")
PATH_COLUMNS = ("file_path", "origin_ref", "logo", "background")
_VISIBLE = ("listed", "coming_soon")


@dataclass
class Entry:
    key: str      # "<kind>/<name>"，相对 .agents/ 与 hub 根
    action: str   # move / keep / conflict
    reason: str = ""


@dataclass
class RowChange:
    row_id: int
    label: str
    updates: dict = field(default_factory=dict)
    note: str = ""


def _tracked_keys(repo: Path) -> set[str] | None:
    """git 跟踪的 `.agents/<kind>/<name>` 集合；git 不可用 / 非仓库返回 None。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", DEV_HUB],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    keys: set[str] = set()
    for raw in out.split(b"\0"):
        parts = raw.decode("utf-8", "replace").split("/")
        if len(parts) >= 3 and parts[0] == DEV_HUB:
            keys.add(f"{parts[1]}/{parts[2]}")
    return keys


def _lock_plugins(repo: Path) -> set[str]:
    path = repo / "plugins-lock.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set((data.get("plugins") or {}).keys())


def _classify(child: Path, key: str, target: Path, tracked: set[str], locked: set[str]) -> Entry:
    if child.is_symlink():
        return Entry(key, "keep", "符号链接（插件指针农场）")
    if key.startswith("plugins/") and child.name in locked:
        return Entry(key, "keep", "plugins-lock.json 登记的插件")
    if key in tracked:
        return Entry(key, "keep", "git 跟踪的开发内容")
    if (target / key).exists() or (target / key).is_symlink():
        return Entry(key, "conflict", f"hub 根已有 {target / key}")
    return Entry(key, "move")


def plan_entries(repo: Path, target: Path, tracked: set[str], locked: set[str]) -> list[Entry]:
    """逐项判定 `.agents/<kind>/<name>`（README 与隐藏项不参与）。"""
    entries: list[Entry] = []
    for kind in KINDS:
        base = repo / DEV_HUB / kind
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.name.startswith(".") or child.name.lower() == "readme.md":
                continue
            entries.append(_classify(child, f"{kind}/{child.name}", target, tracked, locked))
    return entries


def move_entries(entries: list[Entry], repo: Path, target: Path) -> int:
    moved = 0
    for entry in entries:
        if entry.action != "move":
            continue
        dst = target / entry.key
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(repo / DEV_HUB / entry.key), str(dst))
        moved += 1
    return moved


def _key_of(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text.startswith(LEGACY_HUB_PREFIX):
        return None
    parts = text[len(LEGACY_HUB_PREFIX):].split("/")
    return f"{parts[0]}/{parts[1]}" if len(parts) >= 2 and parts[0] in KINDS and parts[1] else None


def _row_change(row, in_hub, dev_keys: set[str]) -> RowChange | None:
    label = f"{row.asset_type}/{row.name}"
    updates = {
        col: HUB_PATH_PREFIX + getattr(row, col)[len(LEGACY_HUB_PREFIX):]
        for col in PATH_COLUMNS
        if (key := _key_of(getattr(row, col))) is not None and in_hub(key)
    }
    if updates:
        note = f"{','.join(updates)}: {LEGACY_HUB_PREFIX} → {HUB_PATH_PREFIX}"
        return RowChange(row.id, label, updates, note)
    key = _key_of(row.file_path)
    if key in dev_keys and row.deleted_at is None and row.listing_state in _VISIBLE:
        return RowChange(row.id, label, {"listing_state": "unlisted"},
                         f"开发内容行 {row.listing_state} → unlisted")
    return None


def plan_rows(conn, entries: list[Entry], target: Path) -> list[RowChange]:
    """库内 legacy 前缀行 → 改写 / 下架计划（只读）。"""
    from sqlalchemy import or_, select

    from platform_core.models.capability import CapabilityAsset

    table = CapabilityAsset.__table__
    moving = {e.key for e in entries if e.action == "move"}
    dev_keys = {e.key for e in entries if e.action == "keep"}

    def in_hub(key: str) -> bool:
        return key in moving or (target / key).exists()

    rows = conn.execute(
        select(table.c.id, table.c.asset_type, table.c.name, table.c.listing_state,
               table.c.deleted_at, *(table.c[c] for c in PATH_COLUMNS))
        .where(or_(*(table.c[c].like(f"{LEGACY_HUB_PREFIX}%") for c in PATH_COLUMNS)))
        .order_by(table.c.id)
    ).all()
    return [ch for ch in (_row_change(r, in_hub, dev_keys) for r in rows) if ch is not None]


def apply_rows(conn, changes: list[RowChange]) -> None:
    from sqlalchemy import update

    from platform_core.models.capability import CapabilityAsset

    table = CapabilityAsset.__table__
    for change in changes:
        conn.execute(update(table).where(table.c.id == change.row_id).values(**change.updates))


def _default_db_url() -> str:
    from config import settings

    cfg = settings.MYSQL.DEFAULT
    pwd = os.getenv("MYSQL_DEFAULT_PASSWORD") or str(settings.get("MYSQL_DEFAULT_PASSWORD", "") or "")
    return (f"mysql+pymysql://{cfg.USER}:{quote_plus(pwd)}@{cfg.HOST}:{cfg.PORT}/"
            f"{cfg.DB_NAME}?charset={cfg.get('CHARSET', 'utf8mb4')}")


def migrate_db(url: str, entries: list[Entry], target: Path, *, apply: bool) -> list[RowChange]:
    """单事务：读计划 → 打印 →（apply 时）落库；dry-run 只读。"""
    from sqlalchemy import create_engine

    kwargs: dict = {}
    if url.startswith("mysql"):
        from platform_core.timeutil import MYSQL_UTC_CONNECT_ARGS

        kwargs["connect_args"] = dict(MYSQL_UTC_CONNECT_ARGS)
    engine = create_engine(url, **kwargs)
    try:
        with engine.begin() as conn:
            changes = plan_rows(conn, entries, target)
            for ch in changes:
                print(f"[db] capability_assets#{ch.row_id} {ch.label} {ch.note}")
            if apply:
                apply_rows(conn, changes)
    finally:
        engine.dispose()
    return changes


def _target_root(raw: str | None, repo: Path) -> Path:
    if not raw:
        from config import settings

        from backend.config_consts import SKILLS_AGENTS_ROOT

        raw = str(settings.get("SKILLS.AGENTS_ROOT", SKILLS_AGENTS_ROOT) or SKILLS_AGENTS_ROOT)
    root = Path(raw).expanduser()
    return root if root.is_absolute() else repo / root


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true", help="执行（默认 dry-run 只打印计划）")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--repo", default=str(ROOT), help="仓库根（含 .agents/ 与 plugins-lock.json）")
    parser.add_argument("--target", default=None, help="产品 hub 根（默认 SKILLS.AGENTS_ROOT）")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy URL（默认 MYSQL.DEFAULT）")
    parser.add_argument("--skip-db", action="store_true", help="只搬文件，不改库")
    return parser.parse_args(argv)


def _print_entries(entries: list[Entry], target: Path) -> None:
    for e in entries:
        if e.action == "move":
            print(f"[move] {LEGACY_HUB_PREFIX}{e.key} -> {target / e.key}")
        else:
            print(f"[{e.action}] {LEGACY_HUB_PREFIX}{e.key}（{e.reason}）")


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.env:
        os.environ["APP_ENV"] = args.env
    repo = Path(args.repo).expanduser().resolve()
    target = _target_root(args.target, repo)
    if target.resolve() == (repo / DEV_HUB).resolve():
        print("hub 根就是开发中枢 .agents/（运维显式指定），无需迁移")
        return 2
    tracked = _tracked_keys(repo)
    if tracked is None:
        print(f"git ls-files 失败（{repo} 不是 git 仓库？）：无法区分开发内容与产品内容，拒绝执行")
        return 2
    entries = plan_entries(repo, target, tracked, _lock_plugins(repo))
    _print_entries(entries, target)
    moved = move_entries(entries, repo, target) if args.apply else 0
    changes = [] if args.skip_db else migrate_db(
        args.db_url or _default_db_url(), entries, target, apply=args.apply)
    counts = {a: sum(1 for e in entries if e.action == a) for a in ("move", "keep", "conflict")}
    unlisted = sum(1 for c in changes if "listing_state" in c.updates)
    print(f"汇总：move={counts['move']} keep={counts['keep']} conflict={counts['conflict']} "
          f"| 改写={len(changes) - unlisted} 下架={unlisted}" + (" | 库：已跳过" if args.skip_db else ""))
    if args.apply:
        print(f"已执行：搬移 {moved} 项到 {target}；库改动 {len(changes)} 行")
    else:
        print("dry-run：未改动任何文件与数据库；核对后加 --apply 执行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
