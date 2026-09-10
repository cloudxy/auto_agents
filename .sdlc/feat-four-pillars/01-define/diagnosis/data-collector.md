# 数据采集诊断（data-collector）

| 字段 | 值 |
|------|----|
| 角色 | data-collector（采集 / 反爬 / 源接入；不写主库、不写产品 FR、本波不新建爬虫） |
| 特征 | `feat-four-pillars` · 定义帽刷新 |
| 日期 | 2026-09-07 |
| 对照 | `01-define/spec.md` v1（Wave 0/1 冻结）· ADR-0013（候选所有权 accepted）· `power-market-design.md` Accepted |
| 约束 | 采集出口只经 Redis；B2：`scrapy/` 禁止 import `backend/`；ADR-0013：**不改** harvester 出口 |

**一句话**：采集闭环（Redis 队列 + 清洗管道 + 注册表）骨架在，但 **租户在采集链路上只活到任务入队**——结果回流丢 `tenant_id`，调度/模板/AI 试采根本不入队租户；智能采集仍是演示级；市场采集与 Source 注册表仍是两件事。默认 Worker 终态靠本地 idle-close，零条目不告警、不收尾。

---

## 0. 采集心智模型（现状 vs 目标）

平台上有 **三条互不相交的入站路径**，口语都叫「扫描 / 采集 / 市场」：

| 路径 | 真相源 | 执行者 | 出口 | 今日代码 |
|------|--------|--------|------|----------|
| **A. 智能采集支柱** | 任意 HTML/API（任务 `params.urls`） | Scrapy Worker | Redis `spider:item_queue` → `spider_results` | `generic` / `flow_generic` + 演示爬虫 |
| **B. 市场候选采集** | 公开 GitHub 清单 | `skill_harvester` | 同上，`source=marketplace` → 候选 Tab | `scrapy/spiders/skill_harvester.py` |
| **C. 本机/git 源索引** | `~/.zcode/local-plugins`、Kimi managed、git clone | **不是爬虫**，是适配器扫盘 | 直接 upsert `capability_sources` + `capability_assets`（设计稿，尚未落地） | 设计：`power-market-design.md` §1/§4.4；现状：`POST /skills/scan` + `POST /capabilities/scan-plugins` |

Power Market 把 C 叫 Source 注册表，把 B 叫 crawl 适配器（§4.4 / mermaid A4）。**把 B 当成 C、或把 C 交给 Scrapy，都会写错数据流。**

ADR-0013（塑形已 accepted，FR-11）：Wave 0/1 **不**新建候选表；harvester 继续 Redis → `spider_results.source=marketplace`；配额与租户结果列表 **排除** marketplace；平台入站任务不应挂在触发者企业上。采集帽 **不改 harvester 出口**。

```
外部站点 / GitHub API          ~/.zcode · Kimi · git
        │                              │
        ▼                              ▼
   scrapy Worker                  源适配器（只读树）  ← 禁止新开 spider
        │                              │
        ▼                              ▼
  Redis ITEM_QUEUE              capability_sources
        │                       + capability_assets
        ▼
  backend consumer  ← 必须在这里解析租户（Scrapy 保持租户盲）
        │
        ▼
  spider_results ── source=marketplace ──► 候选（人工闸门）
                 ── 其它 source ──────────► 租户「我的结果」
```

红线未破（本轮抽查成立）：`scrapy/` 无 `from backend` / `sqlalchemy`；StorePipeline 只 `rpush` Redis。

---

## 1. 数据源与爬虫覆盖

### 1.1 代码爬虫 vs 注册表 vs 站点配置（三套清单对不齐）

**磁盘爬虫**（`scrapy/spiders/`，`run_spider.py --list` 能加载）：

| spider | 基类 | 源类型 | 实际能力 |
|--------|------|--------|----------|
| `example` | `TaskAwareRedisSpider` | JSON/HTML 嗅探 | 演示；`allowed_domains` 钉死 httpbin/example.com |
| `openweather` | 同上 | JSON API | 可用；密钥走 `sites.yml`，占位符拒绝；入库 URL 剥 `appid` |
| `zhihu_feed` | 同上 | HTML | **桩**：`div.Card` 选择器过时；`login_required` 只打日志 |
| `dianping_home` | 同上 | HTML | **桩**：只取 `title`；注释写明字体加密未处理 |
| `generic` | `RedisSpider`（**未**继承基类） | 配置化 CSS/XPath/regex | 智能采集主路径；无站点级 delay |
| `flow_generic` | 同上 | 列表/翻页/详情/过滤 | 智能采集进阶 + AI 规划出口 |
| `skill_harvester` | `TaskAwareRedisSpider` | GitHub contents JSON + awesome README | **唯一市场爬虫** |

**yml 种子** `config/default/spiders.yml` `SPIDERS`：example / openweather / dianping_home / zhihu_feed / generic / flow_generic。**没有 `skill_harvester`。**

**DB 种子**：

