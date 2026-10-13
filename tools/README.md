# tools/

开发与 CI 门禁，不是项目启停。

| 路径 | 职责 |
|------|------|
| `check/arch.sh` | 架构红线 R1–R13 + B1–B4 + FR-14 + PL + SZ（规模约定，调用 `check/size.py`） |
| `check/size.py` | SZ：Python 单文件 ≤ 500 行、单函数 ≤ 40 行（不含测试与迁移；`python3 tools/check/size.py <文件…>` 可单查） |
| `check/db_ir.sh` | DBML IR lint |
| `check/db_migrations.sh` | 迁移破坏性变更 |
| `check/frontend.sh` | 前端工程门禁 |
| `git/sync_main.sh` | post-checkout 钩子：切分支后自动合并 `origin/main`（fail-open） |
| `dump_openapi.py` | 离线导出 OpenAPI → 前端 codegen |

```bash
bash tools/check/arch.sh
uv run python tools/dump_openapi.py
```
