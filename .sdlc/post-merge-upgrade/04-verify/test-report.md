# 测试报告 · 合入后四角色完备（post-merge-upgrade）

> 版本/commit：工作树 `feat/litellm-l1`（origin tip `1db6a47` 为合入基线；本波测试在工作区）｜环境：本地 pytest SQLite + Jest jsdom｜作者：/qa｜日期：2026-09-14
> 覆盖矩阵：`.sdlc/post-merge-upgrade/04-verify/coverage.md`
> 泳道：L3。verify r2：M12.8 Then 已可失败。**不**标四柱 GA。

## 1. 结论先行

| 项 | 结论 |
|---|---|
| 本轮测试结论 | 有条件通过：GWT-M 无剩余 ❌。GWT-M12.8 重写后 2 passed。仍 ⚠️ GWT-M11.12 需 MYSQL_FIDELITY=1（SQLite ThreadPool 不算已兑） |
| blocker 缺陷 | 0 |
| major 缺陷 | 1 张仍 open（BUG-V02 真库并发） |
| 覆盖空洞 | 0 个 ❌；环境闸 / 真库 ⚠️ 仍在 |
| 未在真实环境验证 | C2、C4、GWT-M11.7 live 收银台、结账 5s、MYSQL_FIDELITY 并发 |

**放行决策不由我做** → `/qc` 或 `/reviewer`。本报告只陈述事实。

## 2. 分层执行结果

### 单元测试（Jest · admin GWT-M 面）

```
$ cd frontend/admin && CI=true npm test -- --maxWorkers=2 --watchAll=false \
  src/pages/AiPlans.m01.test.tsx src/pages/Data.test.tsx src/pages/Spiders.test.tsx \
  src/pages/Usage.test.tsx src/pages/Checkout.test.tsx src/pages/MyOrders.test.tsx \
  src/pages/OutboundKeys.test.tsx src/pages/Members.test.tsx src/pages/RelayGroups.test.tsx \
  src/pages/MyInstalls.test.tsx src/pages/PlatformOps.test.tsx src/pages/Users.test.tsx \
  src/pages/Settings.test.tsx src/pages/Capabilities.governance.test.tsx \
  src/pages/market/TenantShelf.test.tsx src/pages/Pricing.test.tsx src/frU24CopyScan.test.tsx \
  src/App.menu.test.tsx src/components/newapi/DutyKeysTab.test.tsx \
  src/components/newapi/Overview3q.test.tsx src/components/quota/UpgradeIntentButton.test.tsx \
  src/components/spider/TaskModal.test.tsx
Test Suites: 22 passed, 22 total
Tests:       196 passed, 196 total
Time:        23.799 s
exit: 0
```

| 项 | 数字 |
|---|---|
| 通过 / 失败 / 跳过 | 196 / 0 / 0 |
| 耗时 | 23.8s |

控制台有 antd `valueStyle`/`Spin tip`/`message` 弃用警告，**不是失败**。

### 单元测试（Jest · official）

```
$ cd frontend/official && CI=true npm test -- --maxWorkers=2 --watchAll=false \
  src/frU24CopyScan.test.tsx src/pages/Pricing.test.tsx src/pages/Register.test.tsx \
  src/components/layout/SiteLayout.test.tsx
Test Suites: 4 passed, 4 total
Tests:       26 passed, 26 total
Time:        6.616 s
exit: 0
```

| 项 | 数字 |
|---|---|
| 通过 / 失败 / 跳过 | 26 / 0 / 0 |
| 耗时 | 6.6s |

### 集成测试（pytest · FR-M）

