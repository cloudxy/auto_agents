<!-- manager 落盘：2026-09-27，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# Findings：F1-product（产品：价值、功能地图、核心旅程、定价与对外宣称）

## Snapshot（沿用 manager 提供的值，本人未计算）
- HEAD 82259f301c060dbf411424ec8775f29944e313e1（工作区仅新增 docs/ops/）；explore_roots `git ls-files -s` sha256 7535c4acfe0ae95a82be684709cdbf17b7a91dad5b70333f4127058b1bdd07c1
- reviewer：sdlc-workflow:reviewer（G-fresh，只读）；packet：`/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F1-product/packets/2026-09-27-2310-review-reviewer-F1-product.md`
- 评判依据：findings 9 维；产品标准按 prd-gwt 的要求判断，宣称核验按 growth 的要求判断（两份 skill 未加载，只按其标准判断）。
- 实际做了什么：静态阅读代码和配置，查看了 12 张截图，读了 manager 的运行记录（ui-runtime-summary.md、devdb-readonly.txt）。**我没有执行任何命令，也没有独立复现任何问题。**需要复现的地方写在文末「需 manager 代跑的验证」。
- 与第一轮 R7 的关系：没有重复 R7 的问题。QA-9 补了新证据，把 R7 QA-11 的【未验证】升级为已证实，并扩大了范围。QA-7 讲的是 R7 QA-3 的产品和货架层面，R7 QA-3 讲的是写入路径安全，两者角度不同。

---

## FINDINGS

### QA-1 定价口径有三套说法互相矛盾：定价页写「企业档定制／不限并发」，后端实际是 ¥999 和 50 并发，首页又说「尚未开通购买」
- Dimension: 1 · 6 · 9 | Severity: **major** | 工作量: M | 核验方式: 截图 + 静态
- 现象：
  - 官网和后台的定价页（截图 `official_pricing-1440.png`、`admin_pricing-1440.png`）：企业档写「定制」「不限并发（协商）」，主按钮是「去结账」。
  - 首页底部 CTA：`frontend/official/src/pages/Home.tsx:208`「专业档与企业档尚未开通购买。」
  - 后端种子：`backend/alembic/versions/047_w2_channel_null_pro_quota.py:19,38` 企业档 `price_cents=99900`（¥999/月），`task_concurrency: 50`，和专业档的 50 一样。
  - 履约兜底：`backend/services/billing_fulfill.py:98-106` 同样给 50 并发。
  - 结账金额读取：`backend/services/billing_service.py:151-162` 从 plans 表取价，所以企业档结账页会显示 ¥999。
  - 计费描述也有两种说法：`CONTEXT.md:48` 说「无支付宝/微信网关」，`backend/services/billing_service.py:1-2` 说「在线结账（支付宝/微信真实网关）」。另外还有 `/admin/payment-credentials` 和 `/external/v1/payments/{alipay,wechat}/notify` 两组路由（module-inventory.md:28-31,255-256）。
- 触发条件：租户负责人在官网定价页点企业档「去结账」，会看到「企业档 ¥999」，付款履约后只拿到 50 并发；访客同时在首页读到「尚未开通购买」。
- 根因：
  - `frontend/official/src/pages/Pricing.tsx:55-67` 把企业档文案硬编码在前端，没有从 `GET /api/v1/billing/plans` 读取。
  - 只有免费档和专业档共用 `frontend/shared/src/constants/quota.ts:6-39`，企业档没有单一数据源。
  - 企业档怎么定价、首页那句话是否作废，这些战略决定都没有产品层记录可查。
- 后果：宣称的「不限并发」和「定制」与实际收费、交付不符，有退款和虚假宣传风险。同一个访客会看到三种说法，影响转化。
- 修复方案：
  1. 先回答 Q-PRICE-ENT 和 Q-PAID-OPEN。
  2. 两个定价页、结账页和首页 CTA 改为统一从 `/billing/plans`（加 quota_json）渲染。
  3. 如果企业档是「定制」：CTA 改为联系销售（复用 `/public/ops-contact`），并从 `CHECKOUT_PRODUCTS` 移除 `plan_enterprise`。
  4. 如果企业档是固定价：定价页显示 ¥999 和真实配额。
  5. 删掉 `Home.tsx:208`，或按开关显示；同步修正 `CONTEXT.md:48`。
- 应补的测试或验收：
  - 契约测试：每张付费卡的价格和配额与 `/billing/plans` 返回一致。
  - 断言企业档配额不等于专业档，或者文案与配额一致。
  - 首页文案扫描：付费档可以购买时，不得出现「尚未开通购买」。

### QA-2 付费档宣称的权益没有实现：「私有技能库」「不限并发」「工单支持」「专属客户成功」
- Dimension: 1 · 9 | Severity: **major** | 工作量: S（改文案）/ L（真做） | 核验方式: 静态 + 截图
- 现象：
  - 企业档卡片（`Pricing.tsx:59-66`）列出「私有技能库」「不限并发（协商）」「专属客户成功」，专业档列出「工单支持」（`:51`）。
  - 能力资产是平台级的，租户用不了私有资产：`platform_core/models/capability.py:24,53` 注明「平台级公共资产 tenant_id 恒 NULL」，`CONTEXT.md:11` 也这样写。
  - 路由清单里没有工单或支持域（module-inventory.md 全表），只有 `/public/ops-contact` 一个邮件入口。
  - 「不限并发」与 QA-1 的 50 并发矛盾。
