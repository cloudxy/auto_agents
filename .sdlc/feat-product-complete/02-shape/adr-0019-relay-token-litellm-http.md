# ADR-0019：渠道组令牌经 LiteLLM 管理 HTTP 登记虚拟 Key；租户直打独立网关 chat

> 状态：**accepted**
> 日期：2026-09-11｜决策者：architect 帽｜相关：spec v1.2 FR-60 / FR-61；Q-RELAY 已决；ADR-0014（本 ADR **只 supersede**「不发租户虚拟令牌 / 租户浏览器禁直连网关端口」两条；其余 0014 仍生效）

## 背景

018c369 已能签发 `sk-` 并写入 `relay_tokens`（hash + prefix），但 **LiteLLM 从不认识这把钥匙**：`used_tokens` 恒 0，页上无 Base URL，GWT-60.3 无法成立。ADR-0014 在 **Q-RELAY 未关** 时写「不发租户虚拟令牌、租户浏览器禁止直连网关端口」——那是当时的范围锁，不是数据面禁令。Q-RELAY 已决「常见中转站」履约；本特征必须让令牌 **打到独立 LiteLLM**，且 backend **不持** `LITELLM.DB_DSN`。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 令牌按页上用法打平台网关；用量 0→≥1 | GWT-60.3 / 60.2 |
| backend 禁止网关 DSN | ADR-0014 备选 E；NFR-10 |
| 平台网关钥匙不发给租户 | spec §0.4；X-KEY |
| 不焊进根编排 | ADR-0010；操作者禁令 |
| 网关不可达 ≠ 套餐超限 | GWT-60.5；已兑 FR-74 |
| 吊销后不可再打网关 | spec 状态机；QA-20 |
| 60.3 Given 必须网关可达夹具 | QA-21 |

## 决策

1. **签发 = 扩现网 `RelayService.issue_token`，不是从零。** 在本地落 hash/prefix **之前或同一事务意图内**，用已有 `llm_gateway/admin.py` **新增** Key 管理 HTTP（`POST /key/generate` 或当前镜像 tag OpenAPI 等价路径），把组上的 models / rpm / tpm 映射为网关虚拟 Key 限额。响应里的明文只出现一次。本地行保存网关侧稳定引用（字符串 `gateway_key_id` / token id，**不是** DSN 行）。
2. **租户客户端按页上 Base URL 直打独立 LiteLLM 的 OpenAI 兼容 chat**（`/v1/chat/completions`）。Base URL = `LITELLM.PUBLIC_BASE_URL`（若配）否则 `LITELLM.BASE_URL`。仍是 `LITELLM.*` 前缀，不新造产品前缀。
3. **用量观察点 = 网关 spend / key info HTTP**，回填或展示 `used_tokens`。禁止 `create_async_engine` 打网关库。
4. **吊销 = 本地 `revoked_at` + 网关 HTTP 作废该虚拟 Key。** 吊销后再打 Base URL 必须拒绝（QA-20）。
5. **签发时网关 HTTP 失败 → 签发失败（可见，走 FR-84），禁止退回「只写本地 hash、HTTP 201」**（那是现网空壳）。
6. **租户仍禁止**：网关管理面、`LITELLM.MASTER_KEY`、改全局熔断/探针阈值。ADR-0014 的「租户禁直连」**仅对 chat + 虚拟 Key 放开**；管理端口 / master 仍禁。
7. **不**把 litellm 服务写入根 `docker-compose.yml`。

**明确不在本 ADR：** 是否把渠道组写成标价 SKU / 企业档专属 / 「当前可买中转」（Q-AGPL / Q-PRICE）。GWT-60.9 只冻官网 0 次该句。

## 备选与否决理由

### 备选 A：维持本地 `sk-` + hash，不登记网关

**否决理由：** 现网即此。GWT-60.2/60.3 用量恒 0、令牌打网关 = 无效钥匙。把骨架四测勾成完成态是合同错误。

### 备选 B：backend 反向代理，租户打 FastAPI，服务端用 master 转发 LiteLLM

