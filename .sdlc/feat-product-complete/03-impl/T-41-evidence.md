# 实现证据 · T-41 方案视图纯净（demo/收割器/flow 伪爬虫/源码文件清单不混入）

> 票：T-41（contract §11；spec FR-104 GWT-104.1..104.4）｜角色：/backend｜lane：api｜日期：2026-09-11
> QA-40 口径遵守：未建任何「来源分组展示」形态；GWT-104.2 唯一 Then = 方案视图与治理目录均无 demo/内部项独立入口。

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GWT-104.1 registry 清单滤内部项（DB 行 + yml 兜底两路） | Service | `backend/services/spider_registry_service.py` `registry()` | demo（example/openweather）/收割器（skill_harvester）/flow 引擎（flow_generic）不下发；AI flow 定义保留 |
| GWT-104.1/104.2 源码清单不并入（files 收敛为「已登记且非内部」） | Service | 同上 `spider_files()` | 未登记 .py（含 base.py/stray）一律不列出；DB 读失败收敛为空（宁空勿泄） |
| 内部项清单（单一事实源） | 常量 | `backend/services/spider_common.py` `_INTERNAL_SPIDERS` | frozenset，registry/files 共用；防漂移有冻结断言测试 |
| GWT-104.2 治理目录无独立入口 | 核对+断言 | `backend/app/api/v1/capabilities.py`（零改动） | 目录本就只有资产；测试断言 asset_type ⊆ 资产集 + 路由表无 spider 入口 |
| GWT-104.2 尾句「不删爬虫/文件」 | 测试断言 | `test_t41_plan_view_purity.py` | 读视图后 DB 行数不变、tmp 目录文件仍在 |
| GWT-104.3 空态可达 | Service | `registry()` | 查询成功而可见方案为 0 → 空清单（**不再回退 yml 种子充数**，对齐 GWT-103.4「不是把 demo 填回去充数」） |
| GWT-104.4 只读同口径 | 数据层 | 同 registry/files | 过滤在 Service 数据面，与角色无关；viewer 断言同集 |
| 端点文档同步 | Router 注释 | `backend/app/api/v1/spiders/definitions.py` `/files` docstring | 路径/状态码/信封零变化 |

