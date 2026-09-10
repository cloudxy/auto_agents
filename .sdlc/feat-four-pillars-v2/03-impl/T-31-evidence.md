# 实现证据 · T-31 许可闸；已订与解析不被拆；特例仅超管

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-31.md`｜FR 锚点：FR-42 / NFR-06｜角色：/backend｜日期：2026-09-10
> 上游：ADR-0018 · spec v1.6 FR-42 QA-13 · db-spec `license` + `public_license_override`（无许可表）· T-23 `_fr33_clause` · T-25 安装行 · T-27 引用列表
> 泳道：L4

默认未放行许可不公开、不可新订。仅超管可写 `public_license_override`。收回许可不 DELETE 安装行、不拆引用解析（非黑名单/软删）。未建许可表；允许集仍 `DEFAULT_ALLOWED_LICENSES`。未把许可合成 `listing_state`。未把 `capability_installs` 写入 `TENANT_EXEMPT`。未实现 T-32 `market_*` 事件名、T-33 alias、T-29 sync。未复活 028–030。未代选六问。`power_market/` 零命中 `llm_gateway`。

GWT-42.6：企业 A 经办 PATCH 许可闸 → 403；DELETE B 安装行 → 404；B 行不变。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` | PATCH `/{asset_type}/{name}/license-override`；三段先于动态详情；`require_platform_admin` |
| 字段校验（0/1） | Schema | `power_market/types.py` `PatchLicenseOverrideRequest` | 非法 → 422 |
| 跨字段参数约束 | Schema | 同上 | 单字段 |
| 权限判定（数据范围） | **Router 守卫** | `require_platform_admin` | 租户/经办 403；PIT-2 |
| 业务规则/状态流转 | Service | `license.py` `LicenseWriter`；`service.py` `_license_clause` / `_license_ok` / `subscribe_public` | 放行只改 override；新订走 FR-33；不拆已订/引用 |
| 数据读写 | ORM | `CapabilityAsset.public_license_override` | 无新表/列 |
| 错误码映射 | 统一异常处理器 | `FORBIDDEN` / `MARKET_NOT_FOUND` / `NOT_FOUND` | Router 无业务 try/except |
| 幂等 | Service | 再写同一 0/1 覆盖同值；不插行 | 无先查后插 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/types.py` | 修改 | `PatchLicenseOverrideRequest`；允许集注释改为 T-31 不建表 |
| `backend/services/power_market/license.py` | 新增 | 超管写 override；commit 前投影 |
| `backend/services/power_market/service.py` | 修改 | `_license_clause` / `_license_ok` 接到 FR-33；`set_license_override` 薄委托 |
| `backend/services/power_market/__init__.py` | 修改 | 导出 `PatchLicenseOverrideRequest` |
| `backend/app/api/v1/capabilities.py` | 修改 | PATCH license-override + `license.override` 审计（非 `market_*`） |
| `backend/tests/test_t31_license.py` | 新增 | GWT-42.1…42.6 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-31.md` | 修改 | done + GWT 勾选 |
| `.sdlc/feat-four-pillars-v2/03-impl/T-31-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：票未列路径；落地 override 写面 + 同一 FR-33 谓词；无新迁移）

**未触碰「不许改的文件」**：☑ 确认（未 DELETE 安装行、未按许可拆 T-27 引用、未合成 listing_state、未豁免 installs、未加 market_* 事件、未实现 T-32/T-33/T-29、未复活 028–030）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 写 `public_license_override` | 是 | 单列覆盖；不碰 installs / components |
| 公开列表 / 引用列表 | 否 | 只读 |
| 新订 | 沿 T-25 | 未过许可闸 → `MARKET_NOT_FOUND`，无行 |

**事务提交后的操作失败怎么办**：审计独立短事务（`license.override`）；失败不挡 200。无提交后外部调用。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 资产行自然键 + 覆盖列 |
| 保证方式 | 直接赋值 0/1，再写同值仍 200 |
| 重复请求返回 | 当前 override |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 资产不存在 | `_load_asset` SELECT | `NotFoundException` |
| 跨租户卸 B 行 | installs WHERE tenant_id | 404，B 行不变 |

☑ 无条件更新行数（单行覆盖）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 沿用 assets `license` VARCHAR(64) NULL、`public_license_override` TINYINT(1) NOT NULL default 0。无许可表（db-spec FR-42「无许可表」）。未改 `uq_asset_type_name_alive`。未改 installs 唯一键。未复活 028–030。

结构核对输出：

```
$ bash tools/check/arch.sh
（见 §6；本票无新迁移）
mig: N/A 无 Alembic
```

**未自行加字段/改类型**：☑ 确认（未发明许可表；允许集仍 `types.py`）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `set_license_override` / `LicenseWriter.set_override` |
| trace_id | 现网中间件 |
| 错误日志上下文 | 越权经 `require_platform_admin`；审计 `action=license.override`（禁止 `market_*`） |
| 慢操作耗时 | 单行 UPDATE |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

红（TDD：override 路由尚未注册；42.2 写面 404）：

```
$ uv run pytest -x -q backend/tests/test_t31_license.py::test_gwt_42_2_override_appears_still_gated --tb=short
F
=================================== FAILURES ===================================
__________________ test_gwt_42_2_override_appears_still_gated __________________
backend/tests/test_t31_license.py:112: in test_gwt_42_2_override_appears_still_gated
    assert resp.status_code == 200, resp.text