**否决理由：** 租户令牌从未成为网关钥匙，「不是无效平台钥匙」的 oracle 变成 backend 自签；要在 FastAPI 再造一套 OpenAI 表面；与「常见中转站」（Base URL + sk- 贴进客户端）不符。HTTP 到 LiteLLM 仍发生，但履约对象错了。

### 备选 C：backend 持 `LITELLM.DB_DSN` 直接插 LiteLLM keys 表

**否决理由：** ADR-0014 备选 E。网关 PG 表结构不可控；lint 已禁 DSN。

### 备选 D：LiteLLM custom auth 回调本库校验 hash

**否决理由：** 本波多一条对外回调契约与鉴权环；仍要暴露网关 chat。第二次出现（多数据面）再评估。本波用官方 `/key/generate`。

### 备选 E：等 Q-AGPL 关了再履约

**否决理由：** Q-RELAY 已决「能用 + 能量」。Q-AGPL 只阻塞「当前可买中转」文案，不阻塞本企业令牌打网关。

## 证据

```
spike：现网令牌是否进网关
问题：issue_token 之后 LiteLLM 能否认证该 sk-，used_tokens 会不会增加
环境：读码 2026-09-11；relay_service.py L117–135 只 secrets+sha256；
      llm_gateway/admin.py 仅 model/spend/budget，无 /key/*；
      test_billing_relay.py 只钉 CRUD/明文一次/跨租户 404
结果：全仓无 used_tokens 写点；无 /key/generate
结论：必须扩 admin HTTP + 签发路径；禁止把四测当 60.3
```

LiteLLM Proxy 官方管理面提供 Key generate/delete/info（路径以 `/sre` 钉的 tag OpenAPI 为准）。本 spawn **未**起容器跑 generate。T-08 第一刀只读核对 OpenAPI；盖不住则签发失败可见，**仍禁止 DSN**。

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 签发依赖网关可达 | 60.5 同一失败句；禁止本地假成功 |
| 租户网络需到达 LiteLLM chat | PUBLIC_BASE_URL；管理面不暴露 |
| spend 回读最终一致 | 延迟窗口：成功调用后刷新列表可见 ≥1；对账=再打 key info |
| ADR-0014 条款部分 superseded | 本文写死范围：只放开虚拟 Key chat |

**最终一致口径（v2 修订，QA-04——只此一套 Then）：** 以 spec GWT-60.2/60.3 为唯一 Then：成功调用后，用户**打开或刷新渠道组页**即可见该令牌用量 ≥1（本地 `used_tokens` 缓存列经网关 key info 回填）；期间短暂见 0 **不得**渲染成「已用完」。发现不一致时以网关 key info HTTP 对账，不以本地列为金标。原文「可接受窗口 = 下一次打开页」的独立窗口表述作废——它不是第二套 Then，只是同一 Then 的迟到说明。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 扩 `llm_gateway/admin.py` Key HTTP；扩 `issue_token`/`revoke_token`/`list_tokens`；禁 DSN |
| `/dba` | 既有 `relay_tokens` 增加网关引用语义（§7）；禁止新网关 PG 表进 Alembic |
| `/frontend` | 页上 Base URL + 三步用法；明文一次；用量数字 |
| `/sre` | 不焊根编排；钉 PUBLIC_BASE_URL 与 chat 可达性；禁 `:latest` |
| `/qa` | GWT-60.3 夹具 **网关可达**（QA-21）；吊销后再打拒绝（QA-20）；A 不动 B |

## 后续复审条件

LiteLLM tag 去掉 `/key/generate` 且无等价 HTTP → 重开，仍禁 DSN。Q-AGPL 关闭后若渠道组变标价 SKU，只加文案/价目，不改本登记路径。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-11 | proposed → accepted | 塑形第一 spawn；supersede ADR-0014 两条范围锁 |
| 2026-09-11 | accepted（v2 修订） | shape r1 QA-04：用量可见 Then 收敛为 spec GWT-60.2/60.3 单一口径；QA-08 读模型补充见 contract v2 §7.4（列表读本地缓存、禁每行打网关）；QA-05 夹具口径见同节（chat 路径真实认证，裸 200 不算） |
