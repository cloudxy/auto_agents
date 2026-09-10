# 实现证据 · T-07 全部产任务路径带企业；回流归属=入队企业

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-07.md`｜FR 锚点：FR-09 / FR-10｜角色：/backend｜日期：2026-09-08
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `spiders/tasks.py` `/run`；`templates.py` create/run；`schedules.py` POST；`ai.py` create_plan | 超管/无企业 → 400，不入队 |
| 字段校验（类型/范围/枚举） | Schema | 未改 | 本票不改请求体 |
| 跨字段参数约束 | Schema | 未改 | |
| 权限判定（数据范围） | Router + Service | `deps.task_actor_tenant_id`；`require_enqueue_tenant` | 超管无企业空间 → None；无 tenant 不入队 |
| 业务规则/状态流转 | Service | enqueue / 调度 fire / 模板 run / AI 试采；ingest 无主死信 | 归属=入队 `tenant_id`；工人不决定 |
| 数据读写 | Repository | `repo.create(..., tenant_id=owner_id)` | 显式写入；禁止靠 Mixin 回填 |
| 错误码映射 | 统一异常处理器 | `BusinessException` 400「没有企业身份，无法入队」；跨模板 `NotFoundException`「任务模板」；猜任务 `NotFoundException`「爬虫任务」 | Router 无 try/except |
| 幂等 | N/A | | 每次提交新任务；无主回流不写结果 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 返回 schema/DTO ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/spider_common.py` | 修改 | `require_enqueue_tenant`；无企业不入队 |
| `backend/app/api/deps.py` | 修改 | `task_actor_tenant_id`（超管 → None） |
| `backend/services/spider_task_service.py` | 修改 | enqueue 强制 tenant；显式落库；队列消息不含 tenant |
| `backend/services/spider_service.py` | 修改 | 门面 enqueue 转发 `tenant_id` |
| `backend/services/schedule_service.py` | 修改 | create 写计划 tenant；fire 传 `schedule.tenant_id` |
| `backend/services/spider_registry_service.py` | 修改 | 模板 create/run 显式 tenant；跨企业模板 404 |
| `backend/services/ai_planner/orchestrator.py` | 修改 | create_plan / 试采 enqueue 传计划 tenant |
| `backend/app/api/v1/spiders/tasks.py` | 修改 | `/run` 用 `task_actor_tenant_id` |
| `backend/app/api/v1/spiders/templates.py` | 修改 | create/run 传租户 |
| `backend/app/api/v1/spiders/schedules.py` | 修改 | create 传租户 |
| `backend/app/api/v1/ai.py` | 修改 | create_plan 传租户 |
| `backend/tasks/consumer.py` | 修改 | 结果 tenant=任务行；无主死信+任务失败；不取工人消息 tenant |
| `backend/tests/test_saas_wiring.py` | 修改 | 09.1 / 09.3 / 09.4 / 10.1 / 10.2 |
| `backend/tests/test_task_consumer.py` | 修改 | 10.1/10.2 归属；10.4 无主不写 |
| `backend/tests/test_spider_task_flow.py` | 修改 | 09.2 定时归属；10.3 猜编号；T-02 导出仍绿 |
| `backend/tests/test_t10_api_coverage.py` 等 | 修改 | 入队单测补 `tenant_id`；HTTP 写面走企业 JWT |

**与票里「会改哪些文件」一致**：☑ 是（另：HTTP 写面夹具须带企业，否则 `/run` 与模板/调度 create 会 400）

**未触碰「不许改的文件」**：☑ 确认（未改 Scrapy 管道协议、未迁候选、未改 `App.tsx` / `menuConfig.tsx`、未改 T-06 过期登录、未改 T-02 导出上限语义、未改 `Usage.tsx` / 配额谓词、未改 official、未代选六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 任务行 INSERT + commit | 是 | 入队落库 |
| Redis rpush | 否 | 既有：commit 后投递；失败置 failed |
| 结果 bulk insert + result_count | 是 | ingest 单次 commit |
| 无主死信 rpush / 任务 failed | 否 | 不写入结果后再留档；不得塞给别的企业 |

**事务提交后的操作失败怎么办**：投递 Redis 失败 → 任务 failed（既有）。无主死信写失败仅记日志，仍不落「我的结果」。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（每次入队新任务） |
| 保证方式 | 无主回流不 INSERT 结果 |
| 重复请求返回 | 再提交再入队（既有） |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 入队并发配额 | `check_task_concurrency` | 超限 `QUOTA_EXCEEDED`（既有） |
| 无主回流 | 跳过 `add_all` | 死信 + `_fail_task` |

☑ 本票无新的条件更新行数分支

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 队列（既有） | 既有连接 | 投递失败任务 failed | 槽位检查失败放行（既有） | 否 |
| 死信队列 | 既有 | 无 | 写失败记日志，仍不落结果 | 否 |

