"""技能目录扫描入库（09）——SkillService 的扫描能力（mixin，自 skill_service 拆出）

治理语义（D1）：扫描只写"内容派生字段"（title/description/content_hash/raw_meta/
sync_state），已入库行的人工治理字段（score/tier/category/status...）永不被扫描覆盖。
本模块同时承载 SKILL.md / meta.yaml 解析工具（skill_service 与写回层共用）。
"""
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import SKILLS_LIBRARY_ROOT
from platform_core.logger import get_logger
from platform_core.models.skill import Skill, SkillJob

logger = get_logger("service.skill")


# 存量 status 映射（总方案 3.2-A-4）：本地 8765 时代的三态 → 平台六态
_STATUS_MAP = {"active": "testing"}


class SkillParseError(ValueError):
    """技能目录解析失败（frontmatter/meta 非法或文件缺失）"""


def _parse_frontmatter(skill_md_text: str) -> dict:
    """解析 SKILL.md 顶部 YAML frontmatter；无 frontmatter 容忍为空（正文型 skill）"""
    if not skill_md_text.startswith("---"):
        return {}
    lines = skill_md_text.splitlines()
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            block = "\n".join(lines[1:idx])
            data = yaml.safe_load(block)
            return data if isinstance(data, dict) else {}
    raise SkillParseError("SKILL.md frontmatter 未闭合")


def _content_hash(skill_dir: Path) -> str:
    """目录内容 sha256（排序后全文件拼接：相对路径 + 字节）——变更检测锚点"""
    digest = hashlib.sha256()
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(skill_dir)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_meta(skill_dir: Path) -> dict:
    meta_path = skill_dir / "meta.yaml"
    if not meta_path.exists():
        raise SkillParseError("meta.yaml 缺失")
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SkillParseError("meta.yaml 非对象结构")
    return data


def _map_status(raw: Any) -> str:
    status = str(raw or "experimental")
    return _STATUS_MAP.get(status, status)


def _json_safe(value: Any) -> Any:
    """yaml 解析出的 date/datetime 递归转 ISO 字符串（JSON 列可序列化）"""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


