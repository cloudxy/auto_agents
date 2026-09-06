# 运营/增长独立深审报告（plan2-2026-09-06）

- 审查角色：运营/增长负责人（独立视角，仅依据仓库事实 + 公开竞品 URL）
- 审查范围：frontend/official + frontend/admin（用户可见面）、backend/app + services（能力面）、config/、根文档；未读 .sdlc/.scratch/docs/plan/docs/research
- 产品现状：四板块（智能爬虫 SaaS 多租户 / LLM 配置 BYOK / new-api 中转站管控 / 技能资产库），无外部用户，准备公开

---

## 一、总体判断

工程底座（多租户隔离中间件、限流、审计、配额模型、测试覆盖）明显高于"无外部用户"阶段的平均水准，但**商业化外壳与内核严重脱节**：官网在讲一个注册即用的 SaaS 故事（定价页、免费配额、企业注册），而后台的真实能力面里，对外 API 是"平台全局静态 Key + 不做租户过滤"，宣传的 LLM 配额从未被执行，会话 30 分钟硬过期且"记住我 7 天"是假的，租户管理员可以改平台级渠道与系统配置。这三类问题单独看是 bug，合起来是"第一批用户明天来就会踩"的信任炸点与口碑雷。增长侧则是三块地基全缺：无埋点（转化不可测）、无 SEO（内容引擎失效）、无 UGC/协作/自传播机制（技能广场只进不出）。当前**不具备公开获客的条件**，但距离合格只差一轮"商业化收口"：把承诺的配额、会话、隔离真正执行，把注册→首次任务成功→API 集成这条唯一重要的路径打通。竞品借鉴上：Apify 的资产落地页 SEO、LiteLLM 的按 Key 预算强制、Firecrawl 的 1 分钟 API 上手都值得抄；回避 Apify 的积分黑盒定价与 new-api 的渠道运维概念外泄。

---

## 二、深层次问题清单（按严重度排序）

### 1. 对外数据 API：全局静态 Key + 不做租户过滤，等于跨租户数据可互读
**严重度：高**

**证据**
- `backend/app/external_api/v1/public.py:26-34`：`X-API-Key` 唯一鉴权入口，Key 来自配置
- `config/default/external_api.yml:8-11`：`EXTERNAL_API.API_KEYS` 为平台全局静态列表（.env 注入）
- `backend/app/middleware/tenant_context.py:11-13`：租户作用域仅由 Bearer JWT 注入；X-API-Key 通道无租户上下文
- `backend/services/spider_query_service.py:91-114`（query_public_results）→ `backend/repositories/spider_result_repository.py:131-162`（query_by_spider）：查询条件仅 spider_name/时间/关键词，**无 tenant_id 过滤**

**为什么深层**：`/external/v1/data/{spider_name}` 是唯一的工作流嵌入通道（留存引擎），现状是"一把平台万能钥匙读全平台所有租户的采集数据"。多租户 SaaS 的立身之本（数据隔离承诺）在外部 API 面完全不成立；同时租户无法自助签发/吊销自己的 Key，集成闭环不存在。这既是安全事故倒计时，也是留存的死结。

**解决方案（可执行）**
1. 新建 `tenant_api_keys` 表（`key_prefix + secret_hash + tenant_id + scopes + revoked_at`），后台「系统设置 → API 密钥」页支持租户自助签发/吊销/查看最后使用时间（后台已有 Settings 页与 audit 基建可复用）。
2. `validate_api_key` 改为两段：先查 `tenant_api_keys`（命中→按 key 的 tenant_id 设置 `tenant_scope`，中间件已支持）；未命中再回落平台配置 Key（仅映射平台自用，文档标注 deprecated）。
3. `query_by_spider` 强制追加 `tenant_id == current_tenant_id()` 断言；为 `spider_result_repository` 增加跨租户查询的白名单参数（仅 platform_scope 可用）。
4. Webhook HMAC 签名密钥同步改为按租户生成（`spider_tasks` 已有租户归属）。

### 2. 「免费档 20 万 tokens/月」从未被执行：`check_llm_tokens_month` 零生产调用方
**严重度：高**

