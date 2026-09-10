# 数据采集诊断（data-collector）· feat-four-pillars-v2

| 字段 | 值 |
|------|----|
| 角色 | data-collector（采集 / 反爬 / 源接入；不写主库、不写产品 FR、本波不新建爬虫、**不改** `scrapy/` 代码） |
| 特征 | `feat-four-pillars-v2` · 定义帽并行诊断 |
| 日期 | 2026-09-08 |
| 对照 | 旧 `.sdlc/feat-four-pillars/01-define/diagnosis/data-collector.md`（2026-09-07）· 方案书 `/Users/xuyun/Documents/grok-files/four-pillars-plan.md` v2.1 · ADR-0013 v2 accepted · 度量蓝图 WACT |
| 约束 | 采集出口只经 Redis；B2：`scrapy/` 禁止 import `backend/`；harvester **不改出口**；C 路径（本机/git 源）**不是爬虫** |

**一句话**：采集柱现在 **不能真出数**。任务/AI 向导/结果/CSV 控制面在，Redis 闭环骨架在，本机另开 Worker 对 httpbin/`example` 能刮到 Item——但租户路径上结果回流 `tenant_id=None`（MySQL 017 会 IntegrityError；SQLite 写下后 Mixin 把行藏起来），根 compose / `run.py all` 没有 Worker，零条目永不收尾。旧方案把「第一次出数」丢进 Wave 4 stub，与北极星「completed ∧ result_count>0」矛盾。全新方案必须把 **最小出数环做成实现波**，不能再 stub。

本文件是诊断，不是现行合同。旧票 T-05/T-07/T-10 只作裂缝清单输入。

---

## 0. 相对旧诊断 / 旧方案：什么没变、什么已决、什么漏票

2026-09-08 对 `scrapy/`、`backend/tasks/consumer.py`、入队三门面逐跳复核：**采集裂缝代码面与 09-07 诊断一致，一夜未修。**

| 对象 | 状态 | 对 v2 的含义 |
|------|------|----------------|
| Redis 闭环 + B2（爬虫不写主库、不 import backend） | **仍成立** | 新方案不要拆这条边界 |
| `SpiderService.enqueue` 不转发 `tenant_id` | **仍在** `spider_service.py:78-79` | 调度/模板/AI 试采仍产无主任务 |
| consumer 回流 `tenant_id=msg.get("tenant_id")` | **仍在** `_flush_batch`；StorePipeline 消息体无此字段 | **即使 T-05 修完入队，结果行仍是 NULL** |
| IdleAutoClose 零条目直接 return | **仍在** `extensions/__init__.py` | 选择器失效/403/限流 → 任务卡 running |
| 根 `docker-compose.yml` 无 scrapy | **仍无** | 「compose up 全栈」采集永远 pending |
| ADR-0013 v2（accepted） | 旧诊断 Q3「017 NOT NULL vs 平台 NULL」**已由塑形拍板**：禁止 NULL、占位租户 + `source` 过滤 | **不要把 Q3 再打开**。旧 data-collector 那条 open_question 作废 |
| 旧票 T-05 / T-07 | 叙事写了「结果 tenant_id NOT NULL」，**文件清单没有 `consumer.py`** | 全新方案必须单列「ingest 回查任务租户」票，否则 Wave 0 修完租户仍看不见自己的条 |
| 旧方案 Wave 4 stub（FR-70…72） | 明确「本方案不拆实现票」；sre 的 Worker 编排「不在本程序实现票」 | 与度量蓝图北极星（WACT = 完成且条数>0）互斥。v2 **不得原样复制这段 stub** |
| `POWER_MARKET` 全库 0 命中 | **仍 0** | C 路径适配器仍不存在；禁止用新 spider 去爬 `~/.zcode` |

---

## 1. 判定：现在能不能真出数

「真出数」采用产品口径（旧 spec FR-70 + 度量蓝图）：**租户经办提交 URL → Worker 真采 → 结果带该租户落库 → 本租户能看见并能导出 CSV/JSON → 任务 completed 且 result_count>0。** 市场候选不算。

### 1.1 结论

| 场景 | 能出数？ | 说明 |
|------|----------|------|
| 产品柱（租户自助、compose 联调、MySQL） | **否** | Worker 不在编排；回流无租户；真库 NOT NULL 会拒写；租户列表靠 Mixin 过滤 NULL → 自己的成果也看不见 |
| 实验室（本机另开 `run_spider.py`、Redis、对 httpbin/`example`、SQLite 测试库） | **有条件的 Item** | 能刮到条目并 rpush `spider:item_queue`；local `SPIDER_IDLE_CLOSE_SECONDS=30` 且 **本轮有产出** 才会 webhook 收尾。结果行仍无租户 |
| 知乎 / 点评 / 热搜当支柱样本 | **否** | 桩或无 spider |
| 市场候选当商店供给 | **否** | 只产 GitHub 目录名；extra 嵌套导致候选 Tab `kind`/`repo` 空；无 token 易 0 条 |
| 本机插件树 / Kimi / git（Power Market Source） | **不是采集问题** | 适配器未落地；采集帽拒绝接活 |

