# 实现证据 · T-05 出站拉数执法 + 与渠道组互否 + 签发事件

> 票：contract §11 T-05 + §7.3｜FR 锚点：FR-51（GWT-51.1 后半、51.3/51.4/51.6/51.7/51.10）+ FR-92（GWT-92.3）｜角色：/backend｜日期：2026-09-11
> 依据：contract §7.3 + §2.3 边界强制 + ADR-0020 + spec FR-51/FR-92 + T-04 交接（前缀 `ok-`、`outbound_key_service.py` 扁平风格）
> 范围闸：不动 T-04 域文件结构（只扩方法）、不碰 relay_service、网关侧拒绝句归 T-08/T-09（本票只文档化 + 钉不变量）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 查找链编排（出站钥匙表 → KEY_BINDINGS → 401） | Router 助手（external_api） | `backend/app/external_api/v1/public.py` `_require_bound_tenant` | 协议胶水：两环命中记链路日志，未命中 401（与 FR-13 同一拒绝句）不查结果库 |
| 查找链第一环执法（sk- 不进查找 / revoked / 乱填 → None） | **Service** | `backend/services/outbound_key_service.py` `resolve_active_tenant` | 业务规则在 Service；SHA-256 指纹 + `hmac.compare_digest`（SEC-1） |
| 查找链第二环（KEY_BINDINGS 恰好一租户） | 既有配置读 | `backend/app/external_api/v1/webhooks.py` `bound_tenant_id` | **零改动**（仅 docstring 标注它是第二环）；FR-13 行为原样 |
| 指纹取行（revoked_at IS NULL 守卫） | Repository | `backend/repositories/outbound_key_repository.py` `get_active_by_hash` | 只碰 outbound_keys 一张表；吊销即不命中（GWT-51.7） |
| 签发事件 `outbound_key_issued`（tenant_id，无明文） | Service（commit 后） | `backend/services/outbound_key_service.py` `issue_key` | T-04 未挂 → 本票补挂；失败不挡签发（GWT-92.6） |
| 本企业非候选过滤（`source <> marketplace`） | 既有 Service | `backend/services/spider_query_service.py` `query_public_results` | **零改动**，语义保持（FR-11/FR-13） |
| 51.10 互否（ok- 不进任何网关鉴权路径） | 文档化 + 测试钉 | `outbound_key_service.py` 模块 docstring + `test_gwt_51_10_*` | 后端无钥匙形态的 chat 鉴权入口（chat 走 LiteLLM 直连；适配叶只持 master）→ 无需加拒绝分支 |

