# frontend memory · post-merge-upgrade

> Facts this role learned. Cap **2200**.

## Last

- Date: 2026-09-14
- Hat: frontend (implement G-fresh r1 QA-01/03/05)
- Outputs: `03-impl/T-09-evidence.md`（## UI 追加）

## Facts

- W1–W4 仍真：规划未开放；导出 101；提交开通；去结账仅买方；出站名；渠道组已开通零令牌只「还没有令牌」；安装「还没有安装」；值班钥匙折进 `/newapi`；设置租户 404。
- T-09 QA-01：pending 金标「收款通道未开通，提交后等待平台确认开通」当 `can_pay===false` **或** `notice`/`empty_state` 该句 **或** `channels` 全 `configured=false`。Alert title 仍「待支付」。M11.2 打开未配仍商品+提交开通。
- GWT-M11.1 夹具=GET 真包络：`can_pay: false` + `notice`/`empty_state` 金标句 + `order_id`。`CheckoutPreview.notice` 可选。
- QA-03：`relayCopy.ts` 已删 `RELAY_EMPTY_GROUPS` 产品导出；RelayGroups 测仍把该句当禁句。
- F-7 Checkout 229。验证：`cd frontend/admin && CI=true npx jest --maxWorkers=2 src/pages/Checkout.test.tsx src/pages/RelayGroups.test.tsx` 26 passed exit 0；`bash tools/check/frontend.sh` 0。无 live 收银台。
- T-22/T-23 仍真：关旗「能力市场未开放」；开旗空「暂无已上架能力」；超管上架/下架 Toast；租户无投稿。

## Open (mine)

- GET `/ai/plans`.planning_disabled；POST checkout 无 channel。

## Do not re-litigate

- 禁四字。xlsx 非导出。P-FE-01 dist；P-FE-08 antd title。设置无说明态。市场两空句不得同屏。渠道组第三套空态不得产品导出。