**证据**
- `backend/services/quota_service.py:119-135`：定义了月度 LLM token 检查
- 全仓 grep：`check_llm_tokens_month` 仅出现在 `backend/tests/test_saas_quota.py:82`、`backend/tests/test_saas_byok.py:88`，**生产代码无任何调用**（对比：`check_task_concurrency` 在 `spider_task_service.py:173`、`check_result_storage` 在 `tasks/consumer.py:694` 均已接线）
- 实际生效的是平台级全局预算：`backend/services/ai_planner/llm_client.py:286-289` 按 `LLM.MAX_TOKENS_BUDGET`（默认 200,000，`config/default/llm.yml:19`）按 provider 维度熔断
- 对外承诺：`frontend/official/src/pages/Register.tsx:46`（"20 万 tokens/月"）、`Pricing.tsx:13-14`

**为什么深层**：定价页与注册页白纸黑字承诺的配额是装饰品。一个免费租户可以烧光全平台当月 200k token 预算，随后**所有租户**的 LLM 调用统一报"预算已耗尽"——单个租户的噪声邻居演变成全平台功能停摆，且错误文案不解释原因。这正是"配额限制不透明 + 静默降级"的教科书口碑炸点：用户付了钱（专业档 500 万/月）却发现配额根本不按承诺执行。

**解决方案（可执行）**
1. 在 `llm_client` 预算检查点（`llm_client.py:290` 附近，已取到 `current_tenant_id()`）追加：租户态请求先调 `QuotaService.check_llm_tokens_month(tenant_id, year_month)`，或把计量维度改为 `tenant:{id}` 使全局预算按租户分桶。
2. 平台公共供应商兜底调用单独记 `platform_shared` 维度并设独立平台总预算（与租户配额分离），平台预算触发时免费档文案改为"平台公共额度暂满，请配置自有 Key"（可行动）。
3. 租户用量看板（`tenant_usage.py` 已有三指标）增加 80%/100% 阈值事件，走已有 notify 渠道（`notify_service.py` 支持 email/webhook/dingtalk）。

### 3. 权限口径混淆：任意租户的 admin 可写平台级渠道配置与系统配置
**严重度：高**

**证据**
- `backend/app/api/deps.py:116`：`require_admin = require_role("admin")` —— 命中任意租户的 admin 角色即放行，非平台超管
- `backend/app/api/v1/newapi.py:99-124`：`PUT/DELETE /newapi/channels/{id}/config` 仅 `require_admin`，写入平台全局 Redis `newapi:channel:cfg:{id}`（`limit_quota=0` 可直接下线渠道，影响全部租户）
- `backend/app/api/v1/configs.py:18-21`（GET `/configs/` 仅 `require_login`，viewer 可读全平台配置）；`:37-43`（PUT 仅 `require_admin`，可写 `notify.webhook_url` 等平台键）
- `backend/app/tenant_isolation.py:34-41`：`system_configs`/`channel_events` 为平台豁免表（无租户过滤）

**为什么深层**：「管理员」语义在多租户商品里分叉为"租户管理员"和"平台超管"，但 API 守卫层没有落地这个区分。一个付费租户的 admin 可以：把平台告警 webhook 改到自己的端点（平台运行数据外泄）、关掉全平台的 LLM 中转渠道（让所有租户的兜底 LLM 停摆）。这类"越权写平台"一旦被任何租户发现（或被演示时误触），信任归零。

**解决方案（可执行）**
1. 守卫替换（机械改动，半天量级）：`newapi.py` 全部写端点、`configs.py` PUT、`admin.py` 的 tenants/notify-config 端点改用已有的 `require_platform_admin`（`deps.py:119-125`）。
2. `GET /configs/` 按键白名单裁剪：租户可见集 = 站点标题等展示键；`notify.*`、`newapi.*` 键仅平台态返回。
3. RBAC 权限码增加 `platform:` 前缀约定，`/auth/menus` 下发时按 `is_platform_admin` 过滤（`menuConfig.tsx:77-78` 的「中转站管控」「用户管理」同步做 tenantOnly/platformOnly 标记），避免"租户后台出现平台菜单"的认知错位。

### 4. 会话 30 分钟硬过期、无刷新令牌，「记住我（7 天）」是假的
**严重度：高**