**分层依赖核对**：☑ Router/external_api 未 import ORM（import 的是 Service） ☑ Service 未返回 ORM 对象（只回 `Optional[int]`） ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（arch.sh R7/R8 绿）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/external_api/v1/public.py` | 修改 | `_require_bound_tenant` 转 async + 双环查找链 + 链路日志；端点 docstring 更新 |
| `backend/app/external_api/v1/webhooks.py` | 修改 | 仅 docstring：`bound_tenant_id` 标注为查找链第二环（逻辑零改动） |
| `backend/services/outbound_key_service.py` | 修改 | +`resolve_active_tenant`；`issue_key` commit 后挂 `outbound_key_issued` 事件；模块 docstring 写入 X-KEY 互否不变量（无 `llm_gateway` 字面量，保 grep 零命中） |
| `backend/repositories/outbound_key_repository.py` | 修改 | +`get_active_by_hash`（指纹 + revoked 守卫） |
| `backend/tests/test_outbound_pull_enforcement.py` | 新增 | 9 测：GWT-51.1 后半/51.3/51.4/51.6/51.7/51.10 + FR-13 链回退 + GWT-92.3/92.6 |

**与票里「会改哪些文件」一致**：☑ 是（执法面 = external_api 入口 + 出站域两文件 + 测试；未动 T-04 域文件结构、未碰 relay_service）

**未触碰「不许改的文件」**：☑ 确认（`relay_service.py`、`backend/services/llm_gateway/**`、T-04 四层结构均未动；git status 核对）

## 3. 关键实现决策

### 查找链（ADR-0020 §2）

```
X-API-Key ──► 第一环：outbound_keys（key_hash 等值 + compare_digest，revoked_at IS NULL）
                 │命中 → tenant_id（只拉本企业非候选行）
                 ▼未命中（含 sk- 前缀直接跳过本环 = 查找集合不相交，GWT-51.6）
             第二环：KEY_BINDINGS（既有平台配置绑定，恰好一租户；FR-13 不放宽）
                 ▼未命中
             401「Invalid API Key」，不查结果库（0 行，GWT-51.3）
```

- `source <> marketplace` 谓词在既有 `query_public_results` 不动——本票只换「钥匙→tenant_id」的解析来源，行过滤语义保持。
- sk- 形态守卫在 **第一环入口**（Service）：`startswith("sk-")` 直接不进出站表查找。KEY_BINDINGS 是平台显式配置，不受该守卫影响（操作员若显式绑定 sk- 字符串属平台决策，不属租户互否面）。

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 拉数（只读：钥匙解析 + 结果查询） | 否 | 单读路径无写 |
| 签发（T-04 既有 insert）→ 事件（独立短会话） | 否 | 事件走 `emit_product_event` 独立会话，在签发 commit **之后**；失败不回滚钥匙（GWT-92.6） |

**事务提交后的操作失败怎么办**：事件失败 → `emit_product_event` 自吞异常记 warning（至少一次语义、不挡主路径）；钥匙行已落库，不产生孤儿外部资源（本域零外部调用）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（本票无新写路径；查找是只读） |
| 保证方式 | 既有 `uk_outbound_keys_key_hash`（迁移 041）兜底指纹唯一 |
| 重复请求返回 | 重复拉数 = 幂等读 |

☑ 未使用「先查后插」（无插入）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 吊销后并发拉数 | 既有条件写 `revoked_at`（T-04）；查找侧 `revoked_at IS NULL` 守卫 | 查不到 active 行 → None → 401（0 行），无 TOCTOU 窗口（吊销提交后即不可见） |

☑ 所有条件更新的返回行数都有处理（本票无新条件写）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无（本票零新增外部调用；事件走本地库） | — | — | — | — |

NFR-04 落点：明文只在签发响应出现一次（T-04）；本票新增路径（查找/事件/日志）全部只处理指纹与 tenant_id，明文与指纹都不落日志、不进事件。

## 4. ORM 与 DBML 对齐

本票零 schema 改动（无新表/列/索引/迁移）。`get_active_by_hash` 依赖既有 `uk_outbound_keys_key_hash`（迁移 041，T-04 交付，真库对拍过）。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `service.outbound`：`resolve_active_tenant` 入口 `logger.info`（链=出站钥匙表 形态=非sk-，无明文/指纹）；`public.py`：命中环别 info / 双环未命中 warning（R10 + 执法留痕） |
| 错误日志上下文 | 拒绝面只记链路与原因分类（未绑定/已吊销/他形态），不带钥匙材料 |
| 事件 | `outbound_key_issued`：tenant_id / actor_user_id / role / props={key_id}——**无明文、无前缀**（连前缀片段都不进事件，GWT-92.3 测试断言） |

**日志脱敏核对**：☑ 无明文钥匙 ☑ 无 hash 全量 ☑ 无密码/token（事件 props 经 `strip_secret_props` 二道闸）

## 6. 自测证据（命令与退出码原样粘贴）

**红（TDD：测试先行；实现未落时全状态首跑）**

```
$ uv run pytest -q backend/tests/test_outbound_pull_enforcement.py
4 failed, 5 passed in 4.36s
FAILED test_gwt_51_1_latter_half_outbound_key_pulls_own_rows   # 401：ok- 钥匙无解析路径
FAILED test_gwt_51_4_tenant_a_key_never_returns_tenant_b_rows
FAILED test_gwt_51_7_revoked_key_pull_zero_rows
FAILED test_gwt_92_3_issue_event_has_tenant_no_plaintext       # 0 事件
exit: 1
（5 passed = 拒绝面回归钉：51.3/51.6 当时因 KEY_BINDINGS 环未命中而绿——实现后拒绝理由变为「链未命中/sk- 不进查找」，拒绝结果不变）
```

**红复核（精确探针：仅回退 public.py 查找链，保留 T-04 域）**

```
$ git stash push -m t05-red-public -- backend/app/external_api/v1/public.py && \
  uv run pytest -q backend/tests/test_outbound_pull_enforcement.py
3 failed, 6 passed in 9.12s        # 51.1 后半 / 51.4 / 51.7 红；92.3 此时绿（事件在 Service，未回退）
exit: 1
$ git stash pop                     # 改动原样恢复
```

**绿（本票域）**

```
$ uv run pytest -q backend/tests/test_outbound_pull_enforcement.py
.........                                                          [100%]
9 passed in 9.70s
exit: 0
```

**邻域回归（FR-13 既有面 + T-04 + 渠道组）**

```
$ uv run pytest -q backend/tests/test_external_api.py backend/tests/test_outbound_keys.py \
  backend/tests/test_relay_token_gateway.py backend/tests/test_relay_group_empty_state.py
................................................                   [100%]
48 passed in 5.79s
exit: 0
```

**全量后端套件**

```
$ uv run pytest -x -q backend/tests
1441 passed, 37 skipped, 7 warnings in 446.82s (0:07:26)
exit: 0
```

**架构红线 / lint**

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

**契约 §2.3 边界 grep（执法面同查，原样执行）**

```
$ grep -rnE 'backend\.services\.relay|llm_gateway' backend/services/outbound_key_service.py backend/app/api/v1/outbound_keys.py
exit: 1        # 零命中：出站域不引用渠道组/网关适配包（互否=结构不相交，非运行时判断）
$ grep -rnE 'outbound_key|KEY_BINDINGS' backend/services/relay_service.py
exit: 1        # 零命中：渠道组不把出站凭证当令牌
$ grep -rnE 'LITELLM\.DB_DSN' --include='*.py' backend/
backend/tests/test_llm_probe.py:163:    assert "LITELLM.DB_DSN" not in probe_src + sched_src
exit: 0        # 唯一命中是「断言不存在」的测试自身；生产代码零 DSN
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-51.1 后半（拉到行） | `test_gwt_51_1_latter_half_outbound_key_pulls_own_rows`（真实 DB 全链：签发→X-API-Key→本企业行） | ✅ |
| GWT-51.3 未绑定/乱填 → 0 行 | `test_gwt_51_3_unbound_or_garbage_key_rejected_zero_rows`（ok- 形态未签发 / 乱填 / 空） | ✅ |
| GWT-51.4 跨企业 → 0 行 | `test_gwt_51_4_tenant_a_key_never_returns_tenant_b_rows`（同名爬虫双企业夹具） | ✅ |
| GWT-51.6 渠道组 sk- 当出站 → 0 行 + 不入列 | `test_gwt_51_6_relay_sk_token_rejected_and_not_listed`（T-08 桩签发真 sk-；同企业令牌也拉不到自家数据） | ✅ |
| GWT-51.7 吊销后再拉 → 0 行 | `test_gwt_51_7_revoked_key_pull_zero_rows`（拉到行→吊销→再拉 401） | ✅ |
| GWT-51.10 ok- 打网关路径 | `test_gwt_51_10_outbound_key_rejected_on_gateway_paths_no_usage_side_effect` | ✅（钉不变量，见下注） |
| FR-13 保持（链回退） | `test_chain_fallback_key_bindings_still_works` + 既有 `test_external_api.py` GWT-13.1–13.4 全绿 | ✅ |
| GWT-92.3 签发事件无明文 | `test_gwt_92_3_issue_event_has_tenant_no_plaintext`（props={key_id}；明文与前缀片段都不进事件） | ✅ |
| GWT-92.6 事件失败不挡主路径 | `test_gwt_92_6_event_failure_does_not_block_issue`（_persist_event 抛错仍 201 + 行落库） | ✅ |

**51.10 实现归属说明（票面口径）**：后端**没有**钥匙形态的 chat 鉴权入口——渠道组 Base URL（LiteLLM）由租户客户端直打，后端 chat 适配叶只持 master（`llm_gateway/_settings._auth_headers`）。故 relay 域无需加拒绝分支。本票落三断言：(1) 适配叶鉴权头只可能是 master，ok- 钥匙从不被携带（ok- 也从不注册进网关——§2.3 grep 钉死结构不相交）；(2) 网关管理既有路由对 Bearer ok- 一律非 2xx 且可见处无 `QUOTA_EXCEEDED`（非套餐句）；(3) 尝试前后渠道组 `used_tokens` 相对基线不变。LiteLLM 侧对未知钥匙的 401「网关不认」与稳定拒绝句归 T-08/T-09 e2e（QA-20 同族）。

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（拉数零写；签发单语句 insert，无多步事务可回滚） | |
| 幂等 | `test_gwt_51_7_revoked_key_pull_zero_rows`（重复拉数=幂等读；吊销即不可见） | ✅ |
| 并发写 | ➖ N/A（无新写路径；吊销/签发并发面在 T-04 已由 revoked 守卫覆盖） | |
| 外部依赖失败 | `test_gwt_92_6_event_failure_does_not_block_issue`（事件面失败降级为 warning） | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-04 | 明文只一次；事件/日志不含明文 | 92.3 测试断言事件全行（含 props JSON dump）无明文、无前缀片段；查找链日志只记链路分类 | SQLite 单测库 + TestClient |
| SEC-1 | hash 存；compare_digest；跨企业 0 行 | `resolve_active_tenant`（SHA-256 + `hmac.compare_digest`）+ 51.4 测试 | 同上 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 51.6/51.10 的「网关不认」终局 401 来自 LiteLLM 本体（后端结构上不可能注册 ok-），e2e 请按 T-08/T-09 桩口径或真网关复核；② 拒绝面 HTTP 形态 = 401 `{"detail":"Invalid API Key"}`（与 FR-13 既有面同句同码，票面「同一拒绝」即此）；③ 51.10 后端侧只有不变量测试（非 2xx + 非 QUOTA_EXCEEDED + 用量不变），不是新拒绝分支 |
| T-08/T-09（backend） | 网关侧若未来出现「后端代收 chat」入口，需按前缀形态拒绝 ok-（票面已授权一处 if，不 import 出站域）；本票未加（无该入口） |
| `/frontend`（T-06） | 拉数端点与用法不变（`GET /external/v1/public/data/{spider}` + `X-API-Key`）；出站钥匙从签发响应即可用，无需二次激活 |
| `/architect` | contract §2.3 grep 路径写的是目录 `backend/services/outbound_keys/`，T-04/T-05 均按仓内扁平风格落 `outbound_key_service.py`（单文件）——挂 lint 前需改 grep 路径（T-04 §8 已报，本票沿报；成功检查按票面文件级 grep 已零命中） |
| 管理窗 | 全量 1441 passed（共享工作树较 T-04 时的 1364 增长来自并行泳道合入，非本票）；本票 9 测全绿、arch/ruff/边界 grep 全绿 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样；红/绿双跑）
- [x] 自测全绿（本票 9 + 邻域 48 + 全量 1441 passed / 37 skipped，exit 0）
- [x] 契约落位表已核对，分层无违规（arch.sh 13 红线 + 4 边界全绿；Router 未 import ORM）
- [x] ORM 与 DBML 一致，未自行加字段（零 schema 改动）
- [x] 无硬编码连接串/密钥/端口/阈值（sk-master-marker 等仅测试内标记并 try/finally 恢复）
- [x] async 上下文无同步阻塞调用（无 redis 路径；事件走既有 async 通道）
- [x] 无 `except: pass`（事件失败走既有 warning 通道，非本票新增吞异常）
- [x] 日志已脱敏（无明文/hash 全量/前缀）
- [x] 事务里无外部调用（事件在 commit 后独立会话）
- [x] 幂等未用「先查后插」（无插入路径）
- [x] 条件更新的 `rows == 0` 已处理（本票无新条件写；既有 revoked 守卫语义核对）
- [x] 外部依赖四件套 N/A（零新增外部调用，已给理由）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8 grep 路径沿报），未自行绕过
- [x] 票状态：backend 侧 T-05 交付（state 由管理窗翻）