```
$ uv run pytest -q backend/tests/test_fr_m01_planning_disabled.py \
  backend/tests/test_fr_m03_first_collect.py \
  backend/tests/test_fr_m06_planning_export_events.py \
  backend/tests/test_fr_m10_orders_closed.py \
  backend/tests/test_fr_m11_checkout_pending.py \
  backend/tests/test_fr_m11_confirm.py \
  backend/tests/test_fr_m12_fulfill.py \
  backend/tests/test_fr_m14_checkout_events.py \
  backend/tests/test_fr_m20_outbound_lookup.py \
  backend/tests/test_fr_m21_members.py \
  backend/tests/test_fr_m23_relay_empty.py \
  backend/tests/test_fr_m30_duty_entry.py \
  backend/tests/test_fr_m31_ops_console.py \
  backend/tests/test_fr_m32_user_lifecycle.py \
  backend/tests/test_fr_m33_contact_settings.py \
  backend/tests/test_fr_m40_market_shelf.py \
  backend/tests/test_fr_m41_listing.py \
  backend/tests/test_fr_m51_signup_enterprise.py --tb=line
........................................................................ [ 86%]
...........                                                              [100%]
83 passed in 12.37s
exit: 0
```

| 项 | 数字 |
|---|---|
| 通过 / 失败 / 跳过 | 83 / 0 / 0 |
| 耗时 | 12.37s |
| 数据库类型 | SQLite 文件库（默认）。**MYSQL_FIDELITY 未开** → 见第 5 节 |

对照映射补跑（verify 首轮）：9 passed in 2.17s / exit: 0。

verify r1 新映射复跑：12 passed in 4.80s / exit: 0。

verify r2 M12.8 重写（HTTP 200 + selectors + 70.1 outbound；免费档 oracle 可失败）：

```
$ uv run pytest -q \
  backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_8_tokens_200001_plan_visible_not_free_cap \
  backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_8_free_tier_200001_blocks_plan \
  --tb=short
..                                                                       [100%]
2 passed in 1.39s
exit: 0
```

未跑全量 `uv run pytest backend/tests`。SQLite ThreadPool 的 M11.12 **不**记 W2 已兑。

### E2E

未执行 `frontend/admin/e2e/smoke.spec.ts`。主干路径由 HTTP 集成 + 组件 Jest 承担。

### 专项（性能/容量）

未跑生产量级。NFR-M01 3s 仅在单测墙钟（本机空库）。NFR-M02 100 条在 Jest/pytest 夹具数据上。

| NFR | 要求 | 实测 | 环境 | 结论 |
|---|---|---|---|---|
| NFR-M01 采集/规划未开放 3s | ≤3s | pytest `elapsed <= 3` 通过 | SQLite 单测 | ✅ 夹具 |
| NFR-M01 结账 5s | ≤5s | 未测墙钟 | — | ⚠️ |
| NFR-M01 出数 120s | live worker | 未测 | C4 | ⚠️ |
| NFR-M02 导出 100 / 并发 1 待支付 | 100 行闸已测；SQLite ThreadPool 有用例但不算真库并发 | 见 BUG-V02 | SQLite | 部分 |

**跳过的用例**：本轮命令无 skipped。

## 3. 缺陷清单

| 编号 | 标题 | 严重度 | 违反的 GWT | 状态 | 指派 |
|---|---|---|---|---|---|
| BUG-V01 | 专业档执法 Then（M12.6/7/8） | **major** | GWT-M12.6 / M12.7 / M12.8 | 已验证关闭 | `/backend` |
| BUG-V02 | 两买方并发需 MYSQL_FIDELITY；SQLite ThreadPool 不算 W2 已兑 | **major** | GWT-M11.12 | open | `/backend` + `/sre` |
| BUG-V03 | 企业档/relay 迟到通道通知未测 | **major** | GWT-M11.18 | 已验证关闭 | `/backend` |
| BUG-V04 | 提交取消 API 未测 | major | GWT-M11.13 | 已验证关闭 | `/backend` |
| BUG-V05 | 错平面事件空筛未测 | minor | GWT-M26.2 | 已验证关闭 | `/backend` |

implement r2 遗留 minor（非本帽新开）：QA-01 已配通道+channel None 金标；QA-02 无单 GET empty_state。见 `05-review/findings.md`。未在本轮复现为失败。

### 严重度分布

| 级别 | 总数 | 已修复 | 待验证 | open |
|---|---|---|---|---|
| blocker | 0 | 0 | 0 | 0 |
| major | 4 | 3（V01、V03、V04） | 0 | 1（V02） |
| minor | 1 | 1（V05） | 0 | 0 |

## 4. 回归执行

