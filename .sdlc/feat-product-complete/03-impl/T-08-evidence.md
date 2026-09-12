# 实现证据 · T-08 签发/吊销登记 LiteLLM 虚拟 Key（HTTP，禁 DSN）

> 票：contract §11 T-08（FR-60 / ADR-0019）｜GWT 锚点：GWT-60.1 签发半程（明文一次）+ 吊销（QA-20 前置）｜角色：/backend｜日期：2026-09-11

## 0. OpenAPI 核对（票面第一刀，实读非猜测）

```
$ docker inspect litellm-proxy --format '{{.Config.Image}} {{.State.Status}}'
ghcr.io/berriai/litellm:v1.100.0 running
$ curl -s http://127.0.0.1:4000/openapi.json   # 只读核对，未对运行网关做任何写
```

核对结论（钉 tag `ghcr.io/berriai/litellm:v1.100.0`，与 `deploy/litellm/docker-compose.yml` 注释一致）：

| 端点 | 请求 schema | 关键字段 | 响应 |
|---|---|---|---|
| `POST /key/generate` | `GenerateKeyRequest` | `key_alias`、`models[]`、`rpm_limit`、`tpm_limit`、`metadata{}` | `GenerateKeyResponse` 含 `key`（明文一次）、`token_id`、`expires` |
| `POST /key/delete` | `KeyRequest` | **只有 `keys[]` / `key_aliases[]`，无 `key_ids`** | — |

**实现含义**：明文不落库 ⇒ 吊销只能按 `key_aliases` 作废 ⇒ 本地 `relay_tokens.gateway_key_id` 存 **`key_alias`**（不透明稳定引用，满足 041 列语义与 UNIQUE；ADR-0019 决策 1 写「gateway_key_id / token id」，但同文规定「路径以钉的 tag OpenAPI 为准」——本 tag 下 token_id 不可用于删除，alias 是唯一可作废引用）。

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 网关 Key HTTP（generate/delete） | 适配叶 | `backend/services/llm_gateway/admin.py` | `generate_key` / `delete_key`，复用 `_http_json`（master 鉴权、超时、`trust_env=False`）；transport 测试缝与既有九函数同款 |
| 签发=网关登记在前（ADR-0019 决策 1/5） | Service | `backend/services/relay_service.py::issue_token` | `_register_gateway_key` 先行；组 `models`/`rpm`/`tpm` 映射限额（0/空=缺省不下发） |
| 网关失败=签发失败可见 | Service | 同上 | `httpx.HTTPError` 或响应无明文 → `BusinessException(502, RELAY_GATEWAY_UNAVAILABLE)`；**零本地行**（禁「列表有网关无」） |
| 明文只回一次 | Service | 同上 | 明文来自网关响应，仅签发响应体回传；本地只 `key_hash`+`key_prefix`+`gateway_key_id` |
| 吊销=网关作废+本地 revoked | Service | `revoke_token` | 网关 `/key/delete` 在前，失败不本地假吊销；已吊销幂等（不重复打网关）；`gateway_key_id IS NULL`（040 骨架行）只本地吊销 |
| 本地存网关引用（041 列） | Service | 同上 | `gateway_key_id=key_alias`；**无新迁移**（041 已含列+UNIQUE，票面确认勿重复建） |
| 审计/信封 message | Router | `backend/app/api/v1/relay.py` | 签发成功 message「明文只显示这一次…」 |

