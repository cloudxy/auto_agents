# Alembic 迁移演练留档 · 2026-08-30

> 目的：发布前在隔离演练库完成本次交付三个迁移（010 / 011 / 012）的全流程验证，
> 确认 upgrade / downgrade 双向可执行、可重复。
> 环境：本地 MySQL，临时演练库 `auto_agents_rehearsal`（演练结束可删除，不影响业务库）。
> 结论：三组往返全部通过，012 索引断言两枚命中。细节见下文各节结果摘要。

## 〇、演练库准备（两组演练共用）

```bash
# 1. 创建临时演练库
mysql -h127.0.0.1 -uroot -p -e \
  "CREATE DATABASE IF NOT EXISTS auto_agents_rehearsal DEFAULT CHARACTER SET utf8mb4;"

# 2. 环境变量把连接指向演练库（不改配置文件；密码经环境变量注入，与 env.py 取法一致）
export MYSQL_DEFAULT_PASSWORD='<你的密码>'
export AUTO_AGENTS_MYSQL__DEFAULT__DB_NAME=auto_agents_rehearsal
```

## 一、010 / 011 演练（建表类迁移，当时 head=011）

验证目标：`llm_providers` / `channel_events` / `channel_probe_results` 三张新表的
upgrade → downgrade → upgrade 全链路往返。

```bash
cd backend
uv run alembic upgrade head     # 从 009 一路升到 011（建三张表）
uv run alembic current          # 断言：011
uv run alembic downgrade -2     # 回退 010/011（删三张表）
uv run alembic current          # 断言：009
uv run alembic upgrade head     # 重建到 011
uv run alembic current          # 断言：011
```

**结果摘要**：三轮全部成功。纯建表/删表 DDL，不触碰既有数据；往返可重复、幂等。

## 二、012 演练（索引类迁移，模拟线上存量库处于 011）

验证目标：`spider_results` 两枚二级索引的在线 DDL 往返与索引落库断言。

```bash
cd backend
uv run alembic stamp 011        # 模拟存量库已处于 011（跳过建表历史）
uv run alembic upgrade head     # 执行 012（创建两枚二级索引）
uv run alembic current          # 断言：012

# 索引断言：两枚索引必须存在
mysql -h127.0.0.1 -uroot -p -e \
  "SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols
   FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA='auto_agents_rehearsal' AND TABLE_NAME='spider_results'
   GROUP BY INDEX_NAME;"
# 预期包含：
#   ix_spider_results_created_at        → created_at
#   ix_spider_results_spider_created    → spider_name,created_at

uv run alembic downgrade -1     # 删除两枚索引
uv run alembic upgrade head     # 重建
uv run alembic current          # 断言：012
```

**结果摘要**：upgrade → downgrade -1 → upgrade 往返全部成功，索引断言两枚命中。
012 为纯二级索引在线 DDL（MySQL 8.0 默认 `ALGORITHM=INPLACE`、`LOCK=NONE`，不锁表），
downgrade 仅删索引，无损。

## 三、上线提示

- 上线顺序与回滚窗口约束见 `docs/release-notes-2026-08-30.md` 第二节；
- **012 上线前如距本次演练超过一周，建议在临时库复跑一遍第二节命令**
  （防止期间模型/迁移链变动引入偏差）；
- 演练库 `auto_agents_rehearsal` 验证完毕后可
  `DROP DATABASE auto_agents_rehearsal;` 清理。
