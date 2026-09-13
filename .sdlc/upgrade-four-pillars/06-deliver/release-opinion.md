# 放行意见 · upgrade-four-pillars N1–N4 v1.2

> 作者：/qc｜日期：2026-09-13｜决策对象：**工作区** N1+N2+N3+N4（T-01…T-27），**未冻结 SHA**；**非四柱 GA**
> 上游：`01-define/spec.md` v1.2 · `02-shape/contract.md` · `04-verify/coverage.md` · `05-review/findings.md`（verify G-fresh）
> 本文件替换盘上 **N1-only stale** 意见（归档 `release-opinion-n1.md`）。
> **结论必须是三者之一。** 不允许「基本可以」。

## 1. 结论

| 项 | 内容 |
|---|---|
| **结论** | **有条件放行** |
| 一句话理由 | N1–N4 的 25 条 FR-U 与本波 GWT 在矩阵有映射；verify G-fresh blocker=0、major=0；本窗 pytest/arch/mig/T-26/T-27 指纹绿。**不得**标四柱 GA。合入前须冻结 SHA 并补跑已配置的 admin+official **build**。 |
| 阻塞项数量 | **0**（无 blocker/major；无 exit≠0 闸门。缺 build 指纹 = 条件，不是改判红闸） |

### 有条件放行的条件（具体可执行）

| # | 条件 | 责任人 | 验证方式 |
|---|---|---|---|
| 1 | **不得**标四柱 GA；**不得**把本波写成生产北极星已出现 | `/pm` `/ops` | 对外材料无「四柱已 GA / 当前可买 / 支付已通」 |
| 2 | 访客与租户可见面 **禁止**「当前可买」四字。Q-AGPL 未关。支付通道能收款 ≠ 本问已答 | `/frontend` `/pm` | FR-U24 机械钉仍绿；文案评审禁该四字 |
| 3 | 值班行/页「活」**不是**中转 SKU `active`，也不是已买 | `/backend` `/frontend` | 产品面不得把 `duty_row_status=live` 写成 SKU 已开通 |
| 4 | HMAC / `signed_body` 夹具 notify **不是** live 支付宝/微信收银台；无 `pay_url` 不得写成已跳转托管页 | `/backend` `/sre` | 预发/生产接通前另开 live 通道窗；本波合入闸不含沙箱 |
| 5 | GWT-U01.1 的 120s 合格出数本波为 FakeRedis，**不得**宣称非夹具租户北极星已在生产出现 | `/sre` `/analyst` | live 工人窗另证；本意见不给北极星通过 |
| 6 | Q-OPS-DUTY：**不写 SLA 数字**。mock 网关 ≠ 生产值班 SLA | `/ops` `/sre` | 清单/公告/值班页无 SLA 承诺句 |
| 7 | 合入前对 **冻结 SHA** 重跑 `sdlc.config.yaml` 四闸，**必须含** admin+official build | `/sre` 合入执行 | 四闸命令 + 退出码 0 贴进新 checklist |
| 8 | `/sre` 重写 `06-deliver/checklist.md`（现盘为 N1 stale） | `/sre` | 新清单引用本意见条件 1–7 与本窗指纹 |
| 9 | [SEC-7] 应用层 notify **无** `RateLimitPolicy`。生产入口必须有反代限流，否则不得把 notify 打到公网 | `/sre` | checklist 反代 `limit_req` |
| 10 | QA-01 / QA-02 为文档 nits，**不阻塞合入**；下次 verify 刷新 coverage 措辞 | `/qa` | 下一次 coverage diff |

### 不放行时的最小修复集

不适用（结论不是不放行）。

## 2. 门禁指纹

| 项 | 值 |
|---|---|
| 决策对象 commit | **工作区 2026-09-13**（无冻结 SHA） |
| 各闸门执行的 commit | 同工作区；未冻结 → 条件 7 |
| 有无「测完之后又改代码」 | 本窗 implement N4 r2 → verify → review → qc，无产品代码再改记录 |

| 闸门 | 命令 | 退出码 | 状态 |
|---|---|---|---|
| 单元/集成 | `uv run pytest -x -q backend/tests` | **0** · 1679 passed / 40 skipped / 7 warnings · 241.54s | ✅ |
| T-26 | `uv run pytest -q backend/tests/test_fr_u25_duty.py` | **0** · 10 passed | ✅ |
| 架构 | `bash tools/check/arch.sh` | **0** | ✅ |
| 迁移 | `bash tools/check/db_migrations.sh` | **0** | ✅ |
| 构建 | `npm run build --prefix frontend/admin && npm run build --prefix frontend/official` | 本窗 qc 当时无指纹 | ⚠️ 条件 7 |
| 前端工程门禁 | `bash tools/check/frontend.sh` | **0** | ✅ 不替代 build |
| T-27 Jest | Overview3q + NewApiOps + App.menu | **0** · 43 passed | ✅ |
| 覆盖矩阵 | `check-matrix.py` | **0** · 13 条 FR-\d+ | ✅ 不抽 FR-U |
| SDLC | `--hat {implement,verify,review}` | **0** | ✅ |
| E2E | — | — | ➖ `e2e: null` |

本次无人工豁免。无失败闸门。

## 3. 覆盖完整性（摘要）

- FR-U **25/25** 有矩阵行；本波 GWT ❌ = 0
- `edge-states.md` 存在；T-01…T-27 evidence **27/27 在盘**（含 T-24）
- designer 未跳过；sre checklist 仍 N1 stale → 条件 8
- 抽查：notify 无 JWT；商品码 `plan_pro`/`plan_enterprise`/`relay`；禁「当前可买」

## 4. findings 处置

| 编号 | 严重度 | 状态 |
|---|---|---|
| QA-01 coverage 写 T-24 未交 | minor | **waived**（磁盘有证据；NFR-U03 ⚠️ 仍成立） |
| QA-02 GWT-U02.7 误引夹具行 | minor | **waived**（Then 仍有真实测） |

blocker 0 · major 0 · minor 2 waived。

## 5. 剩余风险

| # | 风险 | 判定 |
|---|---|---|
| R-01 | live 120s 工人未证 | 不可当北极星通过；条件 5 |
| R-02 | HMAC ≠ live 支付 | 禁止宣称能付已通；条件 4 |
| R-03 | 应用层 notify 无限流 | 无反代限流不得公网暴露；条件 9 |
| R-04 | Q-AGPL 未关 | 禁止「当前可买」；条件 2 |
| R-05 | mock ≠ 真 LiteLLM | 不写 SLA；条件 6 |
| R-06 | qc 当时无 build 指纹 | 合入前必须跑；条件 7 |

## 6. 人工豁免记录

本次无人工豁免。

## 7. 我做了什么 / 没做什么

qc 做了五类覆盖与放行判定。未修代码、未标四柱 GA、未代答 Q-AGPL。产出者不是 qc。

**decision: 有条件放行**
