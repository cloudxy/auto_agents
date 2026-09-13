# sre memory · upgrade-four-pillars

> Facts (**what**). How stays in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-13
- Hat: deliver / sre（r2 关闭 QA-05…QA-08；不重开 QA-01…QA-04）
- Outputs: `06-deliver/checklist.md`
- Lane: L3 · qc 有条件放行 N1–N4 v1.2（未改）
- root_cause: checklist operator steps were written from intended outcomes, not the FastAPI/lifespan/compose contracts those steps invoke.

## Facts

- 决策对象=工作区，祖先 `99e2f95`，**未冻结 SHA**。
- qc：pytest **1679 passed / 40 skipped** EXIT 0；arch 0；mig 0；T-26 10；T-27 Jest 43；matrix 13 FR-\d+；frontend.sh 0。工作区 admin+official build EXIT 0。本机 npm 11 ≠ CI npm@10。合入须冻结 SHA 四闸（条件 7）。
- head=`046` revises 045。**046 head 禁止 `alembic downgrade 044`**；仅 `current==045` 才允许 down 044。046 回滚=停工人/关市/DELETE 凭据/摘 notify。
- 租户 PUT POWER_MARKET → **403 FORBIDDEN**（GWT-U11.3）。404 只钉 T-09/T-15/T-27。
- 订一行公开路由：`POST /api/v1/public/capabilities/{asset_type}/{name}/subscribe`。单段 `<asset>` FastAPI 404，到不了 MARKET_CLOSED 409。
- `POWER_MARKET.ENABLED=true` 且 `OPS.DUTY_CONTACT=""` → lifespan `_validate_enablement_duty_contact` `RuntimeError` 拒启。超管 PUT 只 `settings.set`，不跑该守卫。本波联系人为空：档 3 **只** PUT；禁止环境变量持久开市。不代填号码。
- Caddy 无 `rate_limit` ≡ 停档 4，notify 不得公网。nginx `limit_req` 仍是档 5。
- 根 compose `networks.litellm-net.external: true`。compose 前置 `docker network create litellm-net`（已存在则跳过）。backend 本波不挂该网。
- compose：mysql/redis/backend only。Redis 无 volume。**禁止任何 compose down**。
- notify 无 JWT；无 RateLimitPolicy。HMAC ≠ live。yaml POWER_MARKET.ENABLED 默认 false。不写 SLA。不标 GA。

## Open (mine)

- 冻结 SHA 四闸（含 build）。
- live stop spider 墙钟未测。
- live 反代摘 location + limit_req 未测。
- 应用层 notify RateLimitPolicy 未接（报 backend）。
- ops 填 DUTY_CONTACT 之前不能环境变量持久开市。

## Do not re-litigate

- FakeRedis ≠ live 120s ≠ 北极星。HMAC ≠ live 收银台。活 ≠ SKU。空态 ≠ 已付。
- 不把 046 down / 从 046 的 downgrade 044 / 任何 compose down 当随手回滚。
- 不把开关 403 当 P1 泄面。不把 litellm nginx 当 billing notify。
- 不把单段 subscribe curl 当关市探针。不把无 rate_limit 的 Caddy reverse_proxy 当档 5。
