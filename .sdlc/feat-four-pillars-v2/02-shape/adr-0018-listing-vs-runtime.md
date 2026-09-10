# ADR-0018：上架 ≠ 停用 ≠ 验证 ≠ 订阅 ≠ 启用宿主

> 状态：**accepted**
> 日期：2026-09-08｜决策者：/architect｜相关：FR-30…45；D1–D29；CONTEXT「上架 / 停用 / 合集边」

## 背景

现网把「验证通过」写成分发前提（无 MCP → `health_status=degraded`，`test_b1c` 钉死），公开技能与公开能力两套发布闸，且没有 `listing_state` / 安装行。产品已冻：unlist 后商店不可见但已订仍在；订插件不带礼包；治理台七叶；无 enable-host 按钮。若方案把这些合成一个「status」枚举，客服会把「下架」说成「不能用」，测试会把 bogus 类型兜成技能。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| unlist ≠ 停用；已订行仍在 | FR-35；X-FR35 |
| 订插件不级联子行 | FR-34.8 / FR-35.6；D24 |
| 公开出现 = 上架 ∩ 治理 ∩ 许可 | FR-33 |
| 无 MCP 可 listed，验证态「未知」 | FR-40；X-LISTING |
| Wave 1 无「启用到宿主」 | X-HOST；D21 |
| 七叶，禁止六 Tab | FR-37；X-TAB |
| 商店不存在句只约束 GET 详情 | QA-21；GWT-32.3 |
| 非法类型失败，不兜成技能 | FR-44 |

## 决策

Power Market 用 **五条独立闸**，禁止合成一个字段：

| 闸 | 控制什么 | 不控制什么 |
|---|---|---|
| **listing_state** | 商店列表/搜索/预告/新订 | 已订行、引用解析 |
| **治理 status** | 已发布/推荐 vs 实验/测试中/已弃用 | 单独不足以公开 |
| **许可** | 默认未放行不公开、不可新订 | 已订行与引用解析（非黑名单） |
| **停用**（黑名单或软删） | 公开当不存在；引用跳过并审计；安装行只读（经办可卸、不可改启用/信任） | 不是 unlist |
| **验证 health** | 无 MCP = `unknown` 可 listed；声明了 MCP 但探测失败 = 不可用 | 不是法律担保、不是已在宿主运行 |

**安装行**是租户数据：`TenantMixin`，**禁止**进 `TENANT_EXEMPT_TABLES`。唯一键语义：（企业, 资产, 宿主）一行。再订另一宿主 = 新行。重复订同一宿主 = 已订阅、行数不变。卸载只删该行。

**合集边**（`capability_components`）只表达出处与引用，**不是**安装礼包。公开详情「包含」= FR-33 可见子卡；黑名单/软删永不出现。引用解析（超管/系统列表，非租户执行面）**忽略**子行 listing，跳过黑名单/软删。

**HTTP 形态（本程序选定，PRD 未写码）**：

- 打开未上架/黑名单 **公开详情**：与同站真 404 **字节级同形**（文案「页面不存在，可能已被移除或地址有误」）。禁止「已下架」。
- **提交订阅**未上架/黑名单/从不存在短名：同一 JSON 失败信封（建议 `code=MARKET_NOT_FOUND`），无新安装行，无「已下架」；**不**套官网 HTML 404。
- 预告项提交订阅：拒绝，`market_subscribe_rejected.reason=coming_soon`；预告页 **无**订阅按钮。

**公开列表**：查询侧完成 FR-33 闸 **再**分页。`total` = 仅可见行数。默认 `page_size=20`，最大 50。禁止先 `LIMIT` 再内存滤导致 total 漂。NFR-02 不把 GWT-33.4 当「没拉全表」的证明——本决策是查询侧闸。

**类型**：公开 `asset_type` ∈ `skill|plugin|command|agent|team`。库内 `expert`/`expert_team` **expand-contract**：一个发布周期映射到 agent/team 或 404，禁止第三套店。非法值（含 `bogus`）筛选失败，作废 `test_public_capabilities_invalid_type_falls_back_skill`。

