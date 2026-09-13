# FINDINGS · shape · upgrade-four-pillars

> G-fresh reviewer（经理落盘）｜**decision: pass**  
> blocker 0 · major 0 · minor 1

## Snapshot

| path |
|---|
| 02-shape/contract.md |
| 02-shape/db-spec.md |
| 02-shape/schema.dbml |
| 02-shape/edge-states.md |
| 02-shape/adr-0024-notify-driven-checkout.md |
| 02-shape/adr-0025-relay-sku-entitlement.md |
| 01-define/spec.md |

N1=T-01…T-07，不含验真/履约。T-15…T-22 全在 N3。[SEC-1]/[SEC-2]/[SEC-3] 有 GWT 锚。可见面无「当前可买」。

## QA-01 [SEC-7] 限流 Downstream 钉错 NFR — minor

限流应锚 T-24 或补带阈值 NFR，不要把 NFR-U01 当 DoS 锚。不阻断进入实现。

**decision: pass**