- 根因：定价权益清单是营销文案，没有逐条对应到实现或运营承诺；`docs/claims.md:5-14` 一条也没有覆盖。
- 后果：企业客户按权益付费后拿不到这些能力，属于直接的履约违约风险。
- 修复方案：
  - 每条权益标成「已实现（附锚点）」「人工服务（附 SLA 和负责人）」或「预告」三类之一。
  - 「私有技能库」在实现租户级资产前先撤下或标预告。
  - 「工单支持」如果是人工邮件，改写成「邮件支持（工作日 X 小时响应）」，并指定运营负责人。
- 应补的测试或验收：claims 表扩展到定价页每一条，并加符号级锚点测试（见 QA-9）。PM 验收清单逐条勾选。

### QA-3 中转站／LLM 网关是否卖给租户还没有人拍板，但定价、菜单、商品目录和履约里都已经露出
- Dimension: 1 · 6 · 9（未拍板的战略决定） | Severity: **major** | 工作量: S（拍板后） | 核验方式: 静态
- 现象（已有决策记录，与代码冲突）：
  - `CONTEXT.md:63-65`：「租户渠道组 / 虚拟令牌仍待产品拍板，不发给租户」；`README.md:40`：不要把网关写成可卖产品。
- 现象（代码里已经在卖或已露出）：
  - `Pricing.tsx:64` 企业档写「中转站渠道组分配」。
  - `frontend/admin/src/config/menuConfig.tsx:49` 租户菜单有「我的渠道组」（tenantOnly）。
  - `platform_core/schemas/billing.py:27` 可结账商品包含 `relay`；`config/default/billing.yml:4` 标价 ¥199。这个商品不在任何定价页上，只能直接打开 `/billing/checkout?product=relay`。
  - `backend/services/billing_fulfill.py:114-116,129-131` 在 relay 或企业档履约时开通 relay SKU。
  - `backend/services/billing_service.py:460-465`：`LITELLM.ADMIN.ENABLED` 打开时，每个新注册租户都会生成一把 LiteLLM 虚拟键（`litellm/admin_service.py:57-63`）。
  - dev 库里已有 `relay_token_call_succeeded` 事件（devdb-readonly.txt:50）。
- 根因：一个战略决定（向租户转售 LLM 调用、标价 ¥199）在没有运营方答复的情况下被写进了代码；产品层也没有记录。
- 后果：定价、成本和合规敞口都没有评估；和现有词汇表的决策相冲突，后续评审没有依据可判。
- 修复方案：
  1. 先回答 Q-RELAY。
  2. 拍板之前：从定价页删掉「中转站渠道组分配」；租户「我的渠道组」菜单改为按 SKU 或开关显示；用配置开关控制 `relay` 是否可结账（默认关）。
  3. `attach_free_plan` 里签发虚拟键这一步，在决定前明确写出是否保留。
- 应补的测试或验收：开关关闭时，`/billing/checkout?product=relay` 返回「没有这个商品」，租户菜单里没有 `/relay`。

### QA-4 官网主导航和首页把访客带到默认关闭的能力市场，形成死路；而且市场开关只存在进程内存里，不持久
- Dimension: 1 · 7（配置即代码）· 8 · 9 | Severity: **major** | 工作量: M | 核验方式: 截图 + 静态（持久性需要 manager 复现）
- 现象：
  - `frontend/official/src/components/layout/SiteLayout.tsx:23` 主导航第一项固定是「能力市场」。点进去只显示「能力市场未开放 / 返回首页」（截图 `official_skills-1440.png`）。
  - 首页能力区显示「还没有上架的能力。开通后可在能力市场浏览。去能力市场」（截图 `official_-1440.png`）。但后台目录里有 50 条状态是「已上架」（截图 `admin_capabilities-1440.png`）。所以文案把「市场未开放」错说成了「没有上架的能力」，而且链接又指向那条死路。
- 根因：
  - `config/default/power_market.yml:3` 默认 `ENABLED: false`。
  - `backend/services/power_market/flag.py:20-24` 的 `set_power_market_enabled` 只调用 `settings.set(...)`，也就是只改当前进程内存。
  - `backend/app/api/v1/admin.py:214-227` 的 PUT 接口除了写审计外不做任何持久化。重启后回到 false；多 worker 时各进程状态不一致。
  - 运行期打开开关还绕过了启动守卫：`backend/app/__init__.py:75-82` 规定市场打开时 `OPS.DUTY_CONTACT` 不能为空，但 PUT 路径不检查这一条。
- 后果：导航第一项就是死路。运营方在后台打开市场后，下次重启会悄悄关掉，而且没有提示。「市场开放必须有值班联系人」这条约束也会被绕过。
- 修复方案：
  - 开关持久化到 `system_configs`（这张表已存在）或 Redis 并广播，读取时以持久值为准。
  - PUT 时执行和启动时一样的 DUTY_CONTACT 校验。
  - 官网导航和首页能力区根据 `market_closed` 决定显示：关闭时隐藏入口，或显示「预告」页（写价值说明并引导注册）。
  - 空态文案区分「市场未开放」和「暂无上架能力」（`flag.py:10-11` 已有这两条文案）。