**证据**
- `config/default/jwt.yml:12-13`：`ACCESS_TOKEN_EXPIRE_MINUTES: 30`；`REFRESH_TOKEN_EXPIRE_DAYS: 7` **有配置、无实现**（全仓 grep `refresh_token` 生产代码零命中，前后端均无 refresh 端点/逻辑）
- `frontend/admin/src/pages/Login.tsx:79-80`：提供"记住我（7 天）"勾选框；`store/useAuthStore.ts:29-34` 仅把它用于 localStorage 持久化，服务端 token 仍 30 分钟死
- `frontend/admin/src/services/api.ts:14-17`：任一 401 → 立即清登录态踢回登录页

**为什么深层**：核心场景（AI 采集向导、日志抽屉盯任务）都是长会话，用户会在配置到一半时被静默踢出，未保存的表单全部丢失；同时"7 天"承诺与 30 分钟现实构成"被发现即炸"的静默降级。留存数据上这是最廉价的修复、最贵的忽视。

**解决方案（可执行）**
1. 实现 `POST /auth/refresh`：登录同时签发 refresh token（7 天，旋转 + 旧 token 失效），`shared/api/client.ts` 在 401 时先静默刷新再重放原请求，失败才踢登录页。
2. 短期最小改法（无新端点）：`LoginRequest` 增加 `remember_me` 字段，`auth_service.create_token` 按其签发 30 分钟/7 天两种有效期的 access token，让承诺先变成真的。
3. 长任务页面向到期前 2 分钟弹出"会话即将过期"toast（前端可在 store 记录登录时间戳实现）。

### 5. 注册链路信任三断点：无邮箱验证、无找回密码、无条款/隐私与联系方式
**严重度：高**

**证据**
- `backend/services/tenant_signup_service.py:34-75`：公司名+邮箱+密码直接建 tenant+owner，无邮箱验证；邮箱格式校验仅为 `"@"` 判断（`:41`）
- 全仓无 forgot-password 端点（仅 `backend/app/api/v1/members.py:86` 租户内管理员重置成员密码）；忘记密码 = 账号永久锁死
- `frontend/official/src/pages/Register.tsx`：无条款/隐私勾选；注册成功页（`:53-55`）只显示"管理员账号"与"再注册一家/返回官网"，**没有"去后台登录"直达链接**；用户名是邮箱前缀（`tenant_signup_service.py:61`），登录表单却只认用户名（`auth_service.authenticate` 仅按 username 查询，`:44-66`），用户习惯性输邮箱必 401
- `frontend/official/src/components/layout/SiteLayout.tsx:88-117`：footer 无隐私政策/服务条款/备案号/联系方式；`Pricing.tsx:21,27`「联系升级」「联系销售」CTA 全部指向 `/register`，无任何真实联系通道
- 邮件基建已备而未用：`config/default/notify.yml` EMAIL.SMTP_HOST 为空，`backend/services/notify_service.py:176-190` 具备 SMTP 发送能力

**为什么深层**：面向公众后，爬虫这类合规敏感产品的企业客户第一件事就是找条款与隐私承诺，找不到即流失；任意邮箱可注册（无验证）= 刷租户与占 slug 零成本；typo 邮箱 + 无找回 = 必然产生的客服死角；定价页"联系销售"点进注册页 = 转化链路自断。

**解决方案（可执行）**
1. 注册加邮箱验证：复用 notify SMTP 能力发 6 位验证码，`tenants` 增加 `verified_at`；未验证租户 24h 后降级只读（登录可进、任务不可提交），验证即恢复。
2. 加 `POST /auth/forgot-password`（一次性重置 token 落 Redis 15 分钟）+ 官网/后台登录页入口。
3. 官网 footer 与注册页挂《服务条款》《隐私政策》（明确：采集数据归属租户、平台 LLM 兜底时目标 URL 与页面 HTML 会送至激活的 LLM 供应商——`ai_planner/prompting.py:52-60` 证实该数据流），注册请求加 `accepted_terms` 必填校验。
4. 注册成功页改为两个等权 CTA：「进入管理后台」（ADMIN_URL）+「返回官网」；登录支持邮箱直达（`authenticate` 先按 username 查、miss 后按 email 查，`get_by_email` 已存在）。
5. Pricing 两档 CTA 改为 mailto: 或简单表单（公司/邮箱/需求三字段落 `system_configs` 或新表），不再是 `/register`。

