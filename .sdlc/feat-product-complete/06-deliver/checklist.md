# 上线检查清单 · feat-product-complete（release-opinion §9 执行）

> 执行：/sre（deliver 帽）｜日期：2026-09-12（机器时间 +0800）｜release sha：**743b96b**（钉版，见 §0）
> 输入：`06-deliver/release-opinion.md`（ship-with-conditions，C1–C5）
> 本清单角色：C1 本帽原样执行落档；C2–C5 为待办移交（命令出处 coverage §5.B），本帽不执行真网关/生产环境项。

## 0. Release sha 钉版

- `git rev-parse --short HEAD` → `743b96b`（分支 `feature/pm`，HEAD 即钉版 commit，无 detached）
- commit 主题：`docs(sdlc): feat-product-complete 全程工件——spec v1.6/contract v2.1/ADR×5/coverage 152/152/release-opinion（C1-C5）/42 份 evidence`
- 工作区注记：`deploy/litellm/.env.example` 与 `deploy/litellm/docker-compose.yml` 存在未提交改动（M 状态）。两文件均不在五闸扫描面的业务路径内，但按诚实口径记录在案；如需纯净钉版复跑，操作者可 `git stash` 后重跑（本轮未 stash，保持工作区原样）。

## 1. C1 五闸复跑结果（本帽执行，working tree @ 743b96b，含 §0 注记的两处 deploy/litellm 未提交改动）

| # | 闸门 | 命令（原样口径） | 退出码 | 结果指纹 | 开始时间(+0800) | 耗时 | 判定 |
|---|---|---|---|---|---|---|---|
| G1 | 后端单测 | `uv run pytest -q backend/tests` | **0** | `1546 passed, 39 skipped, 7 warnings in 154.88s (0:02:34)` | 2026-09-12 11:54:58 → 11:57:37 | 2m39s | 绿（skip 计数偏差见下） |
| G2 | 架构红线 | `bash tools/check/arch.sh` | **0** | `✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）`，0 违规 | 2026-09-12 11:54:58 → 11:55:02 | ~4s | 绿 |
| G3 | DB 迁移门禁 | `bash tools/check/db_migrations.sh` | **0** | `✓ 迁移破坏性变更检测通过`（strong_migrations 语义） | 2026-09-12 11:55:08 → 11:55:11 | ~3s | 绿 |
| G4 | 前端构建 | `npm run build --prefix frontend/admin && npm run build --prefix frontend/official` | **0** | admin `Compiled with warnings`（5 文件 TS unused-vars，非阻塞）+ official `Compiled successfully`；双 build folder ready to be deployed | 2026-09-12 11:55:18 → 11:55:38 | ~20s | 绿 |
| G5 | admin 单测 | `CI=true npm test -- --watchAll=false --maxWorkers=2`（frontend/admin） | **0** | `Test Suites: 35 passed, 35 total` / `Tests: 226 passed, 226 total` / Time 580.894s | 2026-09-12 11:55:42 → 12:05:24 | ~9m42s | 绿 |

**五闸退出码全 0。**

**指纹对照 qc §2**：

| 闸门 | qc §2 指纹 | 本次复跑 | 对照 |
|---|---|---|---|
| pytest | 1546 passed / 38 skipped | 1546 passed / 39 skipped | passed **精确一致**；skip +1（见红标） |
| arch | 0 违规 | 0 违规（13 红线 + 4 边界 + FR-14） | 一致 |
| 迁移门禁 | exit 0（041–044 可逆） | exit 0 | 一致 |
| 双 build | exit 0 | exit 0（admin 带 5 处 TS unused-vars 警告，非阻塞，未计入指纹） | 一致 |
| jest | 35 套件 224+ 全过 | 35 套件 / 226 全过 | 一致（满足 224+） |

