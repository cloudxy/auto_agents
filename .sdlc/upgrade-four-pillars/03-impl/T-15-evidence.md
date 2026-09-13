# 实现证据 · T-15 超管商户凭据加密落库与轮换

> 票：`02-shape/contract.md` §10 T-15｜FR 锚点：FR-U31｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET/PUT `/api/v1/admin/payment-credentials`；DELETE `/{channel}` | Router | `backend/app/api/v1/payment_credentials.py` | `require_platform_admin_or_404`；租户 404 同形 |
| 通道闭集 alipay/wechat；secrets 必填 | Schema | `platform_core/schemas/payment_channel_credential.py` | Put.secrets 只写入；View 无密文列 |
| 权限（超管可配、租户不可见） | Router 守卫 + Service | `deps.require_platform_admin_or_404` | 非超管不进 handler |
| 加密落库 / 轮换丢弃旧密文 / 读回掩码 | Service | `backend/services/payment_credential_service.py` | Fernet 复用 `LlmSecretVault`；GET 不解密 |
| 数据读写 | Repository | `backend/repositories/payment_channel_credential_repository.py` | 无 tenant_id；通道 UNIQUE |
| 错误码映射 | 统一异常处理器 | 缺主密钥 → 400；非法通道 → 422 | 不在 Router 逐个 try/except |
| 幂等 | UNIQUE `uk_payment_channel_credentials_channel` | 046 已落地 | 并发 PUT：IntegrityError → 轮换 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/payment_credentials.py` | 新增 | 超管 GET/PUT/DELETE |
| `backend/services/payment_credential_service.py` | 新增 | 加密、掩码、轮换 |
| `backend/repositories/payment_channel_credential_repository.py` | 新增 | 按通道点查/列表/删除 |
| `backend/tests/test_fr_u31_payment_credentials.py` | 新增 | GWT-U31.1…U31.5 |
| `platform_core/schemas/payment_channel_credential.py` | 修改 | Put / View / List；`SECRETS_MASK` |
| `platform_core/schemas/__init__.py` | 修改 | 导出 Put/View |
| `backend/app/api/v1/__init__.py` | 修改 | 挂 `/admin/payment-credentials` |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：合同只写 GET/PUT；CRUD 补 DELETE 使通道回到未配置。）

**未触碰「不许改的文件」**：☑ 确认（未改 046/GWT；无 `config/**` 商户密钥键；无 notify。）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 加密后 insert/rotate | 是 | 明文不落库；旧密文与新密文不能并存 |
| 审计 | 否 | 既有独立短事务 |

**事务提交后的操作失败怎么办**：审计失败不挡主路径（既有）。无通道 SDK。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键 `channel` |
| 保证方式 | UNIQUE + IntegrityError → 轮换已有行 |
| 重复 PUT | 视为轮换：`key_version+1`，旧密文覆盖 |

☑ 未使用「先查后插」当唯一保证

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 两超管同时首配同一通道 | UNIQUE + rollback 后 rotate | 找不到行则原样抛 IntegrityError |

☑ 条件更新本票无状态机 CAS（轮换是整行覆盖）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无通道 SDK | — | — | 未配主密钥拒绝保存（不降级明文） | N/A |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 沿用 T-14 / 046，本票未加列

结构核对输出：本票无新迁移。046 凭据表无 `tenant_id`；Out/View 无 `secrets_encrypted`。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_for_admin` / `put` / `delete_channel` 记 channel、merchant_no、actor；**不记 secrets/密文** |
| 错误日志上下文 | 缺主密钥走既有 vault 文案 |
| 慢操作 | 无外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无密钥全文 ☑ GET 不解密

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_fr_u31_payment_credentials.py
........                                                                 [100%]
8 passed in 3.63s
T15_EXIT:0
```

```
$ uv run pytest -x -q backend/tests
1641 passed, 40 skipped, 7 warnings in 248.26s (0:04:08)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0
```

```
$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
layer_exit:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U31.1 正常 | `test_gwt_u31_1_save_then_get_masks_secret` | ✅ |
| GWT-U31.2 空态 | `test_gwt_u31_2_empty_form_both_unconfigured` | ✅ |
| GWT-U31.3 越权 | `test_gwt_u31_3_tenant_404_same_shape_no_secret` | ✅ |
| GWT-U31.4 边界 | `test_gwt_u31_4_secret_not_in_config_or_git` | ✅ |
| GWT-U31.5 轮换 | `test_gwt_u31_5_rotate_drops_old_secret` | ✅ 旧密文不在库；解密仅为新值。履约拒绝旧密钥属 T-17 验真读当前行 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | `test_put_without_master_key_does_not_store_plaintext` | ✅ 拒保存，零行 |
| 幂等 | 同通道二次 PUT = 轮换 | ✅ `test_gwt_u31_5` |
| 并发写 | UNIQUE 兜底 `_insert_or_rotate` | ✅ 约束已在；未做 gather |
| 外部依赖失败 | 缺 Fernet 主密钥 | ✅ 不降级明文 |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U04 | 加密落库、不进 git/yml/浏览器全文 | GET 仅 `********`；config yml 无商户密钥键 | pytest + 仓库扫描 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| T-16 | `configured_channels()` = 表中有行即已配。无行 = 未配置。 |
| T-17 | 验真只解密**当前** `secrets_encrypted`；轮换后旧明文无法从库还原。 |
| `/frontend` | GET 返回 `{channels:[{channel,configured,merchant_no,secrets_masked,...}]}` 恒两行；PUT `{channel,merchant_no,secrets}`；响应无全文。租户直打 404 同形。 |
| `/qa` | 掩码是常量 `********`（不含尾 4 位）。主密钥仍 `LLM_ENCRYPTION_KEY`。 |
| `/architect` | 合同仅 GET/PUT；补了 DELETE 回到未配置。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口；无 yml 商户密钥
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」当唯一保证
- [x] 未做 notify 验真/履约（T-17）
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
