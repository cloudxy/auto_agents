# 实现证据 · T-21 单一「能力市场」；五类枚举；非法类型失败；`/skills` 映射

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-21.md`｜FR 锚点：FR-30 / FR-44 / NFR-07｜角色：/backend + official｜日期：2026-09-09
> 上游：ADR-0018 · db-spec T-21 行 · schema.dbml `capability_commands` / `capability_components`
> 泳道：L4

未实现 T-23 分页/FR-33 闸；未实现 T-25 安装；未实现 T-29 源同步；未实现 T-33 alias；未新开评分链；未拆市场微服务；未把 LiteLLM 并进根 compose；未给 CapabilityAsset 加 TenantMixin；未改 `uq_asset_type_name_alive`；未豁免 `capability_installs`；未代选六问；未新建聊天 UI。未复活 028–030。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/public_skills.py` | GET `/public/capabilities`；GET `/public/skills` 同枚举 |
| 字段校验（五类枚举） | Service | `backend/services/power_market/types.py` + `service.py` `parse_asset_type` | 非法 → 422 `VALIDATION_ERROR`「没有这种类型」 |
| 跨字段参数约束 | Schema | N/A | 单字段 type |
| 权限判定（数据范围） | Service | `PowerMarketService.list_public` | 公开只读；status=stable（FR-33 闸 T-23） |
| 业务规则/状态流转 | Service | `power_market/` | 五类平级；expert→agent / expert_team→team；JSON 只出新五类 |
| 数据读写 | Service 直查（跟现网 capability_service） | `platform_core/models/capability.py` | 本票无新 repository |
| 错误码映射 | 统一异常处理器 | `ValidationException` → 422 | Router 无 try/except |
| 幂等 | N/A | 只读 listing | |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/__init__.py` | 新增 | 单体内域包；评分只指向 `/skills/{name}/rescore` |
| `backend/services/power_market/types.py` | 新增 | `PUBLIC_ASSET_TYPES` 五类 + 一周期 legacy map |
| `backend/services/power_market/service.py` | 新增 | 公开列表读模型 |
| `platform_core/models/capability.py` | 修改 | 值域 expand；`CapabilityCommand` / `CapabilityComponent`；018 unique 对齐 ORM |
| `platform_core/models/__init__.py` | 修改 | 导出新模型 |
| `backend/app/tenant_isolation.py` | 修改 | `capability_commands` / `capability_components` 进豁免；installs 仍禁止 |
| `backend/app/api/v1/public_skills.py` | 修改 | 双公开端同一枚举；bogus 失败 |
| `backend/alembic/versions/033_t21_capability_commands_components.py` | 新增 | autogenerate CREATE 两表；revises 032 |
| `backend/alembic/env.py` | 修改 | `ALEMBIC_INCLUDE_TABLES` / `ALEMBIC_URL` 供增量 autogenerate |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 作废 bogus→skill；GWT-44 / 30.4 / 双端枚举 |
| `backend/tests/test_saas_isolation.py` | 修改 | T-21 新表豁免夹具；installs 不在清单 |
| `frontend/official/src/pages/Capabilities.tsx` | 修改 | 单一能力市场；五类 Tab；非法失败 |
| `frontend/official/src/App.tsx` | 修改 | `/skills` 与 `/capabilities` 同一页 |
| `frontend/official/src/components/layout/SiteLayout.tsx` | 修改 | 导航只留「能力市场」 |
| `frontend/shared/src/constants/tiers.ts` | 修改 | 五类标签；expert→智能体 |
| `frontend/official` tests / SkillsSection / capabilities.ts | 修改 | CTA / `/skills` 映射 / 非法 type |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：`env.py` 为 autogenerate 增量过滤；本地 MySQL `alembic_version=030` 不可用，用 stamp 032 空库对比）

**未触碰「不许改的文件」**：☑ 确认（未改 uq、未加 TenantMixin、未建 installs/sources/aliases、未碰 LiteLLM compose、未新开评分链）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 公开列表 | 否 | 只读 |
| 033 DDL | 迁移事务 | Alembic |

**事务提交后的操作失败怎么办**：N/A（无提交后外部调用）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（只读） |
| 保证方式 | N/A |
| 重复请求返回 | 同一列表 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| listing | SELECT | N/A |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 公开限流 | 现网 `_enforce_rate_limit` | 否 | Redis 故障 fail-open | 计数窗口 |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— `capability_commands` / `capability_components` 与 `schema.dbml` 一致（`uq_commands_asset` / `uq_components_parent_child` / `idx_components_child`；commands CASCADE；components RESTRICT）

结构核对输出：

```
$ ALEMBIC_URL=sqlite:////tmp/t21-alembic.db ALEMBIC_INCLUDE_TABLES=capability_commands,capability_components \
  uv run alembic -c alembic.ini revision --autogenerate -m "t21 capability commands components"
