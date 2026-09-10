# 实现证据 · T-02 导出仅 CSV/JSON；单次 100 条

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-02.md`｜FR 锚点：FR-03｜角色：/backend（+ admin UI）｜日期：2026-09-08
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/spiders/results.py` | GET export 流式；format 枚举 csv\|json；list `le=100` |
| 字段校验（类型/范围/枚举） | Router Query + Service | `format` pattern；`fmt not in ("csv","json")` 再拒 | xlsx 服务层 BusinessException |
| 跨字段参数约束 | Schema | 未改 | |
| 权限判定（数据范围） | Service | `export_results`：`get_by_id` miss（tenant_scope）→ 不拉结果 | 与「没有这个任务」同形 |
| 业务规则/状态流转 | Service | 空窗 `没有可导出的结果`；窗口 100；排除 marketplace | 返回迭代器前完成，不下载空文件 |
| 数据读写 | Repository | `iter_by_task(exclude_source, limit)` SQL 窗 | NULL source 可导出 |
| 错误码映射 | 统一异常处理器 | `BusinessException` 400；`NotFoundException` 404 | Router 无 try/except |
| 幂等 | N/A | | 只读导出 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 返回字节流/文件名/media_type ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/spider_query_service.py` | 修改 | csv/json；100 非候选；空窗拒绝 |
| `backend/repositories/spider_result_repository.py` | 修改 | SQL 排除 marketplace + limit |
| `backend/app/api/v1/spiders/results.py` | 修改 | list `le=100`；导出注释 |
| `backend/tests/test_spider_task_flow.py` | 修改 | 03.1–03.4；保留 xlsx 拒绝 |
| `backend/tests/test_spider_result_repository.py` | 修改 | exclude+limit SQL |
| `frontend/admin/src/pages/Data.tsx` | 修改 | CSV/JSON；旁注；空句 |
| `frontend/admin/src/components/spider/ResultDrawer.tsx` | 修改 | 任务导出入口同上 |
| `frontend/admin/src/services/spiders.ts` | 修改 | blob 错误信封解析 |
| `frontend/admin/src/pages/Data.test.tsx` | 新增 | 无 xlsx；空窗不下载 |
| `frontend/admin/src/components/spider/ResultDrawer.test.tsx` | 新增 | 同上 |
| `backend/services/quota_service.py` | 修改 | 仅 R10：签名一行，使 logger 落在下一行；**未改配额逻辑** |
| `frontend/admin/src/pages/Usage.tsx` | 修改 | 仅 `keyof NonNullable<usage>`，解开并行 optional usage 的 CRA TS2322 |

**与票里「会改哪些文件」一致**：☑ 是（另两处为闸门机械修，见上）

**未触碰「不许改的文件」**：☑ 确认（未改 official、未实现 T-08/T-10、未加 xlsx、未改 tenant_isolation / require_platform_admin、未改 llm_chat 配额、未改 Register.tsx、未代选六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 导出 | 否 | 只读查询 + 流式编码 |

**事务提交后的操作失败怎么办**：N/A（无写）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A |
| 保证方式 | N/A |
| 重复请求返回 | 同一窗口再导出同一批只读结果 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无条件更新 | — | 空窗 `BusinessException("没有可导出的结果")`，不返回迭代器 |

☑ 本票无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新增外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM 字段/类型/索引/唯一约束/外键。窗口是查询上限，不是删历史行。

结构核对输出：

```
$ 本票无 DDL / 无 autogenerate
（仅 iter_by_task 读谓词 + limit）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `export_results` 记 task_id + fmt |
| trace_id | 既有中间件 |
| 错误日志上下文 | 统一 handler 记 BusinessException message |
| 慢操作耗时 | 未新增外部调用；SQL 窗 ≤100 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -x -q backend/tests/test_spider_task_flow.py
..................................                                       [100%]
34 passed in 1.36s
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

$ npm test --prefix frontend/admin -- --testPathPattern='(Data.test|ResultDrawer.test)' --watchAll=false --silent
PASS src/components/spider/ResultDrawer.test.tsx
PASS src/pages/Data.test.tsx (11.934 s)
Test Suites: 2 passed, 2 total
Tests:       4 passed, 4 total
exit: 0

$ npm run build --prefix frontend/admin
Compiled with warnings.
The build folder is ready to be deployed.
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-03.1 30 条非候选可打开 CSV/JSON | `test_export_thirty_non_candidate_rows_csv`；`test_export_thirty_non_candidate_rows_json` | ✅ |
| GWT-03.2 0 条「没有可导出的结果」不下载空文件 | `test_export_empty_task_raises_without_stream`；`test_export_only_candidates_raises_without_stream`；admin `Data.test` / `ResultDrawer.test` zero rows | ✅ |
| GWT-03.3 120→最多 100；按钮旁「单次最多 100 条」 | `test_export_one_hundred_twenty_capped_at_one_hundred`；admin 文案断言 | ✅ |
| GWT-03.4 跨租户拒绝且导出未执行 | `test_export_cross_tenant_not_executed`（get_by_id miss → iter 未调用） | ✅ |
| GWT-03.5 后台选项无 xlsx | `test_export_bad_format_raises`（xlsx）；admin 正文 `not.toMatch(/xlsx/i)` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（只读导出，无多步写） |
| 幂等 | — | ➖ N/A（无新建写） |
| 并发写 | — | ➖ N/A（无条件更新） |
| 外部依赖失败 | — | ➖ N/A（无新增外部依赖） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-02 | 导出与数据中心单次最多 100 条 | `iter_by_task(..., limit=100)` + Data `page_size: 100` + slice 100；SQL 排除候选后再截断 | 单测桩 + admin 文案 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 空窗 HTTP 400 `BUSINESS_ERROR` + message=`没有可导出的结果`（在返回 StreamingResponse 之前抛，不会 200 空 CSV/JSON）。跨租户 = 404 `爬虫任务不存在`，iter 未跑。候选 `source=marketplace` 不进窗口；NULL source 算非候选。xlsx 服务层拒；Router pattern 对 xml 等仍 422。列表 GET `limit` 上限已改为 100。数据中心列表仍可能含候选（T-08）。 |
| `/frontend` | 任务抽屉走 `/results/{id}/export`；blob 4xx 会解析信封 message。数据中心仍客户端拼文件，选项仅 csv/json。旁注「单次最多 100 条」。 |
| `/architect` | 无新错误码。空窗用既有 `BUSINESS_ERROR`。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口（100 为 FR-03 命名常量 `EXPORT_MAX_ROWS`）
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（N/A 只读）
- [x] 外部依赖四件套齐全（N/A）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态未改 GWT；本证据即交付
