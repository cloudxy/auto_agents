"""A-P3-2 适配器矩阵验证（工单 17）：manifests 读写保格式 + sync 触发受开关约束

Seam（工单预确认）：SkillService.{list_manifests,update_manifest,sync_adapters} + 端点。
"""

import pytest

from backend.services.skill_service import SkillService

MANIFEST_HEADER = "# Claude Code 启用清单（每行一个 - name）\n"


@pytest.fixture
def library_root(tmp_path):
    from config import settings

    original_root = settings.get("SKILLS.LIBRARY_ROOT")
    original_sync = settings.get("SKILLS.ADAPTER_SYNC.ENABLED")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", False)
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "claude-code.yaml").write_text(
        MANIFEST_HEADER + "- example-pdf-extractor\n"
    )
    (tmp_path / "sync.sh").write_text("#!/usr/bin/env bash\necho synced\n")
    (tmp_path / "sync.sh").chmod(0o755)
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original_root)
    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", original_sync)


@pytest.mark.asyncio
async def test_manifests_roundtrip_preserves_format(db_session, library_root):
    async with db_session() as s:
        listing = await SkillService(s).list_manifests()
        assert listing == {"claude-code": ["example-pdf-extractor"]}

        await SkillService(s).update_manifest("claude-code", ["alpha", "beta"])
        content = (library_root / "manifests" / "claude-code.yaml").read_text()

    assert content.startswith(MANIFEST_HEADER)  # 注释头原样保留
    assert "- alpha\n- beta\n" in content  # 行格式不变，adapters 零改动


@pytest.mark.asyncio
async def test_sync_adapters_disabled_rejected(db_session, library_root):
    from platform_core.exceptions import AuthorizationException

    async with db_session() as s:
        with pytest.raises(AuthorizationException):
            await SkillService(s).sync_adapters()


@pytest.mark.asyncio
async def test_sync_adapters_runs_script(db_session, library_root, monkeypatch):
    import backend.services.skill_service as svc_mod
    from config import settings

    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", True)
    executed = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self):
            return (b"symlinked 2\n", b"")

    async def _fake_exec(*args, cwd=None, **kw):
        executed["args"] = args
        executed["cwd"] = cwd
        return _FakeProc()

    monkeypatch.setattr(svc_mod.asyncio, "create_subprocess_exec", _fake_exec)

    async with db_session() as s:
        result = await SkillService(s).sync_adapters()
    assert result["ok"] is True and "symlinked 2" in result["output"]
    assert executed["cwd"] == str(library_root)
    assert "sync.sh" in " ".join(executed["args"])


def test_manifests_endpoints(db_client, db_engine, db_session, library_root):
    resp = db_client.get("/api/v1/skills/manifests")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"claude-code": ["example-pdf-extractor"]}

    put = db_client.put("/api/v1/skills/manifests", json={"tool": "claude-code", "names": ["x1"]})
    assert put.status_code == 200
    assert "- x1\n" in (library_root / "manifests" / "claude-code.yaml").read_text()
