# backend memory · feat-four-pillars-v2

> Facts (**what**). How stays in SKILL.md. Cap 2200.

## Last

- Date: 2026-09-08
- Hat: backend 定义帽只读诊断
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/backend.md`

## Facts

- 守卫：`backend/app/api/deps.py`。`require_admin`≠超管。`require_platform_admin`几乎只挂 `/admin/tenants*`。无 `require_permission`。
- P0 仍在：scan/verify=`require_login`；newapi/LLM写=`require_admin`；`test_b1c` viewer scan 金标。
- 入队仅 `POST /spiders/run` 带 `tenant_id`。门面不转发。`before_flush`只断言不回填。
- `check_llm_tokens_month`仅测试。`llm_chat`走 `MAX_TOKENS_BUDGET`。月 Redis `{dim}|total` 无 tenant。
- 结果 COUNT/数据中心不排除 `source=marketplace`。管理详情仍回 `file_path`。用量 `utcnow`。
- POWER_MARKET/listing_state(代码)/sources/installs/`power_market/`/`power_market.yml`=0。
- `capability_assets` 未豁免。Alembic 头=027。`marketplace_crawled` 19 vs VARCHAR(16)。
- 登录已出 `is_platform_admin`。`_ROLE_PERMISSIONS[admin]` 仍含 `menu:newapi`。LiteLLM 仅 pycache。R7/R11 干净。
- 旧塑形不是现行合同；D14/D16/D5、NOT NULL、两本账必须吸收。

## Open (mine)

- btn:market Depends vs 只改 platform_admin
- BYOK 平台行 vs 租户行；RBAC/configs 是否同波
- 到期登录；FR-03 100条；FR-12 code；CACHE_DIR 锁；公开四类 vs 五类

## Do not re-litigate

- 不另起 /market；不合并 skills 三表；不 Mixin 回填；候选禁止 NULL tenant
- LiteLLM/MCP工具面/代写 ~/.zcode 不做；不拆门面（只转发 tenant_id）
- 收 scan 同 PR 改 test_b1c；D16 ENABLED 默认 false 回退 LIBRARY_ROOT/plugins