- `005_add_spider_definitions.py`：前 5 个（无 flow、无 harvester）
- `007_add_flow_generic_definition.py`：补 `flow_generic`
- `016_add_skill_harvester_definition.py`：补 `skill_harvester`（`type=api`）

注册表「DB 优先、yml 兜底」（`backend/services/spider_registry_service.py`）。yml 与 DB 双源，harvester 只在迁移里，新环境若只读 yml 会从任务弹窗消失。

**站点配置** `config/scrapy/default/sites.yml`：

| site_id | 有爬虫？ | 备注 |
|---------|----------|------|
| `baidu_hot` | **无** | 配了 delay=2；`HotSearchItem` 在 items 里孤儿 |
| `weibo_hot` | **无** | `login_required` + proxy；无 spider |
| `openweather` | 有 | `api_key: YOUR_API_KEY_HERE` 占位，未配则丢弃请求 |
| `zhihu_feed` / `dianping_home` | 有（桩） | 登录态未接线 |
| GitHub / skill 市场 | **无 site 段** | harvester 吃全局 delay；prod 更把全局 delay 压到 **0.5s**（见 §3） |

### 1.2 智能采集支柱：有引擎，没有「源」

spec 柱 A / Wave 4 FR-70…72：经办从一条链接走到可导出结果；无工人要拦住；试采未通过不能上线。采集侧看到的是：

- **通用引擎有了**：`generic` + `flow_generic`（选择器 / 翻页 cap 100 / 详情 / 过滤）。`flow_generic` 空字段时不 yield（不 raise）；`generic.parse` 仍 `raise DropItem`（应在管道 Raise）→ 更像 spider error。
- **目标源没有产品级目录**：没有「值得长期采的源」注册（领域、robots、延迟、代理、JS、新鲜度）。任务是一次性 URL 袋。
- **AI 规划**产出 `flow_generic` 参数，试采仍走同一 Worker。规划质量不在本角色范围；采集侧缺口是：**试采失败与封禁无法按源升级反爬**，且试采入队丢租户（§5）。
- `generic`/`flow_generic` 无 `allowed_domains`：任意 URL 可投。风控本应「站点侧配置兜底」，但这两只爬虫**不读** `sites.yml` 的 `download_delay`（基类 `from_crawler` 只挂在 `TaskAwareRedisSpider` 上）。
- **入队不看 Worker 心跳**：`spider_task_service.enqueue` 不读 `spider:worker:{id}`。FR-71「没有在线节点则拦住」今日不存在——任务照样 pending/running，屏上像在爬。

### 1.3 市场采集：GitHub 目录名，不是技能正文，更不是插件包

`skill_harvester.parse`（本轮复核，行为未变）：

- `api.github.com/.../contents` → **仅 `type=dir`**，`title=目录名`，`content=""`，`source=marketplace`。
- raw README → 正则 `- [title](github-url) — desc`，非 GitHub 链接丢弃。
- **不拉 SKILL.md、不解析 frontmatter、不识别 `plugin.json` / `kimi.plugin.json`、不递归子目录、无 contents 分页、无 `Accept: application/vnd.github+json`、无 token。**

这与 Power Market 要索引的对象（ZCode 插件树、Kimi `kimi.plugin.json`、bundled `SKILL.md`、`content_hash` 折叠）**不是同一类源**。harvester 最多给「公开 skill 仓库的目录名候选」，喂不饱商店面。这是设计预期的 A4 窄口，不是 C 路径的替代。

测试只覆盖离线 Response（`backend/tests/test_skill_harvester.py`），零真外呼，测不到 403/限流/空 content。`test_spider_contract` 里「不 import backend」是空占位。

### 1.4 覆盖缺口（采集视角）

1. `sites.yml` 两个热搜源无 spider；Item 有 `HotSearchItem` 无生产者。
2. 知乎 / 点评是高风控演示，选择器与登录均未落地 → 作为支柱样本会持续 0 有效字段。
3. 市场源只有 GitHub；无 Claude/OpenAI skill 目录的稳定 API 契约、无 npm/MCP registry、无 Kimi plugin-market（设计稿写本机尚不存在，适配器预留）。
4. Power Market 的 `zcode_local` / `kimi_home` / `git` **不应做爬虫**；今日也还没有适配器模块（`config/default/power_market.yml` 不存在）。
5. DrissionPage / Selenium 在 `scrapy/pyproject.toml` 里，**无中间件、无 spider 引用**（`example.py` 注释提到 XHR 监听，代码没有）。Playwright 中间件默认关闭，且 **不在 scrapy 包依赖里**（未装 → `NotConfigured`）。

---

## 2. Item 质量

### 2.1 契约

`scrapy/items/__init__.py` `BaseItem`：`url/title/content/source/extra/_quality_score` + 归属 `task_id`。**无 `tenant_id` 字段**——这是对的（B2：Scrapy 应保持租户盲）。

