# 前端实现证据 · T-05 租户壳隐藏；直打同 404；空缓存；`/llm` 不整页 404

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-05.md`｜FR 锚点：FR-07 / FR-17 / FR-06.5｜角色：/frontend（admin 壳）+ 允许的 backend 404 信封｜日期：2026-09-08
> 上游：`02-shape/adr-0017-platform-vs-tenant-admin.md` · `02-shape/flows/tenant-platform-shell.md` · `02-shape/edge-states.md`
> 泳道：L4

未做 T-17 经办 `/llm` 写/test、未做 T-18 值班 71.2/71.3 文案、未改 `channel_id`、未代选六问、未改 Register/Data/Usage/export、未改 enqueue、未改 expiry authenticate。未作废 `test_create_endpoint_rejects_operator`。

## 1. 组件树

```
<App>
  ├─ /login /unauthorized
  ├─ <PlatformAdminLayout>          非超管（含未登录）→ 同一 <NotFound>
  │    /newapi /platform-ops /users
  ├─ <ProtectedRoute><AdminLayout>  租户壳
  │    ├─ 侧栏「权限加载中」/ 读叶（无平台写叶）
  │    ├─ /dashboard 零任务第一步 → /llm
  │    ├─ /llm（requireAdmin，不整页 404）
  │    └─ 其余租户叶
  └─ * <NotFound>                   「页面不存在或已被移除」+「返回工作台」
<LlmProviders>                      平台行无写控件；本企业行可保存
<Skills>/<Capabilities>             源扫描/上架写/候选审核仅 is_platform_admin
```

| 组件 | 类型 | 复用 | 提取理由 |
|---|---|---|---|
| `<PlatformAdminLayout>` | 路由壳 | App 内 | 平台写面存在性隐藏 |
| `<NotFound>` | 展示 | 缺页 + 平台直打 | 同一模板 |

未重排五组 IA。未改 `/enterprise` `/rbac` 守卫。

## 2. 状态归属表

| 状态 | 放在哪 | 理由 |
|---|---|---|
| 登录投影 `is_platform_admin` | `useAuthStore.user`（persist） | 登录信封字段；缺省 false |
| 权限缓存 / loadState | `usePermission` 模块级 | 非 Zustand；logout 清空 |
| 菜单过滤 | `platformOnly` + `is_platform_admin` | 不用 `role==='admin'` 开平台叶 |
| 平台行写控件 | `LlmProviders` `tenant_id === null` | GWT-06.5 / 06.6 |

- [x] 空缓存 ≠ 全开写面，≠ 整站空白
- [x] 无派生权限布尔被单独 persist

## 3. 数据层

| 项 | 内容 |
|---|---|
| queryKey | 动态菜单仍 `['dynamic-menus']`；前端再剥平台写 key |
| 登录 | `POST /auth/login` 投影 `is_platform_admin` |
| 中转 API | `require_platform_admin_or_404` → HTTP 404 `HTTP_404`，无渠道/无 Key |
| `/llm` 写 | 仍 `require_admin`（T-17 才改经办）；平台行服务层已拒 |

## 4. 六态实现与实测

对照 `edge-states.md` 后台壳 / 仪表盘 / 后台 404 / LLM 配置权限。

| 态 | 实现 | 怎么造出来的 | 实测 |
|---|---|---|---|
| **加载** | 侧栏「权限加载中」+ 读叶 | 缓存未 `loaded` | ✅ Jest 空缓存 |
| **空** | 仪表盘「还没有采集任务。按下面三步开始。」 | `total_tasks===0` | ✅ Dashboard.test |
| **错误** | 「权限暂时刷新失败，已保留上次菜单。」+ 读叶 | permissions fetch reject | ✅ |
| **权限** | 租户无中转/运营/用户管理；直打 404 同形；`/llm` 可进 | App + ProtectedRoute + usePermission | ✅ |
| **边界** | 渠道 404 无密钥；平台行无写；伪装不自动关（未加关闭） | pytest 404 + LlmProviders.test | ✅ |
| **离线** | 权限失败走读叶，不露出平台写 | 同错误 | ✅ 代码路径 |

### 错误码分支覆盖

| 契约 | 前端/后端处理 | 实测 |
|---|---|---|
| 租户 GET `/api/v1/newapi/channels` | 404 `HTTP_404`，data 空，无 sk- | ✅ pytest |
| 租户 PUT 渠道配置 | 404；Redis hash 不变；`authz.denied` leftover | ✅ |
| 未登录缺页 | `<NotFound>` 非登录页 | ✅ App.test |
| 租户 `/newapi` | 同一 NotFound；无「抱歉」；无渠道 | ✅ App.test |
| **default** | 未知 path 外层 `*` NotFound | ✅ |

- [x] 未用掩码当 Then（404 无密钥字段）
- [x] 未进 Unauthorized「抱歉，您没有权限访问该页面。」

## 5. 九维自查

| 维 | 检查 | 结果 |
|---|---|---|
| ① 间距 | 侧栏加载文案 8px/16px，沿用 Sider | ✅ 有限 |
| ② 颜色 | `rgba(255,255,255,0.65)` 侧栏次文；未新色板 | ✅ |
| ③ 字体 | 12px 加载句 | ✅ |
| ④ 圆角 | 未新增 | ✅ |
| ⑤ 图标 | 未新 emoji | ✅ |
| ⑥ 交互态 | 平台写叶不渲染；验证按钮租户 disabled+「需要平台管理员」 | ✅ |
| ⑦ 状态完整性 | 空缓存/已加载/直打 404/零任务引导 | ✅ 单测 |
| ⑧ 响应式 | 未改断点 | ☐ 未量 |
| ⑨ 可访问性 | NotFound 主按钮「返回工作台」 | ✅ 单测 |

## 6. a11y 核对

- [x] 返回工作台为 Button
- [x] 权限加载中为可见文本，非空白 Sider
- [ ] 键盘全流程未在真浏览器走完

## 7. 响应式

未改断点。后台壳沿用既有 Sider+Content。

## 8. 性能

路由仍 lazy + ErrorBoundary。平台写面未登录不进 AdminLayout（不拉渠道）。

## 9. 自测证据

> 命令与退出码原样粘贴。日期：2026-09-08。

```
$ uv run pytest -x -q backend/tests/test_b1c_newapi_channels_coverage.py
...................                                                      [100%]
19 passed in 1.02s
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

