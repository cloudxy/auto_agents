"""专家 + 专家团资产域服务（P6 C5/C6）

专家 canonical = Claude Code subagent 格式（frontmatter name/description/tools + 正文 system prompt）。
专家团一期仅定义层（leader + members + workflow），执行引擎二期。
"""
from pathlib import Path
from backend.config_consts import (SKILLS_LIBRARY_ROOT)
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilityExpert, CapabilityTeam
from platform_core.models.skill import SkillJob

logger = get_logger("service.expert")

_TOOLS_MAX = 32


class ExpertService:
    """专家域（session 注入）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def scan_experts(self, root: Optional[Path] = None) -> dict:
        """扫描 capability-library/experts/：解析 AGENT.md（subagent 格式）"""
        from config import settings

        if root is None:
            library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", SKILLS_LIBRARY_ROOT)))
            root = library_root / "experts"
        root = Path(root)

        job = SkillJob(job_type="scan_experts", status="running", total=0, succeeded=0, failed=0)
        self.session.add(job)
        await self.session.flush()

        dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []
        succeeded, failed = 0, 0
        failed_names: list[str] = []
        for expert_dir in dirs:
            try:
                await self._upsert_from_dir(expert_dir, root)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                failed_names.append(expert_dir.name)
                logger.warning(f"专家解析失败 | dir={expert_dir.name} err={exc}")

        job.total, job.succeeded, job.failed, job.status = len(dirs), succeeded, failed, "done"
        job.detail = {"failed": failed_names}
        await self.session.flush()
        # ADR-0007 D2：快照先于 commit（job 属性 expire 后读取会抛 MissingGreenlet）
        result = {"total": len(dirs), "succeeded": succeeded, "failed": failed,
                  "failed_names": failed_names, "job_id": job.id}
        await self.session.commit()
        return result

    async def _upsert_from_dir(self, expert_dir: Path, root: Path) -> CapabilityAsset:
        agent_path = expert_dir / "AGENT.md"
        if not agent_path.exists():
            agent_path = expert_dir / "SKILL.md"  # 容错：SKILL.md 亦接受
        if not agent_path.exists():
            raise ValidationException(message=f"AGENT.md/SKILL.md 缺失: {expert_dir.name}", field="url")

        text = agent_path.read_text(encoding="utf-8")
        frontmatter, persona = self._parse_subagent(text)
        name = str(frontmatter.get("name") or expert_dir.name)

        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "expert", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        if asset is None:
            asset = CapabilityAsset(
                asset_type="expert", name=name,
                title=str(frontmatter.get("description") or "")[:1024],
                category="expert", status="experimental",
                file_path=expert_dir.relative_to(root.parent).as_posix(),
                sync_state="ok",
            )
            self.session.add(asset)
            await self.session.flush()
        else:
            asset.title = str(frontmatter.get("description") or "")[:1024]
            asset.sync_state = "ok"

        detail = (await self.session.execute(
            select(CapabilityExpert).where(CapabilityExpert.asset_id == asset.id)
        )).scalar_one_or_none()
        if detail is None:
            detail = CapabilityExpert(asset_id=asset.id)
            self.session.add(detail)
        detail.persona_md = persona
        tools = frontmatter.get("tools") or []
        if isinstance(tools, list):
            detail.tools = [str(t) for t in tools[:_TOOLS_MAX]]
        detail.bundled_skills = frontmatter.get("skills") or []
        detail.mcp_refs = frontmatter.get("mcp") or []
        detail.model_pref = str(frontmatter.get("model") or "")
        await self.session.flush()
        return asset

    @staticmethod
    def _parse_subagent(text: str) -> tuple[dict, str]:
        """frontmatter + 正文分离（subagent canonical）"""
        if not text.startswith("---"):
            return {}, text
        lines = text.splitlines()
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                block = "\n".join(lines[1:idx])
                data = yaml.safe_load(block)
                persona = "\n".join(lines[idx + 1:]).strip()
                return (data if isinstance(data, dict) else {}), persona
        raise ValidationException(message="frontmatter 未闭合", field="url")

    async def get_expert_detail(self, name: str) -> dict:
        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "expert", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        if asset is None:
            raise NotFoundException(resource=f"专家 {name}")
        detail = (await self.session.execute(
            select(CapabilityExpert).where(CapabilityExpert.asset_id == asset.id)
        )).scalar_one_or_none()
        return {
            "name": asset.name, "title": asset.title, "status": asset.status,
            "tools": (detail.tools if detail else []) or [],
            "bundled_skills": (detail.bundled_skills if detail else []) or [],
            "mcp_refs": (detail.mcp_refs if detail else []) or [],
            "model_pref": detail.model_pref if detail else "",
            "persona_md": detail.persona_md if detail else "",
        }

    async def validate_skill_bundles(self, name: str) -> dict:
        """捆绑技能存在性校验（悬空引用标记）"""
        detail_dict = await self.get_expert_detail(name)
        missing = []
        for skill_name in detail_dict["bundled_skills"]:
            row = (await self.session.execute(
                select(CapabilityAsset.id).where(
                    CapabilityAsset.asset_type == "skill", CapabilityAsset.name == skill_name
                )
            )).scalar_one_or_none()
            if row is None:
                missing.append(skill_name)
        return {"name": name, "missing_skills": missing}


class TeamService:
    """专家团定义层（一期无执行态）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_team(self, name: str, leader: str, members: list[str],
                          workflow_md: str = "", title: str = "") -> dict:
        """创建/更新专家团（成员/团长引用校验）

        ADR-0007 D2：返回名称快照（dict）——不再回传 ORM 实例，
        commit 后调用方读 ORM 属性会触发惰性加载抛 MissingGreenlet。
        """
        logger.info(f"专家团 upsert | team={name} leader={leader} members={len(members)}")
        all_refs = [leader] + [m for m in members if m != leader]
        for ref in all_refs:
            row = (await self.session.execute(
                select(CapabilityAsset.id).where(
                    CapabilityAsset.asset_type == "expert", CapabilityAsset.name == ref
                )
            )).scalar_one_or_none()
            if row is None:
                raise ValidationException(
                    message=f"专家引用不存在: {ref}（先创建专家再组队）", field="members")

        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "expert_team", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        created = asset is None
        if created:
            asset = CapabilityAsset(
                asset_type="expert_team", name=name,
                title=title or f"专家团 {name}", category="team",
                status="experimental", sync_state="ok",
            )
            self.session.add(asset)
            await self.session.flush()
        detail = (await self.session.execute(
            select(CapabilityTeam).where(CapabilityTeam.asset_id == asset.id)
        )).scalar_one_or_none()
        if detail is None:
            detail = CapabilityTeam(asset_id=asset.id)
            self.session.add(detail)
        detail.leader_expert = leader
        detail.members = members
        detail.workflow_md = workflow_md
        await self.session.flush()
        snapshot = {"name": str(asset.name), "created": created}
        await self.session.commit()
        return snapshot

    async def get_team_detail(self, name: str) -> dict:
        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "expert_team", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        if asset is None:
            raise NotFoundException(resource=f"专家团 {name}")
        detail = (await self.session.execute(
            select(CapabilityTeam).where(CapabilityTeam.asset_id == asset.id)
        )).scalar_one_or_none()
        return {
            "name": asset.name, "title": asset.title, "status": asset.status,
            "leader": detail.leader_expert if detail else "",
            "members": (detail.members if detail else []) or [],
            "workflow_md": detail.workflow_md if detail else "",
        }

    async def export_team_md(self, name: str) -> str:
        """导出为 TEAM.md（workbuddy 风格 markdown 文档）"""
        d = await self.get_team_detail(name)
        lines = [f"# 专家团：{d['title'] or d['name']}", ""]
        lines.append(f"**团长**：{d['leader']}")
        lines.append(f"**成员**：{', '.join(d['members'])}")
        lines.append("")
        if d["workflow_md"]:
            lines.append("## 协作流程")
            lines.append(d["workflow_md"])
        return "\n".join(lines)