| 项 | 内容 |
|---|---|
| 影响面推导 | 直接影响：billing/checkout/confirm、规划闸、出站查找、值班 404、市场货架。调用方：Usage/Checkout/Data/Relay/Members。共享数据：`orders.status`/`product_code`/`open_product_slot`、`tenants.quota`、outbound_keys。共享配置：`LLM.ENABLED`、`OPS.DUTY_CONTACT`、`POWER_MARKET.ENABLED`。已知坑：ESC-2 方言；040 专业档种子≠定价页（T-08 已覆盖写入） |
| 回归集规模 | 既有 FR-M + 本轮 12 条补跑 + 222 Jest |
| 结果 | 补跑 12 passed / 0 失败 |

关闭票回归：TC-M11.18、TC-M11.13、TC-M26.2、TC-M12.6、TC-M12.7、TC-M12.8（含免费档 oracle）。M11.12 ThreadPool **不要**当并发回归保护。

## 5. 保真度与未验证项

### 环境差异风险

| 项 | 测试环境 | 生产环境 | 风险 |
|---|---|---|---|
| 数据库 | SQLite 文件库 | MySQL 8 | 生成列唯一 `uk_orders_tenant_open_product`、行锁 CAS、JSON 配额 |
| 数据量 | 夹具 ≤101 行 | 生产量级 | NFR 容量/性能未证 |
| 实例数 | 单进程 TestClient | 多 worker | 并发下单 |
| 工人 | ingest+webhook 夹具 | Scrapy 工人 | C4 120s 出数 |
| 网关 | mock / 不可达桩 | LiteLLM | C2 真网关轮 |

### 需真库验证清单（转 /sre）

| 用例 | 原因 | 状态 | 结果 |
|---|---|---|---|
| GWT-M11.12 | 并发行锁 + 生成列唯一 | 待执行 MYSQL_FIDELITY=1 | SQLite ThreadPool 绿 ≠ 已兑 |
| GWT-M31.4 并发 CAS | 双超管同时确认 | 待执行 | — |

### mock 掉的依赖

| 依赖 | mock 方式 | 未验证的真实行为 |
|---|---|---|
| Scrapy 工人 | ingest+webhook | 队列时延、工人掉线半途 |
| LiteLLM / 上游 | monkeypatch 不可达 | 真探针、限流、密钥轮转 |
| 支付通道 | 未配通道 + HMAC 夹具 | 支付宝/微信收银台、验真时序 |
| Jest 服务 | jest.fn 列表/预览 | 真 HTTP 信封、权限水合刷新（ESC-3） |

## 6. 覆盖空洞摘要

| 空洞 | 类型 | 风险 | 是否阻塞发布 |
|---|---|---|---|
| GWT-M11.12 并发 | ⚠️ MYSQL_FIDELITY | 双待支付 | SQLite ThreadPool 不得当已兑 |
| GWT-M11.7 live 收银 | ⚠️ 环境闸 | 本波不验收 | 否（spec） |
| C4 / C2 | ⚠️ 环境闸 | 出数/网关 live | 否（不得标 GA） |
| NFR-M09 | ➖ N/A | 仅中文 | 否 |

## 7. 给下游的信息

| 给谁 | 内容 |
|---|---|
| 实现角色 | BUG-V01 已关。BUG-V02 仍须 `MYSQL_FIDELITY=1` 双连接；不要把 SQLite ThreadPool 当完成 |
| `/qc` / `/reviewer` | 本报告 + `04-verify/coverage.md`；重点第 5、6 节。禁止四柱 GA |
| `/pm` | GWT 均可测；空洞是没写测试，不是 GWT 不可测 |
| `/sre` | C2 / C4 / live 收银台 / MYSQL_FIDELITY 并发 |
| `/architect` | `uk_orders_tenant_open_product` 必须在真 MySQL 证并发；SQLite 绿 ≠ 生产绿 |

## 8. 自检

- [x] 结论先行，且未替 `/qc` 做放行决策
- [x] 每层执行命令与退出码原样贴
- [x] skipped=0
- [x] 缺陷有分级
- [x] 每个缺陷指明 GWT
- [x] 回归影响面五个维度
- [x] 环境差异与 mock 已列
- [x] 覆盖空洞已摘要
