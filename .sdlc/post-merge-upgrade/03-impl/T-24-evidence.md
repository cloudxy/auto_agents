# 实现证据 · T-24 注册=创建企业

> 票：T-24｜FR 锚点：FR-M51｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /api/v1/public/tenant/signup` | Router | `tenant_signup.py` | 官网「创建企业」 |
| 空名 / 1 字 | Service | `TenantSignupService.signup` | Schema 放行空串，句由 Service 分 |
| 名 ≥2 创建企业 | Service | 同上 | tenant + owner |
| 已登录再注册 | Service | `actor_tenant_id` → SIGNUP_INCOMPLETE | 不改写、无个人空间 |
| 无个人空间 API | 无此资源 | 404 | 不新开入口 |

**分层依赖核对**：☑ Router 未 import ORM（Pydantic 请求体在 router 文件，既有模式）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/tenant_signup.py` | 修改 | company 去掉 min_length=2，空串进服务层 |
| `backend/services/tenant_signup_service.py` | 修改 | 空→「请填写企业名」；1 字→「企业名至少 2 个字符」 |
| `backend/tests/test_fr_m51_signup_enterprise.py` | 新增 | GWT-M51.1–4 |

**未触碰**：☑ 未关 `POST /auth/register`（挂 default 租户 viewer，不是 C 端个人空间；官网主钮走 signup）

## 3. 关键实现决策

空名与 1 字必须分句：Pydantic `min_length=2` 会把两格收成同一校验句。改为 Service `ValidationException`。

### 事务边界

创建 tenant+owner 仍同一事务（既有）。校验失败零写。

### 幂等

邮箱占用 → SIGNUP_INCOMPLETE（既有，不泄露）。

## 4. ORM 与 DBML 对齐

☑ 未改 `tenants`/`users` 结构。

## 5. 可观测性

既有 `企业注册 | company=`（无密码）。成功 `tenant_signup_succeeded`。

## 6. 自测证据

### Red

实现前 `company=""` / `"星"` 被 Schema `min_length=2` 拦下，message 不是金标句。本票测试断言金标句；实现后转绿。

### Green

```
$ uv run pytest -q backend/tests/test_fr_m51_signup_enterprise.py
....                                                                     [100%]
4 passed

$ uv run pytest -x -q backend/tests
1786 passed, 41 skipped, 9 warnings in 205.78s (0:03:25)
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M51.1 | `test_gwt_m51_1_signup_creates_enterprise_not_personal_space` | ✅ 企业行 + 登录 200 + owner.tenant_id=该企业；响应无 personal_space |
| GWT-M51.2 | `test_gwt_m51_2_empty_company_copy_no_create` | ✅ 「请填写企业名」；不建 |
| GWT-M51.4 | `test_gwt_m51_4_one_char_company_copy_no_create` | ✅ 「企业名至少 2 个字符」 |
| GWT-M51.3 | `test_gwt_m51_3_logged_in_operator_has_no_personal_space` | ✅ `/personal-space` 等 404；已登录 signup 422 不建第二家 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 校验失败零企业 | ✅ |
| 幂等 | 既有占用邮箱 | ➖ 对照 `test_saas_signup_expiry` |
| 并发写 | 无新约束 | ➖ |
| 外部依赖失败 | 限流测试已解耦 | ➖ fixture mock |

## 7. NFR 验证

无新 NFR。限流 fail-closed 既有。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/frontend` | 主钮「创建企业」；空名/1 字两句已与 edge-states 锁句对齐。成功进该企业后台靠登录 token。 |
| `/qa` | 个人空间：无 API。`/auth/register` 仍可挂 default，不是本 FR 的「创建企业」。 |
| `/architect` | 若要废止 `/auth/register` 需另票（会冲登录/限流测）。 |

## 9. 交票自检

- [x] 四格 GWT 有测试
- [x] 全量绿
- [x] 未开个人空间写面