class _SkillScanMixin:
    """扫描入库能力（由 SkillService 组合；宿主提供 self.session）"""

    session: AsyncSession

    async def scan_library(self, root: Optional[Path] = None, *, commit: bool = True) -> dict:
        """扫描 skills 目录：新目录入库 / hash 变化置 hash_changed / 丢失置 missing /
        解析失败置 parse_error；产出 skill_jobs 记录。返回摘要 dict。

        ADR-0007 D3：默认自持事务（API 直调即完整业务操作）；被导入管线组合
        （skill_import_service._ingest_and_enqueue）时传 commit=False，由外层
        统一提交（导入 = 落盘 + 扫描入库 + 任务记录的不可分割整体）。
        """
        logger.info(f"扫描技能库 | root={root} commit={commit}")
        root = self._scan_root(root)
        job = SkillJob(job_type="scan", status="running", total=0, succeeded=0, failed=0)
        self.session.add(job)
        await self.session.flush()

        existing = {
            row.name: row
            for row in (await self.session.execute(select(Skill))).scalars()
        }
        dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []
        succeeded, failed_names = await self._upsert_dirs(dirs, root, existing)

        dir_names = {d.name for d in dirs}
        missing_names = [name for name in existing if name not in dir_names]
        for name in missing_names:
            existing[name].sync_state = "missing"
        retracted_assets = await self._retract_missing_assets(missing_names)

        summary = await self._finish_scan_job(
            job, len(dirs), succeeded, failed_names, missing_names, retracted_assets,
        )
        if commit:
            await self.session.commit()
        return summary

    @staticmethod
    def _scan_root(root: Optional[Path]) -> Path:
        """扫描根：缺省取 SKILLS.LIBRARY_ROOT/skills"""
        from config import settings

        if root is None:
            library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", SKILLS_LIBRARY_ROOT)))
            root = library_root / "skills"
        return Path(root)

    async def _upsert_dirs(
        self, dirs: list[Path], root: Path, existing: dict[str, Skill],
    ) -> tuple[int, list[str]]:
        """逐目录 upsert，返回 (成功数, 失败目录名)；单目录失败置 parse_error 不中断整批"""
        succeeded = 0
        failed_names: list[str] = []
        for skill_dir in dirs:
            try:
                await self._upsert_from_dir(skill_dir, root, existing.get(skill_dir.name))
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 单目录失败不中断整批
                failed_names.append(skill_dir.name)
                logger.warning(f"技能解析失败 | dir={skill_dir.name} err={exc}")
                await self._mark_parse_error(skill_dir, root, existing.get(skill_dir.name))
        return succeeded, failed_names

    async def _finish_scan_job(
        self, job: SkillJob, total: int, succeeded: int, failed_names: list[str],
        missing_names: list[str], retracted_assets: list[str],
    ) -> dict:
        """扫描任务收尾：回填计数与明细，commit 前快照摘要"""
        failed = len(failed_names)
        job.total = total
        job.succeeded = succeeded
        job.failed = failed
        job.status = "done"
        job.detail = {
            "failed": failed_names, "missing": missing_names,
            "retracted": retracted_assets,
        }
        await self.session.flush()
        # ADR-0007 D2：快照先于 commit（job 属性 expire 后读取会抛 MissingGreenlet）
        summary = {
            "total": job.total,
            "succeeded": succeeded,
            "failed": failed,
            "failed_names": failed_names,
            "missing": missing_names,
            "retracted_assets": retracted_assets,
            "job_id": job.id,
        }
        if summary["total"] == 0:
            summary["empty"] = True
            summary["message"] = "没有可同步的包"
        return summary

    async def _upsert_from_dir(
        self, skill_dir: Path, root: Path, existing: Optional[Skill]
    ) -> Skill:
        """单目录 upsert：新建取 meta 治理初值；已存在只更新内容派生字段"""
        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(skill_md)
        meta = _load_meta(skill_dir)
        content_hash = _content_hash(skill_dir)
        file_path = self._rel_path(skill_dir, root)

        if existing is None:
            row = self._new_skill_row(skill_dir, frontmatter, meta, content_hash, file_path)
            self.session.add(row)
            await self.session.flush()
            await self._sync_asset(row)
            return row

        existing.title = str(frontmatter.get("name") or skill_dir.name)
        existing.description = frontmatter.get("description")
        existing.raw_meta = _json_safe(meta)
        existing.file_path = file_path
        existing.sync_state = (
            "hash_changed" if content_hash != existing.content_hash else "ok"
        )
        existing.content_hash = content_hash
        await self.session.flush()
        await self._sync_asset(existing)
        if existing.sync_state == "hash_changed":
            await self._enqueue_rescore_best_effort(skill_dir.name)
        return existing

    def _new_skill_row(
        self, skill_dir: Path, frontmatter: dict, meta: dict, content_hash: str, file_path: str,
    ) -> Skill:
        """新目录建行：治理字段取 meta.yaml 初值（仅首次入库生效）"""
        source = meta.get("source") or {}
        capability = meta.get("capability") or {}
        imported_at = source.get("imported_at")
        return Skill(
            name=skill_dir.name,
            title=str(frontmatter.get("name") or skill_dir.name),
            description=frontmatter.get("description"),
            category=str(meta.get("category") or "uncategorized"),
            industries=_json_safe(meta.get("industries") or []),
            status=_map_status(meta.get("status")),
            source_type="self_built",
            source_url=str(source.get("url") or ""),
            source_author=str(source.get("author") or ""),
            imported_at=self._parse_date(imported_at),
            content_hash=content_hash,
            ai_suggested_score=capability.get("ai_suggested_score"),
            similar_to=_json_safe(meta.get("similar_to") or []),
            file_path=file_path,
            sync_state="ok",
            raw_meta=_json_safe(meta),
        )

    async def _enqueue_rescore_best_effort(self, name: str) -> None:
        """内容变更入评分队列（失败仅告警，不阻断扫描）"""
        try:
            from platform_core.queues import SKILL_SCORE_QUEUE
            from platform_core.redis_async import get_async_redis

            redis = await get_async_redis()
            await redis.lpush(SKILL_SCORE_QUEUE, name)
        except Exception as exc:  # noqa: BLE001 队列不可用不阻断扫描
            logger.warning(f"评分入队失败（忽略） | skill={name} err={exc}")

    async def _sync_asset(self, skill) -> None:
        """技能行 → capability_assets 目录行同步（P6 C2）"""
        try:
            from backend.services.capability_service import CapabilityService

            await CapabilityService(self.session).upsert_skill_asset(skill)
        except Exception as exc:  # noqa: BLE001 目录同步失败不阻断扫描主路径
            logger.warning(f"asset 目录同步失败（忽略） | skill={skill.name} err={exc}")

    async def _retract_missing_assets(self, names: list[str]) -> list[str]:
        """源目录已删的技能：目录镜像行软收回（FR-88，GWT-88.1）

        失败仅告警不阻断扫描主路径——与 _sync_asset 同口径（目录层是投影，
        不反噬扫描事务）。
        """
        if not names:
            return []
        try:
            from backend.services.capability_service import CapabilityService

            return await CapabilityService(self.session).retract_skill_assets(names)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"asset 目录收回失败（忽略） | names={names} err={exc}")
            return []

    async def _mark_parse_error(
        self, skill_dir: Path, root: Path, existing: Optional[Skill]
    ) -> None:
        if existing is not None:
            existing.sync_state = "parse_error"
        else:
            self.session.add(
                Skill(
                    name=skill_dir.name,
                    file_path=self._rel_path(skill_dir, root),
                    sync_state="parse_error",
                )
            )
        await self.session.flush()

    @staticmethod
    def _rel_path(skill_dir: Path, root: Path) -> str:
        try:
            return skill_dir.relative_to(root.parent).as_posix()
        except ValueError:
            return skill_dir.as_posix()

    @staticmethod
    def _parse_date(raw: Any) -> Optional[datetime]:
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None
        return None