落库：`platform_core/models/spider_result.py` — `quality_score`、`content_hash`（md5 of url+title+content）、`source VARCHAR(50)`、`TenantMixin.tenant_id`。

管道顺序（`scrapy/settings.py`）：Clean(200) → Validate(300) → QualityCheck(350) → Store(400)。`scrapy_redis.RedisPipeline` 在 settings.py 里显式 `None`（防 `<spider>:items` 无消费者涨内存）。**yml 仍登记 `RedisPipeline: 100`**（见 §3.2）。

### 2.2 质量评分系统性偏低

`scrapy/pipelines/quality.py`：

- 完整率 = **已声明字段**非空比例 × 50。`BaseItem` 声明了 `id/created_at/updated_at/task_id/_quality_score` 等内部字段，业务 item 几乎永远填不满 → 完整率天花板远低于 1.0。
- 核心字段默认 `url, title, content`。harvester 的 GitHub 目录候选 **`content` 恒空** → 核心率 2/3。
- 去重分只在 **单 spider 进程内存** `_seen`；Worker 重生后清零。跨任务去重是 consumer 的 `params.incremental`（默认关）。

algo/FR-72 用质量分 ≥40 当「抽对」代理指标：公式被内部字段污染后，试采「通过」线不可信。

Validate：无 `url` 丢弃；无 `title` 仅 warning。

### 2.3 市场候选 `extra` 嵌套丢失（生产与测试不一致）

harvester 写 `item["extra"] = {"repo", "kind"}`（dict）。`BaseItem` 未声明 `repo`/`kind`，只能放 extra（Scrapy Item 未声明字段会 KeyError）。

consumer 把未映射键整包进 `spider_results.extra`（`mapped = {url,title,content,source}`），结果落库形如：

```json
{"extra": {"repo": "anthropics/skills", "kind": "github_dir"}}
```

`SkillService.list_candidates` 读 **顶层** `kind` / `repo`（`_extra_of`）。候选 Tab 的类型/仓库在真采集路径上会空。

测试种子却是扁平 JSON（`backend/tests/test_skill_candidates.py`：`extra=json.dumps({"repo":..., "kind":...})`），测不到该洞。

ADR-0013 冻结 extra 协议：**不得再加新键当市场状态机**（`review` 已占用）。采集侧建议的修法是 **consumer 把 `item["extra"]` 为 dict 时上提合并**，不是 harvester 改出口、也不是新状态键。

### 2.4 转正后身份被洗成第一方

`approve_candidate` → `SkillImportService.import_url`：把 GitHub 树 **copy 进** `capability-library/skills/<name>/`，再 `scan_library`。`_upsert_from_dir` **写死 `source_type="self_built"`**（`skill_service.py`），尽管 schema 已有 `marketplace_crawled`。

这违反 Power Market D1（禁止把第三方 vendor 进 git）和 D7（第三方同步不得自动 listed）。采集侧结论：**B 路径的「转正」今天在做 C 路径不该做的落盘。** 这是 Wave 1 市场身份问题，不是采集运输问题；运输按 ADR-0013 保持 Redis → `spider_results`。

### 2.5 候选查询不适合千～万行

设计稿容量：「候选 `spider_results` 按千到万」。`list_candidates` 先 `select` 全部 `source=marketplace` 再内存过滤 `extra.review`、再切片。无 SQL 分页、无 review 索引（review 在 JSON 字符串里）。守卫是 `require_login`（任意登录可看），不是平台超管。ADR-0013 已要求：超管候选列表在 `platform_scope` 下按 source **分页**，禁止全表进 Python。

### 2.6 增量去重与内容指纹

- 管道侧：url|title 的 md5，不规范化、不加租户。
- 落库侧：`md5(url+title+content)`，`incremental=true` 才跳过。
- 批路径 `find_by_content_hash(..., tenant_id=msg.get("tenant_id"))`；单条 `_ingest` **不传租户**。
- 因为回流消息没有 tenant（§5），批路径的租户去重形同关闭。
- harvester 目录候选 content 为空 → 同 URL 重复跑会生成相同 hash；默认不增量则候选表膨胀。

---

## 3. 反爬（生存底线）

对照 skill：delay、UA 轮换、retry+backoff、robots、按成本升级、连续 3 次 0 条告警。

### 3.1 已有（R5/R6 机械检查能过）

| 能力 | 位置 | 评价 |
|------|------|------|
| `DOWNLOAD_DELAY` + `RANDOMIZE_DOWNLOAD_DELAY` | `scrapy/settings.py` 读 Dynaconf | 默认 1s；**`config/prod/settings.yml` 写成 0.5**——生产比默认更激进 |
| UA 轮换 4 条 Chrome/Safari 120 | `middlewares.UserAgentMiddleware` | 池小、版本冻结；`fixed_ua` 站点改用全局 UA |
| Retry 3 次；429 抬槽位 delay | 自研 `middlewares.RetryMiddleware` | 覆盖 429/5xx；**不含 403、不含 408** |
| 代理评分加权 | `ProxyMiddleware` + `PROXY_SCORES_KEY` | **默认 `PROXY_ENABLED=false`** |
| Playwright | `middlewares/playwright_dm.py` | `PLAYWRIGHT.ENABLED=false`；仅 `flow_generic` 透传 `render_js`；`generic` 无 JS 路径 |
| 任务暂停/终止 | `TaskControlMiddleware` | Redis 控制键，B2 合规 |

