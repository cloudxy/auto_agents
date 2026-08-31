"""技能域服务（方案 A）——数据契约 tier 派生（08）+ 扫描入库（09）

后续工单在本模块生长：矫正写回（11）等。
治理语义（D1）：内容真相源在 skills-library/skills/<name>/ 文件；治理真相源在 DB。
扫描只写"内容派生字段"（title/description/content_hash/raw_meta/sync_state），
已入库行的人工治理字段（score/tier/category/status...）永不被扫描覆盖。
"""
import hashlib
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.logger import get_logger
from platform_core.models.skill import Skill, SkillJob, SkillReview

logger = get_logger("service.skill")

# tier 派生（总方案 §5.1）：人工综合分优先（缺省用 AI 建议分）映射
# S≥8.5 / A≥7.0 / B≥5.0 / C<5.0；两者皆无 → None（展示"未评"）
def derive_tier(human_score: Optional[float], ai_score: Optional[float]) -> Optional[str]:
    logger.debug(f"tier 派生: human={human_score} ai={ai_score}")
    score = human_score if human_score is not None else ai_score
    if score is None:
        return None
    value = Decimal(str(score))
    if value >= Decimal("8.5"):
        return "S"
    if value >= Decimal("7.0"):
        return "A"
    if value >= Decimal("5.0"):
        return "B"
    return "C"


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


