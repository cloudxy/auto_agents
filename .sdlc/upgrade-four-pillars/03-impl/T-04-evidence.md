# T-04 evidence · 采集空态 / 拦住 UI / 申请提升着陆

> FR-U01 FR-U02 · frontend · N1  
> 实现帽会话中断后，经理补跑测试并落盘（代码已由 frontend 帽写入）

## Commands

```
npx jest --maxWorkers=2 --watchAll=false src/pages/Data.test.tsx
```

exit 0 · 6 passed（含 GWT-U01.2 真 0 与筛选空）

```
npx jest --maxWorkers=2 --watchAll=false \
  src/components/quota/UpgradeIntentButton.test.tsx \
  src/components/quota/QuotaBlockAlert.test.tsx \
  src/utils/collectBlock.test.ts \
  src/pages/Checkout.test.tsx \
  src/pages/Usage.test.tsx
```

先前 5 suites / 28 tests passed；Data 修 testid 后 6/6。

## What landed

- `constants/collectCopy.ts` 锁句；禁止「当前可买」
- `/data` 真 0 =「还没有结果，去提交采集」；筛选空 =「没有符合条件的结果」
- 配额 vs 工人句分家；`申请提升` 分角色（经办→联系管理员；买方→ `/billing/checkout?product=plan_pro` 空态）
- N1 结账页只空态「收款通道未开通」，不建单

## Not this ticket

T-16 通道 422；T-23 全站禁「当前可买」机械钉；T-19 完整结账。
