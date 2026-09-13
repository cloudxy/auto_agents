# 实现证据 · T-08 市场总开关运行时闸；订一行；关闭不发成功事件

> 票：`02-shape/contract.md` §10 T-08｜FR 锚点：FR-U10 FR-U11 FR-U14｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET/PUT `/api/v1/admin/power-market` | Router | `backend/app/api/v1/admin.py` | 超管可改运行时总开关；租户 403 |
| 公开列表/详情关闭句 vs 空货架 | Service | `power_market/service.py` + `flag.py` | 关闭：`能力市场未开放`；打开且 0 行：`暂无已上架能力` |
| POST subscribe 运行时闸 | Service | `subscribe_public` → `require_power_market_open` | 关闭 409 `MARKET_CLOSED`；不写安装行 |
| 只读拒绝 / 预告 409 / 订插件不带子卡 | Service | 既有 `installs._assert_actor` + `insert_install` 单行 | D24 不级联 |
| `market_subscribe_succeeded` tenant_id+host | Service | `market_events.run_subscribe` | 关闭尝试可 rejected，不进成功事件 |
| 错误码映射 | 统一异常处理器 | `MARKET_CLOSED` 409 | 未新造 HTTP 信封 |
| 幂等 | 既有唯一约束 | 安装行 (tenant, asset, host) | 本票未改约束 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/flag.py` | 新增 | 运行时读写 `POWER_MARKET.ENABLED`；关闭/空货架句 |
| `backend/services/power_market/service.py` | 修改 | list/get/subscribe 读总开关 |
| `backend/services/power_market/__init__.py` | 修改 | 导出关闭码/句 |
| `backend/services/market_events.py` | 修改 | rejected reason `market_closed` |
| `backend/app/api/v1/public_skills.py` | 修改 | 关闭列表/详情不发浏览事件；详情走 JSON 关闭句 |
| `backend/app/api/v1/admin.py` | 修改 | GET/PUT `/admin/power-market` |
| `backend/tests/conftest.py` | 修改 | autouse 测试默认打开总开关 |
| `backend/tests/test_fr_u10_market.py` | 新增 | GWT-U10/U11/U14 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：合同未列具体路径；按 PIT-2 同 PR 改公开/订阅测。未改 yaml 默认 false。）

**未触碰「不许改的文件」**：☑ 确认（无 Alipay notify；无商户凭据；无中转 SKU 履约）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 订阅安装行 | 是（既有 insert_install） | 成功后才 emit succeeded |
| 总开关 PUT | 否（Dynaconf 进程覆盖） | 运行时闸；yaml 仍是进程默认 |

**事务提交后的操作失败怎么办**：产品事件 fail-open（既有）；关闭路径不写安装行。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 既有 (tenant_id, asset_id, host) |
| 保证方式 | 唯一约束 + IntegrityError → 已订 |
| 重复请求返回 | 200 `created=false` |

☑ 未使用「先查后插」（沿用既有 IntegrityError）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 关闭后订阅 | 入口闸，不 UPDATE | 无条件更新 |

☑ N/A 本票无状态机 UPDATE

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 本票无新表/新列。总开关走运行配置 `POWER_MARKET.ENABLED`（NFR-U10），不新建表。

结构核对输出：

```
$ bash tools/check/arch.sh
（见 §6；零违规）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `flag.read/write/require_open`；`subscribe_public` 既有 |
| 错误日志上下文 | 关闭 409 `MARKET_CLOSED`；越权走既有 authz.denied |
| 开关审计 | PUT `power_market.switch` |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_fr_u10_market.py
...........                                                              [100%]
11 passed in 3.98s
exit: 0

$ uv run pytest -x -q backend/tests
1585 passed, 40 skipped, 7 warnings in 237.07s (0:03:57)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U10.1 订一行且插件不带子卡 | `test_gwt_u10_1_subscribe_one_row_no_children` | ✅ |
| GWT-U10.2 打开且 0 行空货架句 | `test_gwt_u10_2_open_empty_shelf_not_closed` | ✅ |
| GWT-U10.3 只读不能订 | `test_gwt_u10_3_readonly_rejected` | ✅ |
| GWT-U10.4 预告无订阅 | `test_gwt_u10_4_coming_soon_not_subscribable` | ✅ |
| GWT-U11.1 关闭订不到 | `test_gwt_u11_1_closed_subscribe_no_row` | ✅ |
| GWT-U11.2 关闭≠空货架（双公开端） | `test_gwt_u11_2_closed_list_not_empty_shelf` | ✅ |
| GWT-U11.3 公司管理员不能改开关 | `test_gwt_u11_3_tenant_admin_cannot_flip` | ✅ |
| GWT-U14.1 成功事件含 tenant_id+host | `test_gwt_u14_1_subscribe_event_queryable` | ✅ |
| GWT-U14.2 关闭尝试无 succeeded | `test_gwt_u14_2_closed_attempt_no_succeeded` | ✅ |
| GWT-U14.3 租户查事件 404 同形 | `test_gwt_u14_3_tenant_query_events_404` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（关闭路径零写；成功路径沿用既有 insert 事务） |
| 幂等 | 既有 `test_gwt_34_6_idempotent_same_host` 全量绿 | ✅ |
| 并发写 | — | ➖ N/A（本票无新条件更新） |
| 外部依赖失败 | — | ➖ N/A（无新外部调用） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U10 | 总开关来自运行配置，不写死仓库 | yaml 默认 false；超管 PUT 改 Dynaconf；测试 `settings.set` | local pytest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 公开列表 `market_closed` + `message`；关闭详情是 JSON 200 不是 HTML 商店不存在句。订阅关闭 409 `MARKET_CLOSED`。PIT-5 双端 `/public/capabilities` 与 `/public/skills` 均钉。 |
| `/frontend` | T-10：关闭句「能力市场未开放」vs 空货架「暂无已上架能力」。`subscribable` 在关闭/预告为 false。开关面 `GET/PUT /api/v1/admin/power-market` 仅超管。 |
| `/architect` | 无新错误码形状；`MARKET_CLOSED` 与 coming_soon 同属 409 业务闸。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] 未自行加 ORM 字段
- [x] 无硬编码连接串/密钥/端口
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 四类易漏测试已覆盖或标 N/A
- [x] 未做 N3 支付宝/微信 notify、商户凭据、中转 SKU
