"""B1c 零 HTTP 覆盖路由清剿——skills 静态段写路由（2 条）

覆盖路由清单（全部 require_admin）：
- POST /api/v1/skills/import-url    URL 导入（GitHub 子目录 / raw / zip；外呼经服务层）
- POST /api/v1/skills/sync-adapters 触发 sync.sh 适配器分发（受
  SKILLS.ADAPTER_SYNC.ENABLED 开关约束）

行为契约级口径：
- import-url：url 非 http(s) → 422 且导入服务零调用；成功路径 200 + 审计动作
  skill.import（外呼拉取的等价类已由 test_skill_import.py 在服务层覆盖，
  本文件只锁 HTTP 接线，不 mock 内部细节之外的东西）
- sync-adapters：开关关 → 403（开关是授权边界，非参数错误）；开关开且脚本
  存在 → 执行并回传 ok/returncode/output，脚本副作用可观察；脚本缺失 → 422
"""
from unittest.mock import AsyncMock

import pytest

IMPORT_URL = "/api/v1/skills/import-url"
SYNC_URL = "/api/v1/skills/sync-adapters"


# ---------------------------------------------------------------------------
# POST /api/v1/skills/import-url
# ---------------------------------------------------------------------------

def test_import_url_admin_ok(db_client, admin_client, monkeypatch):
    """admin 合法 URL：200 回执 + 审计动作 skill.import（服务外呼经桩隔离）"""
    from backend.services.skill_import_service import SkillImportService

    import_mock = AsyncMock(return_value={"name": "imported-skill", "created": True})
    monkeypatch.setattr(SkillImportService, "import_url", import_mock)
    import backend.app.api.v1.skills as api_mod
    audit_mock = AsyncMock()
    monkeypatch.setattr(api_mod, "record_audit", audit_mock)

    resp = admin_client.post(IMPORT_URL, json={
        "url": "https://github.com/o/r/tree/main/skills/imported-skill",
        "category": "dev-tools",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "imported-skill"

    import_mock.assert_awaited_once()  # 透传 url/category
    call = import_mock.await_args
    assert call.args[0] == "https://github.com/o/r/tree/main/skills/imported-skill"
    assert call.kwargs.get("category") == "dev-tools"
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[2] == "skill.import"


@pytest.mark.parametrize("url", ["", "ftp://files.example.com/x", "not-a-url"])
def test_import_url_invalid_scheme_422(db_client, admin_client, monkeypatch, url):
    """非 http(s) URL → 422，且导入服务零调用（拒绝路径零副作用）"""
    from backend.services.skill_import_service import SkillImportService

    import_mock = AsyncMock()
    monkeypatch.setattr(SkillImportService, "import_url", import_mock)

    resp = admin_client.post(IMPORT_URL, json={"url": url})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert "url" in resp.json()["message"]
    import_mock.assert_not_awaited()


def test_import_url_anonymous_401(client):
    assert client.post(IMPORT_URL, json={"url": "https://x.example.com"}).status_code == 401


def test_import_url_operator_403(operator_client):
    resp = operator_client.post(IMPORT_URL, json={"url": "https://x.example.com"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# POST /api/v1/skills/sync-adapters
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter_library(tmp_path):
    """能力库根 + 可执行 sync.sh（写 marker 文件证明真实执行）"""
    from config import settings

    original_root = settings.get("SKILLS.LIBRARY_ROOT")
    original_enabled = settings.get("SKILLS.ADAPTER_SYNC.ENABLED")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", True)
    (tmp_path / "sync.sh").write_text(
        "#!/bin/bash\nset -e\ntouch \"$(dirname \"$0\")/ran.marker\"\necho adapter-synced\n"
    )
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original_root)
    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", original_enabled)


def test_sync_adapters_disabled_403(db_client, admin_client, tmp_path, monkeypatch):
    """开关关闭 → 403（AuthorizationException：开关是授权边界），脚本零执行"""
    from config import settings

    original_root = settings.get("SKILLS.LIBRARY_ROOT")
    original_enabled = settings.get("SKILLS.ADAPTER_SYNC.ENABLED")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", False)
    (tmp_path / "sync.sh").write_text("#!/bin/bash\ntouch \"$PWD/ran.marker\"\n")
    try:
        resp = admin_client.post(SYNC_URL)
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "FORBIDDEN"
        assert "未启用" in resp.json()["message"]
        assert not (tmp_path / "ran.marker").exists()  # 副作用：脚本未执行
    finally:
        settings.set("SKILLS.LIBRARY_ROOT", original_root)
        settings.set("SKILLS.ADAPTER_SYNC.ENABLED", original_enabled)


def test_sync_adapters_ok(db_client, admin_client, adapter_library):
    """开关开 + 脚本存在 → 200 ok/returncode/output + 脚本真实执行（marker 落盘）"""
    resp = admin_client.post(SYNC_URL)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["ok"] is True
    assert data["returncode"] == 0
    assert "adapter-synced" in data["output"]
    assert (adapter_library / "ran.marker").exists()  # 副作用：sync.sh 已执行


def test_sync_adapters_missing_script_422(db_client, admin_client, tmp_path, monkeypatch):
    """开关开但库根无 sync.sh → 422（配置缺失类校验失败）"""
    from config import settings

    original_root = settings.get("SKILLS.LIBRARY_ROOT")
    original_enabled = settings.get("SKILLS.ADAPTER_SYNC.ENABLED")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))  # 空 tmp：无 sync.sh
    settings.set("SKILLS.ADAPTER_SYNC.ENABLED", True)
    try:
        resp = admin_client.post(SYNC_URL)
        assert resp.status_code == 422, resp.text
        assert "sync.sh 不存在" in resp.json()["message"]
    finally:
        settings.set("SKILLS.LIBRARY_ROOT", original_root)
        settings.set("SKILLS.ADAPTER_SYNC.ENABLED", original_enabled)


def test_sync_adapters_anonymous_401(client):
    assert client.post(SYNC_URL).status_code == 401


def test_sync_adapters_operator_403(operator_client):
    assert operator_client.post(SYNC_URL).status_code == 403
