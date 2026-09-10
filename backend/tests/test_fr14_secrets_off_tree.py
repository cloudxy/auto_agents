"""FR-14 / T-11：密钥离树 + 管理详情不对非超管发本机绝对路径。

GWT-14.3 走 T-05 / GWT-07.3（直打中转页同 404），本文件不把「打开渠道页见掩码」当 Then。
GWT-14.4 掩码合同在 test_llm_provider.py，本文件不重复改写。
扫描模式由片段拼接，测试内不出现真实上游 Key。
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from sqlalchemy import select

from backend.app.api._helpers import (
    is_local_absolute_path,
    omit_local_abs_paths_for_non_platform_admin,
)
from backend.app.api.deps import CurrentUser
from platform_core.models.capability import CapabilityAsset
from platform_core.models.skill import Skill
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

REPO = Path(__file__).resolve().parents[2]
ABS_PATH = "/opt/eval-host/capability-library/skills/fr14-abs"
REL_PATH = "skills/fr14-rel"
ASSET_ABS = "fr14-abs-asset"
ASSET_REL = "fr14-rel-asset"
SKILL_ABS = "fr14-abs-skill"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False,
    )


def _seed_asset(db_session, name: str, file_path: str) -> None:
    async def _go():
        async with db_session() as s:
            s.add(CapabilityAsset(
                asset_type="skill", name=name, status="stable",
                category="test", file_path=file_path,
            ))
            await s.commit()

    asyncio.run(_go())


def _seed_skill(db_session, name: str, file_path: str) -> None:
    async def _go():
        async with db_session() as s:
            s.add(Skill(
                name=name, title=name, category="test", status="stable",
                source_type="self_built", file_path=file_path, sync_state="ok",
            ))
            await s.commit()

    asyncio.run(_go())


def _platform_admin_headers(db_session) -> dict:
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            platform = Tenant(slug="platform-fr14", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(
                username="fr14-root", email="fr14-root@x.com", password_hash="x",
                role="admin", tenant_id=platform.id, tenant_role=None,
                is_platform_admin=True,
            ))
            await s.commit()
            root = (await s.execute(
                select(User).where(User.username == "fr14-root"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": root.id, "username": "fr14-root", "is_admin": True,
                "role": "admin", "tenant_id": None, "tenant_role": None,
                "is_platform_admin": True,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def test_config_gen_yaml_not_tracked():
    proc = _git("ls-files", "--", "deploy/litellm/config.gen.yaml")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_tracked_deploy_config_has_no_plaintext_upstream_key_pattern():
    prefix = "sk" + "-"
    pattern = r"api_key[[:space:]]*:[[:space:]]*['\"]?" + prefix + r"[A-Za-z0-9_-]{16,}"
    proc = _git("grep", "-lE", pattern, "--", "deploy", "config")
    assert proc.stdout.strip() == ""
    assert proc.returncode == 1


def test_is_local_absolute_path_posix_and_relative():
    assert is_local_absolute_path(ABS_PATH)
    assert is_local_absolute_path("~/.config/keys")
    assert is_local_absolute_path("C:\\eval-host\\keys")
    assert not is_local_absolute_path(REL_PATH)
    assert not is_local_absolute_path("")
    assert not is_local_absolute_path(None)


def test_omit_abs_path_field_for_tenant_keeps_relative():
    tenant = CurrentUser(id=2, username="t", role="viewer", is_platform_admin=False)
    admin = CurrentUser(id=1, username="root", role="admin", is_platform_admin=True)
    payload = {"name": "x", "file_path": ABS_PATH, "rel": REL_PATH}
    stripped = omit_local_abs_paths_for_non_platform_admin(payload, tenant)
    assert "file_path" not in stripped
    assert stripped["rel"] == REL_PATH
    kept = omit_local_abs_paths_for_non_platform_admin(payload, admin)
    assert kept["file_path"] == ABS_PATH


def test_capability_detail_tenant_omits_local_absolute_path(
    db_client, viewer_client, db_engine, db_session,
):
    _seed_asset(db_session, ASSET_ABS, ABS_PATH)
    resp = db_client.get(f"/api/v1/capabilities/skill/{ASSET_ABS}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert ABS_PATH not in resp.text
    assert "file_path" not in data


def test_capability_detail_keeps_relative_path_for_tenant(
    db_client, viewer_client, db_engine, db_session,
):
    _seed_asset(db_session, ASSET_REL, REL_PATH)
    resp = db_client.get(f"/api/v1/capabilities/skill/{ASSET_REL}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["file_path"] == REL_PATH


def test_capability_detail_superadmin_abs_path_not_emitted_to_tenant(
    db_client, viewer_client, db_engine, db_session,
):
    """GWT-14.1：超管可看详情；同一资源对非超管不发出本机绝对路径。"""
    _seed_asset(db_session, ASSET_ABS, ABS_PATH)
    auth = _platform_admin_headers(db_session)
    super_resp = db_client.get(
        f"/api/v1/capabilities/skill/{ASSET_ABS}", headers=auth,
    )
    assert super_resp.status_code == 200, super_resp.text
    tenant_resp = db_client.get(f"/api/v1/capabilities/skill/{ASSET_ABS}")
    assert tenant_resp.status_code == 200, tenant_resp.text
    assert ABS_PATH not in tenant_resp.text
    assert "file_path" not in tenant_resp.json()["data"]


def test_skill_detail_tenant_omits_local_absolute_path(
    db_client, viewer_client, db_engine, db_session,
):
    _seed_skill(db_session, SKILL_ABS, ABS_PATH)
    resp = db_client.get(f"/api/v1/skills/{SKILL_ABS}")
    assert resp.status_code == 200, resp.text
    assert ABS_PATH not in resp.text
    assert "file_path" not in resp.json()["data"]
