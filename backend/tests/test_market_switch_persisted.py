"""能力市场开关落库（决策 D34 = A，连带 BUG-32；2026-09-29「按照建议做」）

原先超管切换只写进程内 settings：重启即丢、多 worker 各说各话，且绕过启动时的值班联系人检查。
- 真相源：system_configs.power_market.enabled；没有这行时按 yaml POWER_MARKET.ENABLED
- 打开时必须已配置 OPS.DUTY_CONTACT（与启动检查同一口径）；关闭不受限
- 通用配置写接口不能改这个键（否则绕过值班检查）
"""
from __future__ import annotations

import pytest

from config import settings

SWITCH = "/api/v1/admin/power-market"
PUBLIC = "/api/v1/public/capabilities"


@pytest.fixture
def yaml_market(monkeypatch):
    """模拟进程级配置：用例里改 yaml 值 = 重启后读到的部署默认"""
    originals = {k: settings.get(k) for k in ("POWER_MARKET.ENABLED", "OPS.DUTY_CONTACT")}

    def _set(enabled: bool, duty: str = "ops-duty@example.invalid"):
        settings.set("POWER_MARKET.ENABLED", enabled)
        settings.set("OPS.DUTY_CONTACT", duty)

    yield _set
    for k, v in originals.items():
        settings.set(k, v)


def test_switch_survives_restart(platform_admin_client, db_client, yaml_market):
    yaml_market(False)
    opened = db_client.put(SWITCH, json={"enabled": True})
    assert opened.status_code == 200, opened.text
    yaml_market(False)  # 「重启」：进程内配置回到部署默认
    assert db_client.get(SWITCH).json()["data"]["enabled"] is True
    assert db_client.get(PUBLIC).json()["data"].get("market_closed") is not True

    closed = db_client.put(SWITCH, json={"enabled": False})
    assert closed.status_code == 200, closed.text
    yaml_market(True)  # 部署默认是开，但库里明确关了 → 以库为准
    assert db_client.get(SWITCH).json()["data"]["enabled"] is False
    assert db_client.get(PUBLIC).json()["data"].get("market_closed") is True


def test_opening_requires_duty_contact(platform_admin_client, db_client, yaml_market):
    yaml_market(False, duty="")
    resp = db_client.put(SWITCH, json={"enabled": True})
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "DUTY_CONTACT_REQUIRED"
    assert db_client.get(SWITCH).json()["data"]["enabled"] is False
    assert db_client.put(SWITCH, json={"enabled": False}).status_code == 200  # 关闭不受限


def test_no_row_falls_back_to_yaml(platform_admin_client, db_client, yaml_market):
    yaml_market(True)
    assert db_client.get(SWITCH).json()["data"]["enabled"] is True
    yaml_market(False)
    assert db_client.get(SWITCH).json()["data"]["enabled"] is False


def test_generic_config_write_cannot_flip_market(platform_admin_client, db_client, yaml_market):
    yaml_market(False, duty="")
    resp = db_client.put("/api/v1/configs/power_market.enabled", json={"value": "true"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "CONFIG_KEY_GOVERNED"
    assert db_client.get(SWITCH).json()["data"]["enabled"] is False
