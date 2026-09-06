# PM 产品差距评估：四板块可售卖度 · Onboarding · NFR 红线

> 2026-09-06 · SDLC 产品经理（只读评估）。证据口径：`文件:行号` 或端点清单（HEAD=3ce0548）。
> 方法论：`skills/pm/SKILL.md`（问题定义四句话 / RICE / NFR 十类 / GWT 验收）。
> 与 2026-09-05 架构师版 `product-review.md` 的差异：**从"工程成熟度"视角改为"第一个付费客户"视角**，并修正一处过时结论（见 §1.3）。

---

## 1. 总体判断

### 1.1 一句话

**四个板块都能"演示"，没有一个能"收钱"；今天定价页上的 ¥299/月 是全仓唯一一张没有后端承接的 UI。** 骨架质量高（租户隔离、配额闸门、审计、AI 评分闭环都在），但商业闭环四点——套餐、订单、账单金额、自助续费——为零。

### 1.2 证据基线（2026-09-06 HEAD=3ce0548）

| 维度 | 数字 / 事实 | 出处 |
|---|---|---|
| API 端点 | v1 共 **143** 个（skills 17、rbac 16、llm_providers 15、admin 15、spiders 域 33、capabilities 10、newapi 6、tenant_usage 2、tenant_signup 1） | `backend/app/api/v1/` 逐文件 grep |
| ORM 模型 | **34 个，计费相关 0 张**（grep order/subscription/payment/invoice/plan 零命中业务表） | `platform_core/models/` |
| admin 页面 | **26 页**（含 NewApiOps、Usage、SkillsMatrix 等） | `frontend/admin/src/pages/` |
| official 页面 | 8 页，**Pricing.tsx 已有三档价目（免费 ¥0 / 专业 ¥299/月 / 企业定制），三个 CTA 全部 navigate('/register')** | `frontend/official/src/pages/Pricing.tsx:15-27` |
| 注册闭环 | `POST /tenant/signup` 存在：公司名+邮箱+密码 → 自动建租户+owner，`quota=None`（免费档默认配额） | `backend/services/tenant_signup_service.py:55-58` |
| 计量表 | 租户三指标（task_concurrency / result_storage / llm_tokens_month）已有配额闸门（429 QUOTA_EXCEEDED）+ 用量看板 | `quota_service.py:80,100`、`tenant_usage.py:20-30` |
| LLM 用量表 | `llm_token_usage` 有 tenant 维度（uq: tenant_id+provider_name+model+stat_date），**只有 token 数，无金额列**；`llm_providers` **无单价字段** | `platform_core/models/llm_token_usage.py:22-36`、`llm_provider.py`（grep cost/price 零命中） |
| LiteLLM | L1 影子接入**已完成**：exporter/shadow/version-guard + compose profile 隔离，镜像 v1.99.1 pin + 恶意版本黑名单红测；L2/L3 state.yaml 工件已建 | `deploy/litellm/README.md`、提交 bf8db62/3ce0548 |
| 爬虫数据出口 | `GET /results/{task_id}/export`（csv/json 流式）+ 分页查询 API | `backend/app/api/v1/spiders/results.py:81-89` |
| 爬虫质量可见性 | Dashboard 有 success_rate / avg_duration（任务级） | `frontend/admin/src/pages/Dashboard.tsx:97-99` |
| 归档/retention | `ArchiveRecord.retention_until` 字段**已建但全仓无任何 service 引用**（schema 有、执行器无） | `platform_core/models/archive.py:22`；`backend/services/` grep archive 零命中 |
| 备份 | deploy/ 仅 litellm+newapi 两目录；无 mysqldump/xtrabackup 脚本、compose 无备份服务、无恢复演练记录 | `deploy/`、`scripts/` grep 零命中 |

### 1.3 对上次架构师评估的两点修正

1. **"爬虫核心入口无 HTTP 测试（T10 未开工）"已过时**：T10 已交付（`backend/tests/test_t10_api_coverage.py` 18 用例，含 `POST /spiders/run` 的参数校验/权限/未登记拒绝），B1a/B1b/B1c 零覆盖清剿三票也已提交。付费入口裸奔问题**已解决**，Top-8 中不再占位。
2. **LiteLLM L1 从"路线"变成"已交付"**：影子接入 + 供应链守卫已合入，中转站切换窗口判断继续成立，且 L3（虚拟键）现在是中转站可售卖的**唯一剩余前置**。

