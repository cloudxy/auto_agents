# 实现证据 · T-10 出站钥匙必须绑恰好一家企业

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-10.md`｜FR 锚点：FR-13｜角色：/backend｜日期：2026-09-09
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/external_api/v1/public.py` | `GET /external/v1/public/data/{spider_name}`；未绑定 401，响应无结果行 |
| 字段校验（类型/范围/枚举） | Config | `config/default/external_api.yml` | `KEY_BINDINGS` 列表 `{key, tenant_id}` 或 `key→tenant_id`；v1 无表 |
| 跨字段参数约束 | Config 解析 | `webhooks.bound_tenant_id` | 恰好一 `tenant_id`；冲突 / 非正整数 / 字符串列表项丢弃 |
| 权限判定（数据范围） | Service | `spider_query_service.query_public_results` | 绑定企业 + `source <> marketplace`；未绑不查库 |
| 业务规则/状态流转 | Service + 配置 | 同上 + `KEY_BINDINGS` | 旧 `API_KEYS` / `API_KEY` 视为未绑定，禁止静默绑企业 |
| 数据读写 | Repository | `spider_result_repository.query_by_spider` | 显式 `tenant_id` 等值；数据中心可省略（JWT scope） |
| 错误码映射 | Router HTTPException | `public._require_bound_tenant` | 未绑定与错 Key 同形 401，不泄露其它租户 |
| 幂等 | N/A | | 只读拉数 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 返回 dict ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `config/default/external_api.yml` | 修改 | 加 `KEY_BINDINGS: []` |
| `config/default/api.yml` | 修改 | 旧单 key 出站拉数视为未绑定 |
| `.env.example` | 修改 | `AUTO_AGENTS_EXTERNAL_API__KEY_BINDINGS` 注释 |
| `backend/config_consts.py` | 修改 | `EXTERNAL_API_KEY_BINDINGS` 默认 `[]` |
| `backend/app/external_api/v1/webhooks.py` | 修改 | `bound_tenant_id` + 恰好一租户解析 |
| `backend/app/external_api/v1/public.py` | 修改 | 拉数走 `_require_bound_tenant`，传入 `tenant_id` |
| `backend/services/spider_query_service.py` | 修改 | 未绑 0 行；绑定后 `tenant_scope` + 排除 marketplace |
| `backend/repositories/spider_result_repository.py` | 修改 | `query_by_spider(tenant_id=)` |
| `backend/tests/test_external_api.py` | 修改 | GWT-13.1–13.4 |
| `backend/tests/test_spider_datacenter_crud.py` | 修改 | 出站谓词 + SQL `tenant_id` |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-10.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 是（票点名 `test_external_api.py` 及出站拉数相关；无新表）

**未触碰「不许改的文件」**：☑ 确认（未建 `api_keys`；未 stamp 028；未做 FR-51；未改 T-08 谓词；未改 GWT；未代选六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 出站拉数 | 否 | 只读 |
| 绑定解析 | 否 | 配置，无写 |

**事务提交后的操作失败怎么办**：N/A（无写路径）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（只读） |
| 保证方式 | 同一绑定同一 `tenant_id` 过滤 |
| 重复请求返回 | 同一窗口同一批只读结果 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 未绑定 | Router 401 + Service 不查库 | 0 行 |
| 跨租户爬虫名 | SQL `tenant_id=` 绑定企业 | 200 + `items=[]`（0 行 B） |

☑ 本票无新的条件更新行数分支

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Dynaconf `KEY_BINDINGS` | 进程配置 | 无 | 缺省 `[]` = 全拒 | 是（只读） |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM 字段/类型/可空性/默认值/索引/唯一约束/外键。出站钥匙 = 配置绑定，无表。

结构核对输出：

```
$ 本票无迁移。禁止复活 028 api_keys pyc。v1 = KEY_BINDINGS 配置。
未自行加字段/改类型。
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `query_public_results` 记 `spider` + `tenant_id`（未绑只记 spider） |
| trace_id | 既有中间件 |
| 错误日志上下文 | 未绑定走 401，不写钥匙原文 |
| 慢操作耗时 | 既有分页；未绑短路不查库 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token / API Key 原文 ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ uv run pytest -x -q backend/tests/test_external_api.py
.................................                                        [100%]
33 passed in 1.10s
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

出站相关回归（非票闸，本票改了 `query_public_results`）：

```
$ uv run pytest -x -q backend/tests/test_spider_datacenter_crud.py
........................................                                 [100%]
40 passed in 1.27s
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-13.1 正常 | `test_gwt_13_1_bound_key_only_tenant_a` | ✅ |
| GWT-13.2 空态 | `test_gwt_13_2_no_binding_rejects_any_key`；`test_unbound_service_returns_zero_rows_without_query` | ✅ |
| GWT-13.3 越权 | `test_gwt_13_3_tenant_a_key_spider_b_zero_rows_of_b`；`test_query_by_spider_sql_binds_tenant` | ✅ |
| GWT-13.4 边界 | `test_gwt_13_4_string_list_key_rejected`；`test_data_endpoint_legacy_key_rejected` | ✅ |
| 绑定后仍排除候选 | `test_bound_pull_still_excludes_marketplace` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（本票无多步写） |
| 幂等 | 同一绑定重复拉 | ➖ N/A（只读） |
| 并发写 | — | ➖ N/A（无新条件更新） |
| 外部依赖失败 | 缺 `KEY_BINDINGS` 默认 `[]` 全拒 | ✅（GWT-13.2） |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字。未绑定短路不查库。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 拉数未绑定 = HTTP 401 + 不查库（`items` 不在信封）。绑定后 200，SQL `tenant_id` 等值且 `source <> marketplace`。跨租户爬虫名 200 + `items=[]`（不是 404）。旧 `API_KEYS` / `API_KEY` 不能拉数。状态/统计仍走字符串列表。配置例：`EXTERNAL_API.KEY_BINDINGS=[{key, tenant_id}]`。 |
| `/frontend` | 本票无管理 UI（FR-51 自助发钥匙不做）。 |
| `/architect` | 未新增错误码；未绑定与错 Key 同形 401，避免泄露租户存在。无 `FORBIDDEN_SCOPE`。 |
| `/sre` | 出站拉数须配 `AUTO_AGENTS_EXTERNAL_API__KEY_BINDINGS='[{"key":"...","tenant_id":N}]'`；只配 `API_KEYS` 不够。 |

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
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— 配置缺省拒绝
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
