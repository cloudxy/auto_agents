# 实现证据 · prep IdleAutoClose / 18.4 分窗 + 空断言收口

> 票：frozen construction prep（GWT-18.1 Then vs IdleAutoClose）｜FR 锚点：FR-18｜角色：/backend｜日期：2026-09-10

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GWT-18.1 等待预算 120s 内 completed | Config + Scrapy 扩展 | `config/scrapy/*/settings.yml` + `IdleAutoClose` | 收尾钟 `SPIDER_IDLE_CLOSE_SECONDS=30`，≠ 21600，且 idle+~5s crawl < 120 |
| GWT-18.4 无终态满 120s 可见工人不在线 | Service | `spider_worker_gate.annotate_tasks` | 独立钟 `SPIDER_WORKER_OFFLINE_SECONDS=120`；禁止复用 idle-close |
| 入队超并发 Then | Service | `quota_service.check_task_concurrency` | 测试去掉 `or True`，断言 `QUOTA_EXCEEDED` + 用户可见句 |
| BYOK 租户隔离 Then | Service | `LlmProviderService.resolve_runtime_config` | 括号化断言：`provider:{id}` + URL + 可见名互不可见 |
| 启用闸（可选） | 启动 lifespan | `_validate_enablement_duty_contact` | `LLM.ENABLED`/`POWER_MARKET.ENABLED` 且 `OPS.DUTY_CONTACT` 空 → 拒绝启动；不代填号码 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/spider_worker_gate.py` | 修改 | idle 默认 30；新增 `product_worker_offline_seconds`；`annotate_tasks` 只用离线窗 |
| `scrapy/settings.py` | 修改 | `IDLE_CLOSE_SECONDS` 缺省 30 |
| `scrapy/extensions/__init__.py` | 修改 | 注释：30s 收尾；21600 探针锁；18.4 不是本窗 |
| `config/scrapy/default/settings.yml` | 修改 | idle 30 + offline 120 |
| `config/scrapy/local/settings.yml` | 修改 | 同上，避免 local 盖回 120 |
| `config/default/settings.yml` | 修改 | `OPS.DUTY_CONTACT: ""`（空，不代填） |
| `backend/app/__init__.py` | 修改 | 启用闸；lifespan 调用 |
| `backend/tests/test_scrapy_idle_autoclose.py` | 修改 | 钉 idle≠21600 且 <120；offline==120；idle+5s<120 |
| `backend/tests/test_saas_wiring.py` | 修改 | 去掉 `or True` |
| `backend/tests/test_saas_byok.py` | 修改 | 括号化隔离断言 |
| `backend/tests/test_webhook_secret_guard.py` | 修改 | 启用闸单测 |
| `03-impl/prep-idle-close-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（另加启用闸：`backend/app/__init__.py` + `config/default/settings.yml` + webhook 守卫测）

**未触碰「不许改的文件」**：☑ 确认（未改 spec GWT；未答六问；未动 Wave 2/3；未把 LiteLLM 焊进根 compose；未削弱 18.4 120s Then）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 配置读取 / 标注 | 否 | 只读 Redis 心跳 + 叠加响应字段 |
| 启动启用闸 | 否 | 进程启动 fail-fast，不写库 |

**事务提交后的操作失败怎么办**：N/A（本票无新写路径）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A |
| 保证方式 | N/A |
| 重复请求返回 | N/A |

☑ 未使用「先查后插」（无新插入）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 两口钟 | 独立配置键 | 21600 / ≤0 回落到该口默认，永不把探针锁当本窗 |

☑ 本票无新的条件更新行数分支

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新增外部调用 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 未改表 ☑ 未加字段 —— 本票纯配置/服务窗 + 测试收口

结构核对输出：