**分层依赖核对**：☒ Router 未 import ORM（未新增 import）☒ Service 未返回 ORM ☒ Repository 未调 Service ☒ ORM 与 Schema 互不 import —— 本次改动全部落在 Service 读面 + 共享常量，无层级新增依赖。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/spider_common.py` | 修改 | 新增 `_INTERNAL_SPIDERS` frozenset（+`__all__`），注释写明「只滤视图」边界 |
| `backend/services/spider_registry_service.py` | 修改 | registry()：DB 路径滤内部项 + 兜底种子同滤 + 成功空表不回退；spider_files()：收敛为已登记非内部、DB 失败收敛为空 |
| `backend/app/api/v1/spiders/definitions.py` | 修改 | `/files` docstring 同步新口径（协议零变化） |
| `backend/tests/test_t41_plan_view_purity.py` | 新增 | 9 测：GWT-104.1（纯净/兜底滤/失败收敛/清单冻结）、104.2（目录无入口/不删行不删文件）、104.3（全内部→空态）、104.4（viewer 同口径） |
| `backend/tests/test_spider_files_management.py` | 修改 | 钉改写 ×3：example 内部不列、未登记不列（原「展示未登记」钉）、DB 失败 total 2→0 |
| `backend/tests/test_spider_management.py` | 修改 | 钉改写 ×1：registry 端点改 DB 种子断言（example/openweather 不出现） |
| `backend/tests/test_spider_generic_spider.py` | 修改 | 钉改写 ×2：generic 由 DB 登记行下发；兜底种子断言 example 不在 |
| `backend/tests/test_b1c_spiders_registry_results_coverage.py` | 修改 | 钉改写 ×1：`test_spider_files_ok` 未登记 beta 不再入清单 |

**与票里「会改哪些文件」一致**：☐ 是（后端读面 + 测试；未触碰前端、未删任何爬虫文件/资产、未建分组展示形态）。
**未触碰「不许改的文件」**：☐ 确认（frontend/**、scrapy/**、config/**、DBML、迁移均零改动；治理目录代码零改动）。

## 3. 关键实现决策

### 过滤口径：显式清单常量（非定义行标记）

| 选项 | 取舍 |
|---|---|
| 定义行 `source=internal/demo` 标记 | 需迁移改种子行 source 值或加列 —— source 取值集是模型注释/DBML 记载的数据契约，变更归 /dba（本票无 dba 半），不动 |
| **显式清单常量 `_INTERNAL_SPIDERS`（已选）** | 票面明示可选口径；单一事实源，registry/files/兜底三路共用；测试冻结断言防漂移 |

### 源码清单下架方式（GWT-104.2 前半）

票给两支：端点保留但方案视图不用（需前端改动，packet 禁）；端点直接收敛（最小侵入）。**选后者**：`spider_files()` 只返回「已登记且非内部」的文件行（保留 file/size/启停关联，启停开关与再启用路径不受影响），未登记 .py 一律不列出。FileTab（T-40 已落地，零改动）合并 files ∪ registry 差集后天然纯净：无「未登记」行、无内部行，AI flow 定义经 registry 差集保留。

### 空表不再回退种子（GWT-104.3 行为收口）

原语义「查询失败**或空表**回退配置种子」会让清理完全部方案后视图被种子回填——与 GWT-103.4「不是把 demo 填回去充数」/GWT-104.3「空态句」冲突。收紧为：**查询成功 → 按滤后结果（可为空）；仅查询异常 → 回退配置种子（回退路同样滤内部项）**。全仓无空表回退钉（grep `list_enabled` 全部桩均为异常或非空列表）。

### 只滤视图（GWT-104.2 尾句）

- `spider_definitions` 行、`enabled`、软删语义零改动（HTTP 测试断言读视图后行集不变）。
- `scrapy/spiders/*.py` 文件零删除（测试断言调用后文件仍在盘）。
- 入队校验 `_ensure_spider_available` 走 DB 直查 + yml 兜底，不经 registry 读面 → AI 试采（orchestrator 直入队 `flow_generic`）不受影响。

### 事务/幂等/并发

| 项 | 结论 |
|---|---|
| 事务 | N/A：纯读面改动，无多步写 |
| 幂等 | N/A：无写路径 |
| 并发写 | N/A：无写路径 |
| 外部依赖失败 | DB 读失败两路均有降级：registry→回退滤后种子；files→收敛为空（宁空勿泄，`test_files_db_failure_fails_closed`） |

## 4. ORM 与 DBML 对齐

无 ORM/迁移改动（☐ 确认；本次零 SQL 层变化，`alembic` 无需跑）。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `registry()` `logger.debug`、`spider_files()` `logger.info`（R10 第一语句保持） |
| 降级日志 | DB 读失败 warning（含异常摘要，不含敏感数据）；目录缺失 warning |
| 脱敏 | ☒ 无密码 ☒ 无 token（仅爬虫名/异常消息） |

## 6. 自测证据（原样粘贴）

红（TDD，先测后实现）：

```
$ uv run pytest -x -q backend/tests/test_t41_plan_view_purity.py
    from backend.services.spider_common import _INTERNAL_SPIDERS  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   ImportError: cannot import name '_INTERNAL_SPIDERS' from 'backend.services.spider_common' (/Users/xuyun/auto_agents/backend/services/spider_common.py)
!!!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!
1 error in 0.28s
```

旧钉暴露（实现后、钉改写前，证明口径变化被钉捕捉）：

```
$ uv run pytest -q backend/tests/test_spider_files_management.py backend/tests/test_spider_management.py backend/tests/test_spider_generic_spider.py backend/tests/test_b1c_spiders_registry_results_coverage.py
FAILED backend/tests/test_spider_files_management.py::TestSpiderFiles::test_scan_joins_definition_enabled
FAILED backend/tests/test_spider_files_management.py::TestSpiderFiles::test_definition_read_failure_degrades_gracefully
FAILED backend/tests/test_spider_management.py::TestSpiderRegistryEndpoint::test_registry_returns_types_and_spiders
FAILED backend/tests/test_spider_generic_spider.py::test_registry_fallback_to_config_on_db_error
FAILED backend/tests/test_spider_generic_spider.py::test_registry_contains_custom_type_and_generic
FAILED backend/tests/test_b1c_spiders_registry_results_coverage.py::test_spider_files_ok
6 failed, 68 passed in 8.11s
```

绿（本票 + 钉改写后定向）：

```
$ uv run pytest -q backend/tests/test_t41_plan_view_purity.py backend/tests/test_spider_files_management.py backend/tests/test_spider_management.py backend/tests/test_spider_generic_spider.py backend/tests/test_b1c_spiders_registry_results_coverage.py
83 passed in 8.36s
exit:0
```

全量：

```
$ uv run pytest -x -q backend/tests
1528 passed, 38 skipped, 7 warnings in 238.08s (0:03:58)
exit:0
```

架构红线 + lint：

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit:0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-104.1 纯净（四类混入不出现，业务+flow 定义保留） | `test_plan_view_excludes_internal_and_unregistered` / `test_fallback_config_seeds_filtered_on_db_error` / `test_internal_manifest_is_frozen_contract` | ✅ |
| GWT-104.2 独立入口（方案视图+治理目录均无）+ 尾句不删 | `test_capabilities_catalog_has_no_spider_entry`（路由表+目录项双断言）/ `test_view_reads_delete_no_rows` / `test_view_filter_deletes_nothing_on_disk` | ✅ |
| GWT-104.3 空态（0 行可达，总数不被顶满） | `test_all_internal_yields_empty_view`（registry [] ∧ files [] ∧ 合并=∅） | ✅ |
| GWT-104.4 只读同口径 | `test_viewer_sees_same_filtered_view`（viewer=member 同集 + files 同滤） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯读面，无写） | |
| 幂等 | ➖ N/A（无写） | |
| 并发写 | ➖ N/A（无写） | |
| 外部依赖失败 | `test_files_db_failure_fails_closed` / `test_fallback_config_seeds_filtered_on_db_error` | ✅ |

### 混入项过滤前后对照（部署形态推演）

| 读面 | 前 | 后 |
|---|---|---|
| registry spiders | 种子 7 行：example、openweather、skill_harvester、flow_generic、dianping_home、zhihu_feed、generic（+manual/ai_generated） | dianping_home、zhihu_feed、generic（+manual/**ai_generated flow 定义保留**） |
| files 清单 | scrapy/spiders/*.py 全量 8 文件行（含 base.py「未登记」、example、openweather、skill_harvester、flow_generic） | 仅已登记非内部：dianping_home.py、zhihu_feed.py、generic.py |
| FileTab 合并视图 | 8 文件行（4 混入）+ registry 差集 | 3 业务行 + flow/API 定义差集；「未登记」标签不再出现 |

## 7. NFR 验证

票无 NFR（过滤为 O(1) 集合判定，无新增查询）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| /qa | 过滤面=registry/files 两个读面；MySQL 方言不涉及（无 SQL 变化）；mock 面=SpiderDefinitionRepository 桩 + tmp 目录；旧钉改写 7 处（§2）均同 PR 完成。真库验证点：部署库种子行过滤后清单=§6 对照表 |
| /frontend | 零改动：T-40 FileTab 合并逻辑在新数据口径下天然纯净；行为差异=「未登记」行整体消失、空 registry 不再被种子回填（空态句可达） |
| /architect | 将来若按票面「优先口径」落定义行 internal/demo 标记，需 /dba 迁移（改 source 取值集或加列）——本票以显式清单常量过渡，票面明示可选 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（1528 passed / 38 skipped / exit 0）
- [x] 契约落位表已核对，分层无违规（arch.sh 0 违规；Router 零新 import）
- [x] ORM 与 DBML 一致（零改动）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（未新增 I/O 形态；os.listdir/getsize 沿既有同步用法）
- [x] 无 `except: pass`（两处 `except Exception` 均记 warning 后降级）
- [x] 日志已脱敏
- [x] 事务里无外部调用（无事务）
- [x] 幂等未用「先查后插」（无写）
- [x] 条件更新 rows==0：N/A（无写）
- [x] 外部依赖四件套：读面降级两路已测（超时/重试不适用于本地目录扫描）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（internal 标记归 dba，见 §8）
- [x] 票状态：done

附注：`spider_registry_service.py` 516 行（票前已 506，超 ≤500 约定为存量；本票净增 10 行并已压缩 docstring/注释，拆分建议留 refactor 票，不在本票扩散范围）。