`scripts/check-arch.sh` R5/R6 只 grep 字符串存在，不检查 per-spider delay、不检查 AUTOTHROTTLE、不检查 robots、不检查 prod 覆盖把 delay 改小。

### 3.2 空洞

1. **`ROBOTSTXT_OBEY: false`**（`config/scrapy/default/settings.yml`）。Skill 要求尊重 robots；现默认关闭。
2. **无 AUTOTHROTTLE**（全仓零命中）。`CONCURRENT_REQUESTS=32`（prod 16）、`CONCURRENT_REQUESTS_PER_DOMAIN=16` + delay 1s/0.5s，对 GitHub/知乎等于催封。
3. **账号会话未接线**。`AccountSessionMiddleware` 依赖 `request.meta.account_id`；全仓无 spider 设置该字段。`SessionManager` 是死代码。基类对 `login_required` 只 `logger.warning`。zhihu/dianping/weibo 配置是空头支票。
4. **指纹中间件不是指纹**。`FingerprintMiddleware` 给 URL 做 md5 写 meta，无 TLS/JA3、无 Client Hints。
5. **CAPTCHA / 滑块**：无。Wave 4 spec 明确不承诺登录墙/验证码——采集侧不要把升级档当卖点，但高风控演示站也不该算覆盖。
6. **DrissionPage/Selenium 依赖未用**；Playwright 默认关且不在 spider 包依赖。
7. **配置双份**：`config/scrapy/default/settings.yml` 仍登记 `RedisPipeline: 100`，且 middleware 列表缺 TaskControl / Playwright。真正生效的是 `scrapy/settings.py`（`SCRAPY_SETTINGS_MODULE=settings`）。yml 会误导「改配置即改 Worker」。P1-8 已在 settings.py 关掉 RedisPipeline；yml 仍是复发口。
8. **内置 RetryMiddleware 未禁用**。`scrapy/settings.py` 注册自研 Retry 于 550，**没有** `'scrapy.downloadermiddlewares.retry.RetryMiddleware': None`。两套 550 可能叠加重试。
9. **GitHub 市场采集无 token、无 API version header、无 403 重试**。未认证 REST 约 60 次/小时；contents 一页 100 条。被拒后走 HttpError 丢弃（未见 `HTTPERROR_ALLOWED_CODES`），0 item。
10. **`skill_harvester` 无 site 段**，无法单独把 delay 提到 2–5s、无法 `fixed_ua`、无法关并发。

反爬升级阶梯（skill 1→6）今日停在 1–2，且 2 的 UA 池不合格、prod 还把 1 档 delay 削半；3–6 代码有插座、无电流。

---

## 4. Redis 队列 vs 主库

### 4.1 闭环（设计，B2 成立）

`platform_core/queues.py`：

1. Backend `enqueue` → `spider:task_queue:{high,normal,low}`
2. `SpiderTaskConsumer._dispatch`：pending→running，`rpush <spider>:start_urls`
3. StorePipeline → `spider:item_queue`
4. `_ingest_loop` 批量落 `spider_results` + `result_count`
5. 爬虫关闭 → HMAC webhook → completed/failed，清 `ACTIVE_TASK_KEY`

Scrapy **不写 MySQL**。死信：`spider:item_dead`（缺 `task_id`）。推送连续失败 5 条 `CloseSpider("redis_push_failed")`。

StorePipeline 消息形状（**无 tenant_id**）：

```json
{"task_id": 123, "spider_name": "generic", "item_type": "BaseItem",
 "item": {...}, "fetched_at": "ISO-8601"}
```

`build_start_payload` 同样无 tenant：`{"url", "task_id", flow|selectors, params?}`。

### 4.2 终态依赖 idle-close，默认是关的

| 配置 | 值 | 效果 |
|------|----|------|
| `config/scrapy/default/settings.yml` `SPIDER_IDLE_CLOSE_SECONDS` | **0** | `IdleAutoClose.from_crawler` **不注册信号** |
| `config/scrapy/local/settings.yml` | 30 | 本地有产出后 30s 收尾 → webhook → `run_spider.py` 5s 重生 |
| `TASKS.STALE_TASK_HOURS` | 6 | 孤儿 running 回收 |

默认 / prod（prod scrapy yml 不存在）Worker 常驻、**从不因空闲关闭** → webhook 不触发 → 任务一直 `running`，只靠 6 小时回收。README「空闲收尾完成闭环」**只在 local 为真**。根 compose **没有** scrapy Worker（sre 诊断）：联调若只起 backend，任务会永远等。