**目录短名身份**（bundled slug、不改 `uq_asset_type_name_alive`、撞名失败）见 [ADR-0012](adr-0012-catalog-identity.md)。本 ADR 只管五闸与安装，不管身份键。

**治理台 IA**：顶栏七叶 源 \| 目录 \| 插件 \| 技能 \| 命令 \| 智能体 \| 专家团。窄屏滚动不删叶。无「上架全部子资产」。`dev-team` 插件行「已合并，不可上架」，子行不继承。同步 **不得**把第三方标 listed。

**会话**：逛在官网（可匿名）；订/卸在后台。未登录点订阅 → 登录回跳后 **尚未订**。

## 备选与否决理由

### 备选 A：一个 `status` 兼上架/停用/验证

**否决理由**：unlist 会误删已订；无 MCP 的包永远不能上架（与 FR-40 冲突）；客服把下架说成停用。

### 备选 B：「未经 verify 不得分发」（旧 ADR-0001 金标 / 现网 degraded）

**否决理由**：X-LISTING；Kimi 多数无 MCP。`degraded` 仅「声明了 MCP 但探测失败」。改枚举必须与 `test_b1c` **同 PR**（PIT-6）。

### 备选 C：订插件级联插入子技能/命令（礼包）

**否决理由**：D24 / GWT-34.8。合集边不是安装边。

### 备选 D：unlist 后拆掉已订行，或引用解析看子行上架态

**否决理由**：FR-35 / FR-36。观测点是安装行 + 超管引用列表，不要求站内执行引擎。

### 备选 E：先分页再内存滤（现网 `/public/skills`）

**否决理由**：PIT-5：页内过滤让 `total` 与翻页不稳定，GWT-33.4/33.5 可被「全表刚好一页」空过。查询侧闸后再 `COUNT`/`LIMIT`。

### 备选 F：治理台砍命令叶迁就「最多 6 Tab」

**否决理由**：X-TAB / FR-37。命令是独立可订卡片（FR-39）。

### 备选 G：Wave 1 做 enable-host / 代写 `~/.zcode`

**否决理由**：X-HOST / D21。详情只折叠说明片段。

## 证据

```
读码：plugin_service.verify_plugin 无 MCP → health_status=degraded；test_b1c 钉死
读码：public_skills.PUBLISHED_STATUSES = stable|recommended；capabilities 公开 list_assets(status="stable")
读码：ASSET_TYPES = skill/plugin/expert/expert_team；全库 0 命中 listing_state / capability_installs
设计：power-market-design.md D1–D29 Accepted
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 五闸组合爆炸 | 夹具 GWT-33.2 六行；「包含」GWT-32.9…32.12 |
| 双公开端并存一周期 | 商店闸只留一条读模型；旧 `/public/skills` 映射到市场技能筛或删除，禁止第三套 |
| `expert`→`agent` 枚举迁移 | expand 双值可读；禁止 rename `capability_experts` 表 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/dba` | listing / 安装 / 组件 / alias / commands 语义；安装表禁止豁免 |
| `/backend` | 单一读模型；订阅不级联；GET 404 vs POST NOT_FOUND 拆开 |
| `/frontend` | 七叶；预告无按钮；「我的安装」已下架可卸；迁 XSS 纯文本合同 |
| `/qa` | 作废 bogus→skill；安装行只读 vs 只读角色两句 |
| `/designer` | 七叶窄屏滚动；不重排后台五组 |

## 后续复审条件

操作者关闭 Q-MARKET-USER 并改主 CTA；或二期要站内执行引擎（那时引用解析才有运行时观测）。enable-host 必须另开 FR，不得挂在订阅成功上。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写；合并 listed≠verify 与 unlist≠停用 |
| 2026-09-08 | accepted（补） | SH-04：身份合同指针到 ADR-0012，不并入五闸 |
