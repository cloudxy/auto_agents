# FINDINGS · deliver r2 · upgrade-four-pillars

> G-fresh reviewer（经理落盘）｜**decision: fail**  
> blocker 0 · major 2 · minor 2  
> r1 QA-01…QA-04 **关闭**。本轮新开 QA-05…QA-08。

## Snapshot

- path: `06-deliver/checklist.md`
  sha256: `205586631b5778d69a67ea19408c4c7a007d3a78cc91bb4df41467df69108102`
- path: `06-deliver/release-opinion.md`
  sha256: `4667a38977696cb156182579c05a9455c2d35d3e1a01ff6a3d8821681f348316`
- path: `.claude/rules/project_rule.md`
  sha256: `c5c56a48e365c3f6733dab379a811ca0aeaa6a25265ae2730a795debe619e456`

## FINDINGS

### QA-05 N2「订一行」curl 少 `{asset_type}/{name}`
- **维度**：6 契约一致性
- **严重度**：major
- **证据**：`checklist.md:257` `POST /api/v1/public/capabilities/<asset>/subscribe`。路由是 `/capabilities/{asset_type}/{name}/subscribe`。
- **修复建议**：curl 改成两段路径（例 `skill/<name>`）。
- **owner**：sre

### QA-06 档 3 把环境变量开市写成可执行，但 DUTY_CONTACT 空时启动即拒
- **维度**：8 边界
- **严重度**：major
- **证据**：`POWER_MARKET.ENABLED=true` 且联系人为空 → `RuntimeError` 拒绝启动。进程内 PUT 不走该守卫。
- **修复建议**：本波 DUTY_CONTACT 空 → 档 3 **只允许**超管 PUT；禁止只靠环境变量重启开市。不要代填号码。
- **owner**：sre

### QA-07 Caddy「等价」段只去了 JWT，没有限流等价
- **维度**：4 安全
- **严重度**：minor
- **证据**：nginx 有 `limit_req`；Caddy 一句只 reverse_proxy。
- **修复建议**：补 `rate_limit` 或写明无限流等价 = 不得公网，停在档 4。
- **owner**：sre

### QA-08 根 compose 声明 external `litellm-net`，清单无建网前置
- **维度**：8 边界
- **严重度**：minor
- **证据**：`docker-compose.yml` `networks.litellm-net.external: true`。
- **修复建议**：清单第一步 `docker network create litellm-net`（已存在则跳过）。
- **owner**：sre

## 总计

| 严重度 | 数量 | 已处置 |
|---|---|---|
| blocker | 0 | open 0 |
| major | 2 | open 2（QA-05、QA-06） |
| minor | 2 | open 2（QA-07、QA-08） |

**decision: fail** — deliver 第二轮返工，挂 debug_protocol。不改 qc 有条件放行。