**控制面超前于执行面**：后台能建任务、看节点页（心跳只读）、导 CSV 格式。执行面缺工人、缺终态、缺租户回流。用户看见「正在采集」时，常见真相是 pending 无人消费，或 running 且 0 条直到 6h stale。

### 1.2 实验室最短成功路径（仅证明引擎，不是支柱）

1. Redis + MySQL/SQLite + `run_backend.py` + **另开** `uv run python run_spider.py`（无 `--spider` 才加载全部，含 `generic`/`flow_generic`）。
2. `POST /api/v1/spiders/run`（此路径会传 `user.tenant_id` 到**任务行**）。
3. Worker 消费 `{spider}:start_urls` → Item → `spider:item_queue`。
4. 到此 Item 在 Redis。落库时 `_flush_batch` 写 `tenant_id=None`。
5. **MySQL 017**：INSERT 失败。**SQLite `create_all`**：写入成功，租户打开「我的结果」仍为空（`spider_results` 不在 `PLATFORM_SHARED_READ_TABLES`，NULL 行对租户不可见）。

所以「引擎能刮」≠「柱能出数」。

---

## 2. 三条入站路径（不要写错数据流）

口语都叫「扫描 / 采集 / 市场」，代码是三条互不相交的路径：

| 路径 | 真相源 | 执行者 | 出口 | 今日 |
|------|--------|--------|------|------|
| **A. 智能采集支柱** | 任务 `params.urls`（任意 HTML/API） | Scrapy Worker | Redis `spider:item_queue` → `spider_results` | `generic` / `flow_generic` + 演示爬虫 |
| **B. 市场候选采集** | 公开 GitHub 清单 | `skill_harvester` | 同上，`source=marketplace` → 候选 Tab | 唯一市场爬虫；出口应保持 |
| **C. 本机/git 源索引** | `~/.zcode/local-plugins`、Kimi、git clone | **适配器扫盘，不是爬虫** | `capability_sources` + `capability_assets`（设计稿） | `POWER_MARKET` 0 命中；`scan_library` / `scan-plugins` 不是 crawl |

Power Market 设计 §4.4：A4 crawl → candidates；Source 是已登记外部树。**把 B 当成 C、或把 C 交给 Scrapy，都会写错数据流。**

CONTEXT.md：候选 = 市场采集产出、人工闸门后转正式资产。运输没写错；没把候选与 Source 索引拆开。

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

红线抽查成立：`scrapy/` 无 `from backend` / `sqlalchemy`；StorePipeline 只 `rpush` Redis。

---

## 3. 数据源与爬虫覆盖（复核）

### 3.1 磁盘爬虫 vs yml vs DB（三套清单仍对不齐）

`scrapy/spiders/`（`run_spider.py --list` 能加载）：

| spider | 基类 | 源类型 | 实际能力 |
|--------|------|--------|----------|
| `example` | `TaskAwareRedisSpider` | JSON/HTML 嗅探 | 演示；`allowed_domains` 钉死 httpbin/example.com |
| `openweather` | 同上 | JSON API | 可用；密钥走 `sites.yml`，占位符拒绝；入库 URL 剥 `appid` |
| `zhihu_feed` | 同上 | HTML | **桩**：`div.Card` 过时；`login_required` 只 warning |
| `dianping_home` | 同上 | HTML | **桩**：只取 `title`；注释写明字体加密未处理 |
| `generic` | `RedisSpider`（**未**继承基类） | 配置化 CSS/XPath/regex | 智能采集主路径；无站点级 delay |
| `flow_generic` | 同上 | 列表/翻页/详情/过滤 | 智能采集进阶 + AI 规划出口 |
| `skill_harvester` | `TaskAwareRedisSpider` | GitHub contents JSON + awesome README | **唯一市场爬虫** |

`config/default/spiders.yml` `SPIDERS`：example / openweather / dianping_home / zhihu_feed / generic / flow_generic。**没有 `skill_harvester`。**

DB 种子：`005` 前 5 个；`007` 补 `flow_generic`；`016` 补 `skill_harvester`（`type=api`）。注册表「DB 优先、yml 兜底」——新环境若只读 yml，harvester 从任务弹窗消失。

