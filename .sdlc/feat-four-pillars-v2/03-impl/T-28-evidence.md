# 实现证据 · T-28 治理台七叶；listed≠verify；无上架全部子资产；`dev-team` 句

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-28.md`｜FR 锚点：FR-37 / FR-40｜角色：/frontend admin + /backend｜日期：2026-09-10
> 上游：ADR-0018 · spec v1.6 FR-37/FR-40 · db-spec `listed_at` · T-21 五类/单一市场名
> 泳道：L4

未实现 T-29 源同步。无 enable-host。未砍命令叶。未重写 T-26 MyInstalls。未碰 official T-22/T-24。未代选六问。未复活 028–030。未改 T-27 引用解析 / 公开 GET 404。未给 assets 加 source_id / writable。`power_market/` 零命中 `llm_gateway`。

TDD 红：`test_plugin_verify_no_mcp_unknown` 在改 `verify_plugin` 前断言 `unknown`，现网仍写 `degraded`。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` | PATCH `/{asset_type}/{name}/listing`；verify 仍 POST `/plugins/{name}/verify` |
| 字段校验（上架三态） | Schema + Service | `power_market/types.py` `PatchListingRequest`；`listing.py` `_guard_state` | unlisted/listed/coming_soon |
| 跨字段参数约束 | Service | `listing.py` `_guard_third_party` | 第三方 → listed 需 `confirm` |
| 权限判定 | **Router 守卫** | `require_platform_admin` | PIT-2 与 b1c 同 PR；租户/viewer 403 |
| 业务规则/状态流转 | Service | `listing.py` `ListingWriter` | listed_at 只在进入 listed 时写；unlist 不清空；dev-team 拒 listed；blacklist 拒 listed；不看 health |
| 数据读写 | ORM | `CapabilityAsset.listed_at` + 036 | 只 expand 加列 |
| 错误码映射 | 统一异常 | `LISTING_MERGED` 400；`LISTING_CONFIRM_REQUIRED` / `LISTING_BLACKLIST` 409 | Router 无 try/except |
| 幂等 | Service | 已 listed 再 listed 不刷新 `listed_at` | `_apply_listed_at` 仅非 listed→listed |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/capability.py` | 修改 | `listed_at` DATETIME NULL |
| `backend/alembic/versions/036_t28_listed_at.py` | 新增 | ADD listed_at；menus 叶名「能力市场」；revises 035 |
| `backend/services/power_market/types.py` | 修改 | `PatchListingRequest` + 冻结句 |
| `backend/services/power_market/listing.py` | 新增 | 上架写 |
| `backend/services/power_market/service.py` | 修改 | `set_listing` 薄委托 |
| `backend/services/power_market/__init__.py` | 修改 | 导出 `PatchListingRequest` |
| `backend/services/plugin_service.py` | 修改 | 无 MCP → `unknown`；详情带 listing 字段 |
| `backend/services/capability_service.py` | 修改 | list 可筛 `listing_state` |
| `backend/app/api/v1/capabilities.py` | 修改 | PATCH listing；列表/详情投影 listed_at |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | PIT-6 unknown；PIT-2 上架 403 |
| `backend/tests/test_t28_listing.py` | 新增 | GWT-37.3/37.4/37.6/40.1/40.3 + 第三方确认 + 黑名单 |
| `frontend/admin/src/config/menuConfig.tsx` | 修改 | 叶名「能力市场」 |
| `frontend/admin/src/services/capabilities.ts` | 修改 | patchListing / getPlugin / listing 字段 |
| `frontend/admin/src/pages/Capabilities.tsx` | 修改 | 七叶壳；窄屏 class `market-tabs` |
| `frontend/admin/src/pages/market/*` | 新增 | 源/目录/插件/命令/智能体/专家团 + listing 控件 |
| `frontend/admin/src/pages/Capabilities.governance.test.tsx` | 新增 | 七叶快照；无批量上架；无 enable-host |
| `frontend/admin/src/pages/Capabilities.subscribe.test.tsx` | 修改 | mock patchListing/getPlugin |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：源登记 API 留给 T-29，本票源叶空态；菜单文案 036 数据 UPDATE 非新列）

**未触碰「不许改的文件」**：☑ 确认（未改 T-26 MyInstalls、official、FR-33 查询闸、GET 404 HTML、uq、028–030、T-27 references）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 上架写 listing_state + listed_at | 是 | 同行两列 |
| 审计 listing.change | 否 | 现网独立短事务 |
| verify 无 MCP 落 unknown | 是 | 健康态副作用 |

**事务提交后的操作失败怎么办**：审计失败只记日志（现网 `record_audit_standalone`）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 资产自然键 (type, name) |
| 保证方式 | 已 listed 再 PATCH listed 不改 `listed_at` |
| 重复请求返回 | 当前行投影 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 上架 | 按主键加载后写 | 找不到 → 404 |

☑ 无条件更新行数语义（单行 ORM）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| MCP verify（声明了 servers） | 现网 mcp_bridge | 否 | 探测失败才 degraded/down | N/A |
| 无 MCP | 不探测 | — | `unknown` 可 listed | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— `listed_at` DATETIME NULL，unlist 不清空；不改 uq；不加 source_id

结构核对：036 `op.add_column('capability_assets', listed_at DateTime nullable=True)` revises 035。物理接表尾（host_compat 之后）。

**未自行加字段/改类型**：☑ 确认（仅 db-spec `listed_at`）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `ListingWriter.set_listing` / `PowerMarketService.set_listing` 记 type/name/state |
| trace_id | 现网中间件 |
| 错误日志上下文 | 统一 handler + 越权 `require_platform_admin` leftover |
| 慢操作耗时 | N/A 单行写 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

TDD 红（改 verify 前，金标仍是 degraded）：

```
$ uv run pytest -x -q backend/tests/test_b1c_capabilities_coverage.py::test_plugin_verify_no_mcp_unknown --tb=short
F
E   AssertionError: assert 'degraded' == 'unknown'
FAILED backend/tests/test_b1c_capabilities_coverage.py::test_plugin_verify_no_mcp_unknown
1 failed in 2.13s
exit: 1
```

绿：

```
$ uv run pytest -x -q backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_t28_listing.py
................................................................         [100%]
64 passed in 10.07s
pytest_exit:0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0

$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
frontend_gate_exit:0

$ npm test --prefix frontend/admin -- --runInBand src/pages/Capabilities.governance.test.tsx src/pages/Capabilities.subscribe.test.tsx --no-coverage
PASS src/pages/Capabilities.governance.test.tsx
PASS src/pages/Capabilities.subscribe.test.tsx
Tests:       14 passed, 14 total
jest_exit:0

$ npm run build --prefix frontend/admin
Creating an optimized production build...
Compiled with warnings.
The build folder is ready to be deployed.
admin_build_exit:0
```

admin build 警告均在既有文件（LogDrawer / EnterpriseManagement / LlmProviders / Nodes / Rbac / SpiderLogs / auth），非本票。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-37.1 七叶；无「专家」作智能体叶名 | `Capabilities.governance.test` 七 tab；`/^专家$/` 不在 | ✅ |
| GWT-37.2 命令可行动空态 | 命令叶 `COMMAND_EMPTY`；无 git 路径 | ✅ |
| GWT-37.3 租户无上架权 | `test_gwt_37_3_*` + b1c PIT-2 403；UI 禁用+「需要平台市场权限」 | ✅ |
| GWT-37.4 `dev-team`「已合并，不可上架」；子卡保持 | `test_gwt_37_4_dev_team_merged_children_keep` + UI Alert | ✅ |
| GWT-37.5 无「上架全部子资产」 | 插件抽屉仅「在目录中打开」「单独上架」 | ✅ |
| GWT-37.6 listed_at unlist 不清空 | `test_gwt_37_6_listed_at_survives_unlist`；UI 仍显示最近上架 | ✅ |
| GWT-40.1 无 MCP=未知可上架 | `test_plugin_verify_no_mcp_unknown` + `test_gwt_40_1_no_mcp_unknown_can_list` | ✅ |
| GWT-40.2 无「已在你的宿主里运行」；无启用到宿主 | 详情 Collapse「订阅不等于已在宿主运行」 | ✅ |
| GWT-40.3 租户验证无权限 | b1c tenant 403 + UI「需要平台管理员」禁用 | ✅ |
| PIT-6 与 b1c 同 PR | 作废 degraded 金标 | ✅ |
| PIT-2 上架守卫与 b1c 同 PR | `test_listing_tenant_admin_403` / viewer 403 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 单行 ORM commit；无多步业务写跨表 |
| 幂等 | 已 listed 再 listed 不刷新 listed_at（`_apply_listed_at`） | ✅ 37.6 只在进入 listed 时打戳 |
| 并发写 | ➖ N/A | 无条件 UPDATE 行数 |
| 外部依赖失败 | 无 MCP 不探测；声明 MCP 仍走 mcp_bridge | ➖ N/A 本票未改探测 |

## 7. NFR 验证（票里有 NFR 时填）

票无独立 NFR 编号。九维：antd token / `type=secondary`；无新硬编码色；七叶 `market-tabs` 横向滚不删叶；图标来自 `@ant-design/icons`；空/错/权限/边界按 edge-states。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | PATCH listing 需超管。无 MCP verify=`unknown` 可 listed。`dev-team` listed → 400「已合并，不可上架」。第三方 listed 无 confirm → 409。源登记 API 未做（T-29）。 |
| `/frontend` | 本票已做 admin 七叶。叶名「能力市场」。Skills 仍嵌在技能叶。 |
| `/architect` | 新码：`LISTING_MERGED` / `LISTING_CONFIRM_REQUIRED` / `LISTING_BLACKLIST`。未改公开 GET 404。 |
| `/dba` | 036 仅 `listed_at` + menus 文案；不改 uq。 |
| `/backend` T-29 | 源叶空态入口已在；登记按钮超管可见，点了「源登记尚未开放」。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新 N/A
- [x] 外部依赖：无 MCP 不探测
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报（源登记留给 T-29；T-27 references 未抢）
- [ ] 票状态仍 todo（交 orchestrator 改 done）