```
$ 未跑 SHOW CREATE TABLE（无 schema 变更）
N/A
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `product_idle_close_seconds` / `product_worker_offline_seconds` / `annotate_tasks` 既有 logger |
| 启用闸 | `RuntimeError` 文案含配置键，不写号码 |
| 日志脱敏 | 无密码/token |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码原样粘贴。未跑 live GWT-18.1 Worker（交 sre）。

TDD 红（idle 仍 120、无离线键、无启用闸）：

```
$ uv run pytest -x -q backend/tests/test_scrapy_idle_autoclose.py backend/tests/test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects backend/tests/test_saas_byok.py::test_tenant_isolated_keys_and_metering backend/tests/test_webhook_secret_guard.py::test_enablement_without_duty_contact_refuses_startup
F
=================================== FAILURES ===================================
_____________ test_idle_close_seconds_not_probe_lock_and_under_120 _____________
>       assert idle < 120
E       assert 120 < 120
backend/tests/test_scrapy_idle_autoclose.py:24: AssertionError
1 failed in 1.34s
exit: 1
```

```
$ uv run pytest -q backend/tests/test_scrapy_idle_autoclose.py::test_worker_offline_window_is_120_not_idle_close backend/tests/test_scrapy_idle_autoclose.py::test_idle_close_plus_crawl_budget_fits_120s backend/tests/test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects backend/tests/test_saas_byok.py::test_tenant_isolated_keys_and_metering backend/tests/test_webhook_secret_guard.py::test_enablement_without_duty_contact_refuses_startup
FF..F                                                                    [100%]
>       assert offline == 120
E       assert 0 == 120
>       assert idle + _CRAWL_BUDGET_SECONDS < _WAIT_BUDGET_SECONDS
E       assert (120 + 5) < 120
E       ImportError: cannot import name '_validate_enablement_duty_contact'
3 failed, 2 passed in 1.61s
exit: 1
```

（wiring / byok 在去掉 `or True` 后已绿：既有 Then 本成立，空断言只是没验。）

绿（产品改完）：

```
$ uv run pytest -q backend/tests/test_scrapy_idle_autoclose.py backend/tests/test_saas_wiring.py backend/tests/test_saas_byok.py backend/tests/test_webhook_secret_guard.py
.......................                                                  [100%]
23 passed in 2.50s
exit: 0

$ uv run ruff check backend/services/spider_worker_gate.py backend/app/__init__.py backend/tests/test_scrapy_idle_autoclose.py backend/tests/test_saas_wiring.py backend/tests/test_saas_byok.py backend/tests/test_webhook_secret_guard.py scrapy/settings.py scrapy/extensions/__init__.py
All checks passed!
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-18.1 结构：idle 足够小，能在 120s 等待预算内收尾 | `test_idle_close_seconds_not_probe_lock_and_under_120` / `test_idle_close_plus_crawl_budget_fits_120s` | ✅ 配置+预算；live Worker 交 sre |
| GWT-18.4 标注窗仍 120s | `test_worker_offline_window_is_120_not_idle_close` / `test_worker_offline_after_submit_visible_within_120s` | ✅ |
| 入队超并发 Then | `test_enqueue_carries_tenant_and_quota_rejects` | ✅ 无 `or True` |
| BYOK 租户隔离 Then | `test_tenant_isolated_keys_and_metering` | ✅ 括号化，非永真 |
| 启用闸（非六问） | `test_enablement_without_duty_contact_refuses_startup` 等 | ✅ 空 contact + enabled 拒绝 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | — | ➖ N/A（无新写） |
| 并发写 | — | ➖ N/A（无条件更新） |
| 外部依赖失败 | — | ➖ N/A（无新外部调用；live 18.1 不在本帽） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| GWT-18.1 等待预算 | idle+5s < 120 | idle 默认 30，35 < 120 | 配置单测，非 live crawl |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/sre` | 请跑 live GWT-18.1 Worker（example + httpbin.org/get）。IdleAutoClose=30s，不要再用 120s idle。18.4 标注仍 120s。 |
| `/qa` | 两口钟已分家；`test_scrapy_idle_autoclose.py` 禁止 `assert idle == 120`。 |
| `/ops` | `LLM.ENABLED` 或 `POWER_MARKET.ENABLED` 打开前必须填 `OPS.DUTY_CONTACT`。未填则启动拒绝。不代填号码；Q-OPS-DUTY 仍开放。 |
| `/architect` | 无契约歧义。未改 GWT。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（touched tests 23 passed）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口；阈值走配置（30 / 120 / 21600 探针锁注释）
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新 N/A
- [x] 外部依赖 N/A
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 未改 spec GWT；未答六问；未施工 Wave 2/3