---

## 2. 四板块可售卖度（第一个付费客户视角倒推）

### 2.1 SaaS：有租户形态、无收钱闭环（可售卖度 2/5）

客户旅程现状：看到定价页 ¥299/月 → 点"联系升级" → **落到免费注册页** → 注册成免费租户 → 再无任何一步能把 ¥299 交出来。到期巡检只做"过期→拒绝登录"（`tenant_expiry_service.py`），意味着今天唯一的"生命周期管理"是**到期即死**——对付费客户没有宽限期、没有自助续费、没有升降级。

**计费模式论证**：与仓内现状（departments 组织树、llm_providers 成本、爬虫任务量、已有三指标 quota JSON）最匹配的是**订阅制（按档位包配额）+ 超额按量升档**：
- 三指标配额结构（并发/存储/token）就是天然的"套餐参数表"，订阅制只需把 `quota` 从手填 JSON 变成套餐定义的实例化；
- 席位制不匹配——成员功能薄（Members 6 端点），按席位收钱撑不起价目；
- 纯按量制需要计量对账+账期闭环（token 记账其实已具备基础），但对 MVP 是过度设计，可作为"专业档超量部分"渐进引入。

**最小计费闭环**：3 张表 + 5 个端点。
- 表：`plans`（档位+配额定义）、`tenant_subscriptions`（租户↔套餐+有效期）、`orders`（金额/状态/支付渠道/回调幂等键）；
- 端点：`GET /plans`（公开价目）、`POST /subscriptions`（订购，生成待支付订单）、`POST /payments/webhook`（支付回调，幂等）、`GET /subscription`（当前订阅，前端 Usage 页挂载）、`GET /orders`（账单历史）。

### 2.2 智能爬虫：交付物存在但只有"手动快照"（可售卖度 3/5）

- **数据怎么到手**：任务跑完 → 结果页分页浏览 → `GET /results/{task_id}/export?format=csv|json` 流式下载。**能交付**，但每次都是人工拉取的快照——客户买的是"持续的数据"，拿到的是"每次来找你要"。
- **质量监控客户可见吗**：部分可见。Dashboard 有 success_rate / avg_duration（任务级），但无结果量趋势、无字段级缺失率——客户无法向自己的老板证明"这份钱花得值"。
- **质量水位**：T10 已补 HTTP 层测试（18 用例），核心入口不再裸奔（修正 §1.3）。

### 2.3 中转站：管控面完整、客户面为零，L3 是生死线（可售卖度 1/5）

- LiteLLM L1 影子已交付，`/newapi/*` 6 个端点全部 `require_admin`（`newapi.py:46`）——**没有任何一个端点是客户自己的**。
- 客户可见的用量面板缺什么：Usage 页只有 token 数（`Usage.tsx:65-74`），**没有金额**；`llm_token_usage` 无 cost 列、`llm_providers` 无单价字段——token→钱的双料缺口，而"钱"恰恰是中转站客户的唯一关心的问题。
- **虚拟 Key 三级分发（租户/部门/个人）最晚何时必须到位**：商业上 = **L3**（工程路线既定）；时间上 = **第一个付费客户签约之前**。L3 不交付，中转站就是"自己用来管内部 LLM 成本的后台"，不构成独立卖点。倒推：L3 依赖 L2（渠道配置面切换），所以若中转站要进首批售卖清单，L2→L3 必须在销售管道成型前排期，且 L3 的验收必须包含"新租户注册即得 key"（见 §5 第 4 条 GWT）。

### 2.4 资源库：治理闭环厚、市场面为零（可售卖度 2/5）

- 采集→人工审批→评分（AI 四维 rubric+人工留痕）→公开广场（official SkillsSquare 只读，**无 upload/publish 入口**，grep 零命中）——**UGC 面不存在**。
- 没有 UGC 的护城河是什么：短期护城河**不是内容量**（采集源人人都可采），而是**治理管线本身**——AI 评分闭环（skill_scoring）、真伪指纹探针（10 维行为判套壳）、人工审批闸门。这是"带质量保证的技能市场"对"技能压缩包下载站"的差异。但长期无作者生态则内容封顶于采集源：UGC 上传+复用同一套审批闸门（而非另建审核流）是低成本长线投资（§5 第 8 条）。
- capabilities 四类资产（技能/插件/专家/团队定义）有治理无分发：无版本订阅、无按租户私有目录。