- 应补的测试或验收：
  - API 测试：PUT enabled=true 后新建 app 实例，GET 仍然是 true。
  - DUTY_CONTACT 为空时，PUT enabled=true 被拒绝。
  - 官网 E2E：市场关闭时导航不出现死路。

### QA-5 核心价值「粘贴链接即可出数」没有在运行中的构建上被证明；默认配置下 AI 规划不可用；首页流程宣称超出实现
- Dimension: 1 · 3 · 9 | Severity: **major** | 工作量: 文案 S；E2E 和 LLM 策略 M | 核验方式: 静态 + 截图 + dev 库记录（E2E 未执行）
- 首页宣称与实现对不上：
  - `frontend/official/src/components/home/AiFlowSection.tsx:31` 写「用一句话描述你想提取的字段，无需编写任何代码」。但创建接口只收两个字段：`platform_core/schemas/ai_plan.py:145-150` 的 `AiPlanCreate` 只有 `target_url` 和 `html_snippet`；截图 `admin_ai-1440.png` 也只有「链接」和「HTML 片段」两个输入框。
  - `AiFlowSection.tsx:39` 写「生成…反爬应对方案」，但方案结构（`ai_plan.py:128-134`）里只有 render_js 和 wait_for，没有任何反爬策略字段。
- 默认配置跑不通：
  - `config/default/llm.yml:12` `LLM.ENABLED: false`；规划被阻断时会发出 `llm_planning_blocked` 事件（`backend/services/ai_planner/orchestrator.py:139`）。
  - 不用 AI 的路径需要手写 CSS/XPath（`README.md:181`），这和「免代码」的说法矛盾。
  - 免费档写的「20 万 LLM tokens/月」（`quota.ts:9,18`）在默认配置下兑现不了。
- 构建上没有证据：
  - dev 库只有 1 个任务，是 2026-09-14 的 `example` 爬虫任务（devdb-readonly.txt:29,56；截图 `admin_spiders_tasks-1440.png`）。
  - 埋点代码已经存在：`spider_task_service.py:301,618`、`tenant_signup_service.py:130`、`spider_query_service.py:200`。
  - 但 292 条 product_events 里，`task_run_submitted`、`task_completed`、`tenant_signup_succeeded`、`results_exported` 这四种事件都是 0 条（devdb-readonly.txt:36-50）。
  - 仪表盘显示「近 7 日采集结果 0 条」（截图 `admin_dashboard-1440.png`）。
- 根因：没有定义核心旅程 J-1（注册 → 粘贴链接 → 规划 → 试采 → 上线 → 出数 → 导出）和它的验收标准；首页文案按愿景写，没有对应到接口字段；免费档是否提供平台 LLM 没有定下来。
- 后果：主张没有证据；新注册租户在默认配置下兑现不了首屏承诺。
- 修复方案：
  1. 删掉「一句话描述字段」，或者给 `AiPlanCreate` 加上可选的 `fields_hint` 并传进规划提示词。
  2. 「反爬应对方案」改成实际能力（动态渲染、等待选择器），或者真正实现。
  3. 回答 Q-LLM-FREE。
  4. 把 J-1 作为验收旅程，接上事件漏斗。
- 应补的测试或验收：
  - Playwright J-1 用租户负责人身份在固定测试站点上跑通，断言结果至少 1 条、能导出，且 product_events 里依次出现 signup → task_run_submitted → task_completed → results_exported。
  - 首页文案和 `AiPlanCreate` 字段做一致性测试。

### QA-6 平台超管访问结账页：本该拒绝的正常情况被当成 HTTP 400；超管仍能看到「去结账」却走进空白页；租户买家路径没有任何证据
- Dimension: 3 · 8 · 9 | Severity: **major** | 工作量: UI/API S；E2E M | 核验方式: 截图 + 已记录执行 + 静态
- 现象：
  - `ui-runtime-summary.md:49` 记录了 `400 GET /api/v1/billing/checkout?product=plan_pro`。
  - 截图 `admin_billing_checkout-1440.png` 整页只有一行「超管不能代企业支付」，没有返回或跳转按钮。
  - 截图 `admin_pricing-1440.png`、`admin_usage-1440.png` 仍然给超管显示「去结账」。
- 根因：
  - `backend/services/billing_service.py:134-138` 用 `BusinessException`（默认 400）表达「超管不能代付」这种预期状态。
  - `frontend/admin/src/pages/Checkout.tsx:210-213` 只渲染一个 info Alert，没有下一步动作。
  - 定价页和用量页没有按 `is_platform_admin` 隐藏或替换 CTA。
- 后果：运行监控把预期状态记成错误（本轮 manager 就是这样记录的）。超管在给客户做支持时看不到买家视角。唯一的收入路径（租户负责人 → 结账 → 超管确认 → 配额生效）在运行中的构建上没有截图，也没有执行记录。
- 修复方案：
  - 超管的 CTA 改为「查看订单 → /platform-ops」。
  - API 改成 403 加业务码，或 200 只读预览（`can_submit=false`）。
  - Checkout 的超管分支加上跳转平台运营台的按钮。
  - 另外请 manager 补做租户负责人路径的走查（见文末）。
- 应补的测试或验收：
  - Checkout 单测：超管分支显示平台运营台链接。
  - API 测试：状态码不是 400。
  - E2E：租户负责人 → 定价 → 结账 → 提交 → 订单 `checkout_pending` → 超管确认 → 用量页配额变为 `PRO_TIER_QUOTA`。

