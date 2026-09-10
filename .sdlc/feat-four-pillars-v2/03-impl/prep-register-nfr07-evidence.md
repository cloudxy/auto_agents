# 实现证据 · prep Register 免费档三数 + NFR-07 44px

> 票：QC condition B + NFR-07｜FR 锚点：FR-01 / FR-04 / NFR-07｜角色：/frontend｜日期：2026-09-10
> 上游：`01-define/spec.md` GWT-01.1 Given `5` / `10,000` / `20 万`；NFR-07「官网主按钮触摸目标 ≥44px」；`FREE_TIER_FEATURE_COPY`
> 泳道：L4 ui
> 禁：支付（Q-PRICE）、代答六问、Wave 2/3、改 GWT、削弱 GWT-04.x

C35-QA-03：Register 手写「5 并发 / 10000 条结果 / 20 万 tokens/月」与 Pricing 三句漂移。NFR-07 无 Jest 量宽。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 免费档三句 5 / 10,000 / 20 万 | shared 常量 | `frontend/shared/src/constants/quota.ts` | 未改常量；Register 改为读取 |
| 注册页卖点 | 官网页 | `frontend/official/src/pages/Register.tsx` | `FREE_TIER_LINE` 组合三句 |
| 触摸目标 44px | token + 主 CTA | `tokens.css` `--size-touch` / `.site-touch-target`；Home / Pricing / Register 内联 `var(--size-touch, 44px)` | jsdom 量宽靠内联 |
| Then 对照 | Jest | `Register.test.tsx` 钉三句；Home/Pricing/Register 钉 minHeight/minWidth ≥44 | 独立 oracle，不从 DEFAULT_QUOTA 推导 |

**分层依赖核对**：☑ 未 import ORM ☑ 未改 schema / GWT / token 数值（仅加 `.site-touch-target` 消费已有 `--size-touch`）☑ 无支付流 ☑ GWT-04.1–04.4 断言未改

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/Register.tsx` | 修改 | 读 `FREE_TIER_FEATURE_COPY`；提交钮与成功主钮 touch |
| `frontend/official/src/pages/Register.test.tsx` | 修改 | 具名三句 + NFR-07 量宽；GWT-04.x 保留 |
| `frontend/official/src/pages/Home.tsx` | 修改 | Hero / CTA 带「免费注册」主钮 touch |
| `frontend/official/src/pages/Home.test.tsx` | 修改 | NFR-07 量宽 |
| `frontend/official/src/pages/Pricing.tsx` | 修改 | 三档主 CTA touch（免费仍 `/register`） |
| `frontend/official/src/pages/Pricing.test.tsx` | 修改 | NFR-07 量宽 |
| `frontend/official/src/tokens.css` | 修改 | `.site-touch-target { min-height/min-width: var(--size-touch) }` |
| `.sdlc/feat-four-pillars-v2/03-impl/prep-register-nfr07-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是

**未触碰「不许改的文件」**：☑ 确认（未改 GWT、未做支付、未改 `quota.ts` 数字、未 Wave 2/3、未削弱 GWT-04.x）

## 3. 关键实现决策

Register 展示组合三句，不另写数字：`免费档：{task_concurrency} / {result_storage} / {llm_tokens_month}` → 「5 个并发任务 / 10,000 条结果存储 / 20 万 LLM tokens/月」。

触摸：token `--size-touch: 44px` + class `.site-touch-target` + 内联 `minHeight/minWidth: var(--size-touch, 44px)`。jsdom 不解析 CSS 文件（identity-obj-proxy），量宽读 inline / getComputedStyle。未改 `--size-touch` 值。未做支付 CTA。

☑ 无「先查后插」☑ 无条件更新 ☑ 无新外部依赖

## 4. ORM 与 DBML 对齐

➖ N/A 本票不加列。☑ 未自行加字段/改类型

## 5. 可观测性 / 九维

未改数据获取。间距用既有 `--size-touch`，无新 hex。六态未扩。Register 失败/离线/成功路径未动。

## 6. 自测证据

> 命令与退出码**原样粘贴**。TDD：先红后绿。

### 6.1 Red（手写 10000；主钮无 minWidth/minHeight）

