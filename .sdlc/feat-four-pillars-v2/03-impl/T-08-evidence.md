# 实现证据 · T-08 候选不计配额、不进我的结果/导出/出站

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-08.md`｜FR 锚点：FR-11｜角色：/backend｜日期：2026-09-08
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `skills.py` GET/POST `/candidates*`；`spiders/results.py` GET `/results` | 候选审核 `require_platform_admin_or_404`（404 同形）；数据中心空窗 message=`还没有采集结果` |
| 字段校验（类型/范围/枚举） | Schema / Query | 未改 page/page_size | 本票不改 source 枚举、不迁表 |
| 跨字段参数约束 | Schema | 未改 | |
| 权限判定（数据范围） | Router + Service | 候选仅超管；租户经办/公司管理员 404 | GWT-11.3 |
| 业务规则/状态流转 | Service | 配额/列表/导出/出站 `source <> marketplace`（NULL source 仍算自有） | 候选仍住 `spider_results` |
| 数据读写 | Repository | `owned_source_clause`；`list_pending_marketplace_candidates` SQL LIMIT/OFFSET | 禁止全表进内存再切片 |
| 错误码映射 | 统一异常处理器 | 非超管 `HTTP_404`；配额仍 `QuotaExceededException` | Router 无 try/except |
| 幂等 | N/A | | 只读谓词 + 既有审核写 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 返回 dict/schema ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/repositories/spider_result_repository.py` | 修改 | `owned_source_clause` / `pending_marketplace_clause`；配额 COUNT；候选 SQL 分页；列表/出站默认排除 marketplace |
| `backend/services/quota_service.py` | 修改 | `check_result_storage` + `usage_overview` 走 `count_owned_by_tenant`；缓存键 `results_owned:` |
| `backend/services/spider_query_service.py` | 修改 | 我的结果 / 数据中心 / 出站透传 `exclude_source=marketplace`；`EMPTY_DATACENTER_COPY` |
| `backend/services/skill_service.py` | 修改 | `list_candidates` 改仓储 SQL 分页，不再 `all()` 后内存切片 |
| `backend/app/api/v1/skills.py` | 修改 | 候选 list/approve/reject → `require_platform_admin_or_404` |
| `backend/app/api/v1/spiders/results.py` | 修改 | 数据中心 total=0 时信封 message=`还没有采集结果` |
| `backend/tests/test_skill_candidates.py` | 修改 | 11.1 / 11.3；超管 HTTP 分页；既有审核改 `platform_admin_client` |
| `backend/tests/test_spider_datacenter_crud.py` | 修改 | 11.2 空列表；出站/我的结果谓词；候选 SQL LIMIT/OFFSET |
| `backend/services/auth_service.py` | 修改 | 仅 R10：`emit_login_failed` 签名一行（闸门机械） |
| `backend/services/product_event_service.py` | 修改 | 仅 R10：`emit_product_event` 签名一行（闸门机械，无 T-12 行为） |
| `backend/services/spider_worker_gate.py` | 修改 | 仅 R10：`annotate_task_worker_status` 签名一行（闸门机械，无 T-13 行为） |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-08.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 是（票未列路径；实现落在读模型谓词 + 超管候选 SQL 分页）

**未触碰「不许改的文件」**：☑ 确认（未迁候选出 `spider_results`；未放宽 `tenant_id` 可空；未代选六问；未改 GWT；未实现 T-10 出站钥匙绑定；未实现 T-12 事件语义；未实现 T-13 worker loop；未改 `App.tsx`）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 配额 COUNT / 列表 / 出站 | 否 | 只读 |
| 候选审核 approve/reject | 是（既有） | 本票只改守卫，不改提交边界 |

**事务提交后的操作失败怎么办**：N/A（本票无新写路径）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（读模型谓词） |
| 保证方式 | SQL `source <> marketplace` 或 `source = marketplace` + pending |
| 重复请求返回 | 同一窗口同一批只读结果 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 配额 COUNT | Redis TTL 缓存 + 故障回源 | 未超限放行；超限 `QuotaExceededException` |
| 候选空页 | SQL COUNT + OFFSET | total=0 / 空 items，不拉全表 |

☑ 本票无新的条件更新行数分支

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 配额计数缓存 | 既有 get_async_redis | 无 | 异常回源 DB COUNT | 是（COUNT 可重入） |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM 字段/类型/可空性/默认值/索引/唯一约束/外键。候选仍住结果表；`tenant_id` 禁止 NULL。