### QA-7 能力市场的货架内容与产品主线脱节：上架的是开发者自己的插件农场（网文写作、研发流程、仓库内部 skill）
- Dimension: 1 · 9（另涉及 4：第三方内容再分发） | Severity: **major** | 工作量: 下架 S；定上架标准 M | 核验方式: 截图 + 静态（许可状态未验证）
- 现象：截图 `admin_capabilities-1440.png` 显示共 50 条，全部是「已上架」（2026-09-14T09:45:04 批量上架），包括：
  - `check-arch`：本仓库内部的架构检查 skill；
  - `dev-team__*`：研发流程；
  - `oh-story__story-*`：网文写作；
  - `sdlc-workflow__*`。
  - dev 库里 `capability_assets` 有 207 行（devdb-readonly.txt:8）。
- 根因：货架来源就是开发中枢 `.agents`（`config/default/skills.yml:5-6`，R7 QA-3 已述写入面）；没有目标客户和上架标准（产品层缺失）。R7 讲的是写入面的安全，这条讲的是货架定位。
- 后果：一旦开放市场，数据采集客户看到的会是网文写作和本仓库研发流程技能，定位被稀释。第三方内容（例如 dev-team 合并了上游开源集合）的许可和再分发责任没有评估【未验证：`listing.py` 的第三方或许可闸门是否拦过这些条目】。内部 skill 会暴露仓库细节。
- 修复方案：
  1. 先回答 Q-MARKET。
  2. 定义上架标准：与采集主线相关、许可明确、第一方优先。
  3. 批量下架不相关的条目；货架来源与开发中枢分开（和 R7 T4 一起做）。
- 应补的测试或验收：PM 评审上架清单；闸门测试：许可不明的第三方资产不能上架。

### QA-8 产品层缺失：定位、北极星、功能地图、旅程都不存在；战略决定散落在代码注释和仓库外文件里，无法核实是谁定的
- Dimension: 1 · 2 · 9 | Severity: **major** | 工作量: M | 核验方式: 静态
- 现象：
  - `docs/product` 不存在（packet:14）。
  - 定位有三种说法：`README.md:3`「综合数据智能平台」（五六个模块并列）；官网 Hero「智能数据采集」（`Home.tsx:29,106`）；页脚「AI 驱动的智能数据采集系统」。
  - 接口面分布：采集相关（spiders 33 + ai 7）约 40 个操作；能力市场（capabilities 28 + skills 17 + public 11）、LLM 与中转（llm 15 + newapi 11 + relay 10 + litellm 4）、计费和组织管理占了其余大部分（总计 229 个操作，module-inventory.md:3）。
  - 指标注册表只有运维类指标，没有北极星或激活指标（module-inventory.md:296-327）。
  - 战略决定只出现在代码注释里：`quota.ts:24,34`「Q-PRICE：不撤 ¥299」、`Home.tsx:28`「FR-U04 首屏锁采集」、`App.tsx:12-15,73` 的 ADR-0021/0022；`CONTEXT.md:5` 的权威产品设计放在仓库外的个人路径。
- 根因：没有初始化产品层；决策以工单或注释形式留存，没有负责人和答复原文。
- 后果：无法做验收（没有 J-n，没有 Aha 定义）；范围蔓延没有约束（QA-3 和 QA-7 就是例子）；每次评审只能拿代码注释当标准。
- 修复方案：
  - 用 `/sdlc-product` 初始化产品层：`strategy.md`（ICP、JTBD、北极星，例如「每周产出至少 1 条有效结果的租户数」）；`feature-map.md`（每个功能域标为主线／支撑／孵化／退役，并对应到功能开关）；J-1..J-n。
  - 已有决策（Q-PRICE、FR-U04 等）连同出处导入 product-delta。
- 应补的测试或验收：功能地图里每个「对外可见入口」都对应一个开关和一个负责人；新功能如果没有功能地图条目，评审直接不通过。

### QA-9 对外宣称对账表形同虚设：所称的 CI 测试在仓库里不存在，而且官网和定价的宣称一条都没覆盖（升级并扩展 R7 QA-11）
- Dimension: 3 · 6 | Severity: **major**（R7 定为 minor，这里加了新证据后升级） | 工作量: S | 核验方式: 静态（Glob 实查）
- 现象：
  - `docs/claims.md:3` 说「CI `test_claims_anchors.py` 校验锚点文件存在」。我对整个工作树做了 Glob `**/test_claims_anchors*.py`，结果为空，这个测试不存在。
  - 表里 8 条全是后端行为（`claims.md:7-14`）。首页和定价页的宣称都没有收录，例如：
    - 「任务失败与节点异常秒级触达，支持 Webhook 多通道通知」（`FeaturesSection.tsx:62`）。但默认配置 `config/default/notify.yml:14-16` 只有 `CHANNELS: [log]`，`WEBHOOK_URL` 为空，所以默认不会有任何对外通知；「秒级」也没有度量。
    - 「节点扩缩容时调度自动均衡」（`:46`）、「一次定义多节点即时生效」（`:30`）。
    - QA-2 和 QA-5 里列出的各条宣称。
