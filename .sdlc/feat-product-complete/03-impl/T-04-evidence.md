# 实现证据 · T-04 新建出站拉数钥匙签发/吊销域（hash，明文一次）+ 迁移 041

> 票：contract §11 T-04（FR-51 前半）｜FR 锚点：FR-51（GWT-51.1 签发半格 / 51.2 / 51.5 / 51.8 / 51.9）｜角色：/backend｜日期：2026-09-11
> 依据：contract §7.3 + §2.3 边界强制 + ADR-0020 + db-spec §1（outbound_keys）§5 §8 §14 + spec FR-51
> 范围闸：不做拉数执法（T-05）、不碰 relay_service（T-07/08）、签发事件 `outbound_key_issued` 归 T-05。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET /api/v1/outbound/keys（列表+空态句） | Router | `backend/app/api/v1/outbound_keys.py` | 空态 message=spec 冻结句（GWT-51.2） |
| POST /api/v1/outbound/keys（签发，201，明文一次） | Router | 同上 | message 带「出站拉数钥匙」产品名 |
| DELETE /api/v1/outbound/keys/{id}（吊销） | Router | 同上 | 幂等；跨企业 404 同形 |
| 字段校验（name ≤64） | Schema | `platform_core/schemas/outbound.py` | OutboundKeyCreate/Out/IssuedOut |
| 权限判定（owner/admin/operator 过，viewer 拒） | **Service** | `backend/services/outbound_key_service.py` | 业务规则在 Service 入口（GWT-51.5/51.9 找管理员句） |
| 业务规则（明文一次、hash、prefix 非 sk-、revoked 终态） | Service | 同上 | 前缀自选 `ok-`（db-spec §0.1 只禁 sk-，实现票自选） |
| 数据读写 | Repository | `backend/repositories/outbound_key_repository.py` | BaseRepository 子类；只碰 outbound_keys 一张表 |
| 错误码映射 | 统一异常处理器 | `OUTBOUND_KEY_ROLE_NOT_ALLOWED`（400，句=「请联系企业管理员」，对齐 T-01 `ORDER_ROLE_NOT_ALLOWED` 先例） | 不走 403 FORBIDDEN（§7.1） |
| ORM | `platform_core/models/outbound_key.py` | TenantMixin **不豁免**（PIT-3/4）；无软删（revoked 即终态审计） | |
| 迁移 041 | `backend/alembic/versions/041_outbound_keys_and_relay_gateway_ref.py` | expand-only 可逆；独占 041，后续票只用列 | |