**分层依赖核对**：☑ Router 未 import ORM ☑ relay_service → `llm_gateway.admin` 是 ADR-0019 点名的既有边（B4 只禁 power_market/ai_planner/outbound 域；出站域未触碰）☑ Service 未返回 ORM ☑ ORM/Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/llm_gateway/admin.py` | 修改 | 新增 `generate_key` / `delete_key`（Key 管理 HTTP）；docstring 注明 ADR-0019 |
| `backend/services/relay_service.py` | 修改 | `issue_token` 重写签发序（网关→本地）、`revoke_token` 网关作废、`_register_gateway_key` / `_discard_gateway_key` / `_gateway_alias`；502 失败句常量 |
| `backend/tests/test_relay_token_gateway.py` | 新增 | 6 测：登记成功+明文一次、零限额缺省映射、网关 5xx/不可达失败无行、吊销作废+幂等、吊销失败保持 active+恢复 |
| `backend/tests/test_billing_relay.py` | 修改 | 骨架签发/吊销测挂网关桩（`monkeypatch gateway_admin.generate_key/delete_key`）——T-08 后签发天然依赖网关可达 |
| `backend/tests/conftest.py` | 修改 | **顺带授权的测试基建修复（仅此一处）**：`_purge_quota_count_keys` 同口径补清 `login_fail:*`（既有缺口：本机 Redis 限流计数跨测试存活曾致 `test_gwt_15_4` 假红） |

**与票里「会改哪些文件」一致**：☑ 是。**未触碰**：☑ 不动 T-09（用量走+调用执法）、T-10（Base URL 用法页）、迁移目录、db-spec、edge-states；未 git commit。

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 网关 `/key/generate` + 本地 insert/commit | 否（网关在事务外先行） | ADR-0019 决策 1「本地落 hash 之前」；事务里无外部调用（交票自检红线） |

**事务提交后的操作失败怎么办**：反向问题——网关成功而本地 commit 失败 ⇒ `_discard_gateway_key` 按 alias 尽力作废孤儿 Key（失败仅告警，可经 `/key/list` 对账）；不产生「网关有本地无」的失控行。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 网关 `key_alias = relay-t{tid}-g{gid}-{uuid8}`（每次签发新 alias ⇒ 新网关 Key，重复签发=两把钥匙，非幂等语义，契约如此） |
| 保证方式 | 本地 `uk_relay_tokens_gateway_key_id`（041）+ LiteLLM alias 唯一性；alias 撞库由网关报错 → 签发失败可见 |
| 重复吊销 | 已 revoked 直接返回，不再打网关（测试钉住 `len(del_calls) == 1`） |

☐ 未使用「先查后插」（吊销走主键查找=读路径）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 吊销并发 | 单行 `revoked_at` 置位，重复吊销幂等分支 | —（`row is None` → 404 同形既有） |

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM 管理 HTTP（generate/delete） | `LITELLM.TIMEOUT`（60s，`_settings` 既有） | 无重试（签发是用户显式动作，失败可见即可，自动重试会产生孤儿 Key） | **无本地假成功**：502 `RELAY_GATEWAY_UNAVAILABLE` + 中文可见句（60.5 同族，非套餐句、无 `QUOTA_EXCEEDED`） | generate 否 / delete 是（重复 delete 同 alias 幂等报错不影响本地终态） |

## 4. ORM 与 DB 对齐

零新迁移。写入仅用 041 既有列：`relay_tokens.gateway_key_id`（存 alias，191 宽度内）、`key_hash`、`key_prefix`。☑ 未自行加字段/改类型（需要变更已回 /dba：无）。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `issue_token` / `revoke_token` 含 tenant/role/group(token)；`_register_gateway_key` 记 alias（不透明引用可记）；`_discard_gateway_key` 失败告警 |
| 错误日志上下文 | 网关失败记 `err={type(exc).__name__}` + tenant/group——**无明文 key、无响应体**（明文只经签发响应回传一次） |
| 脱敏核对 | ☑ 无密码 ☑ 无明文 token（`raw` 不入任何日志/事件/审计 target） |

## 6. 自测证据（命令 + 退出码原样）

**红（T-08 测试先行，T-07 已绿的代码上）**：

```
$ uv run pytest -q backend/tests/test_relay_token_gateway.py
FAILED ...::test_issue_registers_gateway_key_and_plaintext_once
FAILED ...::test_issue_group_without_limits_omits_zero_limits
FAILED ...::test_issue_gateway_5xx_visible_no_local_row
FAILED ...::test_issue_gateway_unreachable_visible_no_local_row
FAILED ...::test_revoke_invalidates_gateway_then_local
FAILED ...::test_revoke_gateway_failure_keeps_active_then_recovers
6 failed in 9.65s
```

（红因即票面：现网 `issue_token` 只本地 `sk-`+sha256、从不打网关；吊销无 `/key/delete`。）

**绿（实现后，含 T-07 同文件串行回归）**：

```
$ uv run pytest -q backend/tests/test_relay_token_gateway.py backend/tests/test_relay_group_empty_state.py backend/tests/test_billing_relay.py backend/tests/test_llm_gateway.py
....................                                                       [100%]
20 passed in 12.40s
```

**全量（最终代码，含 R10 补 logger 后）**：

```
$ uv run pytest -x -q backend/tests
1414 passed, 37 skipped, 7 warnings in 249.65s (0:04:09)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