- 根因：宣称治理只停留在文档；锚点测试从来没有落地。
- 后果：一个空洞的「已校验」声明，比没有声明更糟。营销文案可以随意漂移。
- 修复方案：
  - 真正实现 `backend/tests/test_claims_anchors.py`，检查文件加符号（`def`／`class` 名）。
  - claims 表扩展到 Home、AiFlow、Features、Pricing、Register 的每条宣称，每条标为「实现锚点」「默认开关」或「人工服务」。
  - 前端加文案扫描：页面上的宣称文本必须出现在 claims 表里。
- 应补的测试或验收：删掉或改名任一锚点符号时 CI 变红；新增一条营销宣称但没进 claims 表时 CI 变红。

### QA-10 AI 采集规划页同时显示两套步骤条，标签还不一样
- Dimension: 9 | Severity: minor | 工作量: S | 核验方式: 截图 + 静态
- 现象：截图 `admin_ai-1440.png` 上下两条进度：上面是「输入目标 / 方案与试采 / 上线」，下面是「创建计划 / 方案预览与调整 / 试采与上线」。
- 根因：`frontend/admin/src/pages/AiPlans.tsx:88-93` 加了页面级 Steps（工单 89），而 `frontend/admin/src/components/ai/PlanDetail.tsx:64,363` 原本就有一套 Steps。
- 后果：核心旅程第一屏阶段含义不清，而这正是 Aha 路径的入口。
- 修复：只保留一套，文案统一；另一套删掉，或改成面包屑。
- 验收：AiPlans 单测断言页面上只有一个 `.ant-steps`。

### QA-11 超管用量页和仪表盘的口径让人困惑：成本记 0 元、KPI 时间窗口混用、超管也看到「去结账」
- Dimension: 6 · 9 | Severity: minor | 工作量: S | 核验方式: 截图（成本根因未验证）
- 现象：
  - 截图 `admin_usage-1440.png`：平台租户的配额是 5 / 100,000,000 / 100,000,000；LLM 使用 786 tokens，供应商「config」，金额 0.00 元；页面上有「去结账」。
  - 截图 `admin_dashboard-1440.png`：「任务总数 1」是全量口径，「成功率 -」按 7 天，「近 7 日结果 0」，质量分却基于任务 #3。同一行 KPI 用了不同时间窗口，但没有标注。
- 根因：「config」兜底供应商没有计价，导致注册表里的 `llm_cost_cents_month` 指标失真【未验证，需要查 `llm_token_usage.cost_cents`】；仪表盘卡片没有写明各自的窗口。
- 修复：兜底供应商也按单价计价，或者把金额显示为「未计价」而不是 0；KPI 卡片写明窗口；超管隐藏「去结账」（和 QA-6 一起改）。

### QA-12 README 的「账号与权限」仍是单体三角色模型，和实际的 SaaS 企业注册、租户角色、平台超管不一致
- Dimension: 6 | Severity: minor | 工作量: S | 核验方式: 静态 + 截图
- 现象：`README.md:233-243` 写的是 viewer/operator/admin，「自注册用户默认 operator」。实际情况是：
  - 官网注册是「企业注册」，填写管理员邮箱（截图 `official_register-1440.png`）；
  - 菜单按 tenantOnly/platformOnly 划分（`menuConfig.tsx:48-95`）；
  - 成员管理有 tenant_role，并且不允许授予平台超管（`backend/services/member_service.py:42-44,75`）。
- 后果：新人和评审会拿错误的权限模型去判断越权问题。R7 QA-6 讲的是其他过时条目，这条没有覆盖。
- 修复：按「平台超管 / 企业 owner / 企业管理员 / 成员」重写这一节，并链接到 CONTEXT 词汇表。

---

## Dimensions checked
1. 标准符合 ⚠️：宣称与实现不符（QA-1、2、5、9），未拍板就上线的功能（QA-3），货架偏离主线（QA-7）。
2. 标准质量 ➖（部分 ⚠️）：仓库里没有 PRD、GWT 或 J-n 可以评判；代码注释引用的 GWT 或 FR 编号（例如 GWT-U04.1、GWT-82.3）在仓库里找不到出处。这种缺失本身记为 QA-8。
3. 证据有效性 ⚠️：claims 测试不存在（QA-9）；核心路径 dev 库零事件（QA-5）；租户买家路径没有截图（QA-6）；首页全页截图里特性区、AI 流程区、架构区、底部 CTA 区都是空白，很可能是 `common.tsx:36-37` 的 `whileInView` 在整页截图时没有触发，不能当成缺陷，需要 manager 滚动后重截。
4. 安全 ⚠️（只看产品面）：运行期打开市场会绕过 DUTY_CONTACT 启动守卫（QA-4）；第三方内容再分发和许可没有评估（QA-7）；结账的角色闸门是对的（`billing_service.py:134-142`）。深度安全审查不在本切片。
5. 性能 ➖：不属于产品范围；manager 记录的页面加载在 1.9–2.6 秒之间，没有发现异常。
6. 契约一致性 ⚠️：定价在前端、种子、履约、首页四处各说各的（QA-1）；CONTEXT 与计费实现冲突（QA-1）；中转决策冲突（QA-3）；README 角色模型过时（QA-12）。
7. 合规（逐条对照宪法）⚠️：
   - 「配置即代码」：市场开关只在运行期内存里，没有版本化和持久化（QA-4）；定价权益硬编码在前端，没有由 plans 配置驱动（QA-1）。
   - 「日志即证据」：开关切换有审计（`admin.py:224`），符合。
   - 爬虫和分层相关红线不在本切片。