### 6. 增长三地基全缺：首页假数据、无 SEO、无任何埋点
**严重度：中**

**证据**
- `frontend/official/src/pages/Home.tsx:31-35`：HERO_STATS "128,000+ 累计执行任务 / 12 节点在线 / 3.2 亿条采集数据"（代码注释自认静态示意，`:183-185` 仅小字标注"示意数据"）
- `config/default/official.yml:14-15`：`ENABLE_SSR: false`、`SITEMAP_ENABLED: false`；CRA 纯 CSR（`public/index.html` 无 OG/结构化数据），技能广场几百条内容搜索引擎抓不到
- 全前端 grep `analytics/gtag/baidu/sentry` = 零命中：注册转化率、各步流失、渠道来源完全不可测

**为什么深层**：无用户的产品展示 12 万任务，被任何较真的访客发现（页面小字承认是编的）→"这家公司在造假"的印象一旦形成不可逆，比不展示伤害大得多。纯 CSR + 无 sitemap 让技能广场这个唯一的内容资产对搜索引擎不可见，内容增长引擎等于没接电。无埋点则让所有后续增长动作无法归因，运营盲飞。

**解决方案（可执行）**
1. HERO_STATS 二选一：接 `/public/stats` 真实聚合（后端 1 天工作量，注意只暴露平台级计数不含租户信息），或在有真实数据前换成能力性文案（"免代码 / AI 规划 / 分布式"）并删除数字。
2. 四个官网页做预渲染（Next.js 迁移或 react-snap 预渲染均可）+ `sitemap.xml` + OG tags；技能详情从 Modal 改为独立路由 `/skills/:name`（与问题 8 联动）。
3. 自托管 Umami/Plausible（隐私友好、无需 cookie banner），定义并埋 5 个事件：`home_view / pricing_view / register_submit / first_task_success / first_api_call`；`first_task_success` 是北极星，先让它能被看见。

### 7. 官网单一叙事 vs 后台四板块现实：访客认知断裂
**严重度：中**

**证据**
- 官网只讲爬虫：`SiteLayout.tsx:16` slogan「AI 驱动的智能数据采集系统」，`Home.tsx` 全篇爬虫故事；导航仅技能广场/能力广场/定价/注册（`SiteLayout.tsx:19-24`）
- LLM BYOK 与中转站只存在于后台菜单（`frontend/admin/src/config/menuConfig.tsx:77-78`），官网零提及；README.md:3/38 说明四板块且中转站实为 new-api 的外挂巡检器

**为什么深层**：新访客带着"爬虫 SaaS"认知注册，进后台突然看到 LLM 配置/中转站/平台运营台菜单，第一反应是"这是给谁用的？我是不是进错系统了"。反过来，若 marketing 层把中转站宣传为"LLM 网关"，又与 new-api/one-api（github.com/QuantumNous/new-api、github.com/songquanpeng/one-api）构成误导性竞争——它实际是网关的管控侧车。定位不清会让首批用户无法向同事转述产品是什么（口碑传播的第一句就卡住）。

**解决方案（可执行）**
1. 官网首页加"产品矩阵"分区：四个模块各一屏（爬虫工厂 / LLM 接入与网关管控 / 技能资产库 / 开放 API），每屏 = 一句价值主张 + 一张真实后台截图 + 一个 CTA。
2. 中转站模块文案明确锚定："为你的 new-api/one-api 网关提供额度熔断与渠道真伪巡检"——以配套工具姿态借 new-api 生态流量而非正面竞争。
3. admin 首登加 3 步 onboarding checklist（Dashboard 空态处）：创建租户已完成 → 激活 LLM 或跳过 → 跑通第一个任务；完成打勾写 `system_configs` 按租户存。

### 8. 技能广场只进不出：无公开投稿、无互动、无可分享落地页，内容飞轮转不起来
**严重度：中**

**证据**
- `backend/app/api/v1/public_skills.py:114-146`：公开面仅 GET 列表/详情
- 投稿与治理全部是内部操作：`backend/app/api/v1/skills.py:41-176`（scan/import-url/candidates approve/reject 均为管理员接口）
- `frontend/official/src/pages/SkillsSquare.tsx`：无"发布技能"入口；详情用 Modal 展示（`:142-165`），无独立 URL 可分享

