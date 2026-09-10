# 实现证据 · T-27 引用解析忽略子行上架；黑名单跳过+审计

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-27.md`｜FR 锚点：FR-36｜角色：/backend｜日期：2026-09-10
> 上游：ADR-0018 · spec v1.6 FR-36 QA-27 · db-spec `capability_components` · T-23 HTML 404 · T-25 安装行
> 泳道：L4

观测=超管/系统引用列表，非租户执行引擎（X-FR35）。合集边=出处+引用，不读安装礼包。解析忽略子行 `listing_state`；黑名单或软删跳过并写 `operation_logs`（`action=market.ref.skip`）。未改 T-23 `list_public` FR-33 WHERE/COUNT/LIMIT、GET 404 HTML、分页 total。未级联安装行。未实现 T-28 七叶、T-33 alias、执行引擎。未复活 028–030。未改 `frontend/official`。未代选六问。`power_market/` 零命中 `llm_gateway`。

When 夹具是 `platform_admin_client` GET `/api/v1/capabilities/agent/{name}/references`（`require_platform_admin`）。禁止用租户执行面空过。GWT-36.3 租户商店页复用 T-23 `STORE_NOT_FOUND_HTML` 同句。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` | GET `/{asset_type}/{name}/references` 静态三段先于二段详情；`require_platform_admin` |
| 字段校验（type） | Schema/Service | `power_market/types.py` + `parse_asset_type` | 非法 type → `没有这种类型`；无新 body |
| 跨字段参数约束 | Schema | N/A | 路径参数 |
| 权限判定（数据范围） | **Service** | `references.py` `_assert_observer` | 仅超管或 `user is None`（系统）；租户 403 |
| 业务规则/状态流转 | Service | `references.py` `list_runtime_refs` | 忽略 listing；黑名单/软删跳过+审计；不读 installs |
| 数据读写 | Service/ORM | `capability_components` JOIN assets | 无新表/列 |
| 错误码映射 | 统一异常处理器 | `AuthorizationException` / `NotFoundException` | Router 无业务 try/except |
| 幂等 | N/A | GET 观测 | 审计为追加事件 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/references.py` | 新增 | 合集边解析；skip+审计 |
| `backend/services/power_market/types.py` | 修改 | `REF_SKIP_*` 常量 |
| `backend/services/power_market/service.py` | 修改 | `list_runtime_references` 门面；未改 `list_public`/`_fr33_clause`/`_list_includes` |
| `backend/app/api/v1/capabilities.py` | 修改 | GET references + `require_platform_admin` |
| `backend/tests/test_t27_references.py` | 新增 | GWT-36.1 / 36.2 / 36.3 |
| `backend/tests/t27_support.py` | 新增 | 合集边夹具 + 礼包安装行对照 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-27.md` | 修改 | done + GWT 勾选 |
| `.sdlc/feat-four-pillars-v2/03-impl/T-27-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：票未列路径；落地 GET references 观测点，无新迁移）

**未触碰「不许改的文件」**：☑ 确认（未改 FR-33 查询闸、GET 404 HTML、installs 级联、official、T-28、028–030、TENANT_EXEMPT）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 读合集边 + 投影 dict | 否（只读） | 无 listing 闸 |
| 跳过行写 `operation_logs` | 投影后 `commit` | 审计追加；P-BE-01 先捕获 name 再提交 |

**事务提交后的操作失败怎么办**：N/A（无提交后外部调用）。审计失败不得挡列表：本票 skip 审计与列表同会话，写入失败会抬到统一 handler；无 skip 则不 commit。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（GET 观测） |
| 保证方式 | N/A |
| 重复请求返回 | 同一 `items`；skip 再记一条审计 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无边 | SELECT 合集边 | `items=[]` |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 沿用 `capability_components`（parent/child/role）与 `capability_assets.status`/`deleted_at`/`listing_state`。无新列。未改 `uq_asset_type_name_alive`。未复活 028–030。

结构核对输出：

```
$ bash tools/check/arch.sh
（见 §6；本票无新迁移）
mig: N/A 无 Alembic
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_runtime_references` / `list_runtime_refs` |
| trace_id | 现网中间件 |
| 错误日志上下文 | skip：`power_market.ref.skip \| parent= child= reason=` + `operation_logs` |
| 慢操作耗时 | 单父 JOIN 子行 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

红（TDD：观测路由尚未注册；36.1/36.2/36.3 同一缝）：

```
$ uv run pytest -x -q backend/tests/test_t27_references.py::test_gwt_36_1_unlisted_ref_still_in_list --tb=short
F
=================================== FAILURES ===================================
___________________ test_gwt_36_1_unlisted_ref_still_in_list ___________________
backend/tests/test_t27_references.py:56: in test_gwt_36_1_unlisted_ref_still_in_list
    assert resp.status_code == 200, resp.text
