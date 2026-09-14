# T-05 evidence · 夹具快照与拦住 vs 完成可查

> FR-U03 · 由 T-01 + T-02 交付，本文件索引

- T-01：`internal_fixture_tenants` + `product_events.is_internal_fixture`；`GET /product-events?is_internal_fixture=false`；pytest `test_t01_internal_fixture.py` 9 passed
- T-02：`task_blocked`（worker_offline / quota_*）vs `task_completed`；拦住路径不发 `task_run_submitted`；全量 `uv run pytest -q backend/tests` 1570 passed

open：规划 token 满仍发 `quota_exceeded` 而非 `task_blocked.reason=quota_tokens`（入队不查 token）。