**为什么深层**：技能库是四个板块里唯一的网络效应候选：UGC 技能 → 长尾搜索流量 → 带注册 → 技能被复用又吸引新作者。现状是编辑部模式，供给上限等于运营人力，且评审结果（tier/score）再优质也不产生自传播——没有作者、没有分享链路、没有互动回路。

**解决方案（可执行）**
1. 最小 UGC 闭环（约一周量级）：官网「提交技能」表单（SKILL.md 的 GitHub 仓库 URL + 作者署名 + 邮箱）→ 落 `skill_candidates` 待审（复用现有 candidates approve/reject 流），过审自动进公开广场并在详情页展示作者与来源（`source_author`/`source_url` 字段协议里已有）。
2. 详情页改独立路由 `/skills/:name`（深链已支持 `?q=`，补路由即可）+ 「登录后复制到我的租户」按钮（登录态调用现有技能导入接口），把浏览转化为注册钩子。
3. 每月发布"新上架技能"内容（官网 changelog 页），同时解决问题 10 的发版说明缺失。

### 9. 配额与到期语义"硬拒付"：存储满即拒收数据、到期即拒绝登录
**严重度：中**

**证据**
- `backend/tasks/consumer.py:694`：结果回流前 `check_result_storage` 超限直接拒绝（免费档 10,000 行，`quota_service.py:24-28`），错误文案"请清理历史结果或联系平台管理员"
- `backend/services/tenant_expiry_service.py:21-36`：到期租户置 `expired` → 登录被拒；无到期前提醒、无宽限期设计（`tenants.expires_at` 注释 NULL=不过期，`platform_core/models/tenant.py:21`）
- 数据可携性反而不错（CSV/JSON 导出、`EXPORT_MAX_ROWS` 可配），但无"一键全量导出"入口，可携性未成为承诺

**为什么深层**：对爬虫用户，"任务显示成功但结果没进来"（存储满拒收）是最恶性的静默丢数据——比任务失败更难被发现。到期即锁登录给企业客户的观感是"数据被平台扣押"，这是 B 端口碑里最忌讳的一条。两者都源于同一设计缺口：**降级路径没有为数据安全设计**。

**解决方案（可执行）**
1. 存储超限改"回流降级"：超限结果转对象存储（`platform_core/storage` 已有）打 `archived` 标记，任务照常完成、UI 明示"已归档 N 条，升级后可见"，杜绝静默丢数。
2. 到期保护窗：到期前 7/3/1 天走 notify 渠道提醒；过期后保留 30 天只读 + 导出窗口再降级（`tenant_expiry_service` 加提醒扫描即可，模型不用动）。
3. 数据中心页加"导出全部结果（JSONL）"自助入口，官网把它写成卖点："数据始终是你的，随时全量带走"——这是与 Apify/Firecrawl（数据在他们平台）差异化的信任点。

### 10. 运营可操作性缺位：无 CHANGELOG、无状态页、无公告位、版本 0.1.0
**严重度：低**

**证据**
- 全仓 find `CHANGELOG*/RELEASE*` = 零命中；`config/default/settings.yml:5` `VERSION: "0.1.0"`
- 对外健康面仅 `/api/v2` db/storage 探针（`backend/app/api/v2/`），官网无 status 页与维护公告位
- `backend/app/api/v1/configs.py` + `system_configs` KV 基建已存在但只用于站点配置，未承载用户公告

**为什么深层**：首批用户对爬虫产品最大的敏感点是"我的任务为什么失败"。改了什么、坏了什么、什么时候恢复，如果全靠用户自己发现，每次小事故都会被放大成"这平台不靠谱"。运营可操作性是留存的地板，不是锦上添花。

**解决方案（可执行）**
1. 根目录建 `CHANGELOG.md`（Keep a Changelog 格式），PR 模板强制填"用户视角变更"一栏；官网 `/changelog` 页直接渲染该文件。
2. 官网加 `/status` 页：后端聚合 `/api/v2` 探针（存活/db/storage/redis）渲染成红绿灯 + 最近 30 天事件列表（事件先手工维护在 system_configs）。
3. admin Dashboard 顶部加"系统公告"条（读 `system_configs` 的 `announcement.active` 键），发版/维护前 7 天由平台超管在此发布公告——复用问题 3 收口后的平台态配置通道。

