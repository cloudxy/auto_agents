# 实现证据 · T-42 queue_depth 告警接通（FR-105）

> 票：contract §11 T-42｜FR 锚点：FR-105（GWT-105.1/105.3/105.4）｜db-spec §16.6｜角色：/backend｜日期：2026-09-11

## 0. 状态

- [x] 已实现，自测全绿（定向 + 全量 + arch + ruff）
- 触发链：**调度器 tick（`SpiderScheduler._tick_once`，持分布式锁）→ `AlertService.evaluate_queue_depth()` → `AlertRuleRepository.list_queue_depth_rules()`（rule_type='queue_depth' AND enabled AND deleted_at IS NULL，全租户）→ 逐规则：静默窗（`last_triggered_at`）→ `SpiderTaskRepository.count_pending_by_tenant(rule.tenant_id)`（评估口径=规则所属租户排队任务数，architect 钉）→ 超阈值 → `UserRepository.get_active_id_by_username_in_tenant`（created_by 用户名→同租户在册 users.id）→ `NotifyService.notify_text`（已配置渠道）+ `notifications` 命中行 + `last_triggered_at` 推进（同事务 commit）**。`SCHEDULER.QUEUE_DEPTH_WARN` 配置日志路径已退役（代码 + settings.yml 键删除），规则行评估是 queue_depth 唯一输出口径。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| queue_depth 规则周期读（P-A04） | Repository | `backend/repositories/alert_rule_repository.py` | `list_queue_depth_rules()`；调度器平台态（无租户作用域）全租户读 |
| 租户排队深度（评估口径） | Repository | `backend/repositories/spider_task_repository.py` | `count_pending_by_tenant(tenant_id)`：status='pending' AND deleted_at IS NULL；ix_spider_tasks_tenant_status_priority 等值承接 |
| 创建者→users.id 解析（QA-06） | Repository | `backend/repositories/user_repository.py` | `get_active_id_by_username_in_tenant(tenant_id, username)`；同租户在册行（deleted_at IS NULL） |
| 业务规则（阈值命中/静默窗/命中落库/失败面） | Service | `backend/services/alert_service.py` | `evaluate_queue_depth()` + `_trigger_queue_depth_rule()`；命中→notify_text + notifications 行 + last_triggered_at（同事务） |
| 调度器周期接线（每 tick，持锁） | Service（后台循环） | `backend/services/schedule_service.py` | `_tick_once` 内 `_evaluate_queue_depth(session)`（在 due 扫描前，不依赖到期计划）；`_check_queue_depth` 删除 |
| 命中载体（notifications 行） | Service 写 + 既有 ORM | `platform_core/models/notification.py`（零改动） | type='alert'，resource_type='alert_rule'，resource_id=规则 id，user_id=创建者，content 含深度数字 |
| 前端字段说明（最小文案） | UI | `frontend/admin/src/components/spider/AlertRulesTab.tsx` | queue_depth 选项 label「队列堆积（本企业排队任务数）」+ 阈值 tooltip 补队列堆积口径 |

