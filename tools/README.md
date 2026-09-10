# tools/

开发与 CI 门禁，不是项目启停。

| 路径 | 职责 |
|------|------|
| `check/arch.sh` | 架构红线 R1–R13 + B1–B3 |
| `check/db_ir.sh` | DBML IR lint |
| `check/db_migrations.sh` | 迁移破坏性变更 |
| `check/frontend.sh` | 前端工程门禁 |
| `dump_openapi.py` | 离线导出 OpenAPI → 前端 codegen |

```bash
bash tools/check/arch.sh
uv run python tools/dump_openapi.py
```
