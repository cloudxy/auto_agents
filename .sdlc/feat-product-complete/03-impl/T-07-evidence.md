# 实现证据 · T-07 渠道组空态可达：禁止 GET 建组；经办只读

> 票：contract §11 T-07（FR-60）｜GWT 锚点：GWT-60.4 / 60.7｜角色：/backend｜日期：2026-09-11

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/relay/groups` 不建组（§7.4） | Service | `backend/services/relay_service.py` | 删 `list_groups` 读路径 `_ensure_default`；方法整体移除 |
| 空态句「还没有令牌。…」（GWT-60.4） | Router | `backend/app/api/v1/relay.py` | `list_tokens` 空列表 → `MSG_TOKENS_EMPTY`（常量在 service，单一真相） |
| 经办找管理员句（GWT-60.7） | Service + Router | 同上两文件 | 写面角色判定收 Service（`_require_issuer_role` / `_require_group_writer_role`，`BusinessException` 400 非裸 403）；groups 读模型 message 对无权者给 `MSG_CANNOT_ISSUE` |
| 写权角色集 | Service | `relay_service.py` | `_ISSUER_ROLES = (owner, admin)`（contract §3：经办只看用法） |
| 审计 | Router | `relay.py` | `record_audit` 行为不变（group.create/update、token.issue/revoke） |

**分层依赖核对**：☑ Router 未 import ORM（仅 schemas + service）☑ Service 未返回 ORM 对象（返回 `*Out` Pydantic）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/relay_service.py` | 修改 | 删 `_ensure_default`/`_DEFAULT_GROUP`；写面方法签名加 `actor_tenant_role` + 角色检查；冻结句常量 |
| `backend/app/api/v1/relay.py` | 修改 | 写端点 `require_tenant_manager` → `get_current_user`（角色判定下沉 Service，403→可见句）；读端点空态/角色 message |
| `backend/tests/test_relay_group_empty_state.py` | 新增 | GWT-60.4 / 60.7 红绿测试 |
| `backend/tests/test_billing_relay.py` | 修改 | **作废「GET 必有 data[0]」金标**（票面授权）：`test_relay_group_token_issue_and_revoke` 改显式建组；`test_viewer_cannot_create_order_or_token` viewer 改断言找管理员句（非 403） |

**与票里「会改哪些文件」一致**：☑ 是。**未触碰「不许改的文件」**：☑ 确认（未动 T-09/T-10 范围、未动 db-spec/edge-states、未 git commit）。

## 3. 关键实现决策

- **角色拒绝形态**：对齐 T-01/T-04 既有先例——`BusinessException`（HTTP 400）+ 冻结句，**不是** `AuthorizationException` 裸 403/`FORBIDDEN`。GWT-60.7 测试断言 `status != 403` 且 `code not in {FORBIDDEN, HTTP_403, QUOTA_EXCEEDED}`。
- **判角色 vs 判归属顺序**：`_require_issuer_role` 在 `_owned_group` 之前——经办探测他企业 group_id 得角色拒绝句，不泄露组存在性；跨企业 404 同形由 owner 路径保持（骨架测试 `stolen.status_code == 404` 仍绿）。
- **默认组**：不新造显式建组端点——既有 `POST /relay/groups` 即显式写路径（§7.4「默认组若产品需要，只允许显式写」）。
- **幂等/事务**：本票无新多步写，无新事务边界（签发/吊销的事务与网关序贯在 T-08）。

## 4. ORM 与 DB 对齐

本票零 schema 改动（`relay_tokens.gateway_key_id` 等列属 T-04 迁移 041，已落盘）。☑ 未自行加字段/改类型。

## 5. 可观测性

- `list_groups` / `create_group` / `update_group` / `issue_token` / `revoke_token` 入口 logger 保留并补充 `role=` 字段；模块级 `is_issuer_role` 补 `logger.debug`（R10）。
- **脱敏**：☑ 无明文 key/无 token 入日志（本票未触签发明文路径）。

## 6. 自测证据（命令 + 退出码原样）

**红（实现前，本票测试先行）**：

```
$ uv run pytest -q backend/tests/test_relay_group_empty_state.py
FAILED backend/tests/test_relay_group_empty_state.py::test_gwt_60_4_viewer_get_groups_inserts_nothing
FAILED backend/tests/test_relay_group_empty_state.py::test_gwt_60_7_operator_readonly_no_write_faces
2 failed in 2.35s
```

（红因：现网 `_ensure_default` 在 GET 落 default 组；写面 `require_tenant_manager` 裸 403「需要租户 owner/admin 权限」——正是票面要拆的两处。）

**绿（实现后，本票+金标改写）**：

```
$ uv run pytest -q backend/tests/test_relay_group_empty_state.py backend/tests/test_billing_relay.py
......                                                                       [100%]
6 passed in 3.28s
```

**全量**（含 T-08 同批最终代码，见 T-08 evidence 第 6 节同次运行）：

```
$ uv run pytest -x -q backend/tests
1414 passed, 37 skipped in 477.73s   # 最终复核一次见 T-08 证据（R10 补 logger 后复跑）
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| 60.4 空态·无令牌（GET 不建组、空态句、无权者找管理员句） | `test_gwt_60_4_viewer_get_groups_inserts_nothing`（含 viewer GET 前后组数 0 断言、owner/viewer 同句） | ✅ |
| 60.7 越权·经办签发（能看+无签发/吊销/停用面+找管理员句） | `test_gwt_60_7_operator_readonly_no_write_faces`（issue/revoke/patch/create 四写面 + DB 零副作用断言） | ✅ |
| 作废「GET 必有 data[0]」金标 | `test_billing_relay.py::test_relay_group_token_issue_and_revoke`（改写为 `data == []` + 显式建组） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（本票无新多步写） |
| 幂等 | — | ➖ N/A（无幂等语义新增） |
| 并发写 | — | ➖ N/A（无新并发写路径） |
| 外部依赖失败 | — | ➖ N/A（本票无外部调用；网关失败面在 T-08） |

## 7. NFR 验证

票内无 NFR 条目。➖

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 经办（operator）与只读（viewer）在写面同句同码；跨企业 404 同形仅对有权者保持 |
| `/frontend`（T-10） | 空态句/message 单一来源：`relay_service.MSG_TOKENS_EMPTY` / `MSG_CANNOT_ISSUE`；groups GET 的 message 对无权者即找管理员句，tokens GET 空列表即空态句——页面直接渲染信封 message，勿另造第二套 |
| `/architect` | 无契约歧义发现。经办写面拒绝用 400 + `RELAY_TOKEN_ROLE_NOT_ALLOWED`/`RELAY_GROUP_ROLE_NOT_ALLOWED`（对齐 T-01 `ORDER_ROLE_NOT_ALLOWED` 先例，待追认同 T-01 口径） |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 输出原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规（arch.sh R7/R8 通过）
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」（N/A）
- [x] 条件更新 `rows == 0`（N/A）
- [x] 外部依赖四件套（N/A，本票）
- [x] 四类易漏测试覆盖或 N/A 给理由
- [x] 上游问题回报（见 §8）