E   AssertionError: {"detail":"Not Found"}
E   assert 404 == 200
FAILED backend/tests/test_t27_references.py::test_gwt_36_1_unlisted_ref_still_in_list
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 2.06s
```

绿（本票 GWT + T-23 商店不存在句仍 HTML）：

```
$ uv run pytest -x -q backend/tests/test_t27_references.py backend/tests/test_skill_public_api.py::test_gwt_32_3_unlisted_html_matches_true_404 backend/tests/test_b1c_capabilities_coverage.py::test_gwt_32_3_capability_unlisted_html_404 --tb=short
.....                                                                    [100%]
5 passed in 2.55s
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

$ uv run ruff check backend/services/power_market/references.py backend/services/power_market/service.py backend/services/power_market/types.py backend/app/api/v1/capabilities.py backend/tests/test_t27_references.py backend/tests/t27_support.py
All checks passed!
ruff_exit:0
```

`llm_gw_grep_exit:1` = 零命中（空输出）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-36.1 未上架非黑名单仍在引用列表 | `test_gwt_36_1_unlisted_ref_still_in_list` | ✅ When=`platform_admin_client` GET references；出处边+引用边；礼包安装行不出现；许可未声明不拆行 |
| GWT-36.2 黑名单跳过+审计；商店两边都不出现 | `test_gwt_36_2_blacklist_skipped_with_audit` | ✅ skip `operation_logs` `market.ref.skip`；`/public/skills` 与 `/public/capabilities` 都无该名；详情 HTML 404 |
| GWT-36.3 租户商店页走 32.3 同句；解析列表不是泄漏 | `test_gwt_36_3_tenant_unlisted_store_html_404` | ✅ 与真 404 字节同形；公开 `includes` 不含未上架；租户经办 GET references → 403 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 观测读 + 审计追加；无多表业务写 |
| 幂等 | ➖ N/A | GET 无创建资源 |
| 并发写 | ➖ N/A | 无条件更新 |
| 外部依赖失败 | ➖ N/A | 无新外部调用；不打配额/网关 |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR。NFR-01/02 属 T-23 查询侧，未改。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 观测点 GET `/api/v1/capabilities/{type}/{name}/references`，守卫 `require_platform_admin`。When 必须是超管/系统，不是租户执行。响应 `data.items[]`：`name`/`asset_type`/`listing_state`/`status`/`role`。skip 审计 `action=market.ref.skip`，`target=skill#{name}`，`detail.reason` ∈ `{blacklist,deleted}`。商店 GET 仍 HTML 404（`STORE_NOT_FOUND_HTML`）。租户打 references → 403。 |
| `/frontend` | T-28 七叶不在本票。超管详情若接引用列表：未上架子卡仍列出；黑名单不列出（审计在后台日志/审计表）。租户不要调该端点。 |
| `/architect` | 无新错误码。许可闸完整格仍在 T-31 / GWT-42.5；本票未上架与 `NOASSERTION` 均不拆行。 |

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
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
