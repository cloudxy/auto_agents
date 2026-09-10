# scripts/

只负责两件事：**初始化辅助** 和 **进程启停**。质量门禁、OpenAPI 导出、看门狗不在这里。

```
scripts/
  lib/common.sh   ROOT / log / die / alembic（init_project.sh 与 db/ 共用）
  runlib/         启停：detect / process / catalog / ctl / backend / spider / frontend
  db/             建库、迁移、基线表（初始化会调用）
```

仓库根：`init_project.sh`（第一次）· `run.py`（日常启停）。

质量门禁：`tools/check/`。OpenAPI：`tools/dump_openapi.py`。僵死看门狗：`deploy/watchdog.sh`。
