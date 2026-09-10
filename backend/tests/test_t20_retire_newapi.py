"""T-20：默认 DATA_PLANE=litellm；NEWAPI.ENABLED 恒 false；运行时无 NEWAPI.* 读。"""
from pathlib import Path

from config import settings

ROOT = Path(__file__).resolve().parents[2]
_RUNTIME = [
    ROOT / "backend/app/__init__.py",
    ROOT / "backend/services/ai_planner/llm_client.py",
    ROOT / "backend/services/channel_config_service.py",
    ROOT / "backend/services/channel_probe_service.py",
    ROOT / "backend/services/channel_scheduler_service.py",
    ROOT / "backend/services/newapi_api.py",
    ROOT / "backend/services/newapi_overview_service.py",
    ROOT / "backend/services/gateway_models.py",
]


def test_default_data_plane_is_litellm():
    assert settings.get("LLM.DATA_PLANE") == "litellm"
    yml = (ROOT / "config" / "default" / "llm.yml").read_text(encoding="utf-8")
    assert 'DATA_PLANE: "litellm"' in yml
    assert 'DATA_PLANE: "providers"' not in yml


def test_newapi_enabled_constant_false():
    assert not settings.get("NEWAPI.ENABLED")
    yml = (ROOT / "config" / "default" / "newapi.yml").read_text(encoding="utf-8")
    assert "ENABLED: false" in yml
    assert "TOMBSTONE" in yml


def test_runtime_services_do_not_read_newapi_settings():
    needles = ('settings.get("NEWAPI.', "settings.get('NEWAPI.", 'settings["NEWAPI.')
    for path in _RUNTIME:
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"{path} still reads {needle}"


def test_root_compose_has_no_newapi_service():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "calciumion/new-api" not in text
    assert "container_name: newapi-app" not in text
    assert "newapi-net" not in text
