"""ADR-0007 事务所有权钉子测试

钉住两条事务语义（收口前由路由层 commit 承担，现归 Service 层）：
1. Service 写方法自持事务——方法返回后写入经【新会话】即可见（无需调用方 commit）；
2. 组合调用 commit=False 交出事务权（D3）——提交/回滚由外层定夺：
   外层 commit 则可见，外层丢弃（不 commit）则整体回滚。

端点级等价语义由既有用例隐式钉住（如 test_llm_provider_models_api 跨请求
读回、test_skill_candidates 的 commit=False 断言），本文件钉 service 契约本身。
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.services.config_service import ConfigService
from backend.services.member_service import MemberService
from backend.services.rbac_service import RbacService
from backend.services.skill_service import SkillService
from platform_core.models.role import Role
from platform_core.models.skill import Skill
from platform_core.models.spider_result import SpiderResult
from platform_core.models.system_config import SystemConfig
from platform_core.models.user import User

SKILL_MD = """---
name: tx-skill
description: 事务钉子
---
# T
"""

META_YAML = """name: tx-skill
category: document-processing
status: stable
similar_to: []
source:
  url: ""
  author: ""
"""


def _make_skill_dir(root: Path) -> None:
    d = root / "skills" / "tx-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "meta.yaml").write_text(META_YAML)


@pytest.mark.asyncio
async def test_service_write_methods_commit_at_boundary(db_session):
    """rbac / member / config 三域代表方法：调用方零 commit，新会话已可见"""
    async with db_session() as s:
        await RbacService(s).create_role(
            {"role_key": "auditor", "name": "审计员", "description": None,
             "permissions": ["menu:logs"]},
            builtin_codes={"menu:logs"},
        )
    async with db_session() as s:
        row = (await s.execute(select(Role).where(Role.role_key == "auditor"))).scalar_one()
        assert row.name == "审计员" and row.permissions == ["menu:logs"]

    async with db_session() as s:
        await MemberService(s).create_member(
            1, {"username": "tx-member", "email": "tx@local", "password": "Passw0rd!",
                "tenant_role": "viewer"})
    async with db_session() as s:
        row = (await s.execute(select(User).where(User.username == "tx-member"))).scalar_one()
        assert row.tenant_role == "viewer"

    async with db_session() as s:
        await ConfigService(s).upsert_configs({"notify.webhook_url": "https://h.local"}, "钉子")
    async with db_session() as s:
        row = (await s.execute(
            select(SystemConfig).where(SystemConfig.config_key == "notify.webhook_url")
        )).scalar_one()
        assert row.config_value == "https://h.local"


@pytest.mark.asyncio
async def test_reject_candidate_owns_transaction(db_session):
    """skill 域写方法（含同名拉黑双写）一个事务提交，新会话同时可见两处变更"""
    async with db_session() as s:
        s.add(Skill(name="tx-skill", file_path="skills/tx-skill",
                    status="experimental", source_url="https://github.com/x/tx"))
        s.add(SpiderResult(task_id=1, spider_name="skill_harvester", item_type="BaseItem",
                           url="https://github.com/x/tx", title="tx", source="marketplace",
                           extra=json.dumps({"review": "pending"})))
        await s.commit()

    async with db_session() as s:
        result = await SkillService(s).reject_candidate(1)
    assert result["blacklisted"] == "tx-skill"

    async with db_session() as s:
        extra = json.loads((await s.execute(
            select(SpiderResult).where(SpiderResult.id == 1))).scalar_one().extra or "{}")
        status = (await s.execute(select(Skill).where(Skill.name == "tx-skill"))).scalar_one().status
    assert extra.get("review") == "rejected"
    assert status == "blacklist"  # 标记 + 拉黑同事务生效（业务不可分割）


@pytest.mark.asyncio
async def test_scan_library_commit_flag_controls_boundary(db_session, tmp_path):
    """D3 组合语义：commit=False 时事务权在外层——外层丢弃则整体回滚，外层提交则可见"""
    _make_skill_dir(tmp_path)

    # 外层丢弃（不 commit）→ 回滚
    async with db_session() as s:
        await SkillService(s).scan_library(root=tmp_path / "skills", commit=False)
    async with db_session() as s:
        assert (await s.execute(select(Skill))).scalars().first() is None

    # 外层提交 → 可见
    async with db_session() as s:
        await SkillService(s).scan_library(root=tmp_path / "skills", commit=False)
        await s.commit()
    async with db_session() as s:
        assert (await s.execute(select(Skill))).scalars().first() is not None

    # 默认（API 直调语义）→ 方法自持事务
    async with db_session() as s:
        summary = await SkillService(s).scan_library(root=tmp_path / "skills")
        assert summary["succeeded"] == 1
    async with db_session() as s:
        rows = (await s.execute(select(Skill))).scalars().all()
        assert len({r.name for r in rows}) == 1 and rows[0].name == "tx-skill"