`config/scrapy/default/sites.yml`：`baidu_hot` / `weibo_hot` **无 spider**（`HotSearchItem` 孤儿）；GitHub / skill 市场 **无 site 段**；openweather 占位密钥拒绝（好）。

### 3.2 A 路径：有引擎，没有「源」，也没有工人闸

- 通用引擎在：`generic` + `flow_generic`（翻页 cap 100）。`flow_generic` 列表空字段不 yield；详情空字段 `raise DropItem`。`generic.parse` 空提取同样 `raise DropItem`（应在管道 Raise，现在更像 spider error）。
- 目标是一次性 URL 袋，没有「值得长期采的源」注册（领域、robots、延迟、代理、JS、新鲜度）。
- `generic`/`flow_generic` 无 `allowed_domains`，且 **不读** `sites.yml` 的 `download_delay`（基类 `from_crawler` 只挂在 `TaskAwareRedisSpider`）。
- `spider_task_service.enqueue` 不读 `spider:worker:{id}`。节点页只读心跳。FR-71「没有在线节点则拦住」今日不存在。
- `--spider generic` 单进程：dispatch 把含流程段的任务改名为 `flow_generic` 再投递 → 该 Worker 永不消费 → 卡 running。

### 3.3 B 路径：GitHub 目录名，不是技能正文，更不是插件包

`skill_harvester.parse` 行为未变：

- `api.github.com/.../contents` → **仅 `type=dir`**，`title=目录名`，`content=""`，`source=marketplace`。
- raw README → 正则 `- [title](github-url) — desc`，非 GitHub 链接丢弃。
- **不拉 SKILL.md、不解析 frontmatter、不识别 `plugin.json` / `kimi.plugin.json`、不递归、无 contents 分页、无 `Accept: application/vnd.github+json`、无 token。**

这喂不饱商店面（设计要的是 ZCode 树 / Kimi 包 / `content_hash` 折叠）。A4 窄口「公开仓库目录名候选」可以保留，**不是 C 的替代**。

测试 `backend/tests/test_skill_harvester.py` 只覆盖离线 Response；`test_spider_contract` 仍是 `"backend" not in []` 空占位。

### 3.4 C 路径：禁止做成爬虫

`zcode_local` / `kimi_home` / `git` 用适配器。禁止 `file://` 爬 `~/.zcode`。今日也没有 `config/default/power_market.yml`。

`POST /skills/scan` 与 `POST /capabilities/scan-plugins` 是本机扫盘，不经 Redis，不是采集柱。

### 3.5 覆盖缺口（采集视角）

1. 热搜两个 site 无 spider。
2. 知乎 / 点评高风控演示未落地 → 当支柱样本会持续 0 有效字段。
3. 市场源只有 GitHub；无 Claude/OpenAI 目录稳定契约、无 npm/MCP registry。
4. DrissionPage / Selenium 在 `scrapy/pyproject.toml`，**无中间件、无 spider 引用**。Playwright 中间件默认关，且 **不在 spider 包依赖**（未装 → `NotConfigured`）。`generic` 无 `render_js` 路径；仅 `flow_generic` 透传。

---

## 4. Item 质量

`BaseItem`：`url/title/content/source/extra/_quality_score` + 归属 `task_id`。**无 `tenant_id`——这是对的**（Scrapy 租户盲）。

管道：Clean(200) → Validate(300) → QualityCheck(350) → Store(400)。`scrapy_redis.RedisPipeline` 在 `settings.py` 显式 `None`。**yml 仍登记 `RedisPipeline: 100`**（复发口：改 yml 不等于改 Worker）。

质量分：完整率 = **已声明字段**非空比例 × 50。内部字段 `id/created_at/updated_at/task_id/_quality_score` 几乎永远空 → 天花板远低于 50。harvester 目录候选 `content` 恒空 → 核心率 2/3。去重只在 **单进程内存** `_seen`。algo/FR-72 用 ≥40 当「抽对」代理：公式被污染后试采线不可信。

Validate：无 `url` 丢弃；无 `title` 仅 warning。

### 4.1 市场候选 `extra` 嵌套丢失（生产与测试不一致）

harvester 写 `item["extra"] = {"repo", "kind"}`。consumer 把未映射键整包进 `spider_results.extra`：

```json
{"extra": {"repo": "anthropics/skills", "kind": "github_dir"}}
```

`list_candidates` 读 **顶层** `kind` / `repo`。真采集路径上候选 Tab 类型/仓库为空。测试种子是扁平 JSON（`test_skill_candidates.py`），测不到该洞。

修法：**consumer 把 `item["extra"]` 为 dict 时上提合并**。不是改 harvester 出口，也不是新状态键（ADR-0013 冻结 extra 协议，`review` 已占用）。