8. 边界 ⚠️：超管角色边界走到死路（QA-6）；市场关闭时导航是死路；多 worker 或重启后开关漂移（QA-4）。
9. 产品价值与体验 ⚠️：构建已经存在，所以按「构建证据」标准判断。Aha 没有在构建上被证明（QA-5）；首屏导航是死路（QA-4）；核心页面步骤条重复（QA-10）；付费路径没有证据（QA-6）。没有 E2E，没有 PM 走查。

## Strengths（改进时应保留）
1. 首屏文案诚实，并且锁定主线：`Home.tsx:28-29` 把首屏第一句锁定为采集（FR-U04），`:122`「没有真实聚合时不展示规模数字」；仪表盘的空态也不虚报（截图）。
2. 免费档和专业档的数字只有一个来源：`frontend/shared/src/constants/quota.ts:6-39` 同时供官网、后台和注册页使用，后端履约强制写入 `PRO_TIER_QUOTA`（`billing_fulfill.py:123-127`）。专业档在四处一致，企业档应照这个做法补齐。
3. 漏斗埋点已经覆盖关键节点：signup、task_run_submitted、task_completed、results_exported、checkout_story_started、payment_*、quota_exceeded、llm_planning_blocked（见上文 grep 结果），衡量 Aha 所需的基础已经在。
4. 买家和平台角色分离清楚：结账按角色拦截（`billing_service.py:134-142`）；平台写面和组织幽灵页对非超管返回和缺页一样的 404（`frontend/admin/src/App.tsx:16-19,81-93`）。
5. 已有「宣称对应代码锚点」的机制（`docs/claims.md`）和「上架与停用分开两道闸」的词汇（`CONTEXT.md:17-18`）。方向是对的，需要落实（QA-9）。

## Improvement themes（建议落地顺序：T1 → T2 → T4 → T3 → T5）
- **T1 初始化产品层并完成战略拍板（QA-8，前置 QA-1、3、7）｜M｜第 1 步**。目标：有 strategy.md（定位、ICP、北极星）、feature-map.md（每个功能域对应开关和负责人）、J-1..J-n，并且每个 Q-* 都有运营方答复原文。先做它，因为 T2–T5 的「对错」都要以它为准。
- **T2 定价和宣称只有一个真相源（QA-1、2、9、12）｜M｜第 2 步**。目标：`/billing/plans`（加配额）驱动两个定价页、结账页和首页 CTA；claims 表覆盖全部营销文案，并有符号级 CI 测试；企业档的文案和配额与决定一致。
- **T4 功能开关与可见入口一致（QA-3、4、6、11）｜S–M｜第 3 步**。目标：开关持久化并在多进程间一致；导航、CTA、菜单按开关和角色显示，不出现死路；预期拒绝不用 400。
- **T3 核心旅程 J-1 能在构建上演示（QA-5、10）｜M｜第 4 步**。目标：新租户在默认或文档化的配置下，从粘贴链接走到出数和导出；Playwright J-1 与事件漏斗都通过；首页流程文案和接口字段一致。
- **T5 能力市场定位与货架治理（QA-7）｜M｜第 5 步**。目标：货架服务于采集主线，许可明确，货架来源与开发中枢分离（和 R7 T4 合并做）。

## Decisions / Open questions（战略问题，都待确认，没有替任何人定）
- **Q-POS 产品主线是什么？** A：「采集出数」是唯一主线，市场、LLM、计费、组织管理都是支撑（**推荐**：和官网首屏锁定、指标注册表、Worker 心智模型一致）。B：四柱并行的综合平台（README:3 的口径）。C：以能力市场为主线。
- **Q-PRICE-ENT 企业档怎么卖？** A：定制，走联系销售，不提供自助结账（**推荐**：和现有「定制／协商」文案一致，也规避配额与宣称不符）。B：固定 ¥999 自助结账，文案改为实际配额（50 并发、200 万结果、2000 万 tokens）。C：暂时下架企业档。
- **Q-PAID-OPEN 专业档现在能不能买？** A：开放，提交后由平台超管人工确认收款，删掉首页「尚未开通购买」（**推荐**：下单、确认、履约链路已经实现，专业档口径一致）。B：暂不开放，定价页 CTA 改为「预告／联系我们」，首页文案保留。
- **Q-RELAY 中转站／LLM 网关是否卖给租户？** A：暂不卖，隐藏定价页条目、租户菜单和 `relay` 商品（**推荐**：和 CONTEXT.md:63-65「待拍板、不发给租户」一致，成本和合规没有评估）。B：作为企业档附加或独立 ¥199 SKU 出售，但要先补成本模型、合规评估和负责人。
- **Q-MARKET 能力市场面向谁、上什么？** A：面向采集客户的采集方案、模板和技能货架（**推荐**：服务主线，也能复用 AI 规划产出）。B：通用 AI 技能市场。C：暂缓，关闭官网入口，只保留内部治理。
- **Q-LLM-FREE 免费档新租户能否用平台 LLM 做 AI 规划？** A：可以，平台按定价兑现 20 万 tokens/月，需要打开 LLM 并加预算闸门（**推荐**：Hero 和定价都承诺了这一点）。B：只支持自带 Key（BYOK），定价页删掉免费档的 token 额度，Hero 改为「配置模型后可用 AI 规划」。
- 运营性默认：无（只读审查，没有替任何人应用默认值）。

