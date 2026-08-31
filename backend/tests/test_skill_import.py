"""A-P3-1 URL 导入验证（工单 16）：三形态 + 安全验收（zip-slip/上限）+ 冲突

Seam（工单预确认）：SkillImportService.import_url 公共方法（注入 httpx MockTransport 客户端）。
"""
import io
import zipfile
from pathlib import Path

import pytest
import yaml

import backend.services.skill_import_service as svc
from backend.services.skill_import_service import SkillImportService
from platform_core.exceptions import ValidationException

SKILL_MD = """---
name: imported-skill
description: 外部导入
---
# I
"""


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in entries.items():
            zf.writestr(path, content)
    return buf.getvalue()


def _client(handler) -> "httpx.AsyncClient":
    import httpx

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)


@pytest.fixture
def library_root(tmp_path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


async def _run(db_session, url, client):

    async with db_session() as s:
        result = await SkillImportService(s).import_url(url, client=client)
        await s.commit()
    return result


@pytest.mark.asyncio
async def test_zip_import_happy_path(db_session, library_root):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_zip_bytes({"skill/SKILL.md": SKILL_MD, "skill/extra.md": "x"}),
            request=request,
        )

    result = await _run(db_session, "https://example.com/skill.zip", _client(handler))
    assert result["name"] == "imported-skill" and result["imported"] is True
    skill_dir = library_root / "skills" / "imported-skill"
    assert (skill_dir / "SKILL.md").read_text().startswith("---")
    meta = yaml.safe_load((skill_dir / "meta.yaml").read_text())
    assert meta["status"] == "experimental" and meta["source"]["url"].endswith("skill.zip")
    assert (skill_dir / "SOURCE.md").exists() and (skill_dir / "CHANGELOG.md").exists()


@pytest.mark.asyncio
async def test_zip_slip_rejected(db_session, library_root):
    import httpx

    evil = _zip_bytes({
        "skill/SKILL.md": SKILL_MD,
        "../evil.txt": "pwned",
        "/abs/evil2.txt": "pwned2",
    })

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=evil, request=request)

    with pytest.raises(ValidationException, match="路径"):
        await _run(db_session, "https://example.com/evil.zip", _client(handler))
    assert not (library_root.parent / "evil.txt").exists()
    assert not Path("/abs/evil2.txt").exists()
    # 失败不落任何盘上残留（目标目录未创建或为空）
    target = library_root / "skills" / "imported-skill"
    assert not target.exists() or not any(target.iterdir())


@pytest.mark.asyncio
async def test_size_and_count_limits_rejected(db_session, library_root, monkeypatch):
    import httpx

    # 用例 1：zip 总大小超限
    monkeypatch.setattr(svc, "ZIP_MAX_BYTES", 100)
    big = _zip_bytes({"skill/SKILL.md": SKILL_MD})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big, request=request)

    with pytest.raises(ValidationException, match="大小"):
        await _run(db_session, "https://example.com/big.zip", _client(handler))

    # 用例 2：文件数量超限（放开大小限制）
    monkeypatch.setattr(svc, "ZIP_MAX_BYTES", 1024 * 1024)
    monkeypatch.setattr(svc, "MAX_FILES", 2)

    def many_handler(request: httpx.Request) -> httpx.Response:
        entries = {f"skill/f{i}.md": "x" for i in range(5)}
        entries["skill/SKILL.md"] = SKILL_MD
        return httpx.Response(200, content=_zip_bytes(entries), request=request)

    with pytest.raises(ValidationException, match="数量"):
        await _run(db_session, "https://example.com/many.zip", _client(many_handler))


@pytest.mark.asyncio
async def test_github_subdir_import(db_session, library_root):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com" and "git/trees" in str(request.url):
            return httpx.Response(200, json={
                "tree": [
                    {"path": "skills/demo/SKILL.md", "type": "blob", "sha": "a1"},
                    {"path": "skills/demo/lib/util.py", "type": "blob", "sha": "a2"},
                    {"path": "other/README.md", "type": "blob", "sha": "a3"},
                ]
            }, request=request)
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, text=SKILL_MD, request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    result = await _run(
        db_session,
        "https://github.com/octocat/repo/tree/main/skills/demo",
        _client(handler),
    )
    assert result["name"] == "imported-skill" and result["imported"] is True


@pytest.mark.asyncio
async def test_name_conflict_returns_422(db_session, library_root):
    import httpx

    # 先导入一次
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_zip_bytes({"skill/SKILL.md": SKILL_MD}), request=request)

    await _run(db_session, "https://example.com/skill.zip", _client(handler))
    with pytest.raises(ValidationException, match="已存在"):
        await _run(db_session, "https://example.com/skill-2.zip", _client(handler))


def test_check_update_uses_httpx_trust_env_false(db_client, db_engine, db_session, library_root, monkeypatch):
    """check-update 拉取必须走 httpx 且 trust_env=False（总方案 3.2-A-8）"""
    import asyncio
    import httpx

    captured: dict = {}

    real_client = httpx.AsyncClient

    class _SpyClient(real_client):
        def __init__(self, *a, **kw):
            captured["trust_env"] = kw.get("trust_env", "MISSING")
            super().__init__(*a, **kw)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SKILL_MD + "\nupdated", request=request)

    monkeypatch.setattr(svc.httpx, "AsyncClient", _SpyClient)

    d = library_root / "skills" / "imported-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "meta.yaml").write_text(
        "name: imported-skill\nstatus: experimental\nsource:\n  url: https://example.com/raw/SKILL.md\n"
    )

    async def _seed():
        from backend.services.skill_service import SkillService

        async with db_session() as s:
            await SkillService(s).scan_library(root=library_root / "skills")
            await s.commit()

    asyncio.run(_seed())
    captured.clear()  # 只观测 check-update 的客户端构造

    resp = db_client.get("/api/v1/skills/imported-skill/check-update")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "has_update" in data
    assert captured["trust_env"] is False