```
$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

```
$ grep -rn 'LITELLM.DB_DSN' backend --include='*.py'
backend/tests/test_llm_probe.py:163:    assert "LITELLM.DB_DSN" not in probe_src + sched_src
```

唯一命中是既有守卫测试的**否定断言**（断言源码无 DSN；`git log` 48fabd4 2026-09-10 早于本会话，非本次引入）。产品代码零命中；arch.sh 的 DSN lint（排除 tests）通过。**零 `LITELLM.DB_DSN` 使用**：☑（无 DSN、无 `create_async_engine` 打网关库）。

### 验收项逐条对应

| GWT / 票面项 | 覆盖的测试 | 结果 |
|---|---|---|
| 签发成功（网关桩成功路径）+ 组限额映射 + 引用落库 | `test_issue_registers_gateway_key_and_plaintext_once`（含 body.models/rpm/tpm、metadata、`gateway_key_id==alias`、`key_hash==sha256(网关明文)`） | ✅ |
| 0/空限额缺省映射 | `test_issue_group_without_limits_omits_zero_limits` | ✅ |
| 网关失败=签发失败可见+无本地行（5xx / 不可达） | `test_issue_gateway_5xx_visible_no_local_row`、`test_issue_gateway_unreachable_visible_no_local_row`（断言 502、`RELAY_GATEWAY_UNAVAILABLE`、`tokens == []`、非套餐句/无 QUOTA 码） | ✅ |
| 明文一次 | 同签发测试尾部 + 骨架 `test_relay_group_token_issue_and_revoke`（列表 `plaintext_key is None`） | ✅ |
| 吊销=网关作废+本地 revoked+幂等 | `test_revoke_invalidates_gateway_then_local`（`del_calls == [{"key_aliases": [alias]}]`、二次吊销不重复打网关） | ✅ |
| 吊销网关失败不本地假吊销 | `test_revoke_gateway_failure_keeps_active_then_recovers`（502、`revoked_at is None`、恢复后可吊销） | ✅ |
| 无新迁移 | 迁移目录零改动；写入走 041 列 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚（本地 commit 失败回收网关孤儿） | — | ➖ N/A：SQLite 测试态制造 commit 失败需注入 DBAPI 错误，路径为 best-effort 告警（§3），不承诺原子性；对账面走 `/key/list` |
| 幂等（重复吊销） | `test_revoke_invalidates_gateway_then_local` 尾段 | ✅ |
| 并发写 | — | ➖ N/A：签发新 alias 天然无冲突键；吊销幂等分支已钉 |
| 外部依赖失败（签发/吊销×5xx/不可达） | 上表 4 个失败面测试 | ✅ |

## 7. NFR 验证

票内无 NFR 条目。➖

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 网关桩测的是 relay→admin 的调用契约（alias 删除、限额映射、失败语义）；**对真网关的 alias 删除有效性**（OpenAPI 声明 `key_aliases`）需 QA-21 真网关夹具复核——本票未对运行中网关做写操作。② 040 时代 `gateway_key_id IS NULL` 旧行吊销只走本地（网关本就不认它们），属预期。③ gateway_key_id 存的是 **alias** 而非 token_id（§0 OpenAPI 依据） |
| `/frontend`（T-10） | 签发响应信封 message 已含「明文只显示这一次…」；Base URL/三步用法页仍归 T-10（`LITELLM.PUBLIC_BASE_URL` 尚未引入配置，本票未造） |
| `/sre` | 吊销依赖管理面 `POST /key/delete` 可达；孤儿 Key 对账走 `/key/list`（alias 前缀 `relay-t*-g*`） |
| `/architect` | 无契约歧义。已知边界：alias 撞库/网关 tag 去 `/key/generate` 时按 ADR 复审条件重开，仍禁 DSN |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 输出原样）
- [x] 自测全绿（全量 1414 passed）
- [x] 契约落位表已核对，分层无违规（R7/R8/B4 通过）
- [x] ORM 与 DBML 一致，未自行加字段（无新迁移）
- [x] 无硬编码连接串/密钥/端口/阈值（网关地址/密钥/超时全走 `LITELLM.*`）
- [x] async 上下文无同步阻塞调用（httpx.AsyncClient）
- [x] 无 `except: pass`（孤儿回收失败有告警日志）
- [x] 日志已脱敏（明文不出 service；audit target 只有 `token#{id}`）
- [x] 事务里无外部调用（网关调用均在 commit 之外）
- [x] 幂等未用「先查后插」
- [x] 条件更新 `rows == 0`（N/A）
- [x] 外部依赖四件套（§3 表：超时=既有 LITELLM.TIMEOUT；重试=无，失败可见即产品语义；降级=无假成功；幂等前提=delete 幂等）
- [x] 四类易漏测试覆盖或 N/A 给理由
- [x] 上游问题回报（见 §8）