### 4.2 转正身份被洗成第一方（采集运输之外，但会污染 B）

`approve_candidate` → `import_url` copy 进 `capability-library/skills/<name>/`，`_upsert_from_dir` 写死 `source_type="self_built"`。违反 D1/D7。采集帽 **不改出口**；新方案市场侧必须停 vendor、改为 `marketplace_crawled`。

### 4.3 候选查询与增量去重

`list_candidates` 全表 `source=marketplace` 再内存滤 `extra.review` 再切片。无 SQL 分页。ADR-0013 已要求平台态 SQL 分页。

管道指纹：url|title md5，无租户。落库：`md5(url+title+content)`，`incremental=true` 才跳过。批路径 `find_by_content_hash(..., tenant_id=msg.get("tenant_id"))` —— 消息无租户则跨租户去重关闭。单条 `_ingest` 甚至不传租户。

---

## 5. 反爬（生存底线）

对照 skill：delay、UA 轮换、retry+backoff、robots、按成本升级、连续 3 次 0 条告警。

### 5.1 机械检查能过（R5/R6 只 grep 字符串）

| 能力 | 位置 | 评价 |
|------|------|------|
| `DOWNLOAD_DELAY` + `RANDOMIZE_DOWNLOAD_DELAY` | `scrapy/settings.py` 读 Dynaconf | 默认 1s；**`config/prod/settings.yml` 写成 0.5**——生产比默认更激进。`config/scrapy/prod/settings.yml` 是空文件 |
| UA 轮换 4 条 Chrome/Safari 120 | `UserAgentMiddleware` | 池小、版本冻结；`fixed_ua` 改用全局 UA |
| Retry 3 次；429 抬槽位 delay | 自研 `RetryMiddleware` | 覆盖 429/5xx；**不含 403、不含 408**（yml 的 `RETRY_HTTP_CODES` 含 408，自研中间件不读这份列表） |
| 代理评分加权 | `ProxyMiddleware` | **默认 `PROXY_ENABLED=false`** |
| Playwright | `playwright_dm.py` | `PLAYWRIGHT.ENABLED=false`；包依赖未列入 |
| 任务暂停/终止 | `TaskControlMiddleware` | Redis 控制键，B2 合规 |

`check-arch.sh` R5/R6 不检查 per-spider delay、AUTOTHROTTLE、robots、prod 把 delay 改小。

### 5.2 空洞

1. **`ROBOTSTXT_OBEY: false`**（`config/scrapy/default/settings.yml`）。Skill 要求尊重 robots。
2. **无 AUTOTHROTTLE**。`CONCURRENT_REQUESTS=32`（prod 16）、`PER_DOMAIN=16` + delay 1s/0.5s，对 GitHub/知乎等于催封。
3. **账号会话未接线**。`AccountSessionMiddleware` 依赖 `request.meta.account_id`；全仓无 spider 设置。`SessionManager` 死代码。zhihu/dianping/weibo 配置是空头支票。
4. **指纹中间件不是指纹**。URL md5 写 meta，无 TLS/JA3、无 Client Hints。
5. **CAPTCHA / 滑块：无。** Wave 4 明确不承诺登录墙——不要当卖点；高风控演示站也不该算覆盖。
6. **配置双份**：yml 仍 `RedisPipeline: 100`，middleware 列表缺 TaskControl / Playwright。真正生效的是 `scrapy/settings.py`（`SCRAPY_SETTINGS_MODULE=settings`）。
7. **内置 RetryMiddleware 未禁用**。自研 Retry 也在 550，可能叠加重试。
8. **GitHub 市场采集无 token、无 API version、无 403 重试。** 未认证 REST ≈ 60 次/小时。被拒后 HttpError 丢弃 → 0 item。
9. **`skill_harvester` 无 site 段**，无法单独把 delay 提到 2–5s。

反爬升级阶梯今日停在 1–2，且 2 的 UA 池不合格、prod 还把 1 档 delay 削半；3–6 有插座、无电流。

**对「真出数」的含义**：实验室 httpbin 不需要 L3。对外卖「任意站智能采集」需要源级策略。新方案 Wave 0 **不要**把代理/Playwright/验证码当交付；**要**把 prod delay 从 0.5 改回 ≥1（配置卫生，采集+ops）。

---

## 6. Redis 队列 vs 终态（出数的执行骨架）

### 6.1 闭环设计（B2 成立）

`platform_core/queues.py`：

