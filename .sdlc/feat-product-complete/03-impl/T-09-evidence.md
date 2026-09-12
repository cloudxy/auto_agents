# 实现证据 · T-09 令牌打网关用量走；吊销后再打拒绝

> 票：contract §11 T-09（FR-60 + FR-92；spec GWT-60.2/60.3/60.5/60.6/60.8/60.10/60.11 面 + GWT-92.4；QA-20/21 注记）｜角色：/backend｜日期：2026-09-11｜依赖：T-08（已落：签发=网关 HTTP 登记，gateway_key_id=key_alias）

## 0. 网关观察点 OpenAPI/源码实读（本票第一刀，与 T-08 §0 同法）

```
$ docker exec litellm-proxy python3 -c "from litellm.proxy.auth.auth_utils import hash_token; import hashlib, inspect; print(inspect.getsource(hash_token)); print(hash_token('sk-abc') == hashlib.sha256(b'sk-abc').hexdigest())"
def hash_token(token: str):
    import hashlib
    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    return hashed_token
True
```

核对结论（钉 tag `ghcr.io/berriai/litellm:v1.100.0`，容器内源码 + /openapi.json 实读，未对运行网关做任何写）：

| 端点 | 请求 | 关键事实 |
|---|---|---|
| `GET /key/info?key=<k>` | key 收 **明文或其 sha256 hash**（`_hash_token_if_needed`：sk- 开头才 hash，否则原样） | 网关 token 列 == `sha256(明文)` == **本地 `relay_tokens.key_hash`** → 明文永不出库即可查询。`info` 行含 `spend`(USD)/`last_active`/`key_alias`，**无 token 计数**（VerificationToken 全字段实读核对）；Key 已作废 → 404 |
| `GET /spend/logs/v2?key_alias=<alias>&page=&page_size=` | 分页，响应 `{data, total, page, page_size, total_pages, total_is_capped}` | rows 含 `total_tokens`(int)——**按 Key 累计 token 的可得口径**。`/key/spend/report` 强制日期窗 + 最大天数限，不适合累计；`/spend/logs`(v1) 已标 deprecated + 10k 截断 → 弃用 |

