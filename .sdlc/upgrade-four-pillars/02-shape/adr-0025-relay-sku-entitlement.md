# ADR-0025：中转 SKU 权益与「我的渠道组」产品面分家；值班页仍是超管

> 状态：**accepted**
> 日期：2026-09-12｜决策者：architect 帽｜相关：spec FR-U20…U23、FR-U33、`02-shape/contract.md`

## 背景

Q-RELAY 已答：中转是租户可买 SKU。v2 GWT-60.1「无我的渠道组」、GWT-07.3「租户直打中转站=404」在本特征 §0 已拆开：平台值班页对租户仍 404 同形；已开通 SKU 的「我的渠道组」(`/relay`) 是另一 When。现网 `relay_groups` / `relay_tokens` 在迁移 040 已建，签发走网关 HTTP，**没有**「已开通中转」权益。有组行 ≠ 已买。专业档支付也不得顺带把中转置 active（GWT-U33.1）。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 已开通才能打开「我的渠道组」用量并签发 | FR-U20 / FR-U23 |
| 未开通不得当已买；「去升级」商品=`relay` | FR-U21；GWT-U35.6 |
| 打开「我的渠道组」≠ 直打平台值班页 | spec §0 作废 GWT-07.3 合并句 |
| 专业档开通不得把中转 SKU 置 active | GWT-U33.1 |
| 已开通后经办不能签发 | GWT-U23.5 |
| 到期后旧令牌不可再用 | GWT-U23.6 |
| 浏览器不能直连平台网关 | FR-U22.4 |
| 017 业务表 `tenant_id` 禁止「NULL=平台候选」 | PIT-4 |

## 决策

1. **中转 SKU 权益是独立生命周期**（none → active → expired → active），由收款履约模块在 **商品=`relay` 且 FR-U38 验真通过并开通完成** 后写入。采集套餐档位（free/pro/enterprise）**不是**该权益。
2. **「我的渠道组」读/签发/吊销以权益为闸**：SKU ≠ active 时，不返回本企业渠道列表或可用令牌，不签发；页上「未开通中转」+ 买方「去升级」。**即使**库里已有 040 骨架留下的组行，未开通也不得展示这些行（隐藏，不在本波物理删除）。
3. **平台值班页**（`/newapi` 与 `/api/v1/newapi/*`）继续 `require_platform_admin_or_404`。租户打开 `/relay` 不是值班页，不得带平台上游 Key 全文，不得有「改全局熔断」成功控件。
4. **令牌**只服务本企业；明文只在当次签发响应出现；之后仅掩码。吊销/到期后令牌不可再用。签发角色闭集：公司管理员/开通负责人（与现网 `_ISSUER_ROLES` 一致），**已开通后经办仍拒绝**。
5. **不**把有 `relay_groups` 行、有 `menu:relay`、或专业档已开通，解释成中转已买。

## 备选与否决理由

### 备选 A：有 `relay_groups` 行即视为已开通

**否决理由**：040 骨架可能已给租户建组；GWT-U21.1 未开通必须无渠道列表。用行存在当权益会把骨架租户全部「已买」。

### 备选 B：继续用 GWT-07.3 合并句，租户永远不能有渠道组页

**否决理由**：spec §0 已 superseded。Q-RELAY 已答对外可买。再禁页面会否决 GWT-U20.1。

### 备选 C：专业档/企业档支付成功顺带开通中转

**否决理由**：GWT-U33.1 Then 钉死中转仍 none、令牌数 0、走 U21.1。商品码必须分家。

### 备选 D：已开通后经办可签发（与看用量同一权）

**否决理由**：GWT-U23.5 越权拒绝。看用量 ≠ 签发。现网 `_ISSUER_ROLES` 已是 owner/admin，本波保持并加上 SKU 闸。

### 备选 E：SKU none 时 DELETE 掉已有组行

**否决理由**：破坏性、不可逆、与「未开通隐藏」不等价。expand-contract：先闸读路径，组行仍属该租户，开通后可再看见。本波不删。

### 备选 F：令牌 `tenant_id` NULL 表示平台公共令牌

**否决理由**：PIT-4。令牌必须钉本企业；跨企业令牌读用量拒绝（GWT-U23.3 / U23.7）。

## 证据

```
读码：backend/services/relay_service.py
  无 SKU/权益字段；签发只查 _ISSUER_ROLES
  MSG_TOKENS_EMPTY / MSG_CANNOT_ISSUE 已冻
读码：backend/app/api/v1/relay.py 前缀 /relay；newapi.py GET 走 require_platform_admin_or_404
读码：frontend/admin/src/App.tsx path=relay 在主树；path=newapi 平台写面 404 同形
读码：alembic 040 建 relay_groups/tokens，并给 viewer/operator/admin 追加 menu:relay
读码：frontend/admin/src/pages/RelayGroups.tsx 无「未开通中转」空态
```

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 骨架租户开通前看不见已有组 | 产品正确；开通后组还在。文档写清「隐藏≠删除」 |
| 权益与组行两处状态 | 权益是唯一「已买」真相；组行是产品数据。履约模块写权益，relay 只读 |
| 到期要使旧令牌失效 | 校验走权益+吊销+过期三闸，不靠前端藏按钮 |

**最终一致**：支付验真到 SKU active 的窗口同 ADR-0024；期间「我的渠道组」仍按开通前（none/expired）。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | relay 读/写路径加 SKU 闸；签发失败句「中转已到期」；禁止经办签发 |
| `dba` | 权益实体语义见 contract §7；禁止 NULL 租户当平台 SKU |
| `/frontend` | `/relay` 三态：未开通 / 已开通无令牌 / 已开通有令牌；不是值班页 |
| `/qa` | U20.1 与 U22.2 必须分 When；U33.1 专业档后仍走 U21.1 |

## 后续复审条件

出现「套餐档位捆绑中转」的新商品时另写 ADR，不在履约里写 `if product == plan_pro: sku=active`。租户自助出站钥匙（v2 FR-51）仍下一轮，不与本 SKU 合并。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-12 | proposed → accepted | 塑形初版 |