---

## 3. Onboarding 缺口：最快 6 步，第 3 步硬依赖外部 Key

新客户从注册到第一次拿到价值（爬虫跑完）的现状路径：

1. 官网 Pricing/首页 → `POST /tenant/signup` 注册（自动建租户，1 步，顺畅）
2. 登录 admin
3. **配置 LLM 供应商：客户必须自己有 API Key（BYOK）** ——无 Key 客户在此卡死
4. 创建采集任务（有 task_templates 5 端点，算半个缓解）
5. 等待执行
6. 看结果/导出

**已存在的好东西**：Dashboard 零任务时三步引导（LLM 配置→采集任务→AI 采集规划，`Dashboard.tsx:103-126`，工单 90）——文案和跳转都有。
**缺口**：
- 无**一键演示任务**：example/openweather spider 存在但未包装成"零 Key 可跑的示例"；LLM Key 是第 3 步的硬闸门，而演示任务（预置爬虫+示例数据展示）完全可以绕开它，让客户在第 2 步之后 1 分钟内看到"爬虫能给我什么"；
- 引导无进度持久化/checklist（纯条件渲染 Alert，完成即消失，无跨会话状态）；
- 注册成功页无"下一步去哪"的衔接（tenant_signup 返回 snapshot 后前端落点未见引导）。

---

## 4. NFR 红线快过（十类，逐类给结论）

| 类别 | 结论 | 证据 / 差距 |
|---|---|---|
| 性能 | ✅ 基础达标 | 索引治理迁移 026 已做（删 27 冗余）；无对外延迟目标 |
| 容量 | ⚠️ | archive_records 冷热分离 schema 已建但**无执行器**；无容量预警 |
| 可用性 | ⚠️ | 看门狗 kill 闭环已实测（B4）；无 uptime 度量与目标 |
| 安全 | ✅ | Fernet secret vault、SSRF 守卫、public 端点限流 |
| 权限 | ✅ | R13 隔离套件 + T10 鉴权边界用例 |
| **合规** | 🔴 **红线** | 审计有（audit_service+operation_log），**retention 只有字段没有执行器**——爬虫数据可能含个人信息，"无限期保留"在合规上不可辩护（PIPL 存储 期限最小化） |
| 兼容性 | N/A（本迭代无客户端兼容矩阵需求） | — |
| 可观测性 | ✅ | log_center、llm_token_usage、alert_rules 10 字段契约（B4） |
| i18n | ⚠️ | `i18n` 模型存在；official 定价/注册页未见多语言；暂不阻塞首单 |
| 可维护性 | ✅ | 迁移链 017→027 规整、uv.lock 可复现、CI 三阶段 |

**备份恢复（附加红线，不在十类内但不可跳过）**：🔴 零证据——无备份脚本、compose 无备份服务、无恢复演练记录。付费客户数据（爬虫结果+租户配置）无任何已验证的恢复手段，**任何一次磁盘故障都是不可逆客户流失**。

**SLA 能力**：无对外 SLA 文档、无 uptime 度量。企业档签约前置项。GWT 级目标示例：*Given 连续 30 天，When 每分钟探测 `GET /api/v1/health`，Then 月度 uptime ≥ 99.5% 且失败分钟清单可导出。*

---

## 5. 产品差距 Top-8（RICE 排序）

> R=首批目标付费租户 10–50 + 免费转化漏斗；Impact 按方法论 3/2/1/0.5；Confidence 无数据场景按 50% 起步（方法论红线：无数据不写 100%）；Effort 为人周粗估（实施前须 /architect 校准）。