1. Backend `enqueue` → `spider:task_queue:{high,normal,low}`
2. `_dispatch`：pending→running，`rpush <spider>:start_urls`（JSON：`url` + `task_id` + flow|selectors；**无 tenant_id，该如此**）
3. StorePipeline → `spider:item_queue`（**无 tenant_id，该如此**）
4. `_ingest_loop` 批量落 `spider_results` + `result_count`
5. 爬虫关闭 → HMAC webhook → completed/failed

Scrapy **不写 MySQL**。死信：`spider:item_dead`。推送连续失败 5 条 `CloseSpider("redis_push_failed")`。

StorePipeline 消息形状：

```json
{"task_id": 123, "spider_name": "generic", "item_type": "BaseItem",
 "item": {...}, "fetched_at": "ISO-8601"}
```

### 6.2 终态依赖 idle-close，默认关；零条目永不关

| 配置 | 值 | 效果 |
|------|----|------|
| `config/scrapy/default/settings.yml` `SPIDER_IDLE_CLOSE_SECONDS` | **0** | `IdleAutoClose.from_crawler` **不注册信号** |
| `config/scrapy/local/settings.yml` | 30 | 本地有产出后 30s 收尾 → webhook → `run_spider.py` 重生 |
| `TASKS.STALE_TASK_HOURS` | 6 | 孤儿 running 回收 |

默认 / prod（prod scrapy yml 为空）Worker 常驻、**从不因空闲关闭** → webhook 不触发 → 任务一直 `running`，只靠 6 小时回收。README「空闲收尾完成闭环」**只在 local 且有 Item 为真**。

`IdleAutoClose.spider_idle`：`_has_items` 为假时 **直接 return**。零条目任务永远不 finished。这直接打死 FR-70/71：屏上「正在采集」，其实 0 条且不会收尾。

### 6.3 零条目 ≠ failed；skill 红线告警不存在

`AlertService`：`consecutive_failures` 看 status=failed；`result_drop` 相对上次 completed；`task_timeout` 依赖终态。**没有「连续 3 次 0 item」规则。** 无 403/验证码/空 body 分类。

### 6.4 其它队列问题

- 同爬虫并发上限 2；多 task 时 webhook `item_count=None`。
- pause：`IgnoreRequest` 跳过当前请求，start_urls 可能被吞且不重新入队。
- `_reenqueue` JSON **丢掉 `tenant_id`**（即便入队时写过）。dispatch 本来也不读它，字段漂移会让「消息里有租户」的假设更假。
- 消费者 lifespan **不进 `platform_scope`**：跨租户回流必须 **显式**写结果行 `tenant_id`，不能指望 mixin。
- Webhook 默认 `SECRET_KEY: change-me-in-production`（记给 sre）。
- 心跳：`run_spider.py` 写、Backend 只读，合规。入队不消费。

### 6.5 Worker 不在编排

根 compose：mysql + redis + backend。无 spider。`run.py all` 只起 backend + 双前端。sre 旧诊断 T1/S1 仍真。没有 Worker，A 路径一步都走不完。

---

## 7. 租户在采集链路上的断裂（出数主缝）

今日链路（2026-09-08 逐跳）：

```
HTTP POST /spiders/run
  └─ enqueue(..., tenant_id=user.tenant_id)
        ├─ spider_tasks.tenant_id = T     ✅ 仅此路径任务行有租户
        ├─ task_queue JSON 含 tenant_id   ✅ dispatch 不读（可接受）
        ▼
调度 tick / 模板 /run / AI 试采
  └─ SpiderService.enqueue 无 tenant_id 参数
  └─ schedule / template / plan 的 tenant_id 均未下传
        → MySQL 上 spider_tasks.tenant_id NOT NULL → IntegrityError
        → 并发配额因 tenant_id is None 跳过
        ▼
dispatch → start_urls {url, task_id, flow|selectors}   ✅ 租户盲
StorePipeline → item_queue 无 tenant_id                 ✅ 租户盲
        ▼
_flush_batch
  └─ 已 load spider_tasks 行，却只用 params
  └─ SpiderResult.tenant_id = msg.get("tenant_id")  → 恒 None
  └─ 不回查 task.tenant_id                          ❌
  └─ check_result_storage 只对 msg.tenant_id 非空执行 → 回流配额永不触发
_ingest（兼容路径）create_for_task 甚至不传 tenant_id
```

### 7.1 入队三处丢租户

| 入口 | 代码 | 后果 |
|------|------|------|
| `POST /spiders/run` | `tasks.py:66` 传 `user.tenant_id` | 任务行正确；**结果行仍 NULL** |
| 定时 `schedule_service._fire` | `SpiderService.enqueue` 无 tenant | 017 后真库写任务失败或非法 NULL |
| 模板 `create_task_from_template` | 不传 | 同上 |
| AI 试采 `_execute_test` | 同上门面 | 试采无主；FR-09 / FR-72 失败 |