**分层依赖核对**：☑ Router 未 import ORM（本票零 Router 改动）☑ Service 未返回 ORM 对象（返回 int/写 Notification 经 session.add）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/repositories/alert_rule_repository.py` | 修改 | +`list_queue_depth_rules()`（P-A04 口径显式 deleted_at IS NULL） |
| `backend/repositories/spider_task_repository.py` | 修改 | +`count_pending_by_tenant()` |
| `backend/repositories/user_repository.py` | 修改 | +`get_active_id_by_username_in_tenant()` |
| `backend/services/alert_service.py` | 修改 | +`evaluate_queue_depth()` / `_trigger_queue_depth_rule()`；__init__ 组装 tasks/users 仓储；evaluate() 的 queue_depth skip 注释指向新路径（行为不变：任务终态评估仍不处理 queue_depth） |
| `backend/services/schedule_service.py` | 修改 | `_tick_once` 接线 + `_evaluate_queue_depth()`；删 `_check_queue_depth` 及 `_fire` 调用；退役 `task_queue`/`TASK_QUEUE_PRIORITIES` import；模块/类 docstring 同步 |
| `backend/tests/test_alert_queue_depth.py` | 新增 | 10 测试（GWT-105.1/105.3、静默窗、创建者、失败面、调度接线、退役钉） |
| `backend/tests/test_spider_task_flow.py` | 修改 | 两个既有 `_tick_once` 测试补 `AlertService` 桩（tick 内联评估后 mock session 不可 await；钉改写先例 T-37/T-39/T-41） |
| `config/default/settings.yml` | 修改 | 删 `SCHEDULER.QUEUE_DEPTH_WARN: 50`（读方已退役，配置即代码不留死键；grep 全仓无其他读者） |
| `frontend/admin/src/components/spider/AlertRulesTab.tsx` | 修改 | queue_depth 选项 label + 阈值 tooltip 两处文案（票允许的最小文案改动） |

**与票里「会改哪些文件」一致**：☐ 是（☑：调度器/告警服务/通知复用/命中记录/前端文案均在票面清单内）
**未触碰「不许改的文件」**：☑ 确认（未动其他三类规则的评估路径与既有测试断言；未动 GWT/schema）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| notifications 命中行 + alert_rules.last_triggered_at | 是（同一 commit） | 命中记录与静默窗判据必须成对出现：行落了而时刻没推进会重复发送；时刻推进了而行没落会「缺命中记录」——不可半写 |
| 渠道发送（notify_text，外部调用） | 否（commit 前、无 pending 写状态） | 对齐既有 evaluate() 顺序（先 _send_alert 后 commit）；NotifyService 契约=逐渠道吞异常，失败不挡命中记录（票：通知失败不挡调度，logger 记） |

**事务提交后的操作失败怎么办**：单规则失败（含 DB 异常）→ 外层 try 吞掉记 warning，本轮剩余规则跳过，下一 tick 重试（静默窗尚未推进 → 仍会触发，不丢告警）。P-BE-01：commit 后不再读 ORM 属性（触发日志字段全部在 commit 前取值）。

### 幂等 / 静默窗

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键：rule_id + last_triggered_at（既有列，零 DDL，db-spec §16.6） |
| 保证方式 | 纯读比较 `now < last_triggered_at + window_minutes`（`_is_in_silence` 复用）；窗口内重复命中不发送不落行 |
| 重复请求返回 | 无重复发送（深度持续超阈值时每窗至多一次） |

☐ 未使用「先查后插」（无插入竞争面：单写方=持锁调度器）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 多实例调度器同 tick 双评估 | 既有 `distributed_lock`（SCHEDULER_LOCK_KEY + renewal + lost 早退，m-5） | 锁不可得 → 本轮直接返回（既有行为，未改） |
| 命中行写竞争 | 单写方（仅持锁调度器写命中行；租户 API 无该写面） | N/A |

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| NotifyService 渠道（webhook/email/dingtalk/wechat_work） | 既有 NOTIFY.TIMEOUT_SECONDS（默认 10s） | 无（告警低频，静默窗天然节流） | 逐渠道吞异常记日志，不挡命中记录与调度循环 | 是（重复文本通知，静默窗限频） |

## 4. ORM 与 DBML 对齐

- **零 DDL**（db-spec §16.6 确认）：复用 `alert_rules.last_triggered_at` / `window_minutes` / `created_by`（既有列）与 `notifications` 既有表；无迁移、无新列。
- ☑ 未自行加字段/改类型（Notification 行仅填既有列：tenant_id/user_id/type/title/content/resource_type/resource_id）

结构核对输出（口径=模型列集对拍；本票无 DDL，MYSQL_FIDELITY 真库验证留 qa——本 shell 无 root 口令，既有边界）：

```
$ grep -c "Column" platform_core/models/alert_rule.py platform_core/models/notification.py
alert_rule.py 列集未动（id/name/spider_name/rule_type/threshold/window_minutes/
severity/channels/enabled/last_triggered_at/created_at + mixins）；notification.py 未动
```

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 触发时 `logger.info("queue_depth 告警已触发: rule_id/tenant_id/depth/threshold/recipient")`（关键判定字段全带） |
| 跳过路径 | 创建者不可解析 → `logger.warning`（rule_id/tenant_id/created_by/depth）；评估异常 → `logger.warning` |
| 错误日志上下文 | 含规则 ID、租户、深度、阈值（无用户敏感字段） |
| R10 | `backend/services/*.py` 公开方法入口 logger 核查通过（arch.sh R10 ✓；新方法在异常/触发路径均有 logger） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token（通知文案仅含规则名/深度/阈值）

## 6. 自测证据

> 命令与退出码原样粘贴。红=实现前（TDD，包 companion tdd：先红后绿）。

```
$ uv run pytest -q backend/tests/test_alert_queue_depth.py   # 红（实现前）
FFFFFFFFFF                                                               [100%]
10 failed in 2.19s
exit: 1

$ uv run pytest -q backend/tests/test_alert_queue_depth.py backend/tests/test_alert_service.py backend/tests/test_spider_task_flow.py   # 绿（定向）
.......................................................                 [100%]
55 passed in 2.32s
exit: 0

$ uv run pytest -x -q backend/tests   # 全量（基线 1528/38 → +10）
1538 passed, 38 skipped, 7 warnings in 241.35s (0:04:01)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-105.1 超阈值→通知+命中记录+静默窗 | `test_queue_depth_over_threshold_triggers_notify_and_hit_row`（通知 kwargs + notifications 行字段 + last_triggered_at + 同事务 commit + 按租户查深度）；`test_queue_depth_silence_window_suppresses_repeat` / `test_queue_depth_silence_window_expired_triggers_again`；`test_queue_depth_under_threshold_no_trigger` | ✅ |
| GWT-105.3 四类型零死规则（可失败验收） | `test_all_four_rule_types_have_trigger_path`（四类型命中条件成立时各发一次通知；存在无路径类型即 assert 失败）+ 既有 `test_evaluate_consecutive_failures_triggers` / `test_evaluate_task_timeout_triggers_without_db_query` | ✅ |
| GWT-105.4 越权（既有核对） | 本票零新增 API 写面；规则 CRUD 维持 `require_admin` + R13 租户注入（跨租户同形 404）；命中记录写面仅调度器（无租户入口）；既有 `test_b1b_alert_rules_coverage.py`（operator 403 / anonymous 401 / admin ok）全量套件内通过 | ✅（既有） |
| db-spec §16.6 创建者口径 | `test_queue_depth_creator_unresolvable_skips_entirely`（解析不出→不落行、不发送、不推进时刻、不改投） | ✅ |
| 调度接线（每 tick、失败不挡调度、旧路径退役） | `test_tick_once_invokes_queue_depth_evaluation_every_tick`（无到期计划也评估）；`test_tick_once_alert_failure_does_not_block_scheduling`；`test_queue_depth_config_log_path_retired`（`_check_queue_depth` 不存在钉） | ✅ |
| 既有三类规则零回退 | `test_alert_service.py` 5 测试 + 全量 1538/0 失败 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（写面仅「命中行+时刻」单 commit 对，无跨规则批次事务；失败即整对不落，下一 tick 重试——不存在半写态） |
| 幂等 | `test_queue_depth_silence_window_suppresses_repeat` | ✅ |
| 并发写 | `test_tick_once_enables_renewal_and_exits_when_lock_lost`（既有，锁互斥防多实例双发；命中写面单写方） | ✅（既有） |
| 外部依赖失败 | `test_queue_depth_eval_exception_swallowed` + `test_tick_once_alert_failure_does_not_block_scheduling`（NotifyService 逐渠道吞异常为该服务既有契约，`test_spider_notify_channels.py` 覆盖） | ✅ |

## 7. NFR 验证

票无 NFR 行。性能注：每 tick 一次规则读（≤租户数行，P-A04）+ 每规则一次索引等值 COUNT + 命中时一次用户解析；静默窗内规则仅付前两查。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① mock 面：Repository/NotifyService 全桩（fake_async_session），命中行落库字段为断言非真库写——真库 INSERT（含 user_id FK、tenant 断言在平台态不适用）需 qa 真库复验；② 前端两处文案改动未经 eslint/build（本 shell 无 node_modules），纯字符串字面量，零类型影响；③ 调度器每 tick 评估：真环境验证可用 enabled=1 + threshold=0 + 1 条 pending 任务快速触发 |
| `/frontend` | 无契约差异。文案改动：queue_depth 选项 label 与阈值 tooltip（GWT 口径=本企业排队任务数） |
| `/architect` | 无新歧义。「创建者解析不出→不发送不改投」按 db-spec §16.6 原文执行（发送与命中记录作为成对触发结果）；若业务要「解析不出仍发渠道」，归 /pm |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（1538 passed / 38 skipped / 0 failed；arch 0 违规；ruff 0）
- [x] 契约落位表已核对，分层无违规（R7/R10/R11/R12/R13 ✓）
- [x] ORM 与 DBML 一致，未自行加字段（零 DDL）
- [x] 无硬编码连接串/密钥/端口/阈值（阈值来自规则行；退役配置键已删）
- [x] async 上下文无同步阻塞调用（R11 ✓；通知走 httpx/aiosmtplib 异步栈）
- [x] 无 `except: pass`（吞异常均带 logger.warning，noqa BLE001 显式标注）
- [x] 日志已脱敏
- [x] 事务里无外部调用（渠道发送在 add/commit 之前，对齐既有 evaluate 顺序）
- [x] 幂等未用「先查后插」（静默窗纯读比较）
- [x] 条件更新的 `rows == 0` 已处理（N/A：无条件更新语句）
- [x] 外部依赖四件套齐全（超时=既有 TIMEOUT_SECONDS / 重试=无（静默窗节流）/ 降级=吞异常记日志 / 幂等前提=重复文本可容忍）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（无）
