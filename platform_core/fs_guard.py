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

from pathlib import Path


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
