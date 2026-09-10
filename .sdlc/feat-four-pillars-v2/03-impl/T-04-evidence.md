# 实现证据 · T-04 平台写面 `require_platform_admin`；目录豁免；超管刷新可见

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-04.md`｜FR 锚点：FR-06 / FR-20｜角色：/backend｜日期：2026-09-08
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/{capabilities,skills,newapi,configs,rbac,llm_providers}.py` | 写面 403 走统一 `AuthorizationException` |
| 字段校验（类型/范围/枚举） | Schema | 未改 | 本票不改请求体契约 |
| 跨字段参数约束 | Schema | 未改 | |
| 权限判定（数据范围） | Router + Service | `deps.require_platform_admin`；`LlmProviderService._guard_platform_provider_write` | 平台写面 Depends；`/llm` 平台行行级拆分 |
| 业务规则/状态流转 | Service | `plugin_service` / `expert_service` / `skill_service` 空态 message | GWT-06.2「没有可同步的包」 |
| 数据读写 | Repository | 未改表/未改 `channel_id` | `capability_assets` 进豁免，无 TenantMixin |
| 错误码映射 | 统一异常处理器 | `AuthorizationException` → 403 `FORBIDDEN` | 不在 Router 逐个 try/except |
| 幂等 | N/A | | 本票无新建写幂等键 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象（既有投影保持） ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/deps.py` | 修改 | `require_platform_admin` 拒绝并 `authz.denied` leftover |
| `backend/services/audit_service.py` | 修改 | `record_authz_denied`（请求 session 提交，测试可查） |
| `backend/app/tenant_isolation.py` | 修改 | `capability_assets` + 细节表进 `TENANT_EXEMPT_TABLES`；不登记 `capability_installs` |
| `backend/app/api/v1/capabilities.py` | 修改 | scan/verify/teams → `require_platform_admin`；扫描审计；空目录可行动空态 |
| `backend/app/api/v1/skills.py` | 修改 | `POST /scan` → `require_platform_admin` |
| `backend/app/api/v1/newapi.py` | 修改 | 全部 `require_platform_admin`（渠道窗口） |
| `backend/app/api/v1/configs.py` | 修改 | PUT 系统配置 → `require_platform_admin` |
| `backend/app/api/v1/rbac.py` | 修改 | 角色/菜单/权限写 → `require_platform_admin`；部门仍 `require_admin` |
| `backend/app/api/v1/llm_providers.py` | 修改 | 写面仍 `require_admin`（T-17 经办）；传入 actor 给平台行守卫 |
| `backend/services/llm_provider_service.py` | 修改 | GWT-06.6 平台行写拒绝；行不变 |
| `backend/services/plugin_service.py` | 修改 | 0 包扫描可行动空态 |
| `backend/services/expert_service.py` | 修改 | 同上 |
| `backend/services/skill_service.py` | 修改 | 同上 |
| `backend/tests/conftest.py` | 修改 | `platform_admin_client`；Bearer 助手 |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 作废 viewer 可扫 200；06.1–06.4 / 20.x |
| `backend/tests/test_b1c_newapi_channels_coverage.py` | 修改 | 超管正面路径；租户 admin 改窗口 403 leftover |
| `backend/tests/test_saas_isolation.py` | 修改 | `capability_assets` 豁免 Core UPDATE 夹具 |
| `backend/tests/test_llm_platform_row_writes.py` | 新增 | GWT-06.5 / 06.6（禁止把 operator 403 当完成态） |
| `backend/tests/test_b1b_configs_coverage.py` | 修改 | PUT 正面改超管；租户 admin 403 |
| `backend/tests/test_saas_rbac_deep.py` | 修改 | 平台角色写超管；租户 admin 改角色 403 |
| `backend/tests/test_newapi_api.py` | 修改 | overview 夹具改超管 |
| `backend/tests/test_skills_api.py` | 修改 | scan 正面改超管 |
| `backend/tests/test_llm_provider.py` | 修改 | activate 桩接受 actor kwargs |

**与票里「会改哪些文件」一致**：☑ 是（闸命令路径票写 `scripts/check-arch.sh`，活路径 `bash tools/check/arch.sh`）

**未触碰「不许改的文件」**：☑ 确认（未改 `frontend/official/**`、`deploy/litellm/**`、GWT、表结构、`channel_id`、LiteLLM PG、CapabilityAsset Mixin、`capability_installs`）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 越权 leftover（`authz.denied`） | 独立提交 | 拒绝路径必须留痕；业务未开始 |
| 扫描/验证/组团成功审计 | 既有 standalone | 与业务事务分离 |
| `/llm` 平台行拒绝 leftover | 独立提交（请求 session） | 拒绝前未改行 |

**事务提交后的操作失败怎么办**：leftover 提交失败只记日志，仍抛 403。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A |
| 保证方式 | N/A |
| 重复请求返回 | N/A |

☑ 未使用「先查后插」（本票无新建业务写）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无本票条件更新 | — | — |

☑ 本票无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新增外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM 字段/类型/索引/唯一约束/外键。未给 `CapabilityAsset` 加 TenantMixin。未改 `channel_id`。LiteLLM PG 不进 Alembic。

结构核对输出：

```
$ 本票无 DDL / 无 autogenerate
（仅 TENANT_EXEMPT_TABLES 登记 + 守卫）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `require_platform_admin` / `record_authz_denied` 记 user/role/target（无 token） |
| trace_id | 既有中间件 |
| 错误日志上下文 | leftover 失败记 target |
| 慢操作耗时 | 未新增外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -x -q backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_saas_isolation.py
...........................................                              [100%]
43 passed in 3.57s
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

$ uv run pytest -x -q backend/tests/test_b1c_newapi_channels_coverage.py backend/tests/test_llm_platform_row_writes.py backend/tests/test_b1b_configs_coverage.py backend/tests/test_saas_rbac_deep.py
......................................                                   [100%]
38 passed in 2.35s
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-06.1 超管扫描/验证完成并留痕 | `test_scan_plugins_ok`；verify 既有 `test_plugin_verify_no_mcp_degraded` | ✅ |
| GWT-06.2 0 包可行动空态 | `test_scan_plugins_zero_packages_actionable_empty` | ✅ |
| GWT-06.3 租户 admin 扫描/验证/改窗口拒绝+行不变+leftover | `test_scan_plugins_tenant_admin_403_leftover`；`test_plugin_verify_tenant_admin_403_row_unchanged`；`test_set_config_tenant_admin_403_quota_unchanged`；`test_tenant_admin_cannot_update_platform_role` | ✅ |
| GWT-06.4 查看者扫描拒绝零落库 | `test_scan_plugins_viewer_403_zero_write`（作废 viewer 可扫 200） | ✅ |
| GWT-06.5 负责人保存本企业行 | `test_owner_saves_own_tenant_provider_row`（**未**把 `test_create_endpoint_rejects_operator` 当完成态） | ✅ |
| GWT-06.6 负责人改/激活平台行拒绝且行不变 | `test_owner_activate_platform_provider_rejected_row_unchanged`；`test_owner_update_platform_provider_rejected_row_unchanged` | ✅ |
| GWT-20.1 超管扫描后刷新可见新包 | `test_platform_admin_scan_refresh_sees_new_package` | ✅ |
| GWT-20.2 空目录可行动空态 | `test_list_capabilities_empty_actionable` | ✅ |
| GWT-20.3 经办改平台目录行拒绝且行不变 | `test_team_upsert_operator_403_row_unchanged` | ✅ |
| PIT-3 豁免登记 | `test_capability_assets_exempt_update_unfiltered` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（守卫拒绝发生在业务写之前；leftover 独立提交） |
| 幂等 | — | ➖ N/A（无新建业务写） |
| 并发写 | — | ➖ N/A（无条件更新竞态） |
| 外部依赖失败 | — | ➖ N/A（无新增外部依赖） |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 闸。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 租户 `admin_client` ≠ 超管。正面平台写用 `platform_admin_client` 或 Bearer。`/llm` 本企业写仍 `require_admin`；经办写/test/进页是 T-17。渠道 GET 也已收成超管（与 ADR-0017 值班面一致）。 |
| `/frontend` | 平台写按钮应对 `is_platform_admin`。T-05 租户壳 404；T-17 去掉 `/llm` `requireAdmin`。 |
| `/architect` | 无契约歧义。票闸仍写 `scripts/check-arch.sh`（已不存在）；活路径 `bash tools/check/arch.sh`。 |

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
- [x] 外部依赖四件套齐全（N/A）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