| # | 差距 | 问题定义四句话 | 目标用户 | RICE 粗分 | GWT 级验收标准（一条） | 泳道 |
|---|---|---|---|---|---|---|
| 1 | **订阅计费最小闭环** | ① 决定采购的团队负责人 ② 在定价页看到 ¥299/月后没有任何入口能付款，只能联系销售走线下 ③ TA 能自助选档支付并在注册后 10 分钟内拿到对应配额的租户 ④ 定价页→付费→配额生效全链路转化率可统计，首批付费租户 >0 | 采购决策人（中小企业技术负责人） | R=50 · I=3 · C=80% · E≈3 周 → **最高分** | Given 专业档套餐定价 ¥299/月 且我完成支付回调，When 我查询当前订阅，Then 返回 status=active、有效期至支付日起 30 天，且我的 task_concurrency/result_storage/llm_tokens_month 与套餐定义完全一致 | L2 |
| 2 | **零 Key 一键演示（Onboarding 闸门拆除）** | ① 刚注册、还没有任何 LLM Key 的评估者 ② 三步引导第一步就要求 TA 去申请 API Key，TA 在看到任何价值前就流失 ③ TA 不配置任何 Key 就能跑通一个预置演示并看到结果数据 ④ 注册→首次查看结果的漏斗完成率显著提升（当前该步即最大流失点） | 评估期新租户（注册 48h 内） | R=50 · I=2 · C=80% · E≈1 周 | Given 我以新租户身份登录且尚未配置任何 LLM 供应商，When 我点击 Dashboard"一键体验演示"，Then 系统用平台预置的示例任务模板入队一个不依赖 LLM 规划的爬虫任务，且 5 分钟内我能在结果页看到 ≥1 条数据并可导出 CSV | L1 |
| 3 | **LLM 成本可见化（token→金额）** | ① 为 LLM 支付费用的租户管理者 ② Usage 页只有 token 数，TA 无法回答"这个月花了多少钱、哪个供应商烧的钱" ③ TA 能在用量页直接看到本月金额与按供应商的成本分摊 ④ Usage 页月访问量上升且"成本相关问题"客诉/工单趋零 | 租户管理者（管预算的人） | R=50 · I=2 · C=80% · E≈1.5 周 | Given llm_providers 已配置模型单价（每千 token），When 我查看 /usage，Then 响应含 cost_by_provider（按 stat_date 当月累计的金额，精确到分）且金额=Σ(tokens/1000×单价)，与 llm_token_usage 同源对得上 | L1 |
| 4 | **LiteLLM L3：虚拟 Key 三级分发 + 预算**（中转站可售卖前置） | ① 想接入中转站的客户开发者 ② 没有任何客户自有的 API Key 发放/预算/用量页面（/newapi 全部 require_admin）③ TA 能自助创建租户级 Key、看到自己的 spend 与预算余量、触顶被限且收到通知 ④ 中转站从"内部成本后台"变为可开票售卖的独立板块，首个中转站付费客户 >0 | 客户侧开发者（集成方） | R=20 · I=3 · C=80% · E≈5 周 → 次高分 | Given 我的租户已开通中转站，When 我在租户面板创建虚拟 Key 并设置月预算 ¥100，Then 我获得仅限本租户前缀的 key，经该 key 的调用计入本租户 spend，spend 达 ¥100 后新请求返回 429 且我的租户通知列表出现预算触顶告警 | L4 |
| 5 | **爬虫数据留存执行器**（合规红线） | ① 对数据合规负责的租户管理员与平台运营 ② 爬虫结果可能含个人信息但当前无限期保留，retention_until 只有字段没有执行器，无法满足"存储期限最小化" ③ TA 能按租户设定留存期，过期数据自动清理/归档且留审计痕 ④ 首个合规审查/客户安全问卷可通过 | 租户管理员 / 平台合规 | R=10 · I=1 · C=100%（schema 已在、执行器缺失是既证事实） · E≈1 周 | Given 我的租户留存策略设为 90 天，When 每日清理任务运行，Then created_at 早于 90 天的 spider_results 行被删除或进入 archive_records（快照完整、retention_until 已填），且 operation_log 各留一条含行数的清理记录 | L1 |
| 6 | **备份恢复基线**（运营红线） | ① 承诺"数据不丢"的平台负责人 ② 无备份脚本、无恢复演练、compose 无备份服务，一次磁盘故障即不可逆丢全部客户数据 ③ 平台能每日自动备份且经演练验证可恢复 ④ RTO/RPO 有实测数字可写进企业档合同 | 平台负责人 / 企业档客户 | R=10 · I=1 · C=100%（缺失是既证事实） · E≈1 周 | Given 每日备份任务已配置，When 我在演练环境执行"全库恢复"runbook，Then MySQL+Redis+对象存储在 2 小时内恢复至最近一次备份点，恢复后租户登录与爬虫结果查询验证通过（演练记录留档） | L1 |
| 7 | **爬虫数据持续交付（webhook 推送）** | ① 把爬虫数据接入自己系统的客户开发者 ② 每次都要登录后台手动导出 CSV，数据到手永远是滞后的快照 ③ TA 能配置一个 webhook，任务完成后自动收到带签名的新数据推送 ④ 爬虫板块从"导出工具"升级为"数据管道"，续费理由从"能用"变"离不开" | 已付费租户的开发者 | R=20 · I=2 · C=50%（无客户访谈证据，需求来源为任务书倒推，需 /ops 补证据链） · E≈2 周 | Given 我配置了 webhook URL 与签名密钥，When 一个爬虫任务状态变为 finished，Then 系统在 60 秒内 POST 包含新结果条数与数据地址（或分页游标）的签名通知，且我方响应非 2xx 时按指数退避重试 ≥3 次、最终失败进入死信可见 | L2 |
| 8 | **技能 UGC 上传（复用人工审批闸门）** | ① 想贡献/沉淀自有技能的团队开发者 ② 技能广场只读，内容增长封顶于采集源，平台无网络效应 ③ TA 能上传自有技能包并经既有审批/评分管线进入广场或私有目录 ④ 月度新增技能中 UGC 占比 >0，形成作者生态起点 | 进阶用户 / 潜在作者 | R=10 · I=1 · C=50% · E≈3 周 | Given 我在技能广场点击"上传技能"并提交合法 manifest 的技能包，When 平台审核者完成审批，Then 该技能进入我租户的私有目录且状态为 pending_review→approved 的每次流转在 skill_jobs 留痕；被拒时我能看到拒因 | L2 |