**分层依赖核对**：☑ Router 未 import ORM（R7，arch.sh 绿） ☑ Service 未返回 ORM 对象（只回 Pydantic Out） ☑ Repository 未调 Service ☐→☑ ORM 与 Schema 互不 import（R8 绿）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/outbound_key.py` | 新增 | OutboundKey ORM（9 列，与 db-spec §1 逐列对齐） |
| `platform_core/models/relay.py` | 修改 | 041 expand 两列：`gateway_key_id` VARCHAR(191) NULL UNIQUE + `spend_synced_at` DATETIME NULL（为 T-08 备列，db-spec §0.0/§1） |
| `platform_core/models/__init__.py` | 修改 | 注册 OutboundKey |
| `platform_core/schemas/outbound.py` | 新增 | 契约三 Schema；列表行无明文字段 |
| `backend/repositories/outbound_key_repository.py` | 新增 | list_by_tenant（created_at DESC）/ get_owned |
| `backend/services/outbound_key_service.py` | 新增 | 签发/吊销/列表；R10 入口 logger |
| `backend/app/api/v1/outbound_keys.py` | 新增 | 三端点；注册名匹配 contract §2.3 grep `outbound*.py` |
| `backend/app/api/v1/__init__.py` | 修改 | `/outbound` 静态前缀注册（无动态段冲突，PIT-1） |
| `backend/alembic/versions/041_...py` | 新增 | 见 §4 |
| `backend/tests/test_outbound_keys.py` | 新增 | 7 测（GWT 五支 + 吊销终态/跨企业 + 角色矩阵） |
| `backend/tests/test_outbound_migration_041.py` | 新增 | up→down→up 可逆性（mysql_fidelity 门控） |
| `backend/tests/test_db_fixtures.py` | 修改 | ALL_ORM_TABLES 补 6 表：plans/orders/tenant_subscriptions/relay_groups/relay_tokens（**既有欠账**，018c369 漏记导致该测试在我开工前已红）+ outbound_keys（本票） |

**与票里「会改哪些文件」一致**：☑ 是（新域四层 + 迁移 041 + 测试）
**未触碰「不许改的文件」**：☑ 确认（relay_service.py、external_api/public.py 拉数路径、auth 域均未动）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 签发（insert 一行） | 单语句 commit | 单表写，无跨表不变量 |
| 吊销（条件 UPDATE revoked_at） | 单语句 commit | revoked_at IS NULL 守卫=条件更新，rowcount 语义 |

**事务提交后的操作失败怎么办**：N/A（无外部调用——本票不打网关、不发事件、不进 KEY_BINDINGS；全在 T-05/T-08）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | `uk_outbound_keys_key_hash`（key_hash 全局 UNIQUE，迁移 041） |
| 保证方式 | 明文由 `secrets.token_urlsafe` 生成，撞指纹概率忽略；UNIQUE 兜底 |
| 重复请求返回 | 每次签发=新钥匙行（一企业允许多把并存，db-spec §3「outbound_keys (tenant_id) 无唯一」）；吊销幂等（已 revoked 再 DELETE 返回原状态，revoked_at 不改写） |

☐ 未使用「先查后插」（签发无先查；吊销是条件写非插入）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 吊销 active→revoked | `revoked_at IS None` 守卫后赋值提交 | 已 revoked → 直接回当前行（幂等，终态不可清回 NULL） |
| 跨企业吊销 | SELECT 带 `tenant_id ==`（R13） | None → `NotFoundException("出站拉数钥匙")` 404 同形 |

☑ 所有条件更新的返回行数都有处理

### 外部依赖

无（本票零外部调用）。NFR-04 落点：明文只在签发响应；日志只记 tenant/actor/key id，不记明文。

## 4. ORM 与 DBML 对齐

☑ 字段 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键（**无 FK**，跟 040 orders/relay 先例）——全部与 db-spec §1 对齐

迁移 041 结构（up）：

```
$ uv run python -c "import ast;ast.parse(open('backend/alembic/versions/041_outbound_keys_and_relay_gateway_ref.py').read());print('syntax ok')"
syntax ok
```

- `outbound_keys`：id PK / tenant_id **NOT NULL**（PIT-4）/ name VARCHAR(64) NULL / key_prefix VARCHAR(16) NOT NULL / key_hash VARCHAR(64) NOT NULL / issued_by_user_id INT NOT NULL（无 FK）/ revoked_at DATETIME NULL / created_at / updated_at；`uk_outbound_keys_key_hash` + `idx_outbound_keys_tenant_created (tenant_id, created_at)`
- `relay_tokens`：ADD `gateway_key_id` VARCHAR(191) NULL + `spend_synced_at` DATETIME NULL + `uk_relay_tokens_gateway_key_id`（多 NULL 合法；建 UNIQUE 前 Step0 重复探测，db-spec §8——重复即 raise 停，不猜）
- down：全部对称撤销（drop unique → drop 两列 → drop index → drop table）
- **真库对拍**（隔离 schema，`test_fresh_upgrade_head_matches_create_all`）：迁移链列集 == create_all 列集，逐表一致（含 outbound_keys 9 列与 relay_tokens 新两列）——见 §6 第 4 块

**未自行加字段/改类型**：☑ 确认（gateway_key_id/spend_synced_at 为 db-spec §1 明定的 041 内容，非自加）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `service.outbound`：list/issue/revoke 入口 `logger.info`（tenant/actor/role/key id） |
| 错误日志上下文 | viewer 拒绝走 BusinessException 统一信封（句=请联系企业管理员，无内码） |
| 审计 | Router `record_audit`：`outbound.key.issue` / `outbound.key.revoke` |

**日志脱敏核对**：☑ 无明文钥匙（日志与审计只出现 key#id） ☑ 无 hash 全量 ☑ 无密码

## 6. 自测证据（命令与退出码原样粘贴）

**红（TDD：实现 stash 后仅留测试）**

```
$ uv run pytest -q backend/tests/test_outbound_keys.py
ERROR backend/tests/test_outbound_keys.py
E   ModuleNotFoundError: No module named 'platform_core.models.outbound_key'
!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!
1 error in 0.18s
exit: 2
```

**绿（本票域测试 + 修好的表清单测试）**

```
$ uv run pytest -q backend/tests/test_outbound_keys.py backend/tests/test_db_fixtures.py
...........                                                          [100%]
11 passed in 6.73s
exit: 0
```

**迁移 041 up→down→up 可逆性（真实 MySQL 隔离库）**

```
$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD=123456 \
  uv run pytest -q backend/tests/test_outbound_migration_041.py
