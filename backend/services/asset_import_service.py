"""能力资产统一导入服务（FR-100 / ADR-0023）——上传/目录 → 沙箱 → 四类分发

一个导入通道，四类是分支不是四个入口（ADR-0023 决策 1）：multipart 文件
（单 .md 或 zip 包）或服务器本地目录 → 临时沙箱解包/复制 → 四类判定
（skill=SKILL.md / agent=AGENT.md / command=commands/*.md 或独立 .md /
plugin=plugin.json）→ 落盘资产目录 + capability_assets 目录行（unlisted，
**未上架**，PC-2 不动）。收容/上限执法见 asset_import_sandbox（决策 2）：
逃逸条目拒绝且原因列名称、资产目录外零新文件（GWT-100.7/NFR-04/SEC-11）；
部分成功常态语义（100.2/100.3）；幂等=类型+名称，uq 兜底，并发撞键降级
skipped（100.8）；0 可导入=completed+中性说明；不触发执行不自动上架；
完成上报 asset_imported（GWT-92.9）。细节表由既有扫描端点补全（evidence §8）。
"""
import io
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import (
    ASSET_IMPORT_MAX_BATCH_BYTES,
    ASSET_IMPORT_MAX_ENTRIES,
    ASSET_IMPORT_MAX_FILE_BYTES,
    ASSET_IMPORT_SANDBOX_ROOT,
    SKILLS_LIBRARY_ROOT,
)
from backend.services.asset_import_sandbox import (
    EntryGuard,
    PendingAsset,
    _collect_candidates,
    _entry_failure_for,
    _unmatched_entry_failures,
    _first_segment,
    _is_symlink_member,
    _read_capped,
    _sandbox_dest,
)
from backend.services.product_event_service import emit_product_event
from platform_core.exceptions import ValidationException
from platform_core.logger import get_logger
from platform_core.models.asset_import import AssetImportBatch, AssetImportItem
from platform_core.models.capability import CapabilityAsset

logger = get_logger("service.asset_import")

ASSET_IMPORTED_EVENT = "asset_imported"
EMPTY_MESSAGE = "没有可导入的资产。"
_NAME_MAX = 128
_DESC_MAX = 1024
_ZIP_MAGIC = b"PK\x03\x04"

# 四类 → capability-library 落盘子目录（skill/plugin 与既有扫描器布局一致）
_TYPE_DIRS = {"skill": "skills", "agent": "agents", "command": "commands", "plugin": "plugins"}
_CATEGORY = {"skill": "uncategorized", "agent": "agent", "command": "command", "plugin": "plugin"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_limits() -> "tuple[int, int, int]":
    from config import settings

    return (
        int(settings.get("ASSET_IMPORT.MAX_FILE_BYTES", ASSET_IMPORT_MAX_FILE_BYTES)),
        int(settings.get("ASSET_IMPORT.MAX_BATCH_BYTES", ASSET_IMPORT_MAX_BATCH_BYTES)),
        int(settings.get("ASSET_IMPORT.MAX_ENTRIES", ASSET_IMPORT_MAX_ENTRIES)),
    )


def _library_root() -> Path:
    from config import settings

    root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", SKILLS_LIBRARY_ROOT)))
    return root if root.is_absolute() else Path.cwd() / root


def _landing_root() -> Path:
    """legacy 导入落盘根（AD-4c / OQ-2「执行统一」）：capability-library → .agents。

    单通道北极星：所有导入通道落到同一真相源，同步/对账/详情正文读取才有
    唯一口径。沙箱与限额逻辑完全不动——本改动只换落盘根（GWT-07.8 能力不回退）。
    """
    from backend.services.power_market.agents_hub import agents_root

    return agents_root()


def _make_sandbox() -> Path:
    from config import settings

    base = str(settings.get("ASSET_IMPORT.SANDBOX_ROOT", ASSET_IMPORT_SANDBOX_ROOT) or "")
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="asset-import-", dir=base or None))


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


@dataclass
class _ItemResult:
    asset_type: str
    name: str
    status: str  # succeeded/failed/skipped
    reason: str | None = None
    asset_id: int | None = None


def _dir_files(pkg: Path) -> list[tuple[str, Path]]:
    return sorted((p.relative_to(pkg).as_posix(), p) for p in pkg.rglob("*") if p.is_file())


