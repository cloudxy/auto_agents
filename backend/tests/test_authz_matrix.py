"""T2：401/403 口径矩阵（匿名 vs 租户 admin）。"""
import pytest


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/spiders/nodes"),
    ("GET", "/api/v1/tenants/me/usage"),
    ("GET", "/api/v1/billing/subscription"),
    ("GET", "/api/v1/litellm/keys"),
])
def test_anonymous_is_401(client, method, path):
    resp = client.request(method, path)
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("success") is False or "code" in body or "message" in body


def test_tenant_admin_forbidden_on_platform_litellm(admin_client):
    resp = admin_client.get("/api/v1/litellm/keys")
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("success") is False or body.get("code")