.                                                                    [100%]
1 passed in 25.79s
exit: 0
```

**迁移链 ↔ create_all 对拍（同隔离库）**

```
$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD=123456 \
  uv run pytest -q backend/tests/test_alembic_baseline.py
..s                                                                  [100%]
2 passed, 1 skipped in 13.25s        # skip=downgrade base（errno 1553 既有，与本票无关）
exit: 0
```

**架构红线 / 迁移门禁 / lint**

```
$ bash tools/check/arch.sh
exit: 0        （R7 API 无 ORM import / R10 service 入口 logger / R13 租户收口 全绿）
$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
exit: 0
$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

**契约 §2.3 边界 grep（原样执行）**

```
$ grep -rnE 'backend\.services\.relay|llm_gateway' backend/services/outbound_keys/ backend/app/api/v1/outbound*.py
(no matches — boundary clean)        # 出站域零引用 relay/网关适配包
$ grep -rnE 'outbound_key|KEY_BINDINGS' backend/services/relay_service.py
(relay_service clean of outbound refs)
```

**全量后端套件**

```
$ uv run pytest -q backend/tests
1 failed, 1364 passed, 36 skipped, 7 warnings in 277.30s
exit: 1
```

唯一失败 `test_product_events.py::test_gwt_15_4_login_failed_reasons_no_password`（`assert 'expired' in {'credential','locked'}`）**非本票**：并行泳道正在改 `backend/services/auth_service.py`（登录 reason 域，T-16）。归因证明——把本票全部改动 stash 掉后同一测试仍红：

```
$ git stash push -u -m t04-attr -- <本票 12 个文件> && \
  uv run pytest -q backend/tests/test_product_events.py::test_gwt_15_4_login_failed_reasons_no_password
FAILED backend/tests/test_product_events.py::test_gwt_15_4_login_failed_reasons_no_password
1 failed in 3.01s
exit: 1
$ git stash pop   # 本票改动原样恢复
```

