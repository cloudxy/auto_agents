# FINDINGS · verify N4 · upgrade-four-pillars

> G-fresh reviewer（经理落盘）｜**decision: pass**  
> blocker 0 · major 0 · minor 2（记下，不阻断）  
> 范围：post-qa review。implement N4 pass 归档：`findings-implement-n4-pass.md`

## Snapshot

- path: `01-define/spec.md`
  sha256: `2aa0b069303940da67768297d52be2e46f2f9aaf6bf0becce6f70af4069697ab`
- path: `02-shape/contract.md`
  sha256: `6fe8559b777c2b31a852bfd212a0c12e95607be2b925886504f9390fc12e534a`
- path: `04-verify/coverage.md`
  sha256: `25a9437ae7ccc34b7735e0890045949aedee978c4400642f218297b23263b2f3`
- path: `03-impl/T-26-evidence.md`
  sha256: `c083215edaba74665b3443a8160f7d445ec5dc398cba340571b720348079c158`
- path: `03-impl/T-27-evidence.md`
  sha256: `e3be88657a1d795ccfc51b6ee3a013aafa114c94adcdd30f39541f6d6079752e`
- path: `05-review/findings-implement-n4-pass.md`
  sha256: `832eaf9a71fc307bbba015c9c84ebf0e4305de23edcdbbcc57c4ce3b84b6e1ab`
- path: `.claude/rules/project_rule.md`
  sha256: `c5c56a48e365c3f6733dab379a811ca0aeaa6a25265ae2730a795debe619e456`

## FINDINGS

### QA-01 coverage 把 T-24 写成「证据不在磁盘 / 未交」，与磁盘不符；限流 ⚠️ 仍成立
- **维度**：3 证据有效性
- **严重度**：minor
- **证据**：`04-verify/coverage.md:5` 等写「T-24 未交」。磁盘有 `03-impl/T-24-evidence.md`。应用层 notify 无限流策略 → NFR-U03 ⚠️ 仍对。
- **修复建议**：改成「T-24 已交；[SEC-7] 应用层 notify 限流仍无 → NFR-U03 保持 ⚠️」。
- **处置**：记下，不阻断。

### QA-02 GWT-U02.7 格子引用了非测试行
- **维度**：3 证据有效性
- **严重度**：minor
- **证据**：`04-verify/coverage.md:75` `Checkout.test.tsx:36` 是夹具不是 `test(`。Then 仍由 `test_fr_u02_quota_copy.py` / `Usage.test.tsx` / `UpgradeIntentButton.test.tsx` 覆盖。
- **修复建议**：删掉误引；UI 行改成真实 test 路径。
- **处置**：记下，不阻断。

N4 GWT-U25.1…U25.4 映射成立（10 pytest / 43 Jest）。未宣称四柱 GA。可见面禁「当前可买」。值班「活」≠ SKU active。HMAC ≠ live 支付。

## 已查维度

| # | 维度 | 结果 |
|---|---|---|
| 1 | 标准符合 | ✅ |
| 2 | 标准质量 | ✅ |
| 3 | 证据有效性 | ⚠️ 见 QA-01、QA-02 |
| 4 | 安全 | ✅ |
| 5 | 性能 | ✅ |
| 6 | 契约一致性 | ✅ |
| 7 | 规范 | ✅ |
| 8 | 边界 | ✅ |

## 总计

| 严重度 | 数量 | 已处置 |
|---|---|---|
| blocker | 0 | open 0 |
| major | 0 | open 0 |
| minor | 2 | 记下 2 |

**decision: pass**
