"""路径收容断言（F5，见 .sdlc/feat-agents-market/05-review/findings.md QA-1）。

背景：仓库里曾并存三份强度不同的路径收容实现——
`asset_import_service._contained_write`（resolve + is_relative_to，最强）、
`public_skills._safe_media_file`（前缀 + ".." 分量 + 后缀白名单，中）、
`hub_import._land`（仅前缀字符串判断，最弱——QA-1 blocker：经
`.agents/plugins/*` 既有符号链接把导入内容写到仓库外，且可 `rmtree` 删除
仓外真实目录）。

本模块是**唯一**实现，服务层任何文件写操作（`shutil.copytree` /
`copy2` / `rmtree` / `Path.write_*` / `open(..., "w")`）落盘前必须调用
`assert_contained`。`tools/check/arch.sh` 对此有机械检查（白名单模式：
服务层出现上述写操作时，同文件必须 import 本模块）。

防御边界不依赖"符号链接当前指向哪里"这种拓扑事实——只要路径中任何一段
是符号链接就拒绝，不做"这个符号链接恰好指回收容根内"的例外判断，防止
以后新增符号链接时悄悄放行。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from platform_core.logger import get_logger

logger = get_logger("fs_guard")


class PathEscapeError(OSError):
    """目标路径逃逸出收容根目录（含经符号链接逃逸）。"""


def assert_contained(dst: Path, root: Path) -> Path:
    """断言 dst 落在 root 内、且路径中没有符号链接把它带出 root。

    调用时机：任何 mkdir/copytree/copy2/rmtree/write 之前，dst 必须是
    "将要写入的最终目标路径"，不能是已经穿过 mkdir(parents=True) 之后
    的路径（那样符号链接已经被 OS 静默跟随创建了）。

    - 逐段检查 root 与 dst 之间**已存在**的每个目录分量：任何一段是
      符号链接（不论其目标是否仍在 root 内）一律拒绝。这是主防线，
      在任何写操作发生前生效，不依赖 resolve() 的语义细节。
    - resolve() + is_relative_to 兜底：万一遍历漏检某种间接引用形式，
      展开后的真实路径也必须仍在收容根内。
    - 返回 resolve() 后的 dst，供调用方直接使用；不通过返回 False 让
      调用方"忘记判断"，而是抛异常强制处理。

    Raises:
        PathEscapeError: dst 不在 root 前缀下，或路径中出现符号链接，
            或 resolve 后逃逸出 root。
    """
    try:
        rel_parts = dst.relative_to(root).parts
    except ValueError as exc:
        raise PathEscapeError(f"越界写入拒绝（目标不在收容根前缀下）: {dst}") from exc

    root_real = root.resolve()
    walker = root_real
    for part in rel_parts:
        walker = walker / part
        if walker.is_symlink():
            raise PathEscapeError(f"越界写入拒绝（路径分量为符号链接）: {walker}")

    dst_real = dst.resolve()
    if not dst_real.is_relative_to(root_real):
        raise PathEscapeError(f"越界写入拒绝（resolve 后不在收容根内）: {dst}")
    return dst_real


class LandingJournal:
    """可撤回的落盘日志（审计 BUG-33）：逐文件原子写，记下每个目标原来的样子。

    - 写：先写同目录临时文件，再 os.replace（原子，不会留下写了一半的文件）；
      目标已存在则先备份原内容。
    - 撤回：按写入逆序，原来存在的从备份还原、原来不存在的删掉，本次新建的空目录删掉。
    - mark() / rollback_to(mark)：配合数据库 savepoint 撤回单项；rollback_to(0) 撤回整批。

    收容校验（assert_contained）仍由调用方在写之前做——本类只管原子性与可撤回。
    """

    def __init__(self, backup_dir: Path):
        self._backup_dir = backup_dir
        self._entries: list[tuple[Path, Path | None]] = []   # (目标, 备份；None=原先不存在)
        self._dirs: list[Path] = []                          # 本次新建的目录（先建的在前）

    def mark(self) -> int:
        return len(self._entries)

    def _ensure_dir(self, path: Path) -> None:
        missing = []
        cur = path
        while not cur.exists():
            missing.append(cur)
            cur = cur.parent
        for d in reversed(missing):
            d.mkdir()
            self._dirs.append(d)

    def _place(self, dst: Path, fill) -> None:
        self._ensure_dir(dst.parent)
        backup: Path | None = None
        if dst.exists():
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            backup = self._backup_dir / f"{len(self._entries)}-{dst.name}"
            shutil.copy2(dst, backup)
        tmp = dst.with_name(f".{dst.name}.{uuid4().hex[:8]}.tmp")
        try:
            fill(tmp)
            os.replace(tmp, dst)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        self._entries.append((dst, backup))

    def copy(self, src: Path, dst: Path) -> None:
        self._place(dst, lambda tmp: shutil.copy2(src, tmp))

    def write_bytes(self, dst: Path, data: bytes) -> None:
        self._place(dst, lambda tmp: tmp.write_bytes(data))

    def rollback_to(self, mark: int) -> None:
        while len(self._entries) > mark:
            dst, backup = self._entries.pop()
            try:
                if backup is None:
                    dst.unlink(missing_ok=True)
                else:
                    os.replace(backup, dst)
            except OSError as exc:  # 撤回尽力而为：记录后继续撤其余文件
                logger.error(f"落盘撤回失败 | path={dst} err={exc}")
        for d in reversed(self._dirs):
            try:
                d.rmdir()  # 只删空目录；仍有别的文件说明不是本次独占，保留
            except OSError:
                continue
        self._dirs = [d for d in self._dirs if d.exists()]
