"""T3：OpenAPI 路由清单 golden——新路由不更新本文件即红。"""
from pathlib import Path

GOLDEN = Path(__file__).with_name("openapi_routes_golden.txt")


def _collect(app) -> list[str]:
    from conftest import iter_app_routes

    rows: list[str] = []
    for path, route in iter_app_routes(app):
        methods = getattr(route, "methods", None)
        if not methods or not path:
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            rows.append(f"{method} {path}")
    return sorted(set(rows))


def test_v1_route_inventory_matches_golden(app):
    actual = _collect(app)
    assert GOLDEN.exists(), f"缺少路由清单 {GOLDEN}，请先落地 golden 文件"
    expected = [ln for ln in GOLDEN.read_text(encoding="utf-8").splitlines() if ln.strip()]
    added = sorted(set(actual) - set(expected))
    removed = sorted(set(expected) - set(actual))
    assert actual == expected, (
        f"路由清单漂移 added={added} removed={removed}；请更新 {GOLDEN.name}"
    )
