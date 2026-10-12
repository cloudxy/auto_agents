"""技能库文件层——SkillService 的 meta.yaml 写回 / CHANGELOG / 适配器矩阵（mixin，自 skill_service 拆出）

治理语义（D1）：DB 是治理真相源，meta.yaml 是其导出——写回走 tmp+rename 原子替换，
失败只记 skill_jobs(export_meta) 告警、不回滚 DB。
适配器矩阵（A-P3-2）：manifests/<tool>.yaml 读写 + sync.sh 触发。
"""
import asyncio
import os
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import SKILLS_LIBRARY_ROOT
from backend.services.skill_service_scan import _json_safe
from platform_core.exceptions import AuthorizationException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.skill import Skill, SkillJob
from platform_core.timeutil import business_date_of, business_today

logger = get_logger("service.skill")


class _SkillLibraryMixin:
    """技能库文件读写能力（由 SkillService 组合；宿主提供 self.session）"""

    session: AsyncSession

    # ---------- 适配器矩阵（A-P3-2） ----------

    async def list_manifests(self) -> dict[str, list[str]]:
        """读全部 manifests/<tool>.yaml（每行一个 `- <name>` 的纯文本约定）"""
        logger.debug("读取技能 manifests")
        manifests_dir = self._library_root() / "manifests"
        result: dict[str, list[str]] = {}
        if not manifests_dir.is_dir():
            return result
        for path in sorted(manifests_dir.glob("*.yaml")):
            names = [
                line[2:].strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("- ")
            ]
            result[path.stem] = names
        return result

    async def update_manifest(self, tool: str, names: list[str]) -> dict:
        """写 manifests/<tool>.yaml：保留注释头，`- <name>` 行格式不变（adapters 零改动）"""
        logger.info(f"写入技能 manifest | tool={tool} count={len(names)}")
        import re as _re

        if not _re.fullmatch(r"[a-z0-9][a-z0-9\-]+", tool):
            raise ValidationException(message=f"工具名不合法: {tool}", field="tool")
        manifests_dir = self._library_root() / "manifests"
        manifests_dir.mkdir(parents=True, exist_ok=True)
        path = manifests_dir / f"{tool}.yaml"
        header = ""
        if path.exists():
            header = "".join(
                line + "\n" for line in path.read_text(encoding="utf-8").splitlines()
                if not line.startswith("- ")
            )
        body = "".join(f"- {name}\n" for name in names)
        path.write_text(header + body, encoding="utf-8")
        return {"tool": tool, "names": names}

    async def sync_adapters(self) -> dict:
        """触发 sync.sh（subprocess，cwd=LIBRARY_ROOT；受 SKILLS.ADAPTER_SYNC.ENABLED 约束）"""
        logger.info("触发技能适配器同步（sync.sh）")
        from config import settings

        if not settings.get("SKILLS.ADAPTER_SYNC.ENABLED", False):
            raise AuthorizationException(message="适配器同步未启用（SKILLS.ADAPTER_SYNC.ENABLED=false）")
        root = self._library_root()
        script = root / "sync.sh"
        if not script.exists():
            raise ValidationException(message=f"sync.sh 不存在: {script}", field="url")
        proc = await asyncio.create_subprocess_exec(
            "bash", str(script),
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = (stdout or b"").decode("utf-8", errors="replace")
        ok = proc.returncode == 0
        if not ok:
            logger.error(f"适配器同步失败 | rc={proc.returncode} out={output[:500]}")
        return {"ok": ok, "returncode": proc.returncode, "output": output[:2000]}

    def _library_root(self) -> Path:
        from config import settings

        return Path(str(settings.get("SKILLS.LIBRARY_ROOT", SKILLS_LIBRARY_ROOT)))

    # ---------- meta.yaml 写回 / CHANGELOG ----------

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
                business_date_of(row.reviewed_at).isoformat() if row.reviewed_at else None
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
        """CHANGELOG.md 追加一行 `- YYYY-MM-DD | 摘要`（沿用 capability-library 既有格式）"""
        try:
            skill_dir = self._library_root() / row.file_path
            if not skill_dir.is_dir():
                logger.error(f"CHANGELOG 追加失败 | skill={row.name} 目录不存在")
                return
            changelog = skill_dir / "CHANGELOG.md"
            existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# 更新记录\n"
            line = f"- {business_today().isoformat()} | {summary}\n"
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
