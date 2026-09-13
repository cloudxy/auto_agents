# FINDINGS · deliver · upgrade-four-pillars

> G-fresh reviewer（经理落盘）｜**decision: fail**  
> blocker 0 · major 2 · minor 2  
> 范围：L3 deliver（sre `checklist.md` only）。未审 enablement。不改 qc 有条件放行结论。

## Snapshot

- path: `06-deliver/checklist.md`
  sha256: `fd1ef1bbb89d8207792ef683ae7e94b349d7c871e096bdd8047b954a7b994263`
- path: `06-deliver/release-opinion.md`
  sha256: `4667a38977696cb156182579c05a9455c2d35d3e1a01ff6a3d8821681f348316`
- path: `.claude/rules/project_rule.md`
  sha256: `c5c56a48e365c3f6733dab379a811ca0aeaa6a25265ae2730a795debe619e456`

## FINDINGS

### QA-01 N1 非首选库回滚在 046 head 上可复制为 `downgrade 044`，会顺带毁掉 N3 密文/SKU
- **维度**：6 契约一致性
- **严重度**：major
- **证据**：`checklist.md:187-198` 在「已上 046」之后给出 `alembic downgrade 044`。线性历史下 = 046+045 一起撤。
- **修复建议**：仅当 `alembic current == 045` 才允许 `downgrade 044`；current 为 046 时只保留停工人，并写明从 046 执行 downgrade 044 会丢失商户密文且不可还原。
- **owner**：sre

### QA-02 N2 对「公司管理员打总开关」给出 403 与 404 两套 Then
- **维度**：6 契约一致性
- **严重度**：major
- **证据**：清单一面「期望非 2xx」，一面「必须 404 同形，不得 403」。实现与测是 403 FORBIDDEN（`require_platform_admin`）。T-09 的 404 同形不是这颗开关。
- **修复建议**：开关 curl 写死期望 `403 FORBIDDEN`；404 同形只钉 T-09/T-15/T-27 路径。
- **owner**：sre

### QA-03 046 被写成纯 ADD 可空列+小表
- **维度**：1 标准符合
- **严重度**：minor
- **证据**：046 还含 ALTER、生成列 UNIQUE、`plans.updated_at NOT NULL`。
- **修复建议**：维护窗口行写明 046 含 ALTER + UNIQUE + 非空列，低峰跑；不是纯 ADD。
- **owner**：sre

### QA-04 N1 只禁 `compose down -v`，无 `-v` 也会丢 Redis 队列
- **维度**：8 边界
- **严重度**：minor
- **证据**：redis 无卷；`compose down` 删容器即丢心跳/队列。
- **修复建议**：回滚禁止任何 `compose down`；写明无 `-v` 已丢 Redis，`-v` 再丢 MySQL。
- **owner**：sre

未发现清单写成四柱 GA、「当前可买」、活=SKU、HMAC=live、FakeRedis=北极星、SLA 承诺、无 limit_req 放行公网。

## 已查维度

| # | 维度 | 结果 |
|---|---|---|
| 1 | 标准符合 | ⚠️ QA-03 |
| 2 | 标准质量 | ⚠️ QA-01 |
| 3 | 证据有效性 | ✅ |
| 4 | 安全 | ✅ |
| 5 | 性能 | ✅ |
| 6 | 契约一致性 | ⚠️ QA-01、QA-02 |
| 7 | 规范 | ✅ |
| 8 | 边界 | ⚠️ QA-02、QA-04 |

## 总计

| 严重度 | 数量 | 已处置 |
|---|---|---|
| blocker | 0 | open 0 |
| major | 2 | open 2 |
| minor | 2 | open 2 |

**decision: fail** — `current_hat` 留在 deliver。不改 qc 有条件放行。