class SkillService:
    """技能域服务（session 由 API 层注入）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def scan_library(self, root: Optional[Path] = None) -> dict:
        """扫描 skills 目录：新目录入库 / hash 变化置 hash_changed / 丢失置 missing /
        解析失败置 parse_error；产出 skill_jobs 记录。返回摘要 dict。"""
        from config import settings

        if root is None:
            library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", "skills-library")))
            root = library_root / "skills"
        root = Path(root)

        job = SkillJob(job_type="scan", status="running", total=0, succeeded=0, failed=0)
        self.session.add(job)
        await self.session.flush()

        existing = {
            row.name: row
            for row in (await self.session.execute(select(Skill))).scalars()
        }
        dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []

        succeeded = failed = 0
        failed_names: list[str] = []
        for skill_dir in dirs:
            try:
                await self._upsert_from_dir(skill_dir, root, existing.get(skill_dir.name))
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 单目录失败不中断整批
                failed += 1
                failed_names.append(skill_dir.name)
                logger.warning(f"技能解析失败 | dir={skill_dir.name} err={exc}")
                await self._mark_parse_error(skill_dir, root, existing.get(skill_dir.name))

        dir_names = {d.name for d in dirs}
        missing_names = [name for name in existing if name not in dir_names]
        for name in missing_names:
            existing[name].sync_state = "missing"

        job.total = len(dirs)
        job.succeeded = succeeded
        job.failed = failed
        job.status = "done"
        job.detail = {"failed": failed_names, "missing": missing_names}
        await self.session.flush()
        return {
            "total": job.total,
            "succeeded": succeeded,
            "failed": failed,
            "failed_names": failed_names,
            "missing": missing_names,
            "job_id": job.id,
        }

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
            source = meta.get("source") or {}
            capability = meta.get("capability") or {}
            imported_at = source.get("imported_at")
            row = Skill(
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
            self.session.add(row)
            await self.session.flush()
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
        return existing

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

    async def correct_meta(self, name: str, reviewer: str, payload: dict) -> dict:
        """人工矫正（总方案 §5.1 写回规则）：同 Service 内先落 DB（含 skill_reviews(human)
        与 tier 派生）→ 成功后原子写回 meta.yaml（tmp+rename）→ 追加 CHANGELOG。
        写回失败：DB 不回滚（DB 是真相源），记 skill_jobs 告警，可 export_meta 补导出。
        AI 路径永不调用本方法（评分落库见 15 的独立方法，不写 score/rubric_human）。
        """
        logger.info(f"人工矫正 | skill={name} reviewer={reviewer} fields={sorted(payload)}")
        row = (await self.session.execute(select(Skill).where(Skill.name == name))).scalar_one_or_none()
        if row is None:
            from platform_core.exceptions import NotFoundException

            raise NotFoundException(resource=f"技能 {name}")

        if "category" in payload:
            row.category = str(payload["category"])
        if "industries" in payload:
            row.industries = _json_safe(payload["industries"])
        if "status" in payload:
            row.status = _map_status(payload["status"])
        if "similar_to" in payload:
            row.similar_to = _json_safe(payload["similar_to"])
        if "score" in payload:
            row.score = payload["score"]
        if "rubric_human" in payload:
            row.rubric_human = _json_safe(payload["rubric_human"])
        if "review_notes" in payload:
            row.review_notes = payload["review_notes"]
        row.reviewed_by = reviewer
        row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        row.tier = derive_tier(
            float(row.score) if row.score is not None else None,
            float(row.ai_suggested_score) if row.ai_suggested_score is not None else None,
        )

        self.session.add(
            SkillReview(
                skill_id=row.id,
                reviewer_type="human",
                reviewer=reviewer,
                score=row.score,
                rubric=row.rubric_human,
                notes=payload.get("review_notes"),
                content_hash=row.content_hash,
            )
        )
        await self.session.flush()

        written_back = self._write_back_meta(row)
        if written_back:
            self._append_changelog(
                row,
                f"{reviewer} | 矫正: "
                + ", ".join(f"{k}={payload[k]}" for k in sorted(payload)),
            )
        else:
            self._record_export_failure(name, "矫正后写回失败")
        return {
            "name": name,
            "written_back": written_back,
            "tier": row.tier,
            "category": row.category,
            "status": row.status,
        }

    async def export_meta(self, name: str) -> bool:
        """手动补导出：按 DB 当前治理状态重写 meta.yaml + CHANGELOG"""
        logger.info(f"手动补导出 meta | skill={name}")
        row = (await self.session.execute(select(Skill).where(Skill.name == name))).scalar_one_or_none()
        if row is None:
            from platform_core.exceptions import NotFoundException

            raise NotFoundException(resource=f"技能 {name}")
        ok = self._write_back_meta(row)
        if not ok:
            self._record_export_failure(name, "手动补导出失败")
        else:
            self._append_changelog(row, "system | 补导出 meta.yaml")
            await self.session.flush()
        return ok

    def _library_root(self) -> Path:
        from config import settings

        return Path(str(settings.get("SKILLS.LIBRARY_ROOT", "skills-library")))

    def _write_back_meta(self, row: Skill) -> bool:
        """DB → meta.yaml 原子写回（tmp 文件 + rename，单写者=主后端）"""
        try:
            meta: dict = dict(row.raw_meta or {})
            meta["name"] = row.name
            meta["category"] = row.category
            meta["industries"] = row.industries or []
            meta["status"] = row.status
            meta["similar_to"] = row.similar_to or []
            source = dict(meta.get("source") or {})
            source["content_hash"] = row.content_hash or ""
            meta["source"] = source
            capability = dict(meta.get("capability") or {})
            capability["score"] = float(row.score) if row.score is not None else None
            capability["ai_suggested_score"] = (
                float(row.ai_suggested_score) if row.ai_suggested_score is not None else None
            )
            capability["rubric"] = row.rubric_human or {}
            capability["reviewed_by"] = row.reviewed_by
            capability["reviewed_at"] = (
                row.reviewed_at.date().isoformat() if row.reviewed_at else None
            )
            capability["notes"] = row.review_notes
            meta["capability"] = capability

            skill_dir = self._library_root() / row.file_path
            if not skill_dir.is_dir():
                logger.error(f"meta.yaml 写回失败 | skill={row.name} 目录不存在: {skill_dir}")
                return False
            tmp_path = skill_dir / "meta.yaml.tmp"
            tmp_path.write_text(
                yaml.safe_dump(_json_safe(meta), allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            os.replace(tmp_path, skill_dir / "meta.yaml")
            return True
        except OSError as exc:
            logger.error(f"meta.yaml 写回失败 | skill={row.name} err={exc}")
            return False

    def _append_changelog(self, row: Skill, summary: str) -> None:
        """CHANGELOG.md 追加一行 `- YYYY-MM-DD | 摘要`（沿用 skills-library 既有格式）"""
        try:
            skill_dir = self._library_root() / row.file_path
            if not skill_dir.is_dir():
                logger.error(f"CHANGELOG 追加失败 | skill={row.name} 目录不存在")
                return
            changelog = skill_dir / "CHANGELOG.md"
            existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# 更新记录\n"
            line = f"- {date.today().isoformat()} | {summary}\n"
            changelog.write_text(existing + line, encoding="utf-8")
        except OSError as exc:
            logger.error(f"CHANGELOG 追加失败 | skill={row.name} err={exc}")

    def _record_export_failure(self, name: str, reason: str) -> None:
        self.session.add(
            SkillJob(
                job_type="export_meta",
                status="failed",
                total=1,
                succeeded=0,
                failed=1,
                detail={"failed": [name], "reason": reason},
            )
        )

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