$ npm test --prefix frontend/admin -- --watchAll=false
Test Suites: 11 passed, 11 total
Tests:       37 passed, 37 total
exit: 0

$ npm run build --prefix frontend/admin
Creating an optimized production build...
Compiled with warnings.
（既有 unused-vars，非本票引入）
The build folder is ready to be deployed.
exit: 0

$ uv run pytest -x -q backend/tests/test_llm_provider.py::TestApiEndpoints::test_create_endpoint_rejects_operator
.                                                                        [100%]
1 passed in 0.92s
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-07.1 超管打得开中转叶 | `usePermission.test` 平台超管见「中转站管控」 | ✅ 导航；值班空态句 T-18 |
| GWT-07.2 租户导航无中转/运营/源上架写 | `usePermission.test` 租户 admin 无三叶 | ✅ |
| GWT-07.3 直打同 404、无密钥、无抱歉 | App.test + ProtectedRoute.test + pytest `_assert_hidden_404` | ✅ |
| GWT-07.4 改额度拒绝且不变 | `test_set_config_tenant_admin_404_quota_unchanged` | ✅ leftover 仍记 |
| GWT-07.5 零任务第一步不到 `/newapi` | `Dashboard.test` 点「LLM 配置」→ `/llm` | ✅ |
| GWT-07.6 伪装不自动关 | 未加自动关闭路径；NewApiOps 仍只展示 verdict | ✅ 行为保持 |
| GWT-17.1 经办/租户至少仪表盘+数据工厂 | usePermission 已加载断言 | ✅ |
| GWT-17.2 空缓存「权限加载中」或读叶 | 失败/未就绪无平台写叶 | ✅ |
| GWT-17.3 确认无平台写则入口不出现 | 租户 `is_platform_admin=false` 滤 `platformOnly` | ✅ |
| GWT-06.5 负责人保存本企业行 | 既有 `test_owner_saves_own_tenant_provider_row` + LlmProviders 本行写 | ✅ |
| 登录投影 `is_platform_admin` | `test_login_projects_is_platform_admin_false_for_tenant` | ✅ |
| 不作废 operator 403 | `test_create_endpoint_rejects_operator` | ✅ 仍 403 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 渠道写 404 路径 Redis hash 仍空 | ✅ |
| 幂等 | ➖ N/A（本票无新建写幂等键） | ➖ |
| 并发写 | ➖ N/A | ➖ |
| 外部依赖失败 | 权限接口失败读叶兜底 | ✅ Jest |

## 10. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 租户公司 admin 直打 `/newapi` `/platform-ops` `/users` 应与未登录打缺页同一 NotFound；API 404 无渠道。超管仍进值班页。`/llm` 可进；平台行无写。经办 `/llm` 仍 `requireAdmin`（T-17）。 |
| `/backend` | `require_platform_admin`（403）仍给能力扫描等 T-04 面；中转/运营台 tenants 用 `require_platform_admin_or_404`。`LlmProviderResponse.tenant_id` 可选展开。 |
| `/architect` | 匿名打 `/api/v1/newapi/channels` 仍 401（无 Token）；存在性隐藏做在已登录非超管 404 + 前端未登录直打平台 path 也 404。 |

## 11. 交票自检

- [x] 每条本票 Then 有 evidence（命令 + 退出码）
- [x] 闸命令退出码 0
- [x] 未改 GWT / 未改 `channel_id` / 未做 T-17 / T-18
- [x] 未作废 `test_create_endpoint_rejects_operator`
- [x] 日志无完整 Key