INFO  Detected added table 'capability_commands'
INFO  Detected added table 'capability_components'
INFO  Detected added index 'idx_components_child'
Generating ...331d7ce228d8_t21_capability_commands_components.py ...  done
```

落盘修订号改为 `033`（head after 032）；`CURRENT_TIMESTAMP` 去 SQLite 括号以对齐 MySQL（031 同形）。未自行加 listing_state / source_id（属 T-23 / T-29）。

**未自行加字段/改类型**：☑ 确认（值域 expand 不改列类型；不改 uq 列集）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `PowerMarketService.parse_asset_type` / `list_public` 记 type/page |
| trace_id | 现网中间件 |
| 错误日志上下文 | `ValidationException` 经统一 handler |
| 慢操作耗时 | N/A 只读列表 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
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

$ uv run pytest -x -q backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_saas_isolation.py
.................................................                        [100%]
49 passed in 13.66s
pytest_exit:0

$ npm run build --prefix frontend/official
> official@0.1.0 build
> react-scripts build
Creating an optimized production build...
Compiled successfully.
official_build_exit:0
```

`llm_gw_grep_exit:1` = 零命中（空输出）。包内注释不出现 `llm_gateway` 字面量。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-30.1 唯一入口「能力市场」 | `SiteLayout.beacon.test` 导航文案；无技能广场并列 | ✅ |
| GWT-30.2 `/skills` 已筛技能 | `SkillsSquare.test` `/skills` → 技能 Tab 选中 | ✅ |
| GWT-30.3 无「专家」作类型名；有「智能体」 | 同上 + `ASSET_TYPE_LABELS` | ✅ |
| GWT-30.4 旧 expert 映射智能体 | `test_public_expert_type_maps_to_agent` | ✅ |
| GWT-44.1 插件筛选只出插件 | `test_public_capabilities_plugin_filter_only` | ✅ |
| GWT-44.2 bogus 失败不得出技能列表 | `test_public_capabilities_invalid_type_fails` + `test_public_skills_invalid_type_fails`；作废 `falls_back_skill` | ✅ |
| GWT-44.3 未选类型五类可出现 | `test_public_capabilities_untyped_five_types` | ✅ |
| GWT-44.4 无第六种公开类型入口 | `test_public_endpoints_share_five_type_enum`；官网 Tab 仅五类+全部 | ✅ |
| NFR-07 `power_market/` 零命中网关字面量 | `grep -rn llm_gateway` exit 1 | ✅ |
| PIT-3 新表豁免同 PR | `test_t21_catalog_tables_exempt_and_installs_not` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 本票只读 listing + DDL，无多步业务写 |
| 幂等 | ➖ N/A | 无创建/订阅写 |
| 并发写 | ➖ N/A | 无条件更新 |
| 外部依赖失败 | 现网 Redis fail-open | ➖ N/A 本票未改限流 |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-07 商店读模型 | `grep -rn llm_gateway backend/services/power_market/` 零命中 | exit 1 / 空 | 仓库工作树 |
| NFR-07 `/skills` 映射 | `/skills` 渲染市场且技能筛 | official jest 绿 | jest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 公开 JSON `asset_type` 只出五类；库内 `expert` 行以 `agent` 出现。FR-33 listing_state 闸未做（T-23）。`/public/skills` 默认仍走 Skill 表发布态（含 recommended）；`type=` 非法两端都 422。 |
| `/frontend` | 官网导航只「能力市场」→ `/capabilities`；`/skills` 同页且默认技能。非法 `?type=bogus` 展示「没有这种类型」。 |
| `/architect` | 无新错误码；422 `VALIDATION_ERROR` +「没有这种类型」。 |
| `/dba` | 033 仅 commands/components；assets 加列 / sources / aliases / installs 仍按票表分票。本地 MySQL 版本表曾停在 030，autogenerate 走 stamp 032 空库。 |

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
- [x] 外部依赖四件套：本票未新增
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报（本地 alembic_version=030，未复活 028–030）
- [ ] 票状态仍 todo（交 orchestrator 改 done）
