# 实现证据 · T-23 查询侧 FR-33 闸+分页 total；详情包含闸；商店不存在句

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-23.md`｜FR 锚点：FR-32 / FR-33 / NFR-01 / NFR-02｜角色：/backend｜日期：2026-09-09
> 上游：ADR-0018 · spec v1.6 FR-32/33 · db-spec `listing_state` / `license` / `public_license_override`
> 泳道：L4

未实现 T-25 安装行写入（订阅 POST listed 返回 `created=false`、无 `capability_installs`）；未实现 T-24 XSS 纯文本节点；未实现 T-28 七叶；未实现 T-33 alias（仅预留 `GET /public/capabilities/aliases` 于动态 `/{type}/{name}` 之前）。未复活 028–030。未代选六问。`power_market/` 零命中 `llm_gateway`。

GET 404 vs POST `MARKET_NOT_FOUND` 拆开：公开详情 GET 未上架/黑名单/从不存在短名 → HTML 404 字节级同形（文案「页面不存在，可能已被移除或地址有误」+「返回首页」，无「已下架」）。订阅 POST 同一三态 → JSON `code=MARKET_NOT_FOUND`，不是 HTML 404。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/public_skills.py` | GET 列表/详情；POST subscribe；aliases 静态段先注册 |
| 字段校验（page/page_size） | Schema | 同上 Query `ge=1, le=50`；Service `_page_size` 双闸 | 默认 20，最大 50 |
| 跨字段参数约束 | Schema | N/A | 单字段分页 |
| 权限判定（数据范围） | Service | `PowerMarketService.list_public` / `get_public` | 查询侧 FR-33；匿名可读 |
| 业务规则/状态流转 | Service | `power_market/service.py` `_fr33_clause` | listed∪coming_soon ∩ stable∪recommended ∩ 许可过闸 ∩ 非软删 |
| 数据读写 | Service 直查（跟 T-21） | `platform_core/models/capability.py` | COUNT 后再 LIMIT；包含走 `capability_components` JOIN |
| 错误码映射 | 统一异常处理器 | `MarketNotFoundException` → 404 JSON；GET miss 走 HTMLResponse | Router 无业务 try/except |
| 幂等 | N/A | 本票不写安装行 | |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/capability.py` | 修改 | `listing_state` / `license` / `public_license_override` + P-M01 索引 |
| `platform_core/exceptions/business.py` / `__init__.py` | 修改 | `MarketNotFoundException` |
| `backend/services/power_market/types.py` | 修改 | FR-33 常量、许可允许集、分页上限、商店不存在句文案 |
| `backend/services/power_market/store_page.py` | 新增 | GET 404 HTML 固定字节 |
| `backend/services/power_market/service.py` | 修改 | 查询侧闸再分页；详情包含；订阅合同（无写行） |
| `backend/services/power_market/__init__.py` | 修改 | 导出 HTML / MARKET_NOT_FOUND |
| `backend/app/api/v1/public_skills.py` | 修改 | 双端同一读模型；GET HTML 404；POST JSON；aliases 预留 |
| `backend/alembic/versions/034_t23_assets_listing_license.py` | 新增 | ADD 三列 server_default；revises 033 |
| `backend/tests/fr33_support.py` | 新增 | 33.2/33.4/33.5 与包含夹具 |
| `backend/tests/test_skill_public_api.py` | 修改 | 技能端 FR-33 / 32.3 / 32.8 / 33.4 / 33.5 |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 能力端同一闸；32.9–32.12 不得互勾；NFR-01 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：加 db-spec 已列三列 + 034；未加 `source_id` / installs / alias 表）

**未触碰「不许改的文件」**：☑ 确认（未写安装行、未迁 XSS、未实现七叶、未实现 alias 解析、未复活 028–030）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 公开列表/详情 | 否 | 只读 |
| 订阅 POST | 否 | 本票不写安装行 |

**事务提交后的操作失败怎么办**：N/A（无提交后外部调用）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（本票不写） |
| 保证方式 | N/A |
| 重复请求返回 | GET 404 HTML 固定字节；POST 同一 `MARKET_NOT_FOUND` 信封 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| listing | SELECT WHERE FR-33 再 COUNT/LIMIT | 空页 `items=[]`、`has_more=false` |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 公开限流 | 现网 `_enforce_rate_limit` | 否 | Redis 故障 fail-open | 计数窗口 |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— `listing_state` VARCHAR(16) NOT NULL server_default `unlisted`；`license` VARCHAR(64) NULL；`public_license_override` SMALLINT NOT NULL default 0；`idx_assets_listing_status_type_cat`。未加 `source_id`（T-29 FK）。未改 `uq_asset_type_name_alive`。

结构核对输出：

```
$ bash tools/check/db_migrations.sh
迁移破坏性变更检测（strong_migrations 语义）
==============================================
✓ 迁移破坏性变更检测通过
mig_exit:0
```

034：`listing_state` / `public_license_override` 均带 server_default（SM-5）。列已在 db-spec，手写 ADD 对齐 033 风格；未复活 028–030。

**未自行加字段/改类型**：☑ 确认（仅落地 db-spec 已列；未发明 listing 表）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_public` / `get_public` / `subscribe_public` / `parse_asset_type` |
| trace_id | 现网中间件 |
| 错误日志上下文 | `MarketNotFoundException` 经统一 handler |
| 慢操作耗时 | NFR-01 curl 计时见 §7 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -x -q backend/tests/test_skill_public_api.py backend/tests/test_b1c_capabilities_coverage.py
....................................................................     [100%]
68 passed in 7.31s
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
```

`llm_gw_grep_exit:1` = 零命中（空输出）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-32.1 说明/许可/来源/宿主 + 可订 | `test_gwt_32_1_listed_detail_subscribable` / `test_gwt_32_1_capability_detail_fields` | ✅ |
| GWT-32.6 未登录去登录、无安装行 | `test_gwt_32_6_anonymous_subscribe_401` | ✅ |
| GWT-32.7 回跳安装行仍 0 | `test_gwt_32_7_login_bounce_no_install_row` / `test_gwt_32_7_logged_in_subscribe_no_install_row` | ✅ |
| GWT-32.2 预告无订阅按钮 | `test_gwt_32_2_coming_soon_no_subscribe_button` / `test_gwt_32_2_coming_soon_capability_no_subscribe` | ✅ |
| GWT-32.3 商店不存在句 HTML | `test_gwt_32_3_unlisted_html_matches_true_404` / `test_gwt_32_3_capability_unlisted_html_404` | ✅ |
| GWT-32.8 POST MARKET_NOT_FOUND JSON | `test_gwt_32_8_subscribe_unlisted_json_not_html` / `test_gwt_32_8_capability_subscribe_market_not_found` | ✅ |
| GWT-32.9 包含 A 与 B | `test_gwt_32_9_includes_a_and_b` | ✅ |
| GWT-32.10 未上架子卡不出现 | `test_gwt_32_10_includes_skips_unlisted` | ✅ |
| GWT-32.11 无 C/D | `test_gwt_32_11_includes_skips_blacklist_and_soft_delete` | ✅ |
| GWT-32.12 无 E/F | `test_gwt_32_12_includes_skips_unlicensed_and_experimental` | ✅ |
| GWT-33.1 已上架可订、预告不可订 | `test_gwt_33_1_listed_appears_coming_soon_not_subscribable` | ✅ |
| GWT-33.2 六行只出前两行 | `test_gwt_33_2_six_row_fixture` / `test_gwt_33_2_capabilities_six_row_fixture` | ✅ |
| GWT-33.3 黑名单走商店不存在句 | `test_gwt_33_3_blacklist_store_not_found` | ✅ |
| GWT-33.4 total=一页、第 2 页空 | `test_gwt_33_4_page2_empty_total_visible_only` / `test_gwt_33_4_capabilities_page2_empty` | ✅ |
| GWT-33.5 第 2 页只有过闸行 | `test_gwt_33_5_page2_only_gated_rows` / `test_gwt_33_5_capabilities_page2_gated_only` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 本票只读 + 订阅不写行 |
| 幂等 | ➖ N/A | 无创建/安装写 |
| 并发写 | ➖ N/A | 无条件更新 |
| 外部依赖失败 | 现网 Redis fail-open | ➖ N/A 本票未改限流 |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-01 | 已上架 ≤400 浏览→卡片可见 P95 < 2s | curl n=20 P95=**0.011931s** min=0.007299 max=0.019106 全 200；`data.total=400` `has_more=true`。TestClient 同夹具 P95=0.006469s | 本地 uvicorn + sqlite 400 listed；`curl -s -o /tmp/t23-nfr-body.json -w '%{http_code} %{time_total}' 'http://127.0.0.1:62224/api/v1/public/capabilities?page=1&page_size=20'` |
| NFR-02 | 列表分页；`total` 与第 2 页成员 | 33.4 total=20 第 2 页空 `has_more=false`；33.5 total=25 第 2 页 5 条且仅 `g335-vis-*` | pytest 双端 |

curl 逐次（秒）：0.019106, 0.011931, 0.009661, 0.008871, 0.008351, 0.007923, 0.008179, 0.008484, 0.008174, 0.007299, 0.007912, 0.008069, 0.008329, 0.008050, 0.008203, 0.008082, 0.008535, 0.008450, 0.008766, 0.008300。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | GET 详情 404 是 **HTML**（`STORE_NOT_FOUND_HTML`），POST 订阅是 **JSON** `MARKET_NOT_FOUND`。夹具 33.4/33.5 不可用「全表一页」空过。包含四格独立。许可默认允许集在 `DEFAULT_ALLOWED_LICENSES`（T-31 可换表）。listed POST 本票不落安装行。 |
| `/frontend` | 列表：`total`/`page`/`page_size`/`has_more`；卡片 `listing_state` + `subscribable`（预告 false，禁止「尚未上架」）。详情 `includes`/`hosts`/`license`。未上架详情按官网 404 文案渲染（后端已返回同形 HTML）。订阅未登录 401。 |
| `/architect` | 无新错误码发明：`MARKET_NOT_FOUND` 按 ADR-0018；预告 POST 预留 `MARKET_COMING_SOON` 409（T-25 可接管写路径）。 |

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
