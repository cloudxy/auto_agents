# backend memory · feat-four-pillars-v2

> Facts (**what**). How stays in SKILL.md. Cap 2200.

## Last

- Date: 2026-09-10
- Hat: backend prep IdleAutoClose / 18.4 分窗
- Outputs: `.sdlc/feat-four-pillars-v2/03-impl/prep-idle-close-evidence.md`

## Facts

- IdleAutoClose 与 GWT-18.4 是两口钟：`SPIDER_IDLE_CLOSE_SECONDS` 默认 **30**（连续空闲 → finished）；`SPIDER_WORKER_OFFLINE_SECONDS` 默认 **120**（`annotate_tasks` 专用）。禁止同一键。21600 只属于 RELAY 探针锁。
- `product_idle_close_seconds()` / `product_worker_offline_seconds()`；≤0 或 21600 回该口默认。`scrapy/settings.py` `IDLE_CLOSE_SECONDS` 缺省 30。local yml 必须一起改，否则盖回 120。
- 18.1 live Worker 交 sre；本帽只钉 idle<120、≠21600、idle+5s crawl<120。
- `test_saas_wiring.py` 超并发 Then：`QuotaExceededException` + `code==QUOTA_EXCEEDED` + `PLAN_FULL_*`。禁止 `or True`。
- `test_saas_byok.py` source 是 `provider:{id}` 不是名字；隔离 Then = URL + visible 名 + provider_id。括号化，禁永真。
- 启用闸：`LLM.ENABLED` 或 `POWER_MARKET.ENABLED` 且 `OPS.DUTY_CONTACT` 空 → lifespan `_validate_enablement_duty_contact` 拒绝启动。空串占位，不代填号码。不关闭 Q-OPS-DUTY。
- `llm_chat`：`if not cfg.enabled` 必须在网关探测前。`DATA_PLANE=litellm` except 禁止 `resolve_config_from_settings()`。70.2 与 74.1 不得混句。
- `record_audit` 只委托 `record_audit_standalone`。pytest `_reset_db_manager` 清空 DEFAULT。

## Open (mine)

- 无。六问不代选。live 18.1 归 sre。

## Do not re-litigate

- 不改 GWT-18.4 120s Then；不把 idle 调回 120；不把两口钟并回一键
- 不改 `uq_asset_type_name_alive`；不自动建 alias；不代选六问；不施工 Wave 2/3；不把 LiteLLM 焊进根 compose
- 不改 74.1 族文案；except 不回 yml；不混 70.2/74.1