---

## 三、竞品对照（三层结论）

### 直接竞品
| 赛道 | 对象 | 参照点 |
|------|------|--------|
| 爬虫 SaaS | Apify（Actor 市场 + 平台计费） | https://www.apify.com/pricing |
| 爬虫 SaaS | Firecrawl（API-first 采集） | https://www.firecrawl.dev/ |
| 爬虫 SaaS | ScrapingBee / Browserbase | https://www.scrapingbee.com/pricing · https://www.browserbase.com/pricing |
| LLM 网关 | new-api / one-api（自托管网关，本产品中转站的管控对象） | https://github.com/QuantumNous/new-api · https://github.com/songquanpeng/one-api |
| LLM 网关 | LiteLLM（Proxy + 预算治理） | https://github.com/BerriAI/litellm |
| LLM 网关 | OpenRouter / Helicone | https://openrouter.ai/docs · https://www.helicone.ai/pricing |

### 借鉴（Borrow）
1. **Apify 的"每个资产一个 SEO 落地页"**：Actor Store 每个_actor_独立 URL、可被搜索、展示作者与安装量——本产品技能广场应照此改造（问题 8 + 6 联动），把评审体系变成内容资产。
2. **LiteLLM 的按 Key/Team 预算强制**：`max_budget` 按 key 硬限 + soft limit 告警，服务端强制执行——正是问题 2 缺失的模型；直接照抄其"预算超限即拒 + 80% 告警"语义。
3. **Firecrawl 的 1 分钟上手**：注册完立刻拿到 API Key + 可复制的 curl 示例并当场出结果——本产品注册成功页应直接给出租户 API Key 与第一个任务的成功回执（依赖问题 1 的租户 Key）。
4. **OpenRouter 的用量透明**：每次调用可查、定价与用量公开——本产品用量看板已有三指标，补"按任务/按成员分摊"即可（`usage_by_member` 已实现，缺前端呈现引导）。

### 回避（Avoid）
1. **Apify 式积分黑盒定价**（平台费 + credit 换算让人算不清）——本产品三指标配额（并发/存储/token）直给是优势，坚持"配额=看得懂的三个数字"。
2. **无销售团队却做销售门禁**（Browserbase 式"联系销售"主导）——在有人接销售线索之前，定价页 CTA 必须自助可达，否则等于把转化漏斗末端焊死（问题 5）。
3. **new-api 的"渠道/令牌/分组"运维概念直接暴露给租户**——渠道治理是平台内部概念，租户侧只应看到"我的用量与我的 Key"，避免把运维心智负担转嫁给用户（问题 3 的前端镜像）。

### 差异化（Differentiate）
1. **"AI 规划采集 + 技能资产库 + BYOK"闭环组合**：单点功能上全面弱于 Apify（生态）与 LiteLLM（网关），但"粘贴链接 → AI 规划 → 试采 → 上线 → 沉淀为可复用技能"的完整闭环在两个赛道都无人同时提供——官网叙事应聚焦这条闭环而非罗列功能。
2. **中转站定位为 new-api 生态的管控伴侣**而非网关竞争者：以巡检/熔断/真伪探针切入，吃 new-api/one-api 自托管群体的运维痛点（该群体恰是早期最可能的第一批用户）。
3. **数据可携 + BYOK 作为信任差异点**：结果可全量导出、LLM Key 租户自持（平台兜底可选），对"不敢把数据交给 SaaS"的目标客群是 Apify/Firecrawl 不给的承诺——前提是先修完问题 1/2/9 把承诺做实。

---

## 四、自检对照（方法纪律）

- [x] 每条问题带文件:行号证据（来源=仓库事实，非印象）
- [x] 竞品给了借鉴/回避/差异化三层结论，且 URL 已可达性验证（2026-09-06，HTTP 200；crawl4ai 官网 404 故未引用）
- [x] 对照了"准备走向公开"的原始前提：结论是当前 4 项高危问题未收口前不应公开投放，收口顺序即严重度排序
- 遗留不确定项：①`/auth/register`（非租户注册）产物用户的租户归属路径未逐一追踪，与问题 5 相关；②`newapi` overview 是否含租户维度统计未深挖（当前判定为纯平台域）；③邮件域名/SPF 等送达率问题需部署侧验证