E   AssertionError: {"detail":"Not Found"}
E   assert 404 == 200
FAILED backend/tests/test_t31_license.py::test_gwt_42_2_override_appears_still_gated
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 2.26s
```

绿（本票 GWT-42 + T-23/T-25/T-27 重叠）：

```
$ uv run pytest -x -q backend/tests/test_t31_license.py --tb=short
......                                                                   [100%]
6 passed in 3.02s
pytest_t31_exit:0

$ uv run pytest -x -q backend/tests/test_t31_license.py backend/tests/test_t25_subscribe.py backend/tests/test_t27_references.py backend/tests/test_skill_public_api.py backend/tests/test_b1c_capabilities_coverage.py --tb=short
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed in 15.02s
pytest_exit:0

$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 4 条边界）
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
✓ B4: power_market 禁 spider_/newapi_/litellm_/relay_/channel_/ai_planner/llm_gateway 直连
✓ B4: ai_planner 禁 llm_gateway.admin（三模式）
✓ B4: ai_planner 除 llm_client.py 禁 llm_gateway.chat（三模式）
✓ B4: 禁止 LITELLM.DB_DSN
✓ B4: 禁止 create_async_engine 打网关库

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0

$ grep -rn llm_gateway backend/services/power_market/; echo "llm_gw_grep_exit:$?"
llm_gw_grep_exit:1

$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py
✓ 分层依赖检查通过
layering_exit:0

$ uv run ruff check backend/services/power_market/license.py backend/services/power_market/service.py backend/services/power_market/types.py backend/services/power_market/__init__.py backend/app/api/v1/capabilities.py backend/tests/test_t31_license.py
All checks passed!
ruff_exit:0
```

`llm_gw_grep_exit:1` = 零命中（空输出）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-42.1 未放行不出现 | `test_gwt_42_1_unlicensed_not_in_public_total` | ✅ 公开 `total` 不含 NOASSERTION；新订 `MARKET_NOT_FOUND` 无行 |
| GWT-42.2 超管放行可出现 | `test_gwt_42_2_override_appears_still_gated` | ✅ PATCH override=1 后 listed+stable 出现；unlisted/experimental 仍不出 |
| GWT-42.3 租户放行拒绝 | `test_gwt_42_3_tenant_cannot_override_public_unchanged` | ✅ 租户 admin 403 `FORBIDDEN`；override 仍 0；公开集合不变 |
| GWT-42.4 已订收回仍在可卸 | `test_gwt_42_4_revoke_keeps_install_operator_can_uninstall` | ✅ 收回后安装行仍在、经办可卸；商店不再出现；新订拒绝 |
| GWT-42.5 解析不拆未放行 | `test_gwt_42_5_unlicensed_still_in_ref_list` | ✅ When=`platform_admin_client` GET references；商店无该名 |
| GWT-42.6 A 不能拆 B 已订 | `test_gwt_42_6_tenant_a_cannot_tear_down_b_install` | ✅ A PATCH 许可闸 403；A DELETE B 行 404；B 安装行不变 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 单列覆盖；不写 installs |
| 幂等 | ➖ N/A | 覆盖同值，无创建资源 |
| 并发写 | `test_gwt_42_6_tenant_a_cannot_tear_down_b_install` | ✅ 跨租户写被拒，B 行不变 |
| 外部依赖失败 | ➖ N/A | 无新外部调用；不打配额/网关 |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-06 | 许可默认闸；特例仅超管 | 42.1 未放行不出店不可新订；42.2 仅超管 PATCH 后出现；42.3 租户 403 | pytest sqlite |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 写面 PATCH `/api/v1/capabilities/{type}/{name}/license-override` body `{public_license_override:0\|1}`，守卫 `require_platform_admin`。审计 `action=license.override`（不是 `market_*`）。未放行公开 `total` 不计；新订 `MARKET_NOT_FOUND`。收回后 GET `/capabilities/installs` 行仍在且 `can_uninstall=true`。引用列表仍走 T-27 超管 GET references，许可不拆行。GWT-42.6 夹具：B 先订 NOASSERTION+override=1，A 经办打闸。 |
| `/frontend` | 治理台可接超管放行开关；租户不要调该端点。商店/订阅仍走 FR-33。我的安装不因许可收回消失。 |
| `/architect` | 无新错误码。无许可表。T-32 事件名未在本票发出。 |

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
- [x] 条件更新的 `rows == 0` 已处理
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— N/A 无新外部依赖
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