def _contained_write(dest: Path, data: bytes) -> None:
    """写入前双重收容断言：目标必须落在资产目录内（GWT-100.7 兜底）"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.resolve().is_relative_to(_landing_root().resolve()):
        raise OSError(f"越界写入拒绝: {dest}")
    dest.write_bytes(data)


class AssetImportService:
    """统一导入通道（session 注入；ADR-0007 D3 自持事务，API 直调即完整业务操作）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- 公开入口（两条来源形态，四类是内部分支） ----------

    async def import_files(
        self, files: list[tuple[str, bytes]], actor: str, actor_id: int | None = None,
    ) -> dict:
        """multipart 上传：单 .md 文件或 zip 包（origin=file，GWT-100.1）"""
        logger.info(f"asset_import.start | origin=file files={len(files)} actor={actor}")
        file_bytes, batch_bytes, max_entries = _load_limits()
        if not files:
            raise ValidationException(message="未提供导入文件", field="import")
        raw_total = sum(len(data) for _, data in files)
        if raw_total > batch_bytes:
            raise ValidationException(
                message=f"上传总量超过大小上限（{batch_bytes} 字节），整批拒绝", field="import")
        batch = await self._open_batch("file", actor)
        sandbox = _make_sandbox()
        try:
            guard = EntryGuard(file_bytes, batch_bytes, max_entries)
            for name, data in files:
                self._stage_file(sandbox, name, data, guard)
            return await self._finish(batch, sandbox, guard, actor_id=actor_id)
        except ValidationException:
            await self._fail_batch(batch)
            raise
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    async def import_directory(
        self, path: str, actor: str, actor_id: int | None = None,
    ) -> dict:
        """服务器本地目录（origin=directory，GWT-100.2）：复制进沙箱后同管线"""
        logger.info(f"asset_import.start | origin=directory path={path} actor={actor}")
        root = Path(path).expanduser()
        if root.is_symlink() or not root.is_dir():
            raise ValidationException(
                message=f"导入目录不存在或不是目录: {path}", field="import")
        file_bytes, batch_bytes, max_entries = _load_limits()
        batch = await self._open_batch("directory", actor)
        sandbox = _make_sandbox()
        try:
            guard = EntryGuard(file_bytes, batch_bytes, max_entries)
            self._stage_directory(root, sandbox, guard)
            return await self._finish(batch, sandbox, guard, actor_id=actor_id)
        except ValidationException:
            await self._fail_batch(batch)
            raise
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    # ---------- 暂存（两条来源都收进沙箱；解析只在沙箱内） ----------

    def _stage_file(self, sandbox: Path, name: str, data: bytes, guard: EntryGuard) -> None:
        if data[:4] == _ZIP_MAGIC or name.lower().endswith(".zip"):
            self._extract_zip(sandbox, name, data, guard)
            return
        if not name.lower().endswith(".md"):
            logger.info(f"导入跳过不可识别文件 | name={name}")
            return
        clean = guard.check_path(name)
        if clean is None:
            return
        guard.count_entry()
        if len(data) > guard.file_bytes:
            guard.reject_size(name, _first_segment(clean))
            return
        guard.account_total(len(data))
        _sandbox_dest(sandbox, clean).parent.mkdir(parents=True, exist_ok=True)
        _sandbox_dest(sandbox, clean).write_bytes(data)

    def _extract_zip(self, sandbox: Path, fname: str, data: bytes, guard: EntryGuard) -> None:
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ValidationException(message=f"不是合法 zip 包: {fname}", field="import") from exc
        for info in zf.infolist():
            if info.is_dir():
                continue
            if _is_symlink_member(info):
                guard.symlink_reject(info.filename)
                continue
            rel = guard.check_path(info.filename)
            if rel is None:
                continue
            guard.count_entry()
            group = _first_segment(rel)
            if info.file_size > guard.file_bytes:  # 头标先检，不读体
                guard.reject_size(info.filename, group)
                continue
            payload = _read_capped(zf, info, guard.file_bytes)
            if payload is None:  # 实际解压超限（头标说谎的炸弹条目）
                guard.reject_size(info.filename, group)
                continue
            guard.account_total(len(payload))
            self._write_member(sandbox, rel, payload)

    @staticmethod
    def _write_member(sandbox: Path, rel: str, data: bytes) -> None:
        dest = _sandbox_dest(sandbox, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def _stage_directory(self, root: Path, sandbox: Path, guard: EntryGuard) -> None:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            here = Path(dirpath)
            for d in list(dirnames):
                if (here / d).is_symlink():
                    guard.symlink_reject((here / d).relative_to(root).as_posix())
            for f in filenames:
                src = here / f
                rel = src.relative_to(root).as_posix()
                if src.is_symlink():
                    guard.symlink_reject(rel)
                    continue
                if not src.is_file():
                    continue
                clean = guard.check_path(rel)
                if clean is None:
                    continue
                guard.count_entry()
                size = src.stat().st_size
                if size > guard.file_bytes:
                    guard.reject_size(rel, _first_segment(clean))
                    continue
                guard.account_total(size)
                dest = _sandbox_dest(sandbox, clean)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    # ---------- 分发与批次收口（部分成功常态语义，GWT-100.2/100.3/100.8） ----------

    async def _finish(
        self, batch: AssetImportBatch, sandbox: Path, guard: EntryGuard,
        *, actor_id: int | None,
    ) -> dict:
        batch_id = int(batch.id)  # P-BE-01：commit 前取快照
        origin = batch.origin
        pendings = _collect_candidates(sandbox)
        pendings.extend(_unmatched_entry_failures(pendings, guard))
        items = [
            await self._dispatch(p, _entry_failure_for(p, guard))
            for p in pendings
        ]
        counts = {s: sum(1 for i in items if i.status == s)
                  for s in ("succeeded", "failed", "skipped")}
        batch.total_count = len(items)
        batch.succeeded_count = counts["succeeded"]
        batch.failed_count = counts["failed"]
        batch.skipped_count = counts["skipped"]
        batch.status = "completed"
        batch.finished_at = _utcnow()
        for i in items:
            self.session.add(AssetImportItem(
                batch_id=batch_id, asset_type=i.asset_type, name=i.name,
                status=i.status, reason=i.reason, asset_id=i.asset_id,
            ))
        await self.session.commit()
        await self._emit_event(batch_id, origin, items, counts, actor_id=actor_id)
        payload = {
            "batch_id": batch_id, "origin": origin, "status": "completed",
            "total": len(items), "succeeded": counts["succeeded"],
            "failed": counts["failed"], "skipped": counts["skipped"],
            "items": [
                {"asset_type": i.asset_type, "name": i.name, "status": i.status,
                 **({"reason": i.reason} if i.reason else {}),
                 **({"asset_id": i.asset_id} if i.asset_id else {})}
                for i in items
            ],
        }
        if not items:
            payload["message"] = EMPTY_MESSAGE
        logger.info(
            f"asset_import.done | batch={batch_id} total={len(items)} "
            f"succeeded={counts['succeeded']} failed={counts['failed']} skipped={counts['skipped']}")
        return payload

    async def _dispatch(self, p: PendingAsset, entry_failure: "str | None") -> _ItemResult:
        if entry_failure:
            return _ItemResult(p.asset_type, p.name, "failed", reason=entry_failure)
        if p.error:
            return _ItemResult(p.asset_type, p.name, "failed", reason=p.error)
        existing = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == p.asset_type,
                CapabilityAsset.name == p.name,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing is not None:  # 幂等键=类型+名称（GWT-100.8），不产生第二行
            return _ItemResult(p.asset_type, p.name, "skipped")
        try:
            async with self.session.begin_nested():
                asset = CapabilityAsset(
                    asset_type=p.asset_type, name=p.name, title=p.title,
                    category=_CATEGORY[p.asset_type], status="experimental",
                    source_type="self_built", listing_state="unlisted",
                    file_path=self._file_path(p), sync_state="ok",
                )
                self.session.add(asset)
                await self.session.flush()
                asset_id = int(asset.id)  # P-BE-01：commit 前取 id
                self._land(p)
        except IntegrityError:
            return _ItemResult(p.asset_type, p.name, "skipped")  # 并发撞 uq 幂等键
        except OSError as exc:
            logger.warning(f"导入落盘失败 | type={p.asset_type} name={p.name} err={exc}")
            return _ItemResult(p.asset_type, p.name, "failed", reason=f"落盘失败: {exc}"[:512])
        return _ItemResult(p.asset_type, p.name, "succeeded", asset_id=asset_id)

    def _land(self, p: PendingAsset) -> None:
        """落盘资产目录（限定 capability-library 对应子目录，NFR-04）"""
        root = _landing_root()
        if p.single_file:
            _contained_write(root / _TYPE_DIRS[p.asset_type] / f"{p.name}.md",
                             p.files[0][1].read_bytes())
            return
        dest = root / _TYPE_DIRS[p.asset_type] / p.name
        if not dest.resolve().is_relative_to(root.resolve()):
            raise OSError(f"越界写入拒绝: {p.name}")
        dest.mkdir(parents=True, exist_ok=False)
        for rel, src in p.files:
            _contained_write(dest.joinpath(*PurePosixPath(rel).parts), src.read_bytes())

    @staticmethod
    def _file_path(p: PendingAsset) -> str:
        """AD-4c：落盘根切 .agents 后，file_path 同步带 `.agents/` 前缀——

        详情正文分流（AD-5a）与 prune 判别式（AD-3/QA-7R）都以该前缀识别
        「hub 来源行」，前缀不带会让导入行被当成 legacy 行。
        """
        rel = f".agents/{_TYPE_DIRS[p.asset_type]}/{p.name}"
        return f"{rel}.md" if p.single_file else rel

    async def _open_batch(self, origin: str, actor: str) -> AssetImportBatch:
        batch = AssetImportBatch(origin=origin, status="running", created_by=actor)
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def _fail_batch(self, batch: AssetImportBatch) -> None:
        """整批失败（沙箱/上传层故障，db-spec 2.1）：批次留痕后由异常处理器出 400"""
        batch.status = "failed"
        batch.finished_at = _utcnow()
        await self.session.commit()

    async def _emit_event(
        self, batch_id: int, origin: str, items: list[_ItemResult],
        counts: dict, *, actor_id: int | None,
    ) -> None:
        """GWT-92.9：asset_imported（origin/types/succeeded/failed；失败不挡主路径）"""
        types = sorted({i.asset_type for i in items if i.status != "failed"})
        await emit_product_event(
            self.session, ASSET_IMPORTED_EVENT, tenant_id=None, actor_user_id=actor_id,
            props={"origin": origin, "types": types,
                   "succeeded": counts["succeeded"], "failed": counts["failed"]},
        )
        logger.info(f"asset_import.event | batch={batch_id} types={types}")
