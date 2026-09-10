# ADR-0016：产品事件进 OLTP 追加表，不进数仓、不混用审计日志

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：FR-15 FR-30、`metrics-blueprint.md`、`contract.md` §7
> 本文件是塑形 v2 **新建**。

## 背景

北极星 WACT 与四条驱动指标的验收口径是 **事件可查**（蓝图）。全库无 `official_page_viewed` / `task_completed` 等事件名。`operation_logs` 是操作审计（actor + action + target），无事件名、无匿名访客、无 `tenant_id`，analyst **禁止**当漏斗分母。数仓 ODS/DWD 不存在，warehouse 诊断：本波不建仓。

没有可查询存储，四周后无法判定——这是 FR-15/30 的阻塞，不是分析偏好。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 事件必须能按时间查出 | FR-15/30 GWT |
| 失败不得阻塞用户主路径 | FR-15 |
| 不建数仓 | spec T-23；warehouse 诊断 |
| 审计 ≠ 漏斗 | analyst / 蓝图 |
| 时区 Asia/Shanghai 业务日 | FR-16 |

## 决策

Wave 0 在同一 MySQL 建 **产品事件追加表**（实体名由 /dba 定；语义见 `contract.md` §7）。

- 一行 = 一次已发生的产品事实。不软删。
- `occurred_at` = 事件发生时间；切日用上海日历。
- 写入与业务事务解耦：失败只打日志，主路径仍 2xx。
- 查询面：平台超管按时间 + event_name 翻页；租户不得查他租户用户级事件。
- 保留 ≥90 天。v1 不进 Redis、不上外部分析 SDK。
- 事件名与字段 **冻结为蓝图 §5**，architect 不改口径。
- `task_completed` 必须带 `is_marketplace_candidate`、`spider`、`source`、`result_count`。

## 备选与否决理由

### 备选 A：用 `operation_logs` 冒充漏斗

**否决理由**：无事件名枚举、无匿名页、无 tenant_id。蓝图与 analyst 明确禁止。改审计表当漏斗会污染合规留痕。

### 备选 B：本波建 ODS 并从仓查 WACT

**否决理由**：无稳定带租户的明细可入仓；warehouse 三块就绪度全未就绪。会与蓝图形成第二套口径。

### 备选 C：只打应用日志，四周用 grep 复盘

**否决理由**：GWT 要求「埋点查询面按时间查出」。日志轮转、无租户过滤、无法给 qa 写用例。

### 备选 D：引入 Segment/PostHog/自建分析服务

**否决理由**：新外部依赖 + 密钥 + 合规。本期 n=0，先 OLTP 可证伪。复审条件见下。

## 证据

ops/analyst：事件名 grep 0 命中。`operation_logs` 无 tenant_id。蓝图验收「以事件为准」，任务表弱重构不算过。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 主库多一张日志型表 | TTL 90 天；禁止当配额闸依赖 |
| 写入失败用户无感、qa 可能漏事件 | 验收查查询面；失败不挡主路径是产品规则，不是免测 |
| 匿名 → 租户拼接仍可能断 | `tenant_signup_succeeded` 带 tenant_id；登录成功必须能关联企业；anonymous_id 尽量贯穿注册前 |

选最终一致：事件相对业务提交可晚 **数秒**；用户主路径看到的是业务结果，不是事件行。丢失窗口：进程崩溃可能丢最后几条——可接受（漏斗基线，非账务）。发现不一致时：不回放，记下缺口。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/dba` | 实体/访问模式/TTL；autogenerate |
| `/backend` | 写入叶子 + 超管查询 API |
| `/frontend` | official/admin 调用；失败忽略 |
| `/qa` | GWT-15/30：查询面真能查到 |
| `/analyst` | 不改事件名 |

## 后续复审条件

事件量把主库 P95 打到 NFR 红线；或需要跨实例漏斗且 OLTP 查询不够。那时再评估外部 SDK / 仓，必须新 ADR。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 新建 |