门面签名只有 `(spider_name, params, priority)`，是机械原因。

### 7.2 结果行 NULL 与隔离/配额交叉

`SpiderResult` 继承 `TenantMixin`。`spider_results` **不在** `PLATFORM_SHARED_READ_TABLES`。NULL 行对租户 **不可见**。

因此今日若 SQLite 写下 `tenant_id=NULL`：

- 租户「我的结果」：**连自己的采集也看不见**（FR-08 反了）。
- 市场候选对租户也看不见——**碰巧**贴近 FR-11.3，用「全部结果都丢租户」换来的。
- `check_result_storage` 按 `tenant_id == T` 计数：NULL 不占配额——碰巧贴近 FR-11.1，同样是事故。
- 数据中心/导出无 `source <> marketplace`。一旦回流补上租户，候选会立刻混进租户结果并占满存储。

真库 MySQL：回流 `None` → IntegrityError → 条目进死循环/刷日志，任务卡 running。**这是租户化环境采集闭环的致命缝。**

### 7.3 采集侧正确切法（给塑形，本帽不实现）

Scrapy **不要**携带 `tenant_id`。

1. **ingest 回查** `spider_tasks.tenant_id` 写入结果行（A 路径：可见、计配额）。`_flush_batch` 已经 load 了 task 行，差的是把 `task.tenant_id` 赋给 `SpiderResult`，而不是 `msg.get`。
2. **harvester 任务**按 ADR-0013：平台入站用 **占位租户**（dba 指定 slug），结果 `source=marketplace` 且 tenant_id NOT NULL。禁止 NULL。
3. **配额 COUNT 与租户列表/导出**排除 `source=marketplace`（backend）。
4. 调度/模板/AI 入队补 `tenant_id`；缺则 **拒绝入队**。
5. extra dict 上提（consumer）。

禁止：Item 加 `tenant_id`、爬虫读 JWT、harvester 直写主库、放宽 017。

旧票 T-07 文件清单没有 `backend/tasks/consumer.py`。**这是旧方案漏票，新方案必须补上，否则 T-05+T-07 绿了租户仍无条。**

---

## 8. skill_harvester vs Source 注册表

设计原文（`power-market-design.md` §1 / §4.4）：Sources 含 crawl；A4 crawl → candidates；转正 `source_type=marketplace_crawled`，`listing_state=unlisted`。Source 定义是已登记外部树，**不 copy 进 git**。

ADR-0013：Wave 0/1 候选仍住 `spider_results`；**不改 harvester 出口**。

今日四件事被叫成「市场」：

| 动作 | 实际 | 容易被当成 |
|------|------|------------|
| `POST /skills/scan` | 扫库内 skills，默认 `self_built` | 「从市场拉新技能」 |
| `POST /capabilities/scan-plugins` | 扫 `capability-library/plugins/` symlink | 「同步 Power Market 源」 |
| 跑 `skill_harvester` | GitHub 目录名 → `source=marketplace` | 「索引 zcode/kimi 插件」 |
| 候选「转正」 | `import_url` vendor 进库内 skills/ | 「Source 同步」 |

**采集角色边界（给 PM/architect 的事实，不是产品 FR）：**

- **B**：继续只产 `spider_results.source=marketplace`。补 site 段/token 配置位/403 当 block；extra 上提是 consumer。转正身份必须是 `marketplace_crawled`，不要再 vendor。
- **C**：适配器，禁止新开 spider。
- **A**：generic/flow 需要源级反爬与租户回查；不要再堆演示站。

---

## 9. 与旧 spec / 宪法 / 旧方案对齐（输入，非现行合同）

| 条目 | 采集侧状态（2026-09-08） |
|------|--------------------------|
| FR-08 租户只见本租户任务/结果 | 任务行：仅 `/run` 正确；结果行：回流丢租户 |
| FR-09 定时/模板/AI 属本租户 | 三处入队不传；真库可能写任务失败 |
| FR-11 候选不计配额、不进「我的结果」 | 靠 NULL 事故近似；应用 `source <> marketplace` |
| FR-70 链接→可导出 | 引擎在；Worker 不在 compose；无工人仍入队；0 条不收尾 |
| FR-71 无工人要拦住 | 入队不读心跳 |
| FR-72 试采质量 | 公式污染；试采任务无租户 |
| R3/R4/B2 | **成立** |
| R5/R6 | 字符串存在；prod delay 0.5；generic/flow 无站点 delay |
| 反爬 / robots | 默认不遵守 |
| 数据质量先于数量 | 质量分被内部字段稀释；0 条不收尾 |
| 北极星 WACT | 今日无法形成「租户可见的 completed∧>0」；旧方案把执行面 stub 掉则四周后仍报不出 |