```
$ CI=true npm test --prefix frontend/official -- --runInBand --watchAll=false --testPathPattern='(Register|Home|Pricing)\.test' --testNamePattern='FREE_TIER_FEATURE_COPY|NFR-07'
FAIL src/pages/Register.test.tsx
  ● Register free-tier copy uses FREE_TIER_FEATURE_COPY (GWT Given 5 / 10,000 / 20 万)

    expect(received).toContain(expected) // indexOf

    Expected substring: "5 个并发任务"
    Received string:    "AutoAgents企业注册免费档：5 并发 / 10000 条结果 / 20 万 tokens/月企业名管理员邮箱密码创建企业"

      183 |   expect(copy).toContain(GWT_01_1.concurrencyPhrase)
          |                ^

  ● NFR-07 Register primary submit has 44px touch target

    Expected: >= 44
    Received:    0

FAIL src/pages/Home.test.tsx
  ● NFR-07 Home primary CTAs have 44px touch target

    Expected: >= 44
    Received:    0
    (minWidth；Hero height:54 已过 minHeight)

FAIL src/pages/Pricing.test.tsx
  ● NFR-07 Pricing primary CTAs have 44px touch target

    Expected: >= 44
    Received:    0

Test Suites: 3 failed, 3 total
Tests:       4 failed, 21 skipped, 25 total
```

exit: 1

根因：Register 手写 `10000` 无千分位、短语与 Pricing 三句不一致；主 CTA 未声明 minHeight/minWidth，jsdom 量得 0。

### 6.2 Green

```
$ CI=true npm test --prefix frontend/official -- --runInBand --watchAll=false --testPathPattern='(Register|Home|Pricing)\.test'
PASS src/pages/Register.test.tsx (23.353 s)
PASS src/pages/Home.test.tsx
PASS src/pages/Pricing.test.tsx

Test Suites: 3 passed, 3 total
Tests:       25 passed, 25 total
Snapshots:   0 total
Time:        28.476 s
Ran all test suites matching /(Register|Home|Pricing)\.test/i.
```

exit: 0

### 验收项逐条对应

| GWT / NFR | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-01.1 三数同 Pricing | `Register free-tier copy uses FREE_TIER_FEATURE_COPY (GWT Given 5 / 10,000 / 20 万)` | ✅ 页含三句；含 `10,000`；不含 `10000` |
| GWT-04.1 | `GWT-04.1 success primary goes to admin login…` | ✅ 未改断言 |
| GWT-04.2 | `GWT-04.2 failed register stays on form…` | ✅ |
| GWT-04.3 | `GWT-04.3 secondary is 再注册一家…` | ✅ |
| GWT-04.4 | `GWT-04.4 occupancy failure is generic…` | ✅ |
| NFR-07 | `NFR-07 Register primary submit has 44px touch target` | ✅ minHeight/minWidth ≥44 |
| NFR-07 | `NFR-07 Home primary CTAs have 44px touch target` | ✅ |
| NFR-07 | `NFR-07 Pricing primary CTAs have 44px touch target` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ | N/A（无写库） |
| 幂等 | ➖ | N/A（静态文案 + 触摸） |
| 并发写 | ➖ | N/A |
| 外部依赖失败 | Register 既有 offline 用例 | ✅ 未改；套件内仍绿 |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-07 | 官网主按钮触摸目标 ≥44px | Jest：Home「免费注册」、Pricing「免费注册」、Register「创建企业」inline/computed minHeight 与 minWidth ≥44 | jsdom（official Jest `--runInBand`） |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | Register 卖点现为 Pricing 同三句。NFR-07 量宽在 jsdom 读 inline `var(--size-touch, 44px)`（`--size-touch` 视为 44）；真机触控未测。GWT-04.x 未改。 |
| `/qc` | 条件 B：Register 不再手写 `10000`。NFR-07 有具名断言，不能再用「无量宽」整行 ⚠️。 |
| `/architect` | 无新错误码。未改 token 数值。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（Register+Home+Pricing 25）
- [x] 契约落位表已核对
- [x] 未改 GWT / 未做支付 / 未 Wave 2/3
- [x] 无硬编码连接串/密钥/端口
- [x] GWT-04.x 断言未削弱
- [x] 发现的上游问题已回报：无新歧义
