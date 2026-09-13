# FINDINGS · implement N4 · upgrade-four-pillars

> G-fresh reviewer（经理落盘）｜**decision: fail**  
> blocker 0 · major 2（unwaived） · minor 3  
> 范围：N4 only（FR-U25 / T-26 / T-27）。未把 N1–N3 当本轮缺陷。

## Snapshot

- path: `01-define/spec.md`
  sha256: `2aa0b069303940da67768297d52be2e46f2f9aaf6bf0becce6f70af4069697ab`
- path: `02-shape/contract.md`
  sha256: `6fe8559b777c2b31a852bfd212a0c12e95607be2b925886504f9390fc12e534a`
- path: `02-shape/edge-states.md`
  sha256: `2df4b1dd217c0c0b375819c3561e308e3c3bc3c83ffe723fc35ff743edb1793e`
- path: `03-impl/T-26-evidence.md`
  sha256: `a1abef60bdeaf456657404121bb172569ea2a1ebd2596e2745e8101a4f06ea9e`
- path: `03-impl/T-27-evidence.md`
  sha256: `b9389a34c5e3256e07bf04426229620c7b87e7ef82e625962852f8278984b77b`
- path: `backend/tests/test_fr_u25_duty.py`
  sha256: `65f3cc9db9581ee34c8857942fa7035c17dd08e7f8df8490981356d18ddf172d`
- path: `backend/services/gateway_models.py`
  sha256: `fe9c3c08c953d857f0697541493b9534a192486a0e39916e703a1707525c32d4`
- path: `backend/services/newapi_overview_service.py`
  sha256: `f360ce97ab081a1d4e156cc456f61ee87050189f28c7d3499a3c47e66a9d9577`
- path: `platform_core/schemas/newapi.py`
  sha256: `2a0fc700bed139b88148d149a18a23194fe42f83746451f5a8887cb1c0654601`
- path: `frontend/admin/src/components/newapi/newapiShared.ts`
  sha256: `e6f13303ae5dd673f09800f15bb2500e83b6ec7070a280772942193c974cfece`
- path: `frontend/admin/src/components/newapi/Overview3q.tsx`
  sha256: `bbe45b284c0ba780445dfda7e9aea0df6126da57893905529513488943c95bda`
- path: `frontend/admin/src/components/newapi/OverviewChannels.tsx`
  sha256: `c0553875c4876b557cd678f939c536b398402cb6aee4f11d81321f234c98638f`
- path: `frontend/admin/src/components/newapi/Overview3q.test.tsx`
  sha256: `79e5aaefd3fa8d703f00acf99c40510b2f38427471ffc7348ced46211e257f72`
- path: `frontend/admin/src/pages/NewApiOps.test.tsx`
  sha256: `78da9a77377416827e418aadec51fc6fdcc29ab164a412ddbf86f261887d1f26`
- path: `frontend/admin/src/App.menu.test.tsx`
  sha256: `db7fe3549a04e9871ead0416e218115e12c0530408ba8b8914ea6cc9293414f9`
- path: `.claude/rules/project_rule.md`
  sha256: `c5c56a48e365c3f6733dab379a811ca0aeaa6a25265ae2730a795debe619e456`

## FINDINGS

### QA-01 T-27 证据无法复现本快照
- **维度**：3 证据有效性
- **严重度**：major
- **证据**：`03-impl/T-27-evidence.md:41`（写「T-26 仍 todo」「活不另开 API 字段」）；同文件 `:79`（`Tests: 37 passed`）；`:120`（Overview3q 340 行）。对照本快照：`Overview3q.tsx:10-11` / `newapiShared.ts:52-99` 已消费 `duty_page_state` / `duty_row_status*`；三份 Jest 现为 13+15+14=**42** 条 `test(`；`Overview3q.tsx` 止于 **354** 行。多出的 5 条正好是 Overview3q 里 T-26 字段优先的单测（`Overview3q.test.tsx:111` 起）。
- **修复建议**：按本快照重跑并原样粘贴 Jest / `check-frontend.sh` / 行数；删掉「T-26 仍 todo」；禁句扫描给出命令而不是叙述。
- **owner**：frontend