旧方案 Wave 0 冻结：入队带租户、候选不计配额、导出诚实、出站 Key。**这些必须进新方案**，且必须补 ingest 回查。

旧方案 Wave 4 stub：第一次出数 / Worker 空态。**与「采集柱要真出数」和 WACT 冲突。** 采集帽建议：新方案把 **最小出数环**（Worker 一等公民 + 心跳闸 + 0 条收尾 + 租户可见回流）做成实现波——可独立薄波，**禁止只写 stub 边界**。代理池/JS/登录墙/模板店仍可后置。

本帽 **拒绝**：写 ETL、写候选新表、写 Source 适配器、写商店 API、新建 spider、改 harvester 出口、在 Item 上加 `tenant_id`。

---

## 10. 按 skill 自检

**Crawl strategy**

- [x] 源类型已识别：HTML（generic/flow/桩）、JSON API（openweather/harvester contents）、Markdown 清单（awesome）；**本机树不是爬取源**
- [x] 范围：generic 单页；flow 翻页+详情；harvester 单次 contents/README，无分页
- [ ] robots/ToS：默认不遵守；GitHub API 限额未配置
- [ ] 反爬级别：全局 1–2 档；prod delay 0.5；高风控站未升级

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

## 11. 必须进全新方案的裂缝（采集帽排序）

按「不修则柱假 / 租户隔离假 / 北极星不可测」排。标注建议波次（给 PM，非合同）与负责帽。

### 11.1 最小出数环 — 必须实现，禁止 stub

| # | 项 | 旧方案位置 | 新方案 |
|---|----|------------|--------|
| M1 | **ingest 回查 `spider_tasks.tenant_id` 写结果行**；Scrapy 继续租户盲 | T-07 叙事有、文件清单无 `consumer.py` | **补票**；backend。不修则 T-05 绿了租户仍无条 |
| M2 | 调度 / 模板 / AI 试采入队补 `tenant_id`；缺则拒绝 | T-05 | 保留 |
| M3 | 配额 COUNT、租户结果/数据中心/导出排除 `source=marketplace`；候选 SQL 分页 | T-07 | 保留；依赖 M1，否则过滤的是空集 |
| M4 | 平台入站 harvester 任务挂 **占位租户**（dba 指定），禁止 NULL | ADR-0013；旧诊断 Q3 已决 | **重申，不重开** |
| M5 | consumer 上提 `item.extra` dict（扁平 kind/repo）；测试走真管道 | 旧方案漏票 | **补票**；backend。不修则候选 Tab 空 |
| M6 | Worker 进入根 compose / 联调编排（或文档+脚本一等公民）；镜像能跑 spider 包 | 记风险、不拆票 | **必须进实现波**；sre + 采集 |
| M7 | 入队或提交前读 Worker 心跳；无节点则拒绝或明示，不显示「正在采集」（FR-71） | Wave 4 stub | **拉进最小出数环** |
| M8 | **IdleAutoClose 零条目也要收尾**；prod 终态策略与 webhook 对齐，避免靠 6h stale | 旧 spec 写「下一轮」 | **拉进最小出数环**；否则 result_count 永远 0 且无 completed |

M1–M5 不碰 Scrapy 管道协议。M6–M8 碰 Worker 生命周期，旧方案故意冻结——v2 若仍声称采集是支柱且北极星是出数，就不能再冻。

### 11.2 应进方案、不挡第一行可见数据

| # | 项 | 帽 |
|---|----|----|
| S1 | prod `DOWNLOAD_DELAY: 0.5` 改回 ≥1 或按站点覆盖 | 采集 + 配置 |
| S2 | generic/flow 接入站点级 delay（或源级策略表）；任务参数不得覆盖 delay | 采集 |
| S3 | 质量分只算业务字段；`generic.parse` / flow 详情不要 raise DropItem | 采集 |
| S4 | 0-item × 3 告警（按 spider_name，不依赖 failed） | 采集 + sre |
| S5 | harvester：site 段 delay、token **配置位**（密钥不进库）、403/限流当 block；**不改出口** | 采集 |
| S6 | yml / settings.py / DB 三清单对齐（harvester 进 spiders.yml 或「DB 为唯一清单」）；yml 去掉 RedisPipeline:100；禁用内置 Retry | 采集 + 配置 |
| S7 | 演示桩（zhihu/dianping）标 fixture，不算支柱覆盖 | pm + 采集 |
| S8 | 转正停止 vendor、`source_type=marketplace_crawled` | 市场/backend；采集不改出口 |
| S9 | 导出诚实（csv/json、100 条上限、拒 xlsx） | 旧 T-10；frontend + backend |
| S10 | 出站 Key 无租户绑定则拒绝 | 旧 T-16；非本帽实现 |