本票开工前的基线同为 1 失败（`test_db_engine_creates_all_orm_tables`，018c369 漏登 5 表——本票已顺手修复转绿）。注意：工作树还有 T-01/T-13/T-16/T-29 泳道并发写盘（`test_billing_relay.py` 在两次运行之间被并行泳道改写），全量快照逐分钟在漂。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-51.1 签发半格（明文一次+前缀/hash 落库+产品名） | `test_gwt_51_1_operator_issues_plaintext_once_prefix_stored`（拉到行的另一半归 T-05） | ✅ |
| GWT-51.2 空态句 | `test_gwt_51_2_empty_state_sentence`（owner+viewer 都走得到） | ✅ |
| GWT-51.5 越权·只读签发 | `test_gwt_51_5_viewer_cannot_issue_no_key_row`（句+零行） | ✅ |
| GWT-51.8 再进页不见明文 | `test_gwt_51_8_revisit_shows_prefix_and_status_only` | ✅ |
| GWT-51.9 越权·只读吊销 | `test_gwt_51_9_viewer_cannot_revoke_key_stays_active`（revoked_at 保持 NULL） | ✅ |
| 迁移 up 可逆 | `test_outbound_migration_041_up_down_up_reversible`（真 MySQL） | ✅ |
| 吊销终态/跨企业 404 同形 | `test_revoke_terminal_idempotent_cross_tenant_404` | ✅ |
| 角色矩阵（owner/admin/operator 均可签+吊） | `test_admin_and_operator_both_allowed_on_issue_and_revoke` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（单表单语句写，无多步事务可回滚） | |
| 幂等 | `test_revoke_terminal_idempotent_cross_tenant_404`（重复吊销不改写 revoked_at） | ✅ |
| 并发写 | ➖ N/A（签发无共享计数器/状态机竞态；key_hash UNIQUE 兜底指纹） | |
| 外部依赖失败 | ➖ N/A（本票零外部依赖；网关/事件都在 T-05/T-08） | |

## 7. NFR 验证

| NFR | 要求 | 实测 |
|---|---|---|
| NFR-04 | 明文只一次；再进页只见前缀/状态 | `test_gwt_51_1…` + `test_gwt_51_8…`（响应体全文无 plaintext 明文） |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① SQLite 默认套件验不出 MySQL UNIQUE 多 NULL 方言（`uk_relay_tokens_gateway_key_id`）——MYSQL_FIDELITY=1 时 `test_outbound_migration_041` 已覆盖 up/down/up，请复核；② viewer 拒绝是 **400 + `OUTBOUND_KEY_ROLE_NOT_ALLOWED` + 找管理员句**（对齐 T-01 先例，非 403）——若 QA 口径要钉别的状态码请回 architect；③ GWT-51.1「拉到行」半格在 T-05，本票只交签发半格 |
| `/frontend`（T-06） | 空态句在 GET 列表 200 的 `message` 字段（data=[] 时）；签发明文在 201 的 `data.plaintext_key`，仅此一次；状态枚举 `active|revoked`（页上渲染 已签发/已吊销） |
| T-05（backend） | 拉数查找：先 `outbound_keys`（key_hash 等值）再 KEY_BINDINGS；`_PLAINTEXT_PREFIX="ok-"` 在 `outbound_key_service.py`，明文前缀禁 sk- 的执法口径以此为准；事件 `outbound_key_issued` 归你票 |
| T-08（backend） | `relay_tokens.gateway_key_id/spend_synced_at` 列已就位（041）；ORM 已同步扩列，直接用 |
| `/architect` | ① 并行泳道 auth 改动当前弄红 `test_gwt_15_4_login_failed_reasons_no_password`（本票 stash 归因已证非我）；② contract §2.3 的 grep 路径写的是 `backend/services/outbound_keys/` 目录，实现按仓内既有扁平风格落成 `outbound_key_service.py`（单文件）——grep 如要挂 lint 需改路径，建议 T-05 落 |
| 管理窗 | `test_db_fixtures.ALL_ORM_TABLES` 既有欠账（5 表漏记）已由本票顺手补齐转绿；若有泳道同改此文件以先合者为准，集应收敛相同 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（本票域 11 测 + 迁移真库 1 测 + 门禁 3 项；全量套件唯一红 = 并行泳道 in-flight，已归因）
- [x] 契约落位表已核对，分层无违规（arch.sh R7/R10/R13 绿）
- [x] ORM 与 db-spec 一致，未自行加字段（真库对拍过）
- [x] 无硬编码连接串/密钥/端口/阈值（MySQL 凭据仅出现在测试命令 env，不落代码）
- [x] async 上下文无同步阻塞调用（无 redis 路径）
- [x] 无 `except: pass`
- [x] 日志已脱敏（无明文/hash 全量）
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理
- [x] 外部依赖四件套 N/A（零外部依赖，已给理由）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8），未自行绕过
- [x] 票状态：backend 侧 T-04 交付（state 由管理窗翻）