## 需要 manager 代跑的验证（我没有执行，标注写操作的需要你确认后再做）
1. 核对套餐种子（dev 库的 information_schema 估算显示 plans=2 行，而迁移 047 应该有 3 行）：`mysql auto_agents -e "SELECT slug,name,price_cents,is_public,quota_json FROM plans;"`。如果缺 enterprise，企业档结账会报「商品尚未标价」，这会加重 QA-1。
2. QA-4 开关持久性（**写操作**）：用超管 token 执行 `curl -X PUT -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"enabled":true}' http://127.0.0.1:9111/api/v1/admin/power-market`，然后 `uv run python run.py restart backend`，再 `curl -H "Authorization: Bearer $T" http://127.0.0.1:9111/api/v1/admin/power-market`。预期复现结果是 `enabled:false`。做完请恢复原值。
3. QA-6 租户买家路径（**写操作**，建议用 internal-fixture 租户）：官网 `/register` 注册企业，以 owner 登录（勾选「记住我」），依次截图 `/pricing` → `/billing/checkout?product=plan_pro` → `/billing/checkout?product=plan_enterprise`（看金额是否 ¥999）→ `/billing/checkout?product=relay`（看是否可以购买）。
4. QA-5 核心旅程：用上面的租户打开 `/ai`，输入一个公开测试站点 URL，点「创建并开始规划」，截图结果（是否被 `llm_planning_blocked` 阻断）；然后查 `SELECT event_name,COUNT(*) FROM product_events WHERE created_at>NOW()-INTERVAL 1 HOUR GROUP BY 1;`。
5. 首页重截图：Playwright 逐段 `scrollIntoView` 后再截全页，确认特性区、AI 流程区、架构区、CTA 区是否只是 `whileInView` 没有触发（证据维度 3）。
6. QA-11 成本：`SELECT provider,SUM(total_tokens),SUM(cost_cents) FROM llm_token_usage WHERE created_at>='2026-09-01' GROUP BY provider;`
7. QA-7 许可：`grep -n "_is_third_party\|license" backend/services/power_market/listing.py`，并查 `capability_assets` 里 dev-team、oh-story 条目的 license 字段。

## Product-delta rows（建议在产品层初始化后写入，当前都待确认）
- strategy.md：定位 = Q-POS 的答复；北极星候选「每周产出至少 1 条有效结果的活跃租户数」（待确认）。
- feature-map.md：采集和 AI 规划 = 主线；计费和组织管理 = 支撑；能力市场 = Q-MARKET；中转和 LiteLLM = Q-RELAY；newapi = 退役（出处 README:269）。
- pricing：专业档 ¥299 / 50 / 200,000 / 500 万（出处 quota.ts:26-30、040/047 种子，已被 Q-PRICE 引用但答复原文不在仓库里）；企业档 = Q-PRICE-ENT。

## Lesson rows（只列已核实的陷阱）
- 用 Dynaconf 的 `settings.set` 实现后台「总开关」，只在当前进程内存生效，不持久，重启就丢。已核实：`backend/services/power_market/flag.py:20-24` 加 `backend/app/api/v1/admin.py:214-227`。
- 定价权益硬编码在前端，与种子数据漂移。已核实：`Pricing.tsx:55-67` 对照 `047_w2_channel_null_pro_quota.py:19,38`。
- 文档声称的 CI 测试并不存在，就是一个空洞的「已校验」声明。已核实：Glob `**/test_claims_anchors*.py` 结果为空，而 `docs/claims.md:3` 声称有这个测试。