结构核对输出：

```
$ 本票无迁移。谓词加在 SELECT，不改 spider_results DDL。
未自行加字段/改类型。
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_candidates` / `check_result_storage` 记 page 或 tenant |
| trace_id | 既有中间件 |
| 错误日志上下文 | 非超管候选走 `require_platform_admin_or_404` 留痕 `authz.denied` |
| 慢操作耗时 | 候选分页 LIMIT/OFFSET，避免全表进 Python |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ uv run pytest -x -q backend/tests/test_skill_candidates.py backend/tests/test_spider_datacenter_crud.py
.............................................                            [100%]
45 passed, 2 warnings in 2.73s
pytest_exit:0
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
arch_exit:0
exit: 0
```

T-02 导出仍绿（非本票闸，回归）：

```
$ uv run pytest -x -q backend/tests/test_spider_task_flow.py backend/tests/test_spider_result_repository.py
47 passed in 2.28s
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-11.1 正常 | `test_storage_quota_ignores_marketplace_at_ninety_percent` | ✅ |
| GWT-11.2 空态 | `test_search_results_only_candidates_is_empty_copy`；`test_datacenter_empty_when_only_marketplace` | ✅ |
| GWT-11.3 越权 | `test_tenant_operator_candidates_same_as_missing`；`test_tenant_admin_candidates_same_as_missing` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（本票无多步写） |
| 幂等 | 同一谓词重复读 | ➖ N/A（只读；审核写仍走既有 approve/reject） |
| 并发写 | — | ➖ N/A（无新条件更新） |
| 外部依赖失败 | 配额 Redis 故障回源 COUNT（既有 `_cached_count`；11.1 测试 monkeypatch Redis 抛错走 SQL） | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字。候选列表改为 SQL LIMIT/OFFSET，避免「先拉全表再内存滤」。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 候选审核仅超管 404 同形（非 403）。数据中心空窗信封 `message=还没有采集结果`、`items=[]`。配额 COUNT 不计 marketplace；Redis 键已改为 `results_owned:{tenant_id}`（旧 `results:` 缓存 60s 内可能仍含候选，过期后自愈）。出站拉数已排除候选，但 T-10 钥匙绑定未做。 |
| `/frontend` | 数据中心 GET `/spiders/results` 空窗 message 已是「还没有采集结果」；表格 `emptyText` 若仍走 antd 默认「No data」需消费该 message。候选 Tab 已按 `isPlatformAdmin` 隐藏；直打 API 为 404。 |
| `/architect` | 无新错误码。谓词统一 `source <> marketplace`（NULL 保留）。T-10 可接 `query_public_results` / `query_by_spider(exclude_source=marketplace)`。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（N/A）
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— Redis 计数既有降级
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done

## 缓存隔离

回归：`QuotaService._cached_count` 写 Redis `quota:count:{key}` TTL 60s。工作区 Redis 残留 `quota:count:active_tasks:1` 时，SQLite 新库 `tenant_id=1` 会命中旧计数，`test_task_concurrency_over_limit_rejected` 见 `active=1/2` DID NOT RAISE（solo 亦复现）。

处理：`backend/tests/conftest.py` autouse `_clear_quota_count_cache` 每测前 SCAN+DEL `quota:count:*`，COUNT 回源 DB。不关生产缓存（短窗滞后仍按原注释）。不走 `redis_client()`/`init_all()`（会拉真 MySQL，打穿 TestLlmChat）。T-08 marketplace 仍 monkeypatch Redis 抛错走 SQL；T-13 `_workers_online_unless_offline_node` 未改。

fail-closed：1 running + 1 pending、limit 2 → `QuotaExceededException`。

```
$ uv run pytest -x -q backend/tests/test_saas_quota.py::test_task_concurrency_over_limit_rejected
.                                                                        [100%]
1 passed in 1.14s
pytest_exit:0
exit: 0

$ uv run pytest -x -q backend/tests/test_saas_quota.py backend/tests/test_saas_wiring.py
.......................                                                  [100%]
23 passed in 3.05s
pytest_exit:0
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
arch_exit:0
exit: 0
```

T-08 marketplace / T-13 工人闸夹具回归（非本闸成员）：

```
$ uv run pytest -x -q backend/tests/test_skill_candidates.py::test_storage_quota_ignores_marketplace_at_ninety_percent backend/tests/test_spider_worker_offline.py
...                                                                      [100%]
3 passed in 1.39s
pytest_exit:0
exit: 0
```