更严重：`IdleAutoClose.spider_idle` 在 **`_has_items` 为假时直接 return**（`scrapy/extensions/__init__.py`）。**零条目任务永远不 finished**，本地 30s 也不救。选择器失效、403、GitHub 限流 → 卡 running 直到 stale。这直接打 FR-70/71：用户看见「正在采集」，其实已经 0 条且不会收尾。

### 4.3 零条目 ≠ failed，告警对不上 skill 门槛

`AlertService`：

- `consecutive_failures`：最近 N 条 **status=failed**。0 条若将来被标 completed，不触发。
- `result_drop`：相对上次 completed 的条数下降 %。首次 0 条 / 无历史 → 不触发。
- `task_timeout`：看 `duration_seconds`，依赖终态评估被调用。
- **没有「连续 3 次 0 item」规则**（skill 红线）。

blocked 检测：无 403/验证码/空 body 分类；无成功率、无 P95。SRE：无队列深度对外告警。

### 4.4 其它队列问题

- **同爬虫并发**：`SPIDER_MAX_CONCURRENT_PER_SPIDER=2`；多 task 时 webhook 的 `item_count=None`（stats 无法按任务切）。
- **pause**：`IgnoreRequest` 跳过当前请求，start_urls 可能被吞掉且不重新入队。
- **flow 切爬虫**：dispatch 发现流程段会把任务改名为 `flow_generic` 再投递。Worker 必须已加载 `flow_generic`；`--spider generic` 单进程会让流程任务卡死。
- **心跳**：`run_spider.py` 写 `spider:worker:{id}`，Backend 只读。合规。入队不消费该键（§1.2）。
- **Webhook 密钥**：`config/default/webhook.yml` `SECRET_KEY: change-me-in-production`，采集闭环的认证面偏弱（记给 ops/sre）。
- **`_reenqueue` 重试 JSON 丢掉 `tenant_id`**（即便入队时写过）。dispatch 本来也不读它，但是字段漂移会让「消息里有租户」的假设更假。
- 消费者 lifespan **不进 `platform_scope`**（backend 诊断已记录）：无上下文 = 不过滤不断言。跨租户回流必须 **显式**写结果行的 `tenant_id`，不能指望 mixin。

---

## 5. 租户在采集链路上的断裂（本轮主缝）

spec FR-08/09/11：任务与结果属提交者企业；定时/模板/AI 试采计入该租户配额；市场候选 **不**计入结果存储、**不**出现在「我的结果」。

今日链路（已逐跳核对）：

```
HTTP POST /spiders/run
  └─ 唯一正确：enqueue(..., tenant_id=user.tenant_id)
        │
        ├─ spider_tasks.tenant_id = T     ✅ 任务行有租户
        ├─ task_queue JSON 含 tenant_id   ✅ 但 dispatch 不读
        │
        ▼
调度 tick / 模板 /run / AI 试采
  └─ SpiderService.enqueue 无 tenant_id 参数
  └─ schedule.tenant_id、template.tenant_id、plan.tenant_id 均未下传
        │
        ▼
dispatch → start_urls 载荷 {url, task_id, flow|selectors}
  └─ 无 tenant_id                     ✅ Scrapy 租户盲（B2 该如此）
        │
        ▼
StorePipeline → item_queue
  └─ 无 tenant_id                     ✅ 同上
        │
        ▼
_flush_batch / _ingest
  └─ SpiderResult.tenant_id = msg.get("tenant_id")  → 恒 None
  └─ 不回查 spider_tasks.tenant_id    ❌ 结果行丢租户
  └─ check_result_storage 只对 msg.tenant_id 非空的集合执行
        → 回流配额检查永不触发
```

### 5.1 入队三处丢租户（与 backend 诊断对齐，采集侧后果）

| 入口 | 代码 | 后果 |
|------|------|------|
| `POST /spiders/run` | `tasks.py` 传 `user.tenant_id` | 任务行正确；**结果行仍 NULL**（回流丢） |
| 定时 `schedule_service._fire` | `SpiderService.enqueue` 无 tenant | 017 将 `spider_tasks.tenant_id` **NOT NULL** → MySQL 上 IntegrityError 或写非法 NULL；跳过并发配额 |
| 模板 `POST /templates/{id}/run` | Router 有 `user`，`create_task_from_template` 不传 | 同上 |
| AI 试采 `orchestrator._execute_test` | 同上门面 | 试采任务无主；FR-09 失败 |

`SpiderService.enqueue` 签名只有 `(spider_name, params, priority)`，是过渡门面把租户参数裁掉的机械原因。

### 5.2 结果行 NULL 与隔离/配额的交叉

`SpiderResult` 继承 `TenantMixin`。`tenant_scope` 读注入 `tenant_id == 当前租户`（`spider_results` **不在** `PLATFORM_SHARED_READ_TABLES`，NULL 行对租户 **不可见**）。