```result
{
  "methods_used": [
    {"skill": "sdlc-workflow:findings", "reason": "primary_skill：9 维 G-fresh 审查格式", "provenance": "reported"}
  ],
  "reported_reads": [
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/module-inventory.md",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/ui-runtime-summary.md",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/devdb-readonly.txt",
    "/Users/xuyun/auto_agents/README.md",
    "/Users/xuyun/auto_agents/CONTEXT.md",
    "/Users/xuyun/auto_agents/docs/claims.md",
    "/Users/xuyun/auto_agents/frontend/official/src/App.tsx",
    "/Users/xuyun/auto_agents/frontend/admin/src/App.tsx",
    "/Users/xuyun/auto_agents/config/default/billing.yml",
    "/Users/xuyun/auto_agents/config/default/power_market.yml",
    "evidence/screens: official_-1440, official_-375, official_pricing-1440, official_register-1440, official_skills-1440, admin_dashboard-1440, admin_pricing-1440, admin_billing_checkout-1440, admin_usage-1440, admin_capabilities-1440, admin_spiders_tasks-1440, admin_ai-1440",
    "/Users/xuyun/auto_agents/docs/ops/2026-09-27-项目深度梳理-审查记录/R7-docs-agents-hub-findings.md"
  ],
  "unresolved": [
    {"id": "Q-POS", "owner": "operator", "blocks": "T1/QA-8", "item": "产品主线定位", "severity": "major"},
    {"id": "Q-PRICE-ENT", "owner": "operator", "blocks": "QA-1/QA-2", "item": "企业档定制还是 ¥999 自助", "severity": "major"},
    {"id": "Q-PAID-OPEN", "owner": "operator", "blocks": "QA-1", "item": "专业档是否开放购买", "severity": "major"},
    {"id": "Q-RELAY", "owner": "operator", "blocks": "QA-3", "item": "中转/LLM 网关是否向租户售卖", "severity": "major"},
    {"id": "Q-MARKET", "owner": "operator", "blocks": "QA-7/QA-4", "item": "能力市场目标客户与货架标准", "severity": "major"},
    {"id": "Q-LLM-FREE", "owner": "operator", "blocks": "QA-5", "item": "免费档是否提供平台 LLM", "severity": "major"},
    {"id": "V-1", "owner": "manager", "blocks": "QA-1", "item": "plans 表实际行（enterprise 是否存在）", "severity": "major"},
    {"id": "V-2", "owner": "manager", "blocks": "QA-4", "item": "power-market 开关重启后是否丢失（写操作）", "severity": "major"},
    {"id": "V-3", "owner": "manager", "blocks": "QA-6", "item": "租户 owner 结账路径截图（写操作）", "severity": "major"},
    {"id": "V-4", "owner": "manager", "blocks": "QA-5", "item": "新租户 AI 规划是否被 llm_planning_blocked 阻断", "severity": "major"},
    {"id": "V-5", "owner": "manager", "blocks": "维度3", "item": "首页滚动后重截图（whileInView 空白）", "severity": "minor"}
  ],
  "proposed_changes": [
    {"target": "frontend/official/src/pages/Pricing.tsx + frontend/admin/src/pages/Pricing.tsx", "change": "改由 GET /api/v1/billing/plans 渲染价格与配额；企业档 CTA 按 Q-PRICE-ENT 答复处理", "evidence_refs": ["Pricing.tsx:55-67", "047_w2_channel_null_pro_quota.py:19,38", "billing_fulfill.py:98-106"]},
    {"target": "frontend/official/src/pages/Home.tsx:208", "change": "删除「专业档与企业档尚未开通购买」或按开关显示", "evidence_refs": ["Home.tsx:208", "screens/official_pricing-1440.png"]},
    {"target": "backend/services/power_market/flag.py + backend/app/api/v1/admin.py:214-227", "change": "开关持久化到 system_configs 或 Redis；PUT 时执行 DUTY_CONTACT 校验", "evidence_refs": ["flag.py:20-24", "app/__init__.py:75-82"]},
    {"target": "frontend/official/src/components/layout/SiteLayout.tsx:23 + home SkillsSection", "change": "市场关闭时隐藏入口或显示预告页；区分「未开放」与「无上架」", "evidence_refs": ["screens/official_skills-1440.png", "screens/admin_capabilities-1440.png"]},
    {"target": "backend/services/billing_service.py:134-138 + frontend/admin/src/pages/Checkout.tsx:210-213", "change": "超管拒绝改为 403 或 200 只读预览，并给出跳转平台运营台的链接；超管隐藏「去结账」", "evidence_refs": ["ui-runtime-summary.md:49", "screens/admin_billing_checkout-1440.png"]},
    {"target": "frontend/official/src/components/home/AiFlowSection.tsx:31,39", "change": "文案与 AiPlanCreate 字段对齐，或给 AiPlanCreate 增加 fields_hint", "evidence_refs": ["platform_core/schemas/ai_plan.py:145-150", "screens/admin_ai-1440.png"]},
    {"target": "backend/tests/test_claims_anchors.py（新建）+ docs/claims.md", "change": "实现文件加符号级锚点测试；claims 表覆盖全部官网和定价宣称", "evidence_refs": ["docs/claims.md:3", "Glob **/test_claims_anchors*.py 结果为空"]},
    {"target": "frontend/admin/src/pages/AiPlans.tsx:88-93", "change": "删除重复的步骤条，只保留 PlanDetail 那一套", "evidence_refs": ["PlanDetail.tsx:64,363", "screens/admin_ai-1440.png"]},
    {"target": "Pricing.tsx:64 + menuConfig.tsx:49 + CHECKOUT_PRODUCTS", "change": "Q-RELAY 拍板前隐藏中转相关的对外露出", "evidence_refs": ["CONTEXT.md:63-65", "billing.yml:4", "billing_fulfill.py:114-131"]},
    {"target": "docs/product/*", "change": "用 /sdlc-product 初始化 strategy、feature-map、journeys", "evidence_refs": ["packet:14 product_context N/A", "CONTEXT.md:5"]}
  ],
  "product_delta": [
    "strategy.md：定位 = Q-POS 答复；北极星候选「每周产出至少 1 条有效结果的活跃租户数」（待确认）",
    "feature-map.md：采集和 AI 规划 = 主线；计费和组织管理 = 支撑；能力市场 = Q-MARKET；中转和 LiteLLM = Q-RELAY；newapi = 退役（README:269）",
    "pricing：专业档 ¥299/50/200,000/500 万（quota.ts:26-30）；企业档 = Q-PRICE-ENT（待确认）"
  ],
  "lessons": [
    "Dynaconf settings.set 实现的后台总开关只在当前进程内存生效，重启即丢（flag.py:20-24、admin.py:214-227 已核实）",
    "定价权益硬编码在前端，与种子数据漂移（Pricing.tsx:55-67 对照 047:19,38 已核实）",
    "文档声称的 CI 测试不存在，是空洞的「已校验」声明（Glob **/test_claims_anchors*.py 结果为空 对照 claims.md:3 已核实）"
  ],
  "check_records": []
}
```