### 11.3 明确不要进采集柱

- Source 适配器、`file://` 爬家目录
- 新建候选表（除非产品第二次要独立生命周期）
- 登录墙 / 验证码 / 代理网对外卖点 / 站点模板商店
- 数仓 ODS
- 把 `backend/services` 一次性拆成 domains

---

## 12. 引用

- `/Users/xuyun/Documents/grok-files/power-market-design.md` — Source vs crawl、§4.4、D1/D5/D16
- `/Users/xuyun/Documents/grok-files/four-pillars-plan.md` — Wave 0 vs Wave 4 stub
- `/Users/xuyun/Documents/grok-files/feat-four-pillars-metrics.md` — WACT
- `/Users/xuyun/Documents/grok-files/feat-four-pillars-sre-diagnosis.md` — Worker 编排
- `.sdlc/feat-four-pillars/01-define/diagnosis/data-collector.md` — 旧诊断（裂缝仍在）
- `.sdlc/feat-four-pillars/02-shape/adr-0013-candidate-ownership.md` — NOT NULL + source 过滤；不改 harvester 出口
- `.sdlc/feat-four-pillars/02-shape/tickets/T-05.md` · `T-07.md` · `T-10.md`
- `.sdlc/feat-four-pillars/02-shape/contracts/quota-and-isolation.md`
- `CONTEXT.md` — 候选定义
- `.claude/rules/project_rule.md` — R5/R6/B2
- `scrapy/settings.py` · `scrapy/spiders/*.py` · `scrapy/middlewares/__init__.py` · `scrapy/pipelines/*.py` · `scrapy/extensions/__init__.py` · `scrapy/items/__init__.py`
- `config/scrapy/default/{settings,sites}.yml` · `config/scrapy/local/settings.yml` · `config/scrapy/prod/settings.yml`（空）· `config/default/spiders.yml` · `config/prod/settings.yml`
- `platform_core/queues.py` · `platform_core/models/{spider_result,spider_task}.py`
- `backend/tasks/consumer.py` · `backend/services/{spider_task_service,spider_service,schedule_service,spider_registry_service,skill_service,quota_service,alert_service}.py` · `backend/services/ai_planner/orchestrator.py`
- `backend/app/api/v1/spiders/tasks.py` · `backend/app/tenant_isolation.py`
- `backend/alembic/versions/{016,017}_*.py`
- `docker-compose.yml` · `run.py` · `run_spider.py`
- `sdlc.config.yaml` · `.sdlc/feat-four-pillars-v2/state.yaml`

---

## 13. open_questions（采集帽仍持有）

1. 智能采集支柱的「源」是运营登记的站点目录，还是继续纯 generic URL 袋？没有源目录就无法做 per-site 反爬与新鲜度。Q-VOICE 未关前不要把采集当对外第一句。
2. `skill_harvester` 一期白名单仓库是哪几个？无白名单则 GitHub 60 次/小时先被打满。
3. Worker 部署语义：prod 是否应 `SPIDER_IDLE_CLOSE_SECONDS>0` + 重生，还是常驻不关、改用「start_urls 空 + 本任务无 inflight」作为任务 finished 信号？（M8 的实现选型，dba/sre 一起定）
4. GitHub 采集是否配置 token（配置项，密钥不进仓库）？无 token 则市场候选不能当支柱 SLA。
5. `baidu_hot` / `weibo_hot` 是废弃配置还是待建源？热搜 Item 是否还要保留。
6. 连续 3 次 0 条的判定窗口：按任务、按日历天、还是按调度 plan？告警通道复用 `AlertRule` 还是独立采集健康信号。
7. crawl 适配器是否需要采 **插件包**（plugin.json），还是技能清单足够？前者与 C 重叠——若要插件包，应走 C 而不是加 spider。
8. 入队无 Worker 时：产品要硬拒绝（FR-71）还是允许排队？心跳键已在，缺消费点。采集建议硬拒绝或至少不显示「正在采集」。
9. **最小出数环（M1–M8）放在与 Wave 0 同波，还是独立薄波？** 采集帽要求：必须是实现波，不能 stub。切波由 PM。与 WACT 同波才能在四周后报出基线。
10. 占位租户 slug / 是否提供自助面：交给 dba；采集只要求回流 NOT NULL 且 marketplace 不进「我的结果」。

**不要再问：** `spider_results.tenant_id` 能否 NULL（ADR-0013 v2 已否决）；harvester 是否直写主库（否）；C 路径要不要新开 spider（否）。
