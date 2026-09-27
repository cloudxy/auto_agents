---
name: litellm-billing-defaults
description: LiteLLM 默认全关；计费是下单+超管确认；交付 webhook 租户 opt-in
metadata:
  type: decision
  origin: 2026-09-06/07 feat/litellm-l1
  status: active
---

# LiteLLM / 计费 / webhook 默认行为

不要把这些开关在代码里改成默认开。运维用配置打开。

## LiteLLM（`config/default/litellm.yml`）

全部默认 `false`：`LITELLM.ENABLED`、`PROXY.ROUTE_INTERNAL`、`SHADOW.ENABLED`、`ADMIN.ENABLED`。Sidecar 走 compose profile `litellm`，不进主 venv，禁止引入 `litellm` Python SDK。

## 计费

没有支付宝/微信网关。租户在用量页选渠道（`alipay` / `wechat` / `offline`）下单；超管在运营台「待确认收款」点确认后套配额。`GET /api/v1/billing/admin/orders` 仅平台超管。

## 交付 webhook

默认关。租户在用量页填写 `quota.delivery_webhook_url`（`PUT /tenants/me/delivery-webhook`）后，任务终态 HMAC POST。密钥只走 `AUTO_AGENTS_WEBHOOK__SECRET_KEY`。

## 相关

- `docs/claims.md`