> **⚠ 红标 · C1 指纹偏差一处（上抛人工判定，本帽不改判）**
> - 偏差内容：skip 计数 qc 记 38，本次 39（+1）；passed 1546 精确一致，fail/error=0。
> - 已做取证（证据链，非猜测）：
>   1. `git diff 2506797..743b96b -- backend scrapy platform_core config frontend` 为**空**——release sha 与 qc 门控代码位差为 0（743b96b 是纯 .sdlc 文档 commit，101 files / +17532 行全在 .sdlc/），**排除代码漂移**。
>   2. 39 个 skip 全枚举复跑（`-rs`）分类：MYSQL_FIDELITY 环境门控 15（sqlite 默认态按设计跳，qc §2 自认类别）/ test_newapi_services T-19 历史收敛 23 / `test_alembic_baseline.py:136` 静态 skip 1（errno 1553 记录性 skip，由链内 commit f069aa0 `fix(ci): skip known 1553 downgrade base` 加入，f069aa0 已验为 743b96b 祖先——即 qc 门控代码里同样存在）。15+23+1=39。
>   3. 结论倾向：38 为管理窗基线口径（coverage §0「管理窗给定基线」），与最终链上静态 skip 台账（f069aa0 +1）存在记账时点差；非测试结果退化。**但按 C1 条款「不一致即停」，本帽不豁免、不裁量**——需人工确认后 C1 方可记全绿（确认口径：认可上述取证即可闭环，无需改代码）。
>
> 附：39 skip 明细首行样本（完整列表可由 `uv run pytest -q backend/tests -rs` 复得，2026-09-12 复跑 138.92s 同指纹 1546/39）。

## 1.1 G1 复跑稳定性

同一 sha 下 G1 跑两遍（第一遍全量、第二遍 `-rs` 取枚举）：均 `1546 passed, 39 skipped`，exit 0——结果稳定，非偶发。

## 2. C3 待办 — 迁移链 staging/克隆 apply（责任面：/sre；时机：上线前）

- [ ] staging/生产克隆完整 apply 迁移链（含 041–044）
- [ ] up→down→up 可逆性现场复证
- [ ] alembic 039/040 环境漂移对齐（已裁 /sre）
- [ ] B-6 真库轮（注意 `auto_agents` 用户 1044 无 CREATE 权限 → 用 root 或预授权）
- 命令出处：coverage §5.B-6

## 3. C2 待办 — 真网关轮 B-2+B-3（责任面：/sre + /qa；时机：向租户开放渠道组/令牌前，硬闸）

- [ ] `LLM.ENABLED` + 上游 key（机外配置，不进 git）
- [ ] T-09 口径：Bearer=签发明文 → chat → used_tokens≥1 → 恰 1 条 relay_token_call_succeeded
- [ ] B-3：打出站钥匙验拒绝形态 + 用量基线不变
- [ ] 顺跑 B-4 探针真引擎一枪
- 失败=环境闸未过，QC 不豁免，上抛人工
- 命令出处：coverage §5.B-2 / §5.B-3 / §5.B-4

## 4. C4 待办 — 队列/工人环冒烟（责任面：/sre；时机：上线前）

- [ ] Redis + worker 起链
- [ ] AI 方案 → 试采 → 轮询 completed（任务终态 completed 即过）
- 命令出处：coverage §5.B-5

## 5. 环境密钥三件套（机外配置，仓库零 DSN/零明文）

- `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD`
- `AUTO_AGENTS_REDIS_DEFAULT_PASSWORD`
- `AUTO_AGENTS_JWT__SECRET_KEY`（双下划线嵌套；`.env` 不做 `${VAR}` 展开）

## 6. 上线后红线抽检（四条）

- [ ] `/skills` 零种子
- [ ] 官网零「当前可买」
- [ ] 租户直打 `/platform-ops` `/newapi` → 404 同形
- [ ] 平台租户改名/停用被拒

## 7. C5 待办 — 性能口径（责任面：/qa + /sre）

- [ ] 上线当日：B-1(b) curl P95 冒烟（≥50 样本）
- [ ] 上线后 3 天内：B-1(a) Playwright 全量 P95
- [ ] P95≥2s 告警接线确认
- 命令出处：coverage §5.B-1

## 8. ops 交接

- 不可逆面操作者须知：release-opinion §8（收款确认单向门 / 令牌钥匙明文只显示一次 / 基座守卫不可绕）——上线时随交付 ops，原文以 release-opinion.md 为准
- B-7（WACT/PC）四周窗：**自上线日起算**，中途不下成败判定

## 9. 回滚预案

- 回退上一构建 + 迁移 041–044 down 路径（可逆链已在本仓门禁 G3 验证）
- 本特征以增量为主（新增迁移 041–044 / 新端点），无 destructive 变更面

## 10. 分支状态

- `feature/pm` = 743b96b，**未推送**（无 upstream 跟踪分支；领先 `origin/main` 8 commits）
- 推送与否由操作者决定（本帽禁 git commit / push）
