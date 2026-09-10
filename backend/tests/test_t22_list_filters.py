"""T-22：公开列表 q / host / category 叠在 FR-33 上，禁止 LIMIT 后再滤。"""
from backend.tests.fr33_support import fr33_asset, seed_rows

_CAP = "/api/v1/public/capabilities"
_SKILL = "/api/v1/public/skills"


class _RateLimitRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


def _rate(monkeypatch):
    fake = _RateLimitRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as mod
    monkeypatch.setattr(mod, "get_async_redis", _fake)
    return fake


def test_q_hits_display_name_with_prefixed_catalog(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [
        fr33_asset(
            name="mattpocock-skills__code-review",
            title="代码审查",
            category="dev-tools",
        ),
        fr33_asset(name="other-skill", title="其它", category="dev-tools"),
    ])
    resp = db_client.get(_CAP, params={"q": "代码审查"})
    assert resp.status_code == 200, resp.text
    names = [i["name"] for i in resp.json()["data"]["items"]]
    assert names == ["mattpocock-skills__code-review"]


def test_q_hits_origin_short_name(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [
        fr33_asset(
            name="mattpocock-skills__code-review",
            title="代码审查",
            category="dev-tools",
        ),
    ])
    resp = db_client.get(_CAP, params={"q": "code-review"})
    assert resp.status_code == 200, resp.text
    names = [i["name"] for i in resp.json()["data"]["items"]]
    assert names == ["mattpocock-skills__code-review"]
    skill = db_client.get(_SKILL, params={"q": "code-review"})
    assert skill.status_code == 200
    assert [i["name"] for i in skill.json()["data"]["items"]] == names


def test_q_does_not_surface_unlisted_or_blacklist(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [
        fr33_asset(
            name="listed-review", title="代码审查", category="dev-tools",
        ),
        fr33_asset(
            name="unlisted-review", title="代码审查",
            listing_state="unlisted", category="dev-tools",
        ),
        fr33_asset(
            name="black-review", title="代码审查",
            status="blacklist", category="dev-tools",
        ),
    ])
    resp = db_client.get(_CAP, params={"q": "代码审查"})
    names = {i["name"] for i in resp.json()["data"]["items"]}
    assert names == {"listed-review"}


def test_category_filter_on_top_of_fr33(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [
        fr33_asset(name="in-cat", title="甲", category="dev-tools"),
        fr33_asset(name="out-cat", title="乙", category="ops"),
    ])
    resp = db_client.get(_CAP, params={"category": "dev-tools"})
    assert [i["name"] for i in resp.json()["data"]["items"]] == ["in-cat"]


def test_host_kimi_matches_null_and_declared_not_empty(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [
        fr33_asset(name="undeclared", title="未声明"),
        fr33_asset(name="kimi-only", title="仅 Kimi", host_compat=["kimi"]),
        fr33_asset(name="grok-only", title="仅 Grok", host_compat=["grok"]),
        fr33_asset(name="zero-host", title="零宿主", host_compat=[]),
    ])
    resp = db_client.get(_CAP, params={"host": "kimi"})
    assert resp.status_code == 200, resp.text
    names = {i["name"] for i in resp.json()["data"]["items"]}
    assert names == {"undeclared", "kimi-only"}


def test_host_filter_not_limit_then_filter(
    db_client, db_engine, db_session, monkeypatch,
):
    """先 COUNT/LIMIT 再滤宿主会把后插入的 grok 行占满第 1 页。"""
    _rate(monkeypatch)
    kimi = [
        fr33_asset(name=f"kimi-{i:02d}", title=f"k{i}", host_compat=["kimi"])
        for i in range(5)
    ]
    grok = [
        fr33_asset(name=f"grok-{i:02d}", title=f"g{i}", host_compat=["grok"])
        for i in range(20)
    ]
    hidden = [
        fr33_asset(
            name=f"hid-kimi-{i:02d}", title="hidden",
            listing_state="unlisted", host_compat=["kimi"],
        )
        for i in range(10)
    ]
    seed_rows(db_session, kimi + grok + hidden)
    resp = db_client.get(_CAP, params={"host": "kimi", "page": 1, "page_size": 20})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    names = [i["name"] for i in data["items"]]
    assert data["total"] == 5
    assert names == [f"kimi-{i:02d}" for i in range(4, -1, -1)]
    assert data["has_more"] is False


def test_unknown_host_is_empty_not_500(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [fr33_asset(name="any", title="任意")])
    resp = db_client.get(_CAP, params={"host": "bogus"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