### QA-02 页级三态互斥被 `duty_page_state` 单字段盖掉
- **维度**：6 契约一致性
- **严重度**：major
- **证据**：屏 19（`edge-states.md:62,911`）锁「有任一活行时页级标题不得改回空/降级句」。`newapiShared.ts:93-99`：`isDutyPageState(dutyPageState)` 先于 `hasLiveRow`；单测 `Overview3q.test.tsx:117-119` 把 `hasLiveRow: true, dutyPageState: 'empty'` 期望成 `'empty'`。同文件 `:258-271`「live row hides empty」**不传** `duty_page_state`，因此钉不住生产路径（T-26 在 0 模型时必发 `empty`，见 `gateway_models.py:102-103`）。`Overview3q.tsx:57-60,183-190` 总览与 channels 分两次 react-query，缓存不一致时可达「空句标题 + 行上「活」」。`showDutyLiveRow`（`newapiShared.ts:60-62`）在 API 已给 `live` 时忽略 `gatewayAvailable`；`:137-141` 把「gatewayAvailable: false 仍为活」写成金标，与屏 19 降级「禁止把行标活」（`edge-states.md:907`）相反。
- **修复建议**：`error/loading` 之后：`hasLiveRow` 压过 empty/degrade；行「活」必须 `gatewayAvailable && (API live ∨ 本地 original)`。改掉那两条把冲突组合写成通过的单测；补一条 `duty_page_state=empty` + 活行 → **不得**出空句。
- **owner**：frontend

### QA-03 U25.4「无活行」断言在空列表上恒真
- **维度**：3 证据有效性
- **严重度**：minor
- **证据**：`backend/tests/test_fr_u25_duty.py:162-163`：先 `assert body["models"] == []`，再 `all(m.duty_row_status != live for m in models)`。降级路径本来就不注释行（`newapi_overview_service.py:64-67`），该全称命题对空列表恒真。GWT-U25.4 的「禁止把行标活」实际由前端本地探针行覆盖（`Overview3q.test.tsx:198-220`），后端这条不是证明。
- **修复建议**：要么删掉空列表上的全称断言，要么构造「降级响应里若出现 model 行则不得 `duty_row_status=live`」的非空夹具。
- **owner**：backend

### QA-04 可达且已登记但无 original 的第四态未钉
- **维度**：8 边界
- **严重度**：minor
- **证据**：`gateway_models.py:104-106` 在 available ∧ models ∧ 无 live 时返回 `(None, None, None)`。T-26 证据把这写成「模型在但无 original 时为 null」，但 `test_fr_u25_duty.py` 无此 Given。GWT-U25.2 的 Given 是「未登记任何平台模型」，管不到「有模型、探针未 original」。回归时 null 若被当成 empty，会把已登记页画成「还没有平台模型」。
- **修复建议**：加一条：可达 + ≥1 模型 + 无 original → `empty_state`/`degrade_state` 均为 null、`duty_page_state` 不是 empty/degrade、行不是「活」、正文无「暂无渠道」。
- **owner**：backend

### QA-05 值班总览按渠道拉「最新探针」无时间窗/上限
- **维度**：5 性能
- **严重度**：minor
- **证据**：`backend/repositories/newapi_repository.py:183-198` `latest_result_per_channel`：`GROUP BY channel_id` + `MAX(id)` 后把**全部**渠道最新行载入 dict；`newapi_overview_service.py:64-66` 每次 `get_overview` 在可达且有模型时调用。探针表随历史 `channel_id`（含 string-ref 的 sha256 映射）只增不减。
- **修复建议**：按当前网关 `gateway_ref` 集合过滤，或限制回看窗口/条数；不要让值班总览扫完整探针历史。
- **owner**：backend

## 已查维度

| # | 维度 | 结果 |
|---|---|---|
| 1 | 标准符合 | ⚠️ 见 QA-02 |
| 2 | 标准质量 | ⚠️ 见 QA-04 |
| 3 | 证据有效性 | ⚠️ 见 QA-01、QA-03 |
| 4 | 安全 | ✅ [SEC-4] 租户 404 同形+越权留痕；无完整 Key；伪装无关渠写 |
| 5 | 性能 | ⚠️ 见 QA-05 |
| 6 | 契约一致性 | ⚠️ 见 QA-02 |
| 7 | 规范 | ✅ Router 未 import ORM；tsx ≤400；无硬编码连接串/密钥 |
| 8 | 边界 | ⚠️ 见 QA-04；离线句无测 |

## 总计

| 严重度 | 数量 | 已处置 |
|---|---|---|
| blocker | 0 | open 0 |
| major | 2 | open 2（QA-01、QA-02） |
| minor | 3 | open 3（QA-03、QA-04、QA-05） |

**decision: fail** — 不得推进 verify。`current_hat` 留在 implement。返工 owner：frontend（QA-01/QA-02）∥ backend（QA-03/QA-04/QA-05）。

未单列、已核对为通过的合同点：GWT-U25.1/2/4 在一致夹具下空/降级/活互斥且禁「暂无渠道」；GWT-U25.3 租户 API/页 404 同形；伪装不关渠；值班「活」≠ SKU active；所列源码无「当前可买」。