**实现含义（unit 决策，§8 已回报 architect/dba）：** db-spec §12 命名「key info HTTP」；v1.100.0 的 key info 行只有 USD spend，无 token 计数，而 `used_tokens`/`quota_tokens` 是 token 单位。故观察 = **key info（last_active/存在性）+ spend logs v2（total_tokens 累计）** 两调用，均在 ADR-0019 决策 3「用量观察点 = 网关 spend / key info HTTP」族内。

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 令牌详情（回写触发点 1，单次） | Router+Service | `backend/app/api/v1/relay.py::get_token` / `backend/services/relay_service.py::get_token` | 详情先观察网关再回写；网关不可达 → 200 + 本地缓存数据 + message=60.5 句族（数字不显示「已用完」） |
| 显式刷新（回写触发点 2，按页批量） | Router+Service | `relay.py::refresh_token_usage` / `relay_service.refresh_tokens_usage` | 本企业全部「已登记且未吊销」行；网关不可达 → 502 `LLM_GATEWAY_UNREACHABLE`（60.5 句族，非套餐句）；审计 `relay.token.refresh_usage` |
| `list_tokens` 列表读模型 | Service（**零改动**） | `relay_service.list_tokens` | QA-08：列表只读本地 `used_tokens` 缓存列，**禁止每行打网关**——git diff 核对 UNTOUCHED，测试断言管理面零新调用 |
| 网关观察 HTTP（key info / spend v2） | 适配叶 | `backend/services/llm_gateway/admin.py::get_key_info / list_key_spend_logs` | 复用 `_http_json`（master 鉴权、超时、trust_env=False）；transport 测试缝同款 |
| 回写本地缓存列 | Service | `_apply_usage` | `used_tokens` + `last_used_at`（←info.last_active）+ `spend_synced_at=now`（naive UTC）；041 既有列，零新迁移 |
| GWT-92.4 事件 | Service | `_emit_usage_event` → `emit_product_event` | 仅 **0→≥1 跃迁**（old 在改写前捕获）上报 `relay_token_call_succeeded`（tenant_id、token_id/group_id/used_tokens，无明文）；fail-open 不挡主路径 |
| 60.5 句族单一真相 | 常量 | `relay_service.MSG_GATEWAY_UNREACHABLE = quota_service.GATEWAY_UNREACHABLE_USER`（「平台 LLM 网关不可达」） | 复用已兑 FR-74 冻结句，不另造第二套 |
| 吊销双闸（QA-20） | 既有 T-08 路径 + 测试 | `revoke_token` | 网关 `/key/delete` 作废 + 本地 revoked；测试钉「再打 Base URL → 401」 |
| 跨企业 404 同形（60.8） | 既有 Service 主键+租户过滤 | `_owned_token` | 详情/吊销共用的租户收口查询 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ relay→llm_gateway.admin 为 ADR-0019 点名既有边（B4 通过）☑ relay→quota_service 仅取冻结句常量（spider 域同款先例）☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/llm_gateway/admin.py` | 修改 | 新增 `get_key_info` / `list_key_spend_logs`（用量观察 HTTP） |
| `backend/services/relay_service.py` | 修改 | 新增 `get_token` / `refresh_tokens_usage` / `_observe_gateway_usage` / `_apply_usage` / `_emit_usage_event` / `_owned_token` / `_parse_gateway_dt`；常量 `MSG_GATEWAY_UNREACHABLE`；**list_tokens 零改动** |
| `backend/app/api/v1/relay.py` | 修改 | 新增 `GET /tokens/{token_id}`、`POST /tokens/refresh-usage`（route 形面见 §3 尾注） |
| `backend/tests/test_relay_token_usage.py` | 新增 | 8 测：60.3 全链路+92.4、60.2+QA-08、QA-20、60.5、60.10、60.6、60.8、出站钥匙打 chat 拒绝；内嵌 `_FixtureGateway`（QA-21 等价桩） |

> 共享工作树：`git status` 中的其余改动属并行票（T-10 前端 relay 面、deploy/litellm 等），本会话未触碰；`relay.py` 的 diff 含 T-07/T-08 未提交部分（各自 evidence 已落）。

**与票面边界核对**：☑ 不动 T-10 UI ☑ 不动 `list_tokens` 列表读路径 ☑ 未打开 `LLM.ENABLED` / 未填上游 key（60.5 走不可达句）☑ 未 git commit

## 3. 关键实现决策

### 用量回写触发点（票面要求说明）

| 触发点 | 入口 | 网关调用 | 写入 |
|---|---|---|---|
| 令牌详情（单次） | `GET /api/v1/relay/tokens/{token_id}` | `GET /key/info?key=<key_hash>` + `GET /spend/logs/v2?key_alias=<alias>`（≤10 页/次） | `used_tokens`/`last_used_at`/`spend_synced_at`；跃迁则事件 |
| 显式刷新（按页批量） | `POST /api/v1/relay/tokens/refresh-usage` | 同上 × 本企业未吊销已登记行 | 同上，单事务整批 |
| 列表渲染 | `GET /api/v1/relay/tokens` | **零**（QA-08） | 无 |

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 网关观察（纯读 HTTP）+ 本地回写 commit | 否（观察在事务外/写前） | 事务里无外部调用（红线）；先观察后写入 |
| 刷新批量多行回写 | 是（单 commit） | 整批原子：任一行网关失败 → rollback + 502，零半批状态 |

**提交后操作失败**：事件上报（`relay_token_call_succeeded`）在 commit 后、独立短会话、fail-open（GWT-92.6 同口径——上报失败只告警，回写不回滚）。

### 幂等 / 防重

| 项 | 内容 |
|---|---|
| 事件防重 | 跃迁判定 `old==0 && new>=1`（old 改写前捕获）；已 ≥1 的重复观察不上报（测试钉住二次详情/刷新后事件数仍为 1） |
| 回写收敛 | `used_tokens` 以网关观察为准写整值（本地=缓存，网关=金标，db-spec §12）；`max(0,·)` 防负 |

☐ 未使用「先查后插」（纯 UPDATE 已载入行，主键+tenant_id 收口）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 同令牌并发详情/刷新 | 行级最后写胜（缓存列语义，下次观察自愈）；UPDATE 天然带 tenant_id 载入（60.10 面） | —（无状态机流转） |

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM 管理 HTTP（key info / spend v2） | `LITELLM.TIMEOUT`（既有） | 无（显式动作失败可见；自动重试会在不可达期放大延迟） | **详情**：降级本地缓存 + 60.5 句 message（数字不清零不顶满）；**刷新**：502 `LLM_GATEWAY_UNREACHABLE` 句族 | 是（纯读） |

**Route 形面**：`POST /tokens/refresh-usage` 为字面路径，与既有 `POST /tokens`（签发）、`DELETE /tokens/{id}`、`GET /tokens/{id}` 无方法+形状冲突（PIT-1 静态段序不适用——无同形动态段在前）。

## 4. ORM 与 DB 对齐

零新迁移。写入仅 041 既有列：`used_tokens`（INT）、`last_used_at`（tz-aware，← `info.last_active` ISO 解析）、`spend_synced_at`（**naive** UTC，按列型 `DateTime()`）。☑ 字段名/类型/可空性未动 ☑ 未自行加字段/改类型（需要变更已回 /dba：无）。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `get_token` / `refresh_tokens_usage` / `_observe_gateway_usage` / `_apply_usage` / `_parse_gateway_dt` 各有 logger（R10） |
| 错误日志上下文 | 观察失败记 tenant/token + `err={type(exc).__name__}`（详情降级 / 刷新 502 两分支各一句） |
| 审计 | `relay.token.refresh_usage`（显式刷新）；详情为读面不审计（与既有 issue/revoke 口径一致） |

**脱敏核对**：☑ 无密码 ☑ 无明文 token（网关查询只发 `key_hash`；事件 props 只有 token_id/group_id/used_tokens；日志无明文）

## 6. 自测证据（命令与退出码原样粘贴）

**红（T-09 测试先行，T-08 已绿的代码上）**：

```
$ uv run pytest -q backend/tests/test_relay_token_usage.py
FAILED backend/tests/test_relay_token_usage.py::test_gwt_60_3_chat_authed_usage_moves_and_event
FAILED backend/tests/test_relay_token_usage.py::test_gwt_60_2_viewer_sees_usage_list_reads_local_column_only
FAILED backend/tests/test_relay_token_usage.py::test_qa_20_revoked_token_rejected_on_chat
FAILED backend/tests/test_relay_token_usage.py::test_gwt_60_5_gateway_unreachable_same_then_not_quota
FAILED backend/tests/test_relay_token_usage.py::test_gwt_60_10_tenant_a_call_does_not_move_tenant_b
FAILED backend/tests/test_relay_token_usage.py::test_gwt_60_8_cross_tenant_revoke_and_detail_404
6 failed, 2 passed in 23.29s
```

（红因即票面：`GET /api/v1/relay/tokens/{id}` 路由不存在 → `AssertionError: {"detail":"Method Not Allowed"} assert 405 == 200`——夹具 chat 认证/真实响应体断言全过，失败点正是缺回写触发点；2 个先绿 = 60.6 既有守卫核对与夹具内出站拒绝，钉 oracle 属票面「既有守卫核对+测试」。）

**绿（实现后）**：

```
$ uv run pytest -q backend/tests/test_relay_token_usage.py
........                                                                 [100%]
8 passed in 14.18s
exit: 0
```

**全量（最终代码）**：

```
$ uv run pytest -x -q backend/tests
1449 passed, 37 skipped, 7 warnings in 464.03s (0:07:44)
exit: 0
```

（基线 1414 passed → 1449：+8 全为本票，-0 改。）

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

（`scripts/check-layering.py` 本仓不存在——skill 通用引用；分层由 arch.sh R7/R8/R9 覆盖，通过。）

### 验收项逐条对应

| GWT / 票面项 | 覆盖的测试 | 结果 |
|---|---|---|
| **GWT-60.3**（QA-21/QA-05 夹具口径）Then 三同时 | `test_gwt_60_3_chat_authed_usage_moves_and_event`：真实 HTTP chat（Bearer=签发明文）→ 网关认证通过 + 真实响应体（`chat.completion`/choices/usage.total_tokens≥1，**非裸 200**）；详情回写后 `used_tokens≥1`、`spend_synced_at`/`last_used_at` 落库；信封无 QUOTA/套餐词 | ✅ |
| **GWT-60.2** 只读成员可见（本地列） | `test_gwt_60_2_viewer_sees_usage_list_reads_local_column_only`：viewer 经 `GET /tokens` 列表看到 ≥1；列表前后夹具管理面 hits **零增加**（QA-08） | ✅ |
| **QA-20** 吊销后再打拒绝 | `test_qa_20_revoked_token_rejected_on_chat`：吊销后 chat → 401；本地 status=revoked；详情不再观察已吊销行（管理面零新调用） | ✅ |
| **GWT-60.5** 不可达同一 Then | `test_gwt_60_5_gateway_unreachable_same_then_not_quota`：详情 200 + 缓存数字保持 + message 含「平台 LLM 网关不可达」；刷新 502 + code=`LLM_GATEWAY_UNREACHABLE`；两处均无 QUOTA/套餐词；本地不清零 | ✅ |
| **GWT-60.6** 无入口（既有守卫核对） | `test_gwt_60_6_tenant_no_entry_to_platform_fuse_probe_window`：GET /newapi 数据面 404 同形；PUT 渠道窗口/冷却 → 403 FORBIDDEN + service spy 未调用（窗口不变）。**形态解释见 §8** | ✅ |
| **GWT-60.8** 跨企业 404 同形 | `test_gwt_60_8_cross_tenant_revoke_and_detail_404`：B 吊销/看 A 令牌均 404；A 行 revoked_at=None | ✅ |
| **GWT-60.10** A 不动 B | `test_gwt_60_10_tenant_a_call_does_not_move_tenant_b`：A 全链路后 B used=0、quota JSON 不变、B 明文从未 chat、事件只属 A | ✅ |
| **GWT-92.4** 事件 | 60.3 测内：`relay_token_call_succeeded` 恰 1 条（tenant_id=tid、props.token_id、无明文）；重复观察不重复上报 | ✅ |
| GWT-60.11 面（再进页不见明文） | 60.3 测内 `plaintext_key is None`（主面在 T-08/T-10，此处详情路径复证） | ✅ |
| 出站钥匙打 chat 拒绝（T-05 51.10 同面） | `test_outbound_style_key_rejected_on_chat`：`ok-` 钥匙 → 401；零 spend log（用量基线不变） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | `test_gwt_60_5_...`（刷新整批失败 → rollback 零写入，本地缓存保持） | ✅ |
| 幂等（事件防重） | 60.3 测尾段（二次详情+刷新后事件数仍 1） | ✅ |
| 并发写 | — | ➖ N/A：缓存列最后写胜、无状态机流转；60.10 隔离面已钉 |
| 外部依赖失败 | 60.5（详情降级 / 刷新 502 两分支）+ QA-20（网关拒绝面） | ✅ |

## 7. NFR 验证

票内无 NFR 条目（NFR-06 归 T-10；NFR-04 密钥不落库已由 §5 脱敏核对覆盖）。➖

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 夹具是 **QA-21 允许的等价桩**（真实 HTTP 服务 + 真实 Bearer 鉴权 + 真实 chat 响应体 + key info/spend 应答按 v1.100.0 实读 schema）；**对真网关**的 key-hash 查询语义、spend/logs/v2 `key_alias` 过滤、吊销后 `/key/info` 404 行为需真网关复核——本票未对运行网关做写操作。② spend 日志翻页上限 10 页/令牌/次刷新（正常单 Key 远达不到；超出按已读页合计，属缓存近似）。③ 漂移窗口：本地 active 但网关侧 Key 已被外删 → key info 404 → 按不可达句族降级（不误判套餐）。④ 详情降级形态 = 200 + data(本地缓存) + message=60.5 句——渲染「已用完」禁止（60.5） |
| `/architect` | ① **unit 决策**：v1.100.0 key info 行无 token 计数（仅 USD spend，容器内 VerificationToken 全字段实读），token 口径取 `/spend/logs/v2` 的 `total_tokens` 累计——两调用均属 ADR-0019「spend / key info HTTP」族，但 db-spec §12 字面只点名 key info；如 dba 认为应改口径请裁决（改动面：`_observe_gateway_usage` 单函数）。② **GWT-60.6 形态**：「直打同形」在 GET/页面面 = 404 同形（`require_platform_admin_or_404`，GWT-07.3 既有）；写面（改窗口/冷却/上游）= 403 FORBIDDEN + 越权记录——**GWT-70.3 既有测试冻结 403**（test_newapi_api.py / test_b1c_newapi_channels_coverage.py），本票未改守卫（避免同屏 Then 互否）；若 60.6 要求写面也 404 同形需 pm/architect 裁决后统一改守卫+测试 |
| `/frontend`（T-10） | 新增面：`GET /api/v1/relay/tokens/{id}`（详情；message 携带 60.5 句时=用量观察降级，仍渲染缓存数字）；`POST /api/v1/relay/tokens/refresh-usage`（显式刷新，返回全量令牌列表；502=`LLM_GATEWAY_UNREACHABLE` 走失败句）。列表数字仍读 `GET /tokens` 本地列 |
| `/dba` | `used_tokens` 写点已按 §12 落地（RelayService 单写方；触发点=详情/显式刷新；list 禁打网关）；`spend_synced_at` 写 naive UTC（列型 `DateTime()`）——如需 tz-aware 列型属 expand 变更 |

## 9. 交票自检

- [x] 每条验收项有 evidence（红+绿原样）
- [x] 自测全绿（全量 1449 passed / 37 skipped；arch 0 违规；ruff 0）
- [x] 契约落位表已核对，分层无违规（R7/R8/R9/B4）
- [x] ORM 与 DBML 一致，未自行加字段（零新迁移）
- [x] 无硬编码连接串/密钥/端口/阈值（网关地址/密钥/超时走 `LITELLM.*`；句族复用 quota_service 冻结句）
- [x] async 上下文无同步阻塞调用（httpx.AsyncClient；rollback 后过期对象用重新 SELECT 取值，P-BE-01）
- [x] 无 `except: pass`（降级/失败分支均有 warning 日志）
- [x] 日志已脱敏（明文不出 service；网关查询只发 hash）
- [x] 事务里无外部调用（观察在写事务之外）
- [x] 幂等未用「先查后插」
- [x] 条件更新 `rows == 0`（N/A——无状态机）
- [x] 外部依赖四件套（§3 表）
- [x] 四类易漏测试覆盖或 N/A 给理由
- [x] 上游问题回报（§8 两条 architect 裁决项），未自行绕过