> 第 7 条 Confidence 仅 50% 且无工单/访谈来源，按方法论红线**发出补证要求**：请 /ops 就"已成交或已谈客户中，数据交付方式是手动导出还是系统对接"取证后再进 PRD；若证据显示首批客户全部接受手动导出，第 7 条降级到下一轮。

---

## 6. 如果只能做一件事

**做第 1 条：订阅计费最小闭环（3 张表 + 5 个端点）。**

理由不是它分数最高，而是它是唯一一个"不做则其余七条全部贬值"的差距：Onboarding 做得再顺，转化终点是无处付款的定价页；成本面板再透明，账单仍是手工 Excel；虚拟 Key 发得出去，收不了钱的中转站只是成本中心。反过来，计费闭环会**强制打通**"套餐→配额→用量→账单"四个既有骨架（三指标 quota、tenant_usage、llm_token_usage 全部现成），把 34 个模型串成一个产品——第 2 条（一键演示）可以顺手作为它的验收链路（免费档→付费档升级路径的最短验证）；第 3 条（成本可见化）是它的账单预览地基，应在同一泳道紧随其后。先让产品能收钱，再让收钱变得体面。

### 给下游的交接

- **/architect**：第 1 条的表结构与支付渠道选型、第 4 条的 LiteLLM Postgres sidecar 与对账 ADR（对账差异处理策略）、第 6 条的备份 runbook——均需架构侧裁剪，本文不做技术决策。
- **/ops**：第 7 条补证据链；四板块客户访谈（验证订阅 vs 按量偏好、数据交付方式）。
- **/designer**：注册成功页衔接、Usage 页成本卡、webhook 配置页 IA。
- **/qa**：Top-8 各 GWT 为测试用例唯一来源；第 5/6 条为红线项，appetite 缩减时不减测试。

### Open questions（需人工确认）

1. 支付渠道与主体（微信/支付宝/对公+发票？涉及主体资质，PM 无法替业务决定）；
2. 首批目标客户里"按量计费 vs 订阅"的实际偏好（无访谈数据，本文按仓内结构论证了订阅优先）；
3. 中转站是否进首批售卖清单（决定 L2→L3 的排期紧迫度与 §5 第 4 条泳道是否上调）；
4. 免费档是否有使用期限（当前 `quota=None` 无限期免费，直接挤压付费档价值主张）。