因此今日若回流成功写入 `tenant_id=NULL`：

- 租户打开「我的结果」：**连自己的采集成果也看不见**（FR-08 反了）。
- 市场候选对租户也看不见——**碰巧**贴近 FR-11.3，但是用「全部结果都丢租户」换来的，不是产品过滤。
- `QuotaService.check_result_storage` 按 `SpiderResult.tenant_id == T` 计数：NULL 行不占配额——**碰巧**贴近 FR-11.1，同样是事故。
- 数据中心/导出无 `source <> 'marketplace'` 过滤（ADR-0013 要求后端加）。今日靠 TenantMixin 把 NULL 藏起来，一旦回流补上租户，候选会立刻混进租户结果并占满存储（architect R-K）。

### 5.3 017 NOT NULL vs ADR-0013 NULL（采集回流会撞墙）

| 事实源 | `spider_results.tenant_id` |
|--------|---------------------------|
| 迁移 017 | 回填 default 租户后 **NOT NULL**（仅 `llm_providers` 可空） |
| ORM `TenantMixin` | 可空，注释写「NULL=平台级」 |
| ADR-0013 | 平台入站候选 **必须 NULL**，不挂触发者企业 |
| consumer 今日 | 写入 `None` |

SQLite/`create_all` 测试跟 ORM 走（可空），所以 `test_skill_candidates` 能插无 tenant 的行。**MySQL 017 之后，回流 `tenant_id=None` 会 IntegrityError**——item 进死循环/刷日志，任务卡 running。这是采集闭环在租户化环境的致命缝，dba 必须在「平台候选 NULL」和「017 NOT NULL」之间二选一放行；采集帽不能自己改列。

### 5.4 采集侧正确切法（给塑形，不在本帽实现）

Scrapy **不要**携带 `tenant_id`（保持 B2 / 租户盲）。

1. **ingest 回查** `spider_tasks.tenant_id` 写入结果行（A 路径：租户成果可见、计入配额）。
2. **harvester 任务**按 ADR-0013 以平台入站创建（不把候选挂在企业）；结果 `source=marketplace` 且租户列按 dba 放行的平台语义（NULL 或平台租户）。
3. **配额 COUNT 与租户列表**排除 `source=marketplace`（backend，ADR-0013；采集不改出口）。
4. 调度/模板/AI 入队补 `tenant_id`（backend；采集消费侧才能回查到值）。

禁止：在 Item 上加 `tenant_id`、禁止爬虫读 JWT、禁止 harvester 直写主库。

---

## 6. skill_harvester vs Power Market 源注册表（核心混淆）

设计原文（`/Users/xuyun/Documents/grok-files/power-market-design.md`）：

- §1 mermaid：Sources 含 `crawl skill_harvester`；适配器 `A4 crawl → candidates`。
- §4.4 crawl：候选仍经 Redis，不写主库技能表；转正 `source_type=marketplace_crawled`，`listing_state=unlisted`。
- Source 定义：已登记的外部树（`local_dir|git|kimi_home`），平台索引、**不 copy 进 git**。`url` 类型一期 POST 422。
- D16：`POWER_MARKET.ENABLED=false` 时 `scan_plugins` 回退扫 `LIBRARY_ROOT/plugins`，**不**注册名为 `library_plugins` 的源行。
- D5：`scan_library` 的 missing/写回 **只处理第一方**。

ADR-0013 冻结运输：Wave 0/1 候选仍住 `spider_results`；**不改 harvester 出口**。

### 6.1 今日四件事被叫成「市场」