## 4. ORM 与 DBML 对齐

☑ 未改列类型/可空性/索引/唯一约束/外键。PIT-4：017 真库 NOT NULL；调用方显式传 `tenant_id`，不假设 Mixin 自动填。

结构核对输出：

```
$ 本票无 DDL / 无 autogenerate
（入队/模板/调度/计划/结果均写已有 tenant_id 列）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `require_enqueue_tenant` 记 tenant；enqueue 记 spider；无主回流 warning 记 task_id |
| trace_id | 既有中间件 |
| 错误日志上下文 | 无主 `_reject_reason`；死信写入失败记 error |
| 慢操作耗时 | 未新增外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ uv run pytest -x -q backend/tests/test_saas_wiring.py backend/tests/test_task_consumer.py
.........................                                                [100%]
25 passed in 1.73s
exit: 0

$ uv run pytest -x -q backend/tests/test_spider_task_flow.py
......................................                                   [100%]
38 passed in 1.06s
exit: 0

$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 3 条边界）
======================================
✓ R1: 硬编码连接串
✓ R2: 明文 password
✓ R3: scrapy → backend 反向依赖
✓ R4: scrapy 使用 SQLAlchemy
✓ R5: DOWNLOAD_DELAY 已配置
✓ R6: USER_AGENT 配置存在
✓ R7: API 层 import models
✓ R8: models 反向 import schemas
✓ R9: 无循环 import
✓ R10: service 方法入口缺 logger
✓ R11: backend 同步 redis_client() 直调（阻塞事件循环）
✓ R12: spider_service 门面白名单外 import（应直接依赖子 Service）
✓ R13: 租户过滤收口（安装点/裸语句/豁免清单同步）

--- 核心代码边界 ---
✓ B1: platform_core → backend/scrapy 反向依赖
✓ B2: backend → scrapy 直接依赖
✓ B3: config → 业务模块反向依赖

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 3 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-09.1 经办已登录且企业有效，提交采集 → 任务出现在本企业任务列表 | `test_logged_in_tenant_submit_appears_in_own_list`；`test_enqueue_lists_in_own_tenant_not_other` | ✅ |
| GWT-09.2 本企业一条定时规则到期触发 → 新任务仍属于该企业 | `test_fire_enqueues_with_schedule_tenant` | ✅ |
| GWT-09.3 企业 A 经办用企业 B 的模板 → 拒绝；B 不出现新任务 | `test_template_other_tenant_rejected_no_task_for_owner` | ✅ |
| GWT-09.4 平台超管无企业空间走租户任务提交 → 拒绝入队，不产生无主任务 | `test_platform_admin_run_rejects_no_ownerless_task`；`test_enqueue_without_tenant_does_not_create` | ✅ |
| GWT-10.1 A 的条 A 看得到；B 看不到 | `test_results_visible_to_owner_hidden_from_other` | ✅ |
| GWT-10.2 向导试采出条在 A | `test_wizard_test_crawl_result_stays_in_enqueue_tenant`；`test_flush_result_tenant_is_task_owner_not_message` | ✅ |
| GWT-10.3 B 猜 A 的任务编号 → 与「没有这个任务」同形 | `test_list_results_missing_task_same_as_no_such_task` | ✅ |
| GWT-10.4 回流找不到入队企业 → 不写「我的结果」；任务失败/死信 | `test_flush_orphan_not_written_dead_letter_and_fail_task`；`test_flush_missing_task_not_written`；`test_ingest_single_orphan_skips_create` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 入队拒绝发生在 `repo.create` 前（`create.assert_not_called`） | ✅ |
| 幂等 | 无主回流不 INSERT；禁止 NULL 当平台入站成功 | ✅ |
| 并发写 | ➖ N/A（本票无新状态机条件更新） | ➖ |
| 外部依赖失败 | 死信 rpush 失败记日志，仍不落结果（既有 BLE 口径） | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字。工人协议未改（StorePipeline 仍 `{task_id, spider_name, item_type, item, fetched_at}`）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 超管走 `/run` / 模板 run / 调度 create / AI create 应 400「没有企业身份，无法入队」。跨企业模板 404「任务模板不存在」。猜任务 404「爬虫任务不存在」。无主回流查死信 `spider:item_dead` 与任务 failed。真库 017 NOT NULL：漏传 tenant 不能靠 SQLite create_all 的可空 Mixin。 |
| `/frontend` | 未改 admin 壳。无企业空间提交采集应展示入队拒绝句，不要当成功。 |
| `/architect` | 无新错误码；沿用 BUSINESS_ERROR / NOT_FOUND。队列任务消息去掉 `tenant_id`（工人不决定归属；与 update LREM 对齐）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用（死信在 commit 后）
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（本票无新条件更新）
- [x] 外部依赖四件套齐全或标既有口径
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
