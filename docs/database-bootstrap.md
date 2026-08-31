# 空库引导指南（bootstrap-db）

> 一键入口：`bash scripts/bootstrap-db.sh`（幂等，可重复执行）。

## 背景

Alembic 迁移链 **003/006** 对链外表 `spider_tasks` 做 `add_column`，而该基线表
由 `scripts/init_db_sync.py` 的 `create_all` 预建。因此**空库直接
`alembic upgrade head` 会失败**，新环境初始化必须走
「建库 → create_all 基线 → `alembic stamp head`」三段式引导。
该已知遗留项官方留档见 `docs/release-notes-2026-08-30.md`（基线修复另行排期）。

## 标准流程（脚本自动执行）

| 步骤 | 动作 | 说明 |
|------|------|------|
| Step 1 | 前置校验 + 解析连接参数 | 校验 `uv` 可用；打印目标库（密码掩码） |
| Step 2 | 连接测试 + 按需建库 | 库已存在则跳过；缺失则 `CREATE DATABASE IF NOT EXISTS`（utf8mb4） |
| Step 3 | `uv run python scripts/init_db_sync.py` | create_all 基线表（已存在表自动跳过） |
| Step 4 | 迁移链收口 | 无 `alembic_version` → `stamp head`；已有版本 → `upgrade head`（head 上为 no-op） |

## 手动等价命令

```bash
# 1) 建库（如缺失；参数取自 config/<env>/mysql.yml 与 MYSQL_DEFAULT_PASSWORD）
# 2) 基线表
uv run python scripts/init_db_sync.py
# 3) 收口（alembic.ini 的 script_location 相对 backend/，必须 cd backend 执行）
cd backend && uv run alembic -c alembic.ini stamp head
```

## 配置来源（配置即代码）

脚本不硬编码任何连接串/密码/库名：

- 密码取值优先级：环境变量 `MYSQL_DEFAULT_PASSWORD` > Dynaconf settings
  （`config/` 多层合并，`APP_ENV` 默认 `local`，可用 `APP_ENV=dev` 覆盖）；
- alembic 连接串由 `backend/alembic/env.py` 从 settings 动态注入，与脚本一致。

## 故障排查

- **连接失败**：依次检查 MySQL 服务可达性（HOST/PORT）、
  `MYSQL_DEFAULT_PASSWORD` / `config/<env>/mysql.yml` 凭据；
- **建库被拒**：受限账号无 CREATE 权限时，请 DBA 预建库后重跑（幂等）；
- **Step 3 失败**：traceback 已含根因，修复后直接重跑；
- **Step 4 失败**：确认 Step 3 基线表已建出，再检查 `backend/alembic/versions` 迁移链。