| 动作 | 实际 | 容易被当成 |
|------|------|------------|
| `POST /api/v1/skills/scan` | 扫 `capability-library/skills/*`，upsert `skills`，默认 `self_built` | 「从市场拉新技能」 |
| `POST /api/v1/capabilities/scan-plugins` | 扫 `capability-library/plugins/` 的 **symlink 目录**（现几乎只有 `sdlc-workflow`） | 「同步 Power Market 源」 |
| 跑 `skill_harvester` 任务 | 爬 GitHub 公开目录名 → `spider_results.source=marketplace` | 「索引 zcode/kimi 插件」 |
| 候选「转正」 | `import_url` **vendor 进库内 skills/** | 「Source 同步」 |

CONTEXT.md：「候选 = 市场采集产出，人工闸门后转正式资产。」运输没写错；**没把候选与 Source 索引拆开**。管理端候选 Tab 文案已写死 harvester（`frontend/admin/src/pages/SkillsCandidates.tsx`）。

### 6.2 若把 harvester 当 Power Market 入站

会得到：没有 `origin_ref` / `source_id` / 文件集 hash、没有 D3b 折叠、没有 `kimi.plugin.json`、转正后 `self_built` + 磁盘副本 → 与 D1/D5 冲突。

### 6.3 若把 scan_plugins 当采集

`scan_plugins` 是**本机文件系统索引**，不经 Redis，不经 Item，不是爬虫。它解决不了「公网 skill 清单」；harvester 也解决不了「本机 ~/.zcode 六插件」。

**采集角色边界（给 PM/architect 的事实，不是产品 FR）：**

- **B 路径（crawl）**：继续只产 `spider_results.source=marketplace`（ADR-0013）。补反爬/site 段/token 配置位/403 当 block；Item extra 上提是 consumer 映射，不是改出口。转正身份必须是 `marketplace_crawled`，**不要**再走 vendor 落盘。
- **C 路径（Source）**：`zcode_local` / `kimi_home` / `git` 用适配器，禁止新开 Scrapy spider 去「爬」`file://` 或 `~/.zcode`。
- **A 路径（智能采集）**：generic/flow 需要**源级**反爬与质量，以及租户回查；不要再堆演示站。

---

## 7. 与 spec / 宪法对齐

| 条目 | 采集侧状态 |
|------|------------|
| FR-08 租户只见本租户任务/结果 | 任务行：仅 `/run` 正确；结果行：回流丢租户 → Mixin 下租户什么都看不见 |
| FR-09 定时/模板/AI 试采属本租户并计配额 | 三处入队不传 tenant；并发配额跳过 |
| FR-11 候选不计配额、不进「我的结果」 | 今日靠 NULL 事故近似满足；ADR-0013 要求显式 `source <> marketplace`；017 NOT NULL 会让平台候选写不进去 |
| FR-70 链接→可导出 | 引擎在；Worker 不在 compose；无工人仍入队 |
| FR-71 无工人要拦住 | 入队不读心跳 |
| FR-72 试采质量 | 公式污染内部字段；试采任务无租户 |
| R3/R4/B2 爬虫不写主库、不 import backend | **成立** |
| R5/R6 delay + UA | 字符串存在；prod delay 0.5 与站点级未接到 generic/flow |
| 反爬是生存底线 / 尊重 robots | 默认 `ROBOTSTXT_OBEY=false` |
| 配置即代码 | delay/密钥走 Dynaconf；webhook 默认 `change-me-in-production`；openweather 占位符拒绝（好） |
| 数据质量先于数量 | 质量分被内部字段稀释；0 条不收尾 |

本帽 **拒绝**：写 ETL、写候选新表、写 Source 适配器、写商店 API、新建 spider。

---

## 8. 按 skill 自检

**Crawl strategy**

- [x] 源类型已识别：HTML（generic/flow/桩）、JSON API（openweather/harvester contents）、Markdown 清单（awesome）；**本机树不是爬取源**
- [x] 范围：generic 单页；flow 翻页+详情；harvester 单次 contents/README，无分页
- [ ] robots/ToS：默认不遵守；GitHub API 限额未配置
- [ ] 反爬级别：全局 1–2 档；prod 把 delay 削到 0.5；高风控站未升级

**Spider implementation**

- [x] 全局 DOWNLOAD_DELAY（R5 字符串存在）
- [x] UA 中间件存在（R6）；池不合格
- [x] Retry+429 backoff；无 403；内置 Retry 可能叠加
- [ ] Item 校验：url 硬，其余软；评分公式污染内部字段
- [ ] content_hash：有，默认不启用增量；回流无租户时跨租户去重关闭
- [x] 数据经 Redis，不直写主库
- [x] 不 import backend（B2）
- [ ] 租户：Scrapy 盲是对的；consumer 未回查任务租户

**Monitoring**

- [ ] 连续 3 次 0 条告警：**无**；0 条还不收尾
- [ ] 成功率 / 耗时 / 封禁类型：**无**
- [x] 连续失败 / 结果下降 / 超时：规则类型有，依赖任务真正终态
- [ ] Worker 在线：心跳有写入，入队/UI 不消费（FR-71）

---

## 9. 采集侧优先修补清单（不含实现）

按「不修则支柱假 / 租户隔离假 / 市场候选不可用」排序。标注波次与负责帽。

| # | 项 | 波 | 帽 |
|---|----|----|----|
| 1 | **ingest 回查 `spider_tasks.tenant_id` 写结果行**；Scrapy 继续租户盲 | Wave 0 | backend + 采集合同 |
| 2 | 调度 / 模板 / AI 试采入队补 `tenant_id`（门面签名） | Wave 0 | backend |
| 3 | dba：`spider_results.tenant_id` 017 NOT NULL vs ADR-0013 平台 NULL | Wave 0 | dba（阻塞 1） |
| 4 | 配额 COUNT 与租户结果/导出排除 `source=marketplace` | Wave 0 | backend（ADR-0013） |
| 5 | **IdleAutoClose 零条目也要收尾**；prod 终态策略与 webhook 对齐，避免靠 6h stale | Wave 4 可提前 | 采集 + ops |
| 6 | **0-item × 3 告警**（按 spider_name，不依赖 failed） | Wave 4 / 观测 | 采集 + sre |
| 7 | 入队或提交前读 Worker 心跳，无节点则拒绝/明示（FR-71） | Wave 4 | backend + 采集 |
| 8 | harvester：site 段 delay、token **配置位**（密钥不进库）、403/限流当 block；**不改出口** | 不挡 Wave 0 | 采集 |
| 9 | consumer 上提 `item.extra` dict（扁平 kind/repo）；测试改走真管道 | Wave 0 顺手 | backend |
| 10 | generic/flow 接入站点级 delay（或源级策略表）；任务参数不得覆盖 delay | Wave 4 | 采集 |
| 11 | 质量分只算业务字段；`generic.parse` 不要 raise DropItem | Wave 4 | 采集 |
| 12 | yml / settings.py / DB 三清单对齐（harvester 进 spiders.yml 或「DB 为唯一清单」）；yml 去掉 RedisPipeline:100 | 卫生 | 采集 + 配置 |
| 13 | 演示桩（zhihu/dianping）标 fixture，不算支柱覆盖 | Wave 4 叙事 | pm + 采集 |
| 14 | 转正停止 vendor、`source_type=marketplace_crawled` | Wave 1 | 市场/backend；采集不改出口 |
| 15 | Source 适配器不是 spider；禁止 `file://` 爬 `~/.zcode` | Wave 1 | architect；采集拒绝接活 |

prod `DOWNLOAD_DELAY: 0.5` 应在配置评审里改回 ≥1 或按站点覆盖，不要当「性能优化」留下。

---

## 10. 引用文件

- `/Users/xuyun/Documents/grok-files/power-market-design.md` — Source vs crawl、§4.4、D1/D5/D16
- `.sdlc/feat-four-pillars/01-define/spec.md` — FR-08/09/11、FR-70…72
- `.sdlc/feat-four-pillars/02-shape/adr-0013-candidate-ownership.md` — 候选仍住结果表；不改 harvester 出口
- `CONTEXT.md` — 候选定义
- `README.md` — 采集闭环、反爬中间件清单
- `scrapy/settings.py` · `scrapy/spiders/*.py` · `scrapy/middlewares/__init__.py` · `scrapy/pipelines/*.py` · `scrapy/extensions/__init__.py` · `scrapy/items/__init__.py`
- `config/scrapy/default/{settings,sites}.yml` · `config/scrapy/local/settings.yml` · `config/default/{spiders,settings,skills,webhook}.yml` · `config/prod/settings.yml`
- `platform_core/queues.py` · `platform_core/models/{spider_result,spider_task,skill}.py` · `platform_core/tenant_context.py`
- `backend/tasks/consumer.py` · `backend/services/{spider_task_service,spider_service,schedule_service,skill_service,quota_service,alert_service}.py` · `backend/services/ai_planner/orchestrator.py`
- `backend/app/api/v1/spiders/tasks.py` · `templates.py` · `backend/app/tenant_isolation.py`
- `backend/alembic/versions/{005,007,016,017}_*.py`
- `.claude/rules/project_rule.md` — R5/R6/B2
- `sdlc.config.yaml` · `.sdlc/feat-four-pillars/state.yaml`

---

## 11. open_questions

1. 智能采集支柱的「源」是运营登记的站点目录，还是继续纯 generic URL 袋？没有源目录就无法做 per-site 反爬与新鲜度。（Wave 4；Q-VOICE 未关前不要把采集当对外第一句）
2. `skill_harvester` 一期白名单仓库是哪几个（anthropics/skills？awesome-claude-skills？）？无白名单则 GitHub 60 次/小时会先被打满。
3. `spider_results.tenant_id`：维持 017 NOT NULL（平台候选挂平台/default 租户 + 列表过滤 marketplace），还是按 ADR-0013 放回可空？**采集回流卡在这个决策上。** → dba
4. Worker 部署语义：prod 是否应 `SPIDER_IDLE_CLOSE_SECONDS>0` + 重生，还是常驻不关、改用「start_urls 队列空 + 本任务无 inflight」作为任务 finished 信号？
5. GitHub 采集是否配置 token（配置项，不是密钥进仓库）？无 token 则市场候选不能当支柱 SLA。
6. `baidu_hot` / `weibo_hot` 是废弃配置还是待建源？热搜 Item 是否还要保留。
7. 连续 3 次 0 条的判定窗口：按任务、按日历天、还是按调度 plan？告警通道复用现有 `AlertRule` 还是独立采集健康信号。
8. crawl 适配器是否需要采 **插件包**（plugin.json），还是技能清单足够？前者与 C 路径对象重叠，必须划边界。设计 A4 已是「候选」窄口——若要插件包，应走 C 而不是加 spider。
9. 入队无 Worker 时：产品要硬拒绝（FR-71）还是允许排队？采集侧心跳键已在，缺的是消费点。
10. 候选 Tab `require_login` 是否应升为平台超管？租户看见平台候选正文与 FR-11.3 冲突。（守卫是 backend；采集只指出数据会漏）
