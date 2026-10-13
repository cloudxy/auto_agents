# scripts/

只负责两件事：**初始化辅助** 和 **进程启停**。质量门禁、OpenAPI 导出、看门狗不在这里。

```
scripts/
  lib/common.sh   ROOT / log / die / alembic（init_project.sh 与 db/ 共用）
  runlib/         启停：detect / process / catalog / ctl / backend / spider / frontend
  db/             建库、迁移、基线表（初始化会调用）
```

仓库根：`init_project.sh`（第一次）· `run.py`（日常启停）。`run.py start/restart` 会跑 `scripts/sync_agents_hub.py`，把产品 hub 根（`SKILLS.AGENTS_ROOT`，默认 `runtime/agents-hub/`，不是开发中枢 `.agents/`）增量写入能力市场；D2 前的存量迁移用 `db/migrate_agents_hub_root.py`（默认 dry-run，见 `docs/ops/runbook.md` 第 6 节）。

质量门禁：`tools/check/`。OpenAPI：`tools/dump_openapi.py`。僵死看门狗：`deploy/watchdog.sh`。
