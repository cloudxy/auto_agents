# ADR-0020：出站拉数钥匙与渠道组令牌分平面；不得混名混用

> 状态：**accepted**
> 日期：2026-09-11｜决策者：architect 帽｜相关：spec v1.2 FR-51 / FR-60 / X-KEY；已兑 FR-13

## 背景

三把钥匙用户可见名已冻（spec §0.4）：出站拉数钥匙、渠道组令牌、平台网关钥匙。现网只有后两者的骨架（`relay_tokens.sk-` + `LITELLM.MASTER_KEY`）；出站拉数仍走 Dynaconf `EXTERNAL_API.KEY_BINDINGS`，租户无签发入口。诊断与 qa 都警告：有人会把 018c369 的 `sk-` 勾成 FR-51。CONTEXT 过期句「令牌不发给租户」不得当冻结句。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 出站未绑定仍拒绝、0 行 | 已兑 FR-13；GWT-51.3 |
| 渠道组令牌当出站钥匙 → 拒绝、0 行 | GWT-51.6 |
| 出站钥匙打渠道组 Base URL → 拒绝，不是套餐超限，用量不变 | GWT-51.10 |
| 明文只一次；事件不含明文 | NFR-04；FR-92 |
| 平台共享 `/spider/status|results|stats` 钥匙不得写成租户功能 | spec §5；诊断 backend §3.2 |

## 决策

1. **两个产品对象、两套存储、两套鉴权入口。** 出站拉数钥匙只服务 `GET /external/v1/public/data/{spider}`（`bound_tenant_id`）。渠道组令牌只服务独立 LiteLLM chat（ADR-0019）。平台 master **不**出现在任一租户复制框。
2. **出站钥匙是新的租户凭证行**（给 `/dba` 的是语义不是表结构）：一行 = 一把本企业钥匙；TenantMixin；禁止进 `TENANT_EXEMPT_TABLES`；只存 hash + prefix + 吊销时刻；明文只在签发响应。`bound_tenant_id` **先**查本企业凭证行，**再**查 `KEY_BINDINGS`（配置绑定保持 FR-13 行为）。旧字符串列表 / 未绑定仍拒绝。
3. **禁止**用 `relay_tokens` 加 type 列兼作出站钥匙。禁止签发出站钥匙时去 LiteLLM `/key/generate`。禁止把出站明文写成 `sk-` 前缀去「看起来像中转」。
4. **互否执法在服务端：** 出站查找命中集合不含 relay hash；对 Base URL 使用出站钥匙 = 网关不认（非套餐句）；对出站拉数使用 `sk-` 渠道组令牌 = 未绑定拒绝、0 行。
5. **平台共享 `API_KEYS` 三条**（status/results/stats）本特征 **不改成租户功能**（spec §5）。FR-51 不得收这三条当自助钥匙。

## 备选与否决理由

### 备选 A：一把 `sk-` 同时拉数和打网关

**否决理由：** 出站面一旦被盗可打平台模型；中转面一旦被盗可拉本企业结果。X-KEY 互否。GWT-51.6 / 51.10 会无法写单 Then。

### 备选 B：只把租户签发写入 `KEY_BINDINGS` / `.env`

**否决理由：** 不是自助产品；多实例配置漂移；密钥进配置树风险（FR-14 已离树）。租户吊销无法做行级状态。

### 备选 C：`relay_tokens` 加 `kind=outbound|relay`

**否决理由：** 生命周期与登记目标不同（一个进 LiteLLM，一个禁止进）。查询「当出站用」必须 `if kind`——边界泄漏。第二次若真有第三种钥匙再抽象。

### 备选 D：出站也登记 LiteLLM 虚拟 Key，用 metadata 区分

**否决理由：** 拉数钥匙出现在网关 Key 列表 = 把采集结果面暴露给数据面运维。无收益。

## 证据

```
spike：现网出站 vs relay
问题：relay 签发的 sk- 能否当 X-API-Key 拉数；出站绑定在哪
环境：读码 public.py bound_tenant_id → KEY_BINDINGS；
      relay_service issue_token 只写 relay_tokens；无 api_keys 路由
结果：两套完全不相交；租户无出站签发
结论：FR-51 必须新建租户凭证平面；禁止复用 relay 行
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 多一套凭证表 | 语义简单；查找两次（库 + 配置） |
| 用户可能仍混贴 | 页上产品名冻死；GWT-51.6/51.10 夹具 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 签发/吊销/拉数查找；禁止 import 把 relay 列成出站 |
| `/dba` | 出站凭证实体（合同 §7）；TenantMixin；禁豁免 |
| `/frontend` | 独立「出站拉数钥匙」入口，名称不得写成渠道组令牌 |
| `/qa` | 51.6 / 51.10 / 13 回归；明文不进事件 |

## 后续复审条件

若操作者关闭「平台共享三条也租户化」再开新 FR；本 ADR 不预授权。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-11 | proposed → accepted | 塑形第一 spawn |
