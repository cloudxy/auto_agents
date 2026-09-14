# FINDINGS · shape G-fresh r1

## Snapshot

- spec.md `541c2793901e05f3b9b0c618b1d30425b813603d8f20a6f9030a77638d4a542c`
- contract.md `8fed1f8e09cbb17e8368f3ffa5231bb90173cce2cbe8eb1f4343d11a15b25f3f`
- adr-0026 `43aeb7cd28f9bc461f34f1c644ad31aa5cfaf7ca08c0aa34292e8ef8384a16c9`
- db-spec.md `c27ca7acc657f13639853fcd9b89c43d85eaa678c77eaf06b24d3ffc3481ceeb`
- schema.dbml `e2ab3fd98b77fc6843de65ac9444005cf705579030e775cec066cb3d308446be`
- edge-states.md `c3640309181de85ef86b9cd67d0bf3a6f0287bd70914af672821c643c7f64440`

Stage: shape. Verdict: **FAIL**.

### QA-01 ADR-0026 未点名 supersede 0024 决策 3 / 0025 决策 1
- Dimension: 6 | Severity: major | Evidence: adr-0026; GWT-M11.15; T-08
- Suggestion: 点名 supersede「plan_enterprise 只开通企业档」与「采集套餐 enterprise 不是该权益」；企业档履约写配额 **且** SKU=active；plan_pro 仍不得写 SKU。

### QA-02 渠道组已开通零令牌第三套空态
- Dimension: 6 | Severity: major | Evidence: edge-states 屏 12「还没有渠道组。创建后才能签发令牌。」vs GWT-M23.1「还没有令牌」+签发入口
- Suggestion: 删除第三套空态。已开通+令牌 0 只留金标「还没有令牌」+ 买方签发入口。

### QA-03 channel 放宽 NULL 仍 server_default=offline
- Dimension: 6 | Severity: minor

### QA-04 企业档配额夹具数字未进冻结 FR
- Dimension: 1 | Severity: minor

### QA-05 迟到回调未进票
- Dimension: 1 | Severity: minor

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 2 |
| minor | 3 |

**PASS/FAIL: FAIL**
