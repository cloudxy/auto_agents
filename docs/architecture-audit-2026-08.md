# 全系统架构与模块诊断报告（2026-08）

> 审计范围：backend / scrapy / platform_core / config / frontend(admin+official) / deploy / scripts / CI
> 方法：三路并行深度代码扫描 + 关键发现逐行人肉核验（P0 全部 4 条、prod 配置、前端注册调用均已亲自复核）。
> 性质：诊断报告，本文档不伴随任何代码改动；修复方案与演进设计见第 4/5 章。

---

## 1. 执行摘要

**整体判断**：这是一个治理水平较高的代码库——分层纪律（API→Service→Repository）、异常信封、Redis 异步化、分布式锁（Lua 原子释放）、LLM 密钥 Fernet 加密、SSRF 防护、配置多层合并都执行到位；**未发现已提交的真实密钥、SQL 注入、可远程利用的鉴权缺失**。

但存在系统性的**"引擎造好了、方向盘没接上"**问题：多个模块的核心逻辑完整，而配置面/消费方/收尾链路缺失，导致实际运行形态是"半成品空转"。典型如：new-api 渠道调度器每轮巡检 0 个受管渠道（配置无写入方）、站点级反爬配置无任何代码消费、LLM 用量统计只活在进程内存里。

另有 4 个 P0 级"功能已坏/安全缺口"，其中爬虫无限重试会导致任务在 DB 中永久卡 running。

**问题统计**：第一轮（架构与缺陷审计）P0 × 4｜P1 × 13｜P2 × 46；第二轮（易用性专项走查，第 6 章）新增功能级缺陷 8 项（见 3.4 节）与 22 条 UX 反模式（见 6.4 节）。

**易用性专项结论**（详见第 6/7 章）：系统主链路设计方向正确（动态表单→提交自动看日志→结果导出），但被"假分页 / 运行与模板不回填参数 / 路由级权限缺失"等功能 bug 与系统性的内部概念泄漏（手写 JSON/cron/格式串）拖累。对标 EasySpider / crawlab / spider-flow 的四阶段（U1-U4）优化方案见第 7 章。

**SaaS 化升级方向**（详见第 8 章，2026-08-31 决策）：系统升级为面向企业的多租户 SaaS——企业自助开通、租户内子账号自管理；既有四大功能模块与全部演进方案（4.1 / 4.2 / 第 7 章）保留并叠加租户维度。当前差距：users 表无租户概念，除 `ai_plan.created_by`（字符串用户名）与 `task_template.created_by`（用户 ID，类型还不一致）外**全部业务表无归属字段**。

**自动化脚本存废决策**（详见第 9 章）：保留 5（bootstrap-db.sh / check-arch.sh / migrate.sh / init_db_sync.py(内部依赖) / set_admin_account.py），删除 5（init-db.sh / init-database.sh / start.sh / start_frontend.sh / run-spider.sh，均为被 run.py 编排器或 bootstrap 收编的旧入口）。

**最优先行动**（详见第 5 章批次 1）：修 RetryMiddleware 重试上限、补 webhook 密钥启动守卫、token 用量落库、httpx `proxies=` 参数替换。

另：开发环境问题（git 连接 GitHub 失败：本地代理未启动）的诊断与解决方案见附录 10.3。

---

## 2. 系统架构现状

### 2.1 整体结构

```
auto_agents/ (uv workspace，根 .venv 唯一)
├── backend/          FastAPI（api/v1+v2 内部 + external_api/v1 外部）+ services + repositories + tasks/consumer
├── scrapy/           scrapy-redis 分布式爬虫（禁 import backend，B2 红线）
├── platform_core/    共享基建：db / redis_async / queues / repository / logger / models / schemas / exceptions
├── config/           Dynaconf：default → scrapy/default → <env> → scrapy/<env> → <env>/.env → AUTO_AGENTS_* 环境变量
├── frontend/         admin（React 19 + antd 6 + CRA）13 页面 / official（纯展示，仅 Home）
├── deploy/newapi/    外部 new-api 中转站独立编排（质量高：密钥 ${VAR:?} 强制注入）
└── scripts/          check-arch.sh（12 红线+3 边界）+ 4 套 DB 初始化脚本
```

### 2.2 智能爬虫板块数据流（核心闭环完整）

```
Backend SpiderTaskConsumer (backend/tasks/consumer.py)
  blpop 优先级任务队列 → 任务置 running + 写活跃 SET
  → rpush <spider>:start_urls
      → 爬虫（base/generic/flow_generic，TaskAwareRedisSpider 解析队列条目注入 task_id）
      → 管道：Clean → Validate → QualityCheck(0-100 评分) → Store(rpush spider:item_queue)
  → consumer 批量 lpop(20) → 增量去重 + bulk insert spider_results
       + result_count 累加 + redis/csv 镜像双写
  → 爬虫空闲收尾(IdleAutoClose) → SpiderCloseWebhook（HMAC-SHA256 签名回调）
  → backend finish_task → 终态/失败重试（ZSET 退避 1s→5s→15s）
```

架构合规良好：scrapy 无任何 `import backend`，仅通过 Redis 队列 + webhook 通信。中间件体系完整（UA 轮换 / 代理评分加权随机 / 账号会话 / 任务暂停停止控制 / Playwright 可选渲染）。

### 2.3 大模型管理模块（cc-switch 类）

定位：**多供应商注册表 + 单激活热切换**（非多路复用）。

- 表 `llm_providers`：name 唯一、`api_key_encrypted`（Fernet）、**单一 `model` 字符串**（`platform_core/models/llm_provider.py:32`）、`is_active` 全表至多一行
- `llm_provider_service.py`：CRUD、`activate_exclusive`（单语句互斥 UPDATE）、`test_connectivity`（手动触发）、`resolve_runtime_config`（激活且 enabled 优先，否则回退 `llm.yml` + env）
- 消费方 `ai_planner/llm_client.py::llm_chat`：共享 httpx client 缓存、指数退避重试、**进程内 `_TOKEN_USAGE` 预算熔断**
- 前端 `LlmProviders.tsx` 已接线

关键限制：仅 `openai_compatible` 一种协议；无模型列表；无周期巡检；active 挂掉不切换其他注册供应商。

### 2.4 new-api token 智能调度模块

定位（如实描述）：**不是 new-api 的等价替代品，而是外部独立 new-api 实例的外挂管控侧**。不做请求转发、不做 token 发放、不做渠道负载均衡、不做计费记账——所有 LLM 流量直接打 new-api 本体。

已实现三块：

1. `channel_scheduler_service.py`：渠道额度巡检（lifespan 启动）——分布式锁 → 拉 new-api 管理 API 渠道列表 → **直连 new-api 库**（独立 engine + `NEWAPI.DB_DSN`）聚合 `logs` 表窗口 quota → 超限置 status=3（auto disabled）→ 落 `channel_events` → 通知；冷却到期复核后自动恢复
2. `channel_probe_service.py`：渠道真伪探针（10 维行为指纹：身份矛盾/缓存逐字重复/相似度 <0.15 判 spoofed）
3. `newapi_overview_service.py` + `v1/newapi.py`：全只读 3 端点（overview/events/probe-results，require_admin）+ 前端 `NewApiOps.tsx`

### 2.5 集成点与官网/后台

- LLM ↔ 爬虫（唯一真实闭环）：`ai_planner/orchestrator.py`——LLM 规划生成 selectors → flow_generic 试采 → 质量评判 → 失败自动修复迭代（MAX_ITERATIONS=2）→ 注册 `spider_definitions`（source=ai_generated）
- newapi ↔ LLM 管理模块：仅文档级注释，无代码集成
- 前端：admin 13 页面（含 /ai /llm /newapi）均已接线真实 API；official 仅静态官网

---

## 3. 问题清单

> 每条 = 证据（file:line）+ 影响 + 修复方案。
> 标注 ✅ 的为本次审计中人肉逐行复核过的条目。

### 3.1 P0 —— 功能已坏 / 安全缺口（4 条）

#### P0-1 爬虫自定义 RetryMiddleware 无限重试 → 任务永久卡 running ✅

**证据**：`scrapy/middlewares/__init__.py:325-336`

```python
class RetryMiddleware:
    def process_response(self, request, response, spider):
        if response.status in [429, 500, 502, 503, 504]:
            retry_req = request.copy()
            retry_req.dont_filter = True
            if response.status == 429:
                retry_req.meta["download_delay"] = 5   # ← 自创 meta 键，Scrapy 不读
            return retry_req                            # ← 无重试次数上限
```

三个叠加缺陷：

1. 对 429/5xx **无条件重试，无任何次数上限**，也不读 `retry_times`；与内置 `scrapy.downloadermiddlewares.retry.RetryMiddleware` 同为 550 优先级且未禁用内置（`scrapy/settings.py:65`），自定义的先短路响应链，内置的计数上限永远不生效。
2. `retry_req.meta["download_delay"] = 5` 是自创 meta 键，Scrapy 下载器不消费该键（仅认 spider 属性/槽位设置）——429 风暴下仍按全局 1s 延迟全速重试。
3. 连锁后果：爬虫永不空闲 → `IdleAutoClose` 不触发 → webhook 不回调 → DB 任务**永久卡 running**。全仓无 running 任务超时回收逻辑（仅 Redis 活跃键 86400s TTL 自过期，DB 行无人纠正）。

**修复方案**：
- 读取 `request.meta.get("retry_times", 0)`，达到 `RETRY_TIMES`（建议默认 3）后放行响应并记 warning；
- 429 退避改为 `spider.download_delay` 临时调整或 `twisted` 层延迟（或直接删自定义中间件、启用内置 RetryMiddleware 并配置 `RETRY_HTTP_CODES`）；
- 兜底：consumer 增加周期扫描——`running` 超过 N 小时且 Redis 活跃键不存在的任务置 failed（可复用现有 ZSET 重试机制）；
- 补测试：真实经过下载器中间件链的集成测试（现有测试全部 mock，掩盖了此类缺陷）。

#### P0-2 Webhook 签名密钥默认值无 fail-fast → 外部回调可伪造 ✅

**证据**：`config/default/webhook.yml:6`（`SECRET_KEY: "change-me-in-production"`）+ `backend/app/external_api/v1/webhooks.py:46`（`secret = str(settings.WEBHOOK.SECRET_KEY)` 直接使用）。

防御不对称：JWT 密钥同样默认占位符，但 `backend/utils/auth.py:13-17` 在导入时强制抛错拒绝默认值；webhook 密钥没有等价防线。`config/prod/.env` 也未配置 webhook 密钥。

**影响**：漏配部署时，任何人用仓库内公开的默认密钥即可签名调用 `POST /external/v1/webhooks/spider/callback`，伪造任意 `task_id` 的 completed/failed 终态 → 篡改任务状态、触发失败重试链、钉钉/邮件通知轰炸。

**修复方案**：比照 `auth.py` 的 JWT 守卫，在应用工厂/lifespan 启动时校验 `WEBHOOK.SECRET_KEY`——非空、非占位符、长度 ≥ 32，否则拒绝启动；scrapy 侧 `SpiderCloseWebhook` 同样读取该配置，两侧同源校验。

#### P0-3 LLM token 用量纯进程内存统计 → 预算熔断形同虚设 ✅

**证据**：`backend/services/ai_planner/llm_client.py:33-35`

```python
# 进程级 token 用量累计（跨请求熔断；按 provider 维度计数，兜底路径统一记
# "config" 名下；单实例假设：多副本部署时预算无法跨进程聚合，需外部聚合方案）
_TOKEN_USAGE: dict[str, int] = {}
```

重启清零、多副本无法聚合、**整个仓库不存在 provider 维度的用量落库**。预算熔断（L175-222）在重启后从 0 重新计数；作为"token 智能调度系统"的计量基础完全缺失。

**修复方案**（与 4A 演进设计合并）：新增 `llm_token_usage` 表（按 provider/model/日聚合）+ Redis `INCRBY` 实时累计；熔断判断读聚合值，进程内存仅作读缓存。详见 4.1.4。

#### P0-4 代理健康探测使用 httpx 0.28 已删除的 `proxies=` 参数 → 代理池评分衰减到 0 ✅

**证据**：`backend/services/proxy_health_service.py:114-121`

```python
async with httpx.AsyncClient(timeout=probe_timeout) as client:
    for proxy in low_score_proxies:
        resp = await client.head(
            probe_url,
            proxies={"all://": proxy},   # ← httpx 0.28 已删除该参数
            ...
```

项目锁定 `httpx>=0.28.1`（`backend/pyproject.toml:19`）；`proxies` 参数在 httpx 0.28 中已移除（0.26 起废弃），正确写法是 `httpx.AsyncClient(proxy=proxy)` 或 `mounts=`。当前每次探测抛 `TypeError`，被 `proxy_health_service.py:134` 的 `except Exception` 吞掉并当作"探测失败"走 `_decay_score`（每轮 -0.1）。

**影响**：开启 `PROXY_HEALTH.ENABLED` 后所有低分代理被持续误判失败，评分永久衰减到 0，代理池被清空。测试未发现是因为 `test_proxy_health_service.py` mock 了 httpx，请求参数从未真实发出。

**修复方案**：改为 `httpx.AsyncClient(proxy=proxy)` 循环外构建（或 `mounts={"all://": proxy}`）；重写测试——不 mock `client.head` 签名，改为断言请求构造参数；顺带消除 P2-16 的每请求新建 Redis 连接问题。

---

### 3.2 P1 —— 重要缺陷（13 条）

#### P1-1 prod 配置键名失效 + `${}` 不展开 → 生产部署启动即失败 ✅

**证据**：`config/prod/.env:2-5`（全文仅 5 行）：

```
MYSQL_DEFAULT_PASSWORD="${PROD_MYSQL_PASSWORD}"
REDIS_DEFAULT_PASSWORD="${PROD_REDIS_PASSWORD}"
SECRET_KEY="${PROD_SECRET_KEY}"
JWT_SECRET_KEY="${PROD_JWT_SECRET_KEY}"
```

两个问题：① `JWT_SECRET_KEY` 裸键不能映射到代码读取的 `settings.JWT.SECRET_KEY`（需要 `AUTO_AGENTS_JWT__SECRET_KEY` 或 yml），而 `MYSQL_DEFAULT_PASSWORD` 恰好是 `db.py:43` 认的裸键格式——**同一文件两种口径**；② Dynaconf 的 `.env` 加载不做 `${VAR}` shell 展开，值是字面量字符串 `"${PROD_JWT_SECRET_KEY}"`。

**后果**：JWT 密钥取不到真实值 → 走到 `webhook.yml`/`jwt.yml` 默认占位符 → `auth.py:13-17` 启动即抛 ValueError（fail-fast 本身是对的，但这份配置文件是坏的）；`SECRET_KEY` 无任何消费方。

**修复方案**：统一 prod `.env` 键名为 Dynaconf 双下划线格式（`AUTO_AGENTS_JWT__SECRET_KEY=` 等）；`.env` 中删除 `${}` 插值写法（由部署脚本直接注入真实值）；补一个"配置自检"启动脚本或 `/health/config` 端点列出未生效的键。

#### P1-2 docker-compose 后端容器绑定 127.0.0.1 → 发布端口不可达

**证据**：`run_backend.py:61` 用 `settings.API.HOST`；`config/default/api.yml:5` 为 `127.0.0.1`；`config/local/` 无 api.yml 覆盖；`docker-compose.yml:40-48` 环境变量只覆盖 MySQL/Redis/JWT，不含 `AUTO_AGENTS_API__HOST` → 容器内 uvicorn 只听 loopback，宿主机 `9111:9111`（compose:39）连不通。且 Dockerfile HEALTHCHECK（`Dockerfile:48-49`）在容器内自检 127.0.0.1 通过，呈现"健康但不可访问"假象。

**修复方案**：compose 增加 `AUTO_AGENTS_API__HOST: 0.0.0.0`（保持本地裸跑仍 127.0.0.1）；或 `config/local/api.yml` 覆盖。健康检查保留容器内探测即可。

#### P1-3 前端 register 死功能：密码入 URL + body 为 null → 必然 422 ✅

**证据**：`frontend/admin/src/services/auth.ts:42-46`

```ts
export const register = (username: string, email: string, password: string) => {
  return api.post('/auth/register', null, { params: { username, email, password } })
}
```

后端 `backend/app/api/v1/auth.py:172-176` 期望 JSON body（`request: RegisterRequest`），此调用必然 422——注册功能实际从未可用。同时密码进入 URL 查询串，会被 uvicorn access_log（`run_backend.py:93` `access_log=True`）及各级代理日志记录。

**修复方案**：改为 `api.post('/auth/register', { username, email, password })`；核查 admin 前端是否有注册入口（若有则为可见死按钮）；access_log 在 prod 关闭或脱敏 query。

#### P1-4 结果链路三处静默丢数据（Redis 无 ack 语义）

**证据**：
- `scrapy/pipelines/__init__.py:92-96`：StorePipeline rpush `spider:item_queue` 失败**仅记日志**（"推送失败仅告警，不中断采集"）→ item 无重试、无死信队列，直接蒸发；
- `backend/tasks/consumer.py:416-420`：消息缺 `task_id` 直接跳过（而 StorePipeline 在多活跃任务无法归属时恰好置 None，`pipelines/__init__.py:76-79`）→ 归属失败的合法数据被丢弃；
- `backend/tasks/consumer.py:409`：批量 `lpop(count=20)` 后消息只存在于内存，进程崩溃 → 整批已出队未落库数据丢失；同理 `_dispatch`（L214-227）blpop 后崩溃 → 任务消息丢失且 DB 无对账，任务永久 pending。

**修复方案**：
- StorePipeline 失败改为本地缓冲重投（内存队列 + 周期重试），连续失败触发 spider 停止而非继续采集丢数据；
- 缺 task_id 的消息转入死信 list（`spider:item_dead`）并告警，不静默丢；
- 中期：改用 Redis Stream（XADD/XREADGROUP/XACK）获得消费 ack 语义；短期兜底：consumer 启动时对账——活跃 SET 中的 task 与 DB running 任务互相校验，孤儿任务走失败重试。

#### P1-5 openweather 爬虫双重损坏 + API Key 明文入库

**证据**：`scrapy/spiders/openweather.py`
- `:18-20` `SPIDER_SITES.get('openweather')` 未解包 Dynaconf 顶层 `sites` 命名空间（正确写法见 `middlewares/__init__.py:30` 的 `inner = sites_cfg.get("sites", sites_cfg)`）→ `api_key` 恒为空，`:23-24` 直接 return，**该爬虫永远跑不了**；
- `:22-31` 覆盖 `start_requests`，破坏 RedisSpider 的队列消费语义（scrapy-redis 的 start_requests 是无限消费循环），即使配好 key 也收不到 Backend 分发的任务；
- `:30,36` `appid={api_key}` 拼 URL 且 `item['url'] = response.url` 原样入库 → **key 明文落 `spider_results.url`**，后台用户与 external API（`public.py:40`）均可读；
- 另 `config/scrapy/default/sites.yml:20` 占位符 `YOUR_API_KEY_HERE` 入库（读取逻辑修好后占位符会被当真 key 发请求）。

**修复方案**：修 sites 解包（复用中间件的写法或抽公共函数）；删 `start_requests` 覆盖；`item['url']` 对 query 做脱敏（剥 appid 参数）或存脱敏占位；启动时校验占位符值并拒绝。

#### P1-6 new-api 渠道调度配置无写入方 → 调度器空转（受管渠道 = 0）

**证据**：`backend/services/channel_scheduler_service.py:447` 只读 `newapi:channel:cfg:{id}`；**全仓无任何 API/脚本/页面写这个 hash**（grep `NEWAPI_CHANNEL_CFG_PREFIX` 仅定义+读两处）；叠加 `config/default/newapi.yml:30` `DEFAULT_WINDOW_QUOTA: 0`（0 = 不启用全局默认），三层开关全开时受管渠道仍为 0，调度器每轮空转。运维只能 redis-cli 手工 hset。

**修复方案**：见 4.2 演进设计（渠道配置 CRUD API + admin 前端 + 引导脚本）。

#### P1-7 站点级反爬策略只接线一半（配置面无消费者）

**证据**：`config/scrapy/default/sites.yml:16-19,26,37` 为 zhihu(3s)/weibo(5s)/dianping(4s) 配置 `anti_crawl.download_delay`，但全仓无代码消费该键（grep `download_delay` 仅命中中间件自创 meta 键）→ 高风控站点实际仍用全局 `DOWNLOAD_DELAY=1`（`scrapy/settings.py:30`）。`login_required: true`（weibo/zhihu/dianping）同样无消费者；`AccountSessionMiddleware` 依赖的 `meta['account_id']` 全仓无任何 spider/中间件设置 → `utils/session_manager.py` 账号会话体系整体为死代码。

**修复方案**：在 `TaskAwareRedisSpider` 或站点中间件中消费 `anti_crawl.download_delay`（按 site 动态设置 `spider.download_delay`）；账号会话要么补齐（登录态注入 + account_id 分发）要么明确删除，避免"看起来有账号体系"的误导。

#### P1-8 scrapy_redis RedisPipeline 双写无人消费 → Redis 无限增长

**证据**：`scrapy/settings.py:76` `scrapy_redis.pipelines.RedisPipeline: 100` 把每个 item 再序列化 rpush 到 `<spider>:items` 键——无消费者、无 TTL，与 `spider:item_queue` 形成重复双写，Redis 内存随采集无限增长。

**修复方案**：`ITEM_PIPELINES` 中禁用该行（`scrapy_redis.pipelines.RedisPipeline: null`）；若未来需要再启用需配 TTL/裁剪。

#### P1-9 bcrypt 同步调用阻塞事件循环（登录/注册卡顿全服务）

**证据**：`backend/utils/auth.py:23-35`（`bcrypt.checkpw`/`bcrypt.hashpw` 同步 CPU 密集），由 `backend/services/auth_service.py:59`（authenticate）与 `:122`（register_user）在 `async def` 中直接调用。每次登录/注册期间整个事件循环停摆约 100-300ms（含后台消费者、调度器 tick、其他请求）。项目其他位置已严格遵循"同步操作下 to_thread"惯例（如 `v1/health.py:57`、`spider_task_service.py:660`），唯独 bcrypt 漏网。

**修复方案**：`await asyncio.to_thread(bcrypt.checkpw, ...)`；顺带修 P2-6 的时序枚举（用户不存在时也做一次 dummy hash，放到同一个 to_thread 里）。

#### P1-10 v2 健康检查是 v1 已修复缺陷的"活化石"

**证据**：`backend/app/api/v2/health.py`
- `:60` 与 `:84`：`"error": str(e)` 把内部异常全文（可含连接串、路径）回显客户端——v1 已收窄为 `type(e).__name__`（`v1/health.py:40`）；
- `:69-70`：`storage.create_temp(...)` + `unlink()` 在 `async def` 中直接同步文件 IO——v1 已改 `asyncio.to_thread`（`v1/health.py:57`，注释"m-3 评审修复"）；
- 端点集合不一致：v1 有 `/health/redis` 而 v2 没有；v2 的 `/health/db` 顺带 ping Redis。

**修复方案**：短期 v2 直接复用 v1 的实现（import 同一 service 函数）；或明确 v2 为弃用状态并在路由 docstring 标注。根因是复制粘贴漂移，缺少"同一资源只有一个实现"的约束。

#### P1-11 审计写入与业务事务分离 → 已成功操作变 500 / 审计可丢

**证据**：`backend/app/api/_helpers.py:20-21`——`AuditService.record()` 内部吞掉 create 异常（`audit_service.py:46-48` 只记日志），但若 flush 失败 session 已处于 PendingRollback 态，随后 `record_audit` 的 `await session.commit()` 再抛 `PendingRollbackError` → 全局兜底 500。此时业务事务已成功提交（如 `spider_task_service.py:187`），用户收到 500 后重试会造成重复操作。另外业务 commit 与审计 commit 之间进程崩溃会丢审计记录（高危操作如 `task.delete` 留痕缺失）。

**修复方案**：`record_audit` 改用**独立 session**（审计不与业务共享事务），异常时 rollback 而非 commit；或审计失败仅记结构化日志 + 补偿队列，绝不让审计问题影响业务响应码。

#### P1-12 LLM 供应商无故障转移 / 模型列表 / 周期巡检（"多供应商"名不副实）

**证据**：`backend/services/ai_planner/llm_client.py:150-163` 运行时只解析**一个**激活 provider，失败重试在同一 provider 上指数退避（L174-220），耗尽即抛异常，不切换其他 enabled 供应商。`models/llm_provider.py:32` 单 `model` 字符串——无模型列表、无按模型路由。健康检查仅手动触发（`llm_provider_service.py:285`）。

**修复方案**：按用户选定方向做故障转移演进，见 4.1 设计。

#### P1-13 共享 MySQL 引擎缺 `pool_pre_ping` → 陈旧连接报错

**证据**：`platform_core/db.py:73,79-87` 只配 `pool_recycle=3600`；而项目自己在 `channel_scheduler_service.py:139` 用了 `pool_pre_ping=True`——同一仓库两种口径。MySQL `wait_timeout` 后的陈旧连接在非整点回收窗口会抛 "server has gone away"。

**修复方案**：`DBManager` 创建 engine 统一加 `pool_pre_ping=True`（一次 DB 往返换稳定性，值得）。

---

### 3.3 P2 —— 治理类问题（按主题归组）

#### A. 架构与分层

| # | 问题 | 证据 |
|---|------|------|
| A1 | API 层直接 import ORM 绕过 R7 红线正则：`from platform_core.models.user import User` 这种子模块形式匹配不到 `check-arch.sh:72` 的 `from.*\.models import` 模式 | `backend/app/api/deps.py:21,64`；`tasks/consumer.py:40` |
| A2 | external_api 绕过 Service 直用 Repository；`/data/{spider_name}` 裸 dict 无响应信封 | `backend/app/external_api/v1/public.py:15-16,72,107` |
| A3 | alert_service 在 Service 层手写 `session.execute(select(...))` 绕过 Repository；对不存在的规则抛裸 `ValueError` → 前端收 500 而非 404 | `backend/services/alert_service.py:121-127,137-147,62,71` |
| A4 | 删除类操作权限粒度分裂：delete_task/result/definition/schedule 均 require_admin，唯独 delete_template 是 require_operator；且 update/delete_template 不校验 created_by（任何 operator 可删他人模板） | `v1/spiders/templates.py:71`；`spider_registry_service.py:352-361` |
| A5 | yml 与 settings.py 双份中间件/管道配置漂移：`config/scrapy/default/settings.yml:14-27` 声明的配置不会被 `scrapy/settings.py` 读取（后者硬编码，L59-81），yml 版缺 4 个中间件/管道且含 null 条目——"改 yml 无效"陷阱 | 两处对照 |
| A6 | 死代码/幽灵模块：`middleware/process_time.py` 从未注册；`backend/cors/` 只剩 `__pycache__` 但 `app/__init__.py:14`、`platform_core/models/base.py:1` 注释仍指向已删文件；`storage.py` 的 cache_set/cache_get/save_upload/save_export/cleanup_temp、`UserRepository.get_active_users`、`UpdatePasswordRequest`（`schemas/auth.py:30-34`）均无调用方 | 各处 |
| A7 | 重复代码：`_store_dir`/`_store_targets` 两 Service 逐字重复（`spider_task_service.py:680-694` vs `spider_query_service.py:322-335`）；`_EXPORT_COLUMNS` 两处；consumer `_ingest` vs `_flush_batch` 重复（`consumer.py:519-523`/`:620-625`） | 各处 |

#### B. 安全（次级）

| # | 问题 | 证据 |
|---|------|------|
| B1 | 未知/空角色默认授予 `operator` 而非 viewer；开放注册（`auth.py:172-205`）不设 role → 模型默认 operator → **任何自注册用户即可创建/运行爬虫任务** | `backend/app/api/deps.py:47`；`models/user.py` default |
| B2 | 注册接口用户枚举：已存在用户名/邮箱返回 409 + 明确提示；authenticate 用户不存在时不做 dummy hash，存在时序差异 | `auth_service.py:108-119,48-61` |
| B3 | ~~set_admin_account.py 硬编码弱口令~~ **已按决策采纳为预期设计**（2026-08-31）：初始化脚本固定创建/重置 `admin/123456`，初始化后由后台管理用户；残余风险仅"生产环境误跑脚本会重置口令"，缓解手段：脚本结尾打印醒目"请立即登录修改密码"提示（README 已注明） | `backend/scripts/set_admin_account.py:13-15` |
| B4 | 请求体全局"XSS 清洗"静默篡改业务字段：`on\w+\s*=` 正则会删改 `params`（JSON 字符串）中合法的 `onclick=` 类内容、密码含此类子串也被改写——静默修改输入比不修改更危险 | `platform_core/schemas/base.py:33-46`；`validators.py:34-42`；`schemas/spider.py:43` |
| B5 | 已提交的固定 dev JWT 密钥与弱密码：compose `AUTO_AGENTS_JWT__SECRET_KEY: "auto-agents-dev-secret-key-2026"`、密码 123456（虽声明"严禁用于生产"但密钥可预测）；`scripts/init-db.sh:8` 硬编码 `IDENTIFIED BY '123456'`（check-arch R2 不扫 scripts/，检测不到） | `docker-compose.yml:48,14-17,28,46-47`；`scripts/init-db.sh:8` |
| B6 | logger `diagnose=True` 会在 traceback 中打印变量值，生产日志可能带出敏感数据；轮转不压缩 | `platform_core/logger.py:76-78` |
| B7 | storage.py `save_upload` 对 filename 无路径清洗，`../../x.jpg` 可穿越 uploads 目录（当前零调用的死代码，属潜伏缺陷） | `platform_core/storage.py:66-76` |
| B8 | Dockerfile 全程 root 运行（无 USER 指令） | `Dockerfile:23-51` |

#### C. 可靠性与资源生命周期

| # | 问题 | 证据 |
|---|------|------|
| C1 | 进程退出不清理 DB 引擎与异步 Redis：`close_all()`（`db.py:186-197`）与 `close_async_redis()`（`redis_async.py:73-83`）全仓零调用；lifespan 关闭链只 stop 后台组件。且 `close_all` 用 `asyncio.run()` dispose 异步引擎——在运行中的事件循环内调用直接 RuntimeError，写法本身不可用于 FastAPI 关闭钩子 | `backend/app/__init__.py:91-120` |
| C2 | DBManager 懒加载路径在事件循环内做同步网络 IO（`SELECT 1` + `ping()`）；`app/__init__.py:152` 模块级 `create_app()` 使 `uvicorn backend.app:app` 直启成为可能，首个请求阻塞全量建连。另 `state.py:118-119`、`schedule_service.py:370-371`、`newapi_api.py:50-52` 直接 `manager.async_engines["DEFAULT"]` 绕过 ready 检查，DB 未初始化时 KeyError 被吞成 warning（启动对账静默失效） | `platform_core/db.py:145-153` |
| C3 | `_create_redis_client_for_db` 每次调用新建 100 连接的池且不关闭（当前仅 v2/health 一处无 db 参数的调用，潜伏地雷） | `platform_core/db.py:165-184` |
| C4 | 渠道探针锁 TTL 与批次时长不匹配：锁 TTL 21600s 无自动续期，批次串行 9 题 × N 渠道 × 60s 超时，渠道多时可能超 TTL → 双实例并发批次、事件交叉 | `channel_probe_service.py:344,397-415` |
| C5 | 代理统计读-改-写竞态：hget→内存改→hset 非原子，多 Worker 并发互相覆盖丢计数；`failed_proxies` 仅本地内存，重启即遗忘 | `scrapy/middlewares/__init__.py:232-245,148` |
| C6 | mirror 双写时序：`_mirror_batch`（Redis rpush）发生在 `session.commit()` 之前——commit 失败时 Redis 镜像含未提交数据；反向失败仅告警，两侧都可能不一致 | `backend/tasks/consumer.py:569,572,601-602` |
| C7 | Playwright 浏览器懒初始化竞态：`_ensure_browser` 无锁，首批并发请求启动多个浏览器实例泄漏 | `scrapy/middlewares/playwright_dm.py:93-101` |
| C8 | 质量管道去重集合无界：`self._seen` 只增不减，常驻 Worker 长跑内存泄漏 | `scrapy/pipelines/quality.py:32` |
| C9 | 去重策略断层：任务级请求全部 `dont_filter=True`（`base.py:47`、`flow_generic.py:104,148,176`），跨任务内容级去重仅 `params.incremental=true` 才启用（`consumer.py:527-535`），默认重复任务重复入库 | 各处 |

#### D. 性能

| # | 问题 | 证据 |
|---|------|------|
| D1 | consumer 增量去重 N+1 + 同批重复漏检：每条消息单独 `find_by_content_hash`（一批 50 条 = 50 次点查）；查重在 bulk insert 之前执行，同批两条相同 hash 互相检不出 | `backend/tasks/consumer.py:528,561-563,639-643` |
| D2 | `get_proxy_health` 每请求新建 Redis 连接（`aioredis.from_url` + finally aclose），违背 `get_async_redis()` 门面约定；且端点函数体内 import + 构造 Service 而非依赖注入 | `proxy_health_service.py:182-184`；`v1/spiders/definitions.py:120-123` |
| D3 | `stats()` 6 个串行查询可 gather；`list_nodes` 对每个心跳 key 逐个 hgetall + 每爬虫逐个 smembers（Redis N+1） | `spider_query_service.py:286-320`；`spider_registry_service.py:257-272` |
| D4 | `stats()` 的 `total_results` 语义错误：名为"总结果数"实为近 7 日合计，与 `total_tasks`（全量）口径不一致，仪表盘失真；`datetime.now()` 本地时区裸值 | `spider_query_service.py:316,295` |

#### E. 输入校验与契约一致性

| # | 问题 | 证据 |
|---|------|------|
| E1 | `params` 字段无长度与 JSON 合法性校验（4 处 `Optional[str]`）：超大 payload 直达 DB Text 列，非法 JSON 要到消费者分发时才失败；`AlertRuleRequest.rule_type` 无枚举约束、name 无长度限制 | `schemas/spider.py:43,173,180,256,344,303`；`consumer.py:76` |
| E2 | `PUT /configs/{key}` 的 key 无约束，可写任意长度/任意数量配置键 | `v1/configs.py:32-35`；`config_service.py:23-38` |
| E3 | 成功响应 `request_id` 恒为 None（`ok()/created()` 不填），所有错误处理器都填——同一信封字段成功/失败行为不一致 | `app/responses/api.py:16,19-21` vs `exceptions/handlers.py:34` |
| E4 | webhooks 直接抛 HTTPException（code 为 `HTTP_400` 而非业务码），绕过 AppException 体系 | `external_api/v1/webhooks.py:65,70,77` |
| E5 | alembic DSN 密码未 URL 编码（应用侧用 `quote_plus`），含特殊字符的密码下迁移可用性与应用不一致 | `backend/alembic/env.py:24-28` vs `db.py:67` |
| E6 | spider_files 定义快照 500 条静默截断，超出后 registered/enabled 状态失真（无告警无分页） | `spider_registry_service.py:124` |
| E7 | 限流提示负数分钟：key 无过期（ttl=-1）时提示"请-1分钟后再试" | `v1/auth.py:39` |

#### F. 工程化与 CI

| # | 问题 | 证据 |
|---|------|------|
| F1 | check-arch.sh 盲区：R1/R2 不覆盖 `platform_core/ scripts/ config/ deploy/ docker-compose.yml`；R2 模式只匹配 Python 双引号赋值（漏单引号/yaml `PASSWORD:`/secret-token-api_key 键名），`test_` 前缀全豁免；R10 的 `for f in backend/services/*.py` 漏子包 `ai_planner/*.py`（6 文件真空）；R11 自认两段式赋值不匹配 | `scripts/check-arch.sh:46,72,89,103-105` |
| F2 | CI 无前端测试/ESLint/安全扫描（仅 build）；scrapy 侧无测试目录；后端 pytest 仅 backend/tests | `.github/workflows/ci.yml:63-91` |
| F3 | 文档失联：`AGENTS.md:80` 引用已删除的 GEMINI.md；`run.py:7` 引用不存在的 `scripts/bootstrap.sh`（实际 bootstrap-db.sh）；`ci.yml:6` 与 `.pre-commit-config.yaml:31` 写"10 条红线"，实际 12（check-arch.sh:38） | 各处 |
| F4 | `run.py:130` 端口预检逻辑失效：`or` 短路 + 结果丢弃 + 不阻断启动，纯装饰 | `run.py:130` |
| F5 | 四套 DB 初始化脚本并存且口径矛盾：init-db.sh（硬编码 123456）、init-database.sh、bootstrap-db.sh（自称"唯一推荐入口"）、init_db_sync.py；README:163 用的是 init-db.sh → **存废决策见第 9 章：保留 5 删除 5** | `scripts/` 各处 |
| F6 | 前端工具链老化：react-scripts 5.0.1（CRA 已停止维护）+ TS 4.9.5 配 React 19 类型（官方要求 TS≥5.0）+ target es5；两前端高度同构可抽共享包未抽 | 两处 package.json / tsconfig.json |
| F7 | CI 三阶段关卡无 docker 镜像漏洞扫描与依赖审计（pip-audit / npm audit） | `ci.yml` |

#### G. 前端质量

| # | 问题 | 证据 |
|---|------|------|
| G1 | `official/src/services/api.ts` 零导入（死文件）；`ApiEnvelope` 接口两处重复定义；`unwrap` 强转不校验 `success` 字段（依赖"后端错误必带非 2xx"的隐含约定） | `official/src/services/api.ts`；`admin/src/services/auth.ts:23-29`、`api.ts:49-59` |
| G2 | token 30 分钟过期但无 refresh-token 流程；401 一律 `window.location.href='/login'` 硬跳丢页面状态；token 持久化 localStorage（`useAuthStore.ts:38` 注释自认 rememberMe 语义未实现） | `config/default/jwt.yml:11`；`admin/src/services/api.ts:35-39`；`useAuthStore.ts:36-45` |
| G3 | `usePermission.ts:35` 在 hook 返回值里用 CommonJS `require()`，每次渲染执行且 ESM/TS 风格违规 | `usePermission.ts:35` |
| G4 | 用户管理只读：admin 前端 `menu:users` 权限对应的写操作后端不存在（无改密/禁用/角色分配端点、无 logout/token 撤销；`jwt.yml:13` 配了 REFRESH_TOKEN_EXPIRE_DAYS 但无刷新端点）→ **SaaS S2 补齐（第 8 章）** | `v1/admin.py:33,43,55` |
| G5 | 遗留演示脏代码：zhihu_feed/dianping_home/example 在 RedisSpider 上声明 `start_urls`（scrapy-redis 不消费，纯误导）；openweather 错误提示指向不存在的 `spider_sites.yml` | `zhihu_feed.py:12`、`dianping_home.py:12`、`example.py:20`、`openweather.py:24` |

### 3.4 第二轮易用性走查新增（功能级缺陷，2026-08-31 已人工复核）

> 这些不是风格问题，而是**行为与用户预期直接相悖**的功能缺陷；行号均已逐行核验。

| # | 问题 | 证据 |
|---|------|------|
| UX-B1 | **假分页**：任务列表永远只拉前 50 条，表格翻到第 2 页显示空表（服务端分页未接通） | `frontend/admin/src/pages/Spiders.tsx:77`（fetchTasks(0,50) 固定）+ `TaskList.tsx:256`（pagination 无 onChange） |
| UX-B2 | **"运行"≠重跑**：任务行「运行」、调度「手动运行」只带 spider_name 打开空白表单，不回填该任务/调度的 params——用户以为在重跑，实际要重填一切 | `TaskList.tsx:118-128` → `TaskModal.tsx:31-39`；`Spiders.tsx:180,205` |
| UX-B3 | **"从模板创建"不填参数**：模板保存了完整 params，但创建弹窗选模板只回填 spider_name+priority，placeholder 却写"选择模板快速填充" | `TaskModal.tsx:87-96` |
| UX-B4 | **路由级权限缺失**：`ProtectedRoute` 的 requireAdmin 参数全站 0 处使用（grep 计数=0），viewer 直达 /users /llm /settings 得到的是接口报错 toast + 空表，而非 403 页——菜单隐藏只是视觉隐藏 | `App.tsx:29-49`、`ProtectedRoute.tsx:22-25` |
| UX-B5 | **Dashboard 双页头**：页面自己又渲染一套 Header（第二个标题、第二个"退出登录"） | `Dashboard.tsx:102-116` vs `AdminLayout.tsx:60-68` |
| UX-B6 | **编辑断崖**：创建任务是动态表单，编辑却退化为手写 params JSON 文本域，且要求理解 pending/queued 状态词 | `TaskEditModal.tsx:78,90-95` |
| UX-B7 | **官网假数据与虚假承诺**：官网静态假统计（"累计执行任务 128,000+"）无示意标注；后台设置页宣称"官网内容已实时同步更新"，但官网从不请求任何 API；官网称可"一句话描述提取字段"而后台 AI 表单只有 URL | `official/src/pages/Home.tsx:37-41`、`admin/src/pages/Settings.tsx:46`、`official/.../AiFlowSection.tsx:29` |
| UX-B8 | **导出隐性截断与按钮语义错位**：数据中心导出硬上限 100 条仅靠 toast 告知；「详情」按钮打开的是"整任务结果抽屉"而非该条数据 | `Data.tsx:167-182,317` |

---

## 4. 演进方案设计（用户选定方向：LLM 故障转移 + new-api 调度接线）

### 4.1 LLM 管理模块：多供应商故障转移

**现状**：单激活 + yml/env 单一兜底（`resolve_runtime_config`，`llm_provider_service.py:331-354`）；失败只在同一 provider 上退避重试。

#### 4.1.1 数据模型变更（一张 alembic 迁移）

`llm_providers` 表增列：

- `priority INT NOT NULL DEFAULT 100` —— 故障转移顺序（越小越优先）
- `models JSON NULL` —— 模型列表（替代单一 `model` 字符串；迁移时把存量 `model` 回填为单元素列表，旧列保留兼容期）
- `consecutive_failures INT NOT NULL DEFAULT 0` —— 熔断计数（健康巡检维护）
- `last_health_check DATETIME NULL` / `health_status VARCHAR(16) NULL`

#### 4.1.2 运行时候选链解析

`resolve_runtime_config` 改为返回**有序候选列表**：

1. active 且 enabled 的 provider 排第一；
2. 其余 enabled 且 `health_status != 'down'` 的按 priority 升序；
3. yml/env 兜底配置排最后。

`llm_chat` 按序尝试：每个候选 1 次请求 + 对 429/5xx 有限重试（保留现有指数退避但上限 2 次）；遇到**硬失败**（连接错误/超时/401/403/404 model）立即切下一候选；响应中记录实际使用的 provider_id（供用量归集与前端展示）。全部耗尽才抛 `LLMAllProvidersFailedException`（AppException 子类，聚合各候选错误摘要）。

#### 4.1.3 周期健康巡检

- lifespan 中新增 `LLMHealthProbeTask`（与 channel scheduler 同模式：分布式锁 + 间隔可配 `LLM.HEALTH_CHECK_INTERVAL`）；
- 对全部 enabled provider 做轻量连通性探测（复用 `test_connectivity` 的 1-token 请求）；
- 连续失败 ≥ N（默认 3）→ 置 `health_status='down'` + 通知；探测恢复 → 重新置 `healthy`。down 的 provider 不进候选链，但仍保留在注册表（人工重启或自动恢复）。
- 熔断状态落库（不进程内存），多副本一致。

#### 4.1.4 Token 用量持久化（同时解决 P0-3）

新表：

```sql
llm_token_usage (
  id BIGINT PK AUTO_INCREMENT,
  provider_id INT NULL,            -- NULL = yml/env 兜底路径
  provider_name VARCHAR(64),       -- 冗余存名，防 provider 删除后失义
  model VARCHAR(128),
  stat_date DATE,
  prompt_tokens BIGINT DEFAULT 0,
  completion_tokens BIGINT DEFAULT 0,
  total_tokens BIGINT DEFAULT 0,
  request_count INT DEFAULT 0,
  failed_count INT DEFAULT 0,
  updated_at DATETIME,
  UNIQUE KEY uq (provider_name, model, stat_date)
)
```

写入路径：每次请求成功后 `Redis INCRBY llm:usage:{provider}:{model}:{date}`（异步门面）+ 后台任务每分钟聚合 flush 到 MySQL（`INSERT ... ON DUPLICATE KEY UPDATE`）。预算熔断改读 Redis 聚合值；admin 前端 LlmProviders 页增用量列。进程内 `_TOKEN_USAGE` 降级为读缓存。

#### 4.1.5 模型列表支持

- 管理端"拉取模型列表"动作：`GET {base_url}/models`（openai_compatible 通用），结果写 `models` JSON 列；
- Schema：`ProviderCreate/Update` 增 `models: list[str]`；`ai_planner` 调用处允许指定 model（默认取列表第一个）。

#### 4.1.6 验收标准

- 单测：候选链排序（active 优先/优先级/健康过滤）、故障切换（primary 500 → backup 200 的 mock 双 provider）、用量聚合正确性；
- `uv run pytest -x -q backend/tests` 退出码 0；`bash scripts/check-arch.sh` 0 违规；
- 手动 curl：禁用 active provider 的 base_url，触发 AI 规划，观察自动切换日志与 `llm_token_usage` 落库行。

### 4.2 new-api 调度接线：让调度器真正管起来

**现状**：`channel_scheduler_service.py:447` 读 `newapi:channel:cfg:{id}` hash 但全仓无写入方；`DEFAULT_WINDOW_QUOTA=0` → 受管渠道 0，调度器空转。

#### 4.2.1 渠道配置 CRUD API（backend 侧）

`backend/app/api/v1/newapi.py` 增写端点（require_admin + 审计）：

- `GET /newapi/channels` —— 合并视图：new-api 管理 API 渠道列表 ⨝ 本地 Redis 配置（含 effective 额度：per-channel > 全局默认）
- `PUT /newapi/channels/{channel_id}/config` —— body `{ limit_quota: int, window_hours: int, cooldown_seconds: int }`，写 `newapi:channel:cfg:{id}` hash（经 `get_async_redis()`；字段名即调度器读取侧契约——`limit_quota<=0` 视为显式关闭该渠道调度，见 `channel_scheduler_service.py:444` docstring 与 `newapi.yml:29` 注释）
- `DELETE /newapi/channels/{channel_id}/config` —— 清除 per-channel 配置，回退全局默认

Service 层新建 `channel_config_service.py`（hash 字段名与 scheduler 读取侧严格对齐——以 `channel_scheduler_service.py:447` 的 hkey 契约为准）；写操作记 `channel_events`（复用现有事件表）+ 现有通知通道。

#### 4.2.2 Admin 前端入口

`NewApiOps.tsx` 增"渠道配置"区块：渠道表格（名称/状态/窗口用量/effective 额度）+ 行内编辑抽屉（limit_quota 设 0 即关闭该渠道调度 / window_hours / cooldown_seconds）。services 层沿用 unwrap 信封约定。

#### 4.2.3 生效链路收口

三层开关文档化并加启动自检日志：

```
NEWAPI.ENABLED（总开关）
  └─ SCHEDULER.ENABLED（调度器开关）
      └─ 渠道受管条件：存在 newapi:channel:cfg:{id} 或 DEFAULT_WINDOW_QUOTA > 0
```

- `bootstrap-db.sh` / 空库引导脚本补可选的渠道配置种子步骤；
- 调度器每轮启动/巡检时打印"受管渠道数 = N"，N=0 且开关全开时打 warning（消除静默空转）。

#### 4.2.4 顺带修复

- 探针锁：TTL 按批次规模估算（N 渠道 × 9 题 × 超时）或启用 `distributed_lock` 的 renewal 自动续期（`platform_core/queues.py` 已支持）；
- 探针批次并发上限，避免长批次。

#### 4.2.5 验收标准

- 单测：config service 读写 hash 契约、effective 额度计算（per-channel 覆盖默认）；
- 集成：mock new-api API + 假 DB DSN 下调度器 dry-run，断言受管渠道数 > 0 且超限渠道被置 status=3；
- curl：`PUT /newapi/channels/1/config` 后 `HGETALL newapi:channel:cfg:1` 可见；前端 `npm run build` 通过。

---

## 5. 分批修复路线图

| 批次 | 内容 | 预估 | 验收标准 |
|------|------|------|----------|
| **批次 1（P0）** | P0-1 重试上限+running 回收；P0-2 webhook 守卫；P0-3 用量落库（可先做最小版：Redis 聚合+定时 flush，表结构按 4.1.4）；P0-4 httpx proxy 参数+测试重写 | 1-2 天 | `uv run pytest -x -q backend/tests` 退出码 0；新增回归测试覆盖 4 条；默认密钥启动被拒（curl 验证） |
| **批次 2（P1）** | P1-1~5、7~11、13（prod 配置、compose 绑定、前端 register、丢数据兜底、openweather、反爬接线、RedisPipeline、bcrypt、v2 health、审计独立 session、pre_ping）；P1-6/12 并入批次 4 | 3-5 天 | pytest + check-arch 双绿；`docker compose up` 后宿主机 curl 9111 health 通；前端注册 e2e 可用；scrapy 对 429 站点不再无限重试（本地起 mock 站点验证） |
| **批次 3（P2 backlog）** | 按主题推进：安全加固（B1 角色默认 viewer、B4 清洗白名单、B5 脚本密钥）→ 架构收口（A1/A2/A3）→ 性能（D1 批量去重、D3 gather）→ 工程化（F1 扫描盲区、F2 前端测试、F5 脚本合并）→ 前端（G1/G2/G4） | 持续 | 每项独立 PR，各自带测试；check-arch 盲区修复后全仓扫描 0 违规 |
| **批次 4（演进）** | 4.1 LLM 故障转移 + 4.2 调度接线 | 1-2 周 | 见 4.1.6 / 4.2.5 验收标准 |
| **批次 5（易用性 U1+U2）** | 见第 7.3 章：修假分页/参数回填/路由守卫/双页头等快赢 11 项 + 参数校验前移/参数元数据补全/cron 可视化/预置示例模板/pending 引导/空库 onboarding | 1-2 周 | 见 7.5 节 U1/U2 验收；前端 build 通过；新用户不看文档 3 分钟完成"从零到数据" |
| **批次 6（易用性 U3+U4）** | WebSocket 日志 tail、结果单条预览、服务端流式导出、任务详情页、error_message 结构化；（可选）选择器实时试测/流程只读画布/jsonpath | 2-4 周 | 见 7.5 节 U3/U4 验收 |
| **批次 7（SaaS S1+S2）** | 第 8.5 章：租户基座（tenants/行级隔离/两级 RBAC/越权测试）+ 子账号管理（补 G4）——**硬前置：批次 1 与 UX-B4 已完成** | 2-3 周 | 见 8.5 节 S1/S2 验收（越权测试全绿为 P0 级门槛） |
| **批次 8（SaaS S3-S5）** | 配额与用量看板、LLM 供应商租户化、官网注册/定价与平台运营台（节奏视商业化决定） | 按需 | 见 8.5 节 S3-S5 验收 |

**顺序依赖**：批次 1 的 P0-3 用量表与批次 4 的 4.1.4 是同一张表——建议批次 1 直接按 4.1.4 建表，避免二次迁移。

---

## 6. 易用性专项走查（第二轮，2026-08-31）

> 走查标准：**"简单好用，操作流程符合人的直觉"**——以"一个不了解内部实现的新用户能否顺利完成核心任务"为唯一裁判。方法：admin 全部 47 个源文件逐页走查 + 后端 API 旅程映射 + 对标三款成熟产品（第 7 章）。行为级缺陷已并入 3.4 节；本章记录旅程卡点、后端可用性缺口与 UX 反模式。

### 6.1 总体结论

主链路的设计方向是正确的：**注册表驱动的动态任务表单（创建路径全程无需手写 JSON）→ 提交后自动打开日志抽屉 → 3 秒静默轮询 → 结果抽屉/导出**，这条线接近商业产品手感；旅程 D（LLM 配置）与旅程 F（AI 采集向导）完成度最高。

但整体被三类问题拖累：

1. **功能 bug 直接破坏操作预期**（3.4 节）：假分页、"运行/从模板创建"不回填参数、路由权限缺失；
2. **内部概念与格式串泄漏到 UI**：编辑任务退化为手写 params JSON（`TaskEditModal.tsx:90-95`）、cron 与静默时段手写格式串（`ScheduleTab.tsx:219-266`）、`_strategy/_quiet_hours` 混进爬虫参数（`ScheduleTab.tsx:71-76`）、"注册表/登记/收藏"等动词隐晦、`flow_generic` 内部名直接展示给用户；
3. **反馈与引导缺失**：Dashboard 是无入口死胡同且双页头、错误只藏在 hover、任务 pending 无"执行器未启动"引导、无单条结果完整预览、空库无 onboarding。

### 6.2 六条核心旅程走查

#### 旅程 A：从零跑通一个爬虫任务

步骤流：登录 → Dashboard（死胡同）→ 用户自行发现「爬虫管理→任务列表」→「新增任务」（动态表单，体验好）→ 提交（自动开日志抽屉，好）→「结果」看数据。

| 卡点 | 描述 | 证据 |
|---|---|---|
| A1 | Dashboard 只有只读图表，无"新建任务"/最近任务入口；且自渲染第二套页头（双标题双退出） | `Dashboard.tsx:101-277,102-116` |
| A2 | 「运行」≠重跑：只带 spider_name，参数全要重填（UX-B2） | `TaskList.tsx:118-128` |
| A3 | 「从模板创建」不填参数（UX-B3） | `TaskModal.tsx:87-96` |
| A4 | 假分页：翻页空表（UX-B1） | `Spiders.tsx:77`、`TaskList.tsx:256` |
| A5 | 筛选不足：只有优先级，无状态/爬虫/关键词；找失败任务靠肉眼扫 | `TaskList.tsx:230-241` |
| A6 | 操作列 9 个 link 按钮平铺；「恢复」对从未暂停的 running 任务也常驻显示 | `TaskList.tsx:113-224,154-163` |
| A7 | 编辑断崖：创建是动态表单，编辑是手写 JSON（UX-B6） | `TaskEditModal.tsx:78,90-95` |

#### 旅程 B：查看结果与导出

结果抽屉服务端分页、导出 CSV/JSON 交互合格；但**无单条完整数据预览**——`extra/item_type/source` 字段不展示、无展开行看整条 JSON（`ResultDrawer.tsx:81-115`）；失败原因只藏在状态 Tag 的 hover（`TaskList.tsx:99-107`）；数据中心「详情」按钮打开的是整任务结果抽屉、导出隐性截断 100 条（UX-B8）。

#### 旅程 C：创建定时调度

cron 表达式手写 Input（仅正则校验"5 段"，无可视化选择器、创建时无"下次触发时间"预演）；静默时段手写 `02:00-06:00,23:00-23:59` 格式串、无校验；策略与静默时段以 `_strategy/_quiet_hours` 键混进爬虫 params（内部实现泄漏）；**调度创建后不可编辑**（后端 `updateSchedule` 支持 cron，UI 未接）；「手动运行」不带该调度参数（`ScheduleTab.tsx:219-266,146-170`；`services/spiders.ts:303-309`）。

#### 旅程 D：配置 LLM 供应商（全站最佳实践页）

未激活时顶部 Alert 引导、测试连通性行内反馈（延迟+模型+错误 Tooltip）、API Key 编辑态留空不改+脱敏 placeholder（`LlmProviders.tsx:309-321,170-193,388-397`）。可作为其他页面交互基线。

#### 旅程 E：new-api 中转站运维

纯只读三 Tab；过滤要求用户记**渠道数字 ID**（无名称下拉）；verdict 术语半翻译（"original 正品"）（`NewApiOps.tsx:329-338,42-46`）。写操作能力缺失对应 4.2 演进设计。

#### 旅程 F：AI 智能采集向导

三步向导 + 2.5s 轮询 + 试采历史表（轮次/判定/原因）+ 上线后指路爬虫管理，闭环好；但**输入只有 URL**——无法表达"想要哪些字段"（官网却如此宣传，UX-B7）；想换 URL 只能「重置向导」从头再来（`PlanDetail.tsx:77-105,277-295`）；viewer 可见表单但无提交按钮也无权限提示（`AiPlans.tsx:63-67`）。

### 6.3 后端可用性缺口（前端体验问题的根因）

| # | 缺口 | 证据 |
|---|------|------|
| 1 | **提交时零参数校验**：非法 JSON 的报错文案是误导性的"params 缺少 urls，无法分发采集目标"（真实原因是 JSON 写错） | `spider_task_service.py:149-206`；`consumer.py:254-256` |
| 2 | **隐式流程路由**：params 含 pagination/detail/filters 任一段即被改写为 flow_generic 执行，任务行的爬虫名会变，事先无说明 | `spider_task_service.py:158-160`；`consumer.py:246-252` |
| 3 | **参数元数据不完整**：`store_to/incremental/render_js/wait_for/wait_timeout` 只存在于源码，registry/表单均不暴露 | `config/default/spiders.yml:14-75` vs `spider_common.py:66-81`、`consumer.py:105-127` |
| 4 | **无单任务 GET 端点、无 WebSocket/SSE**：只能轮询任务列表（全仓 grep WebSocket/EventSource = 0） | `v1/spiders/tasks.py` 全文 |
| 5 | **任务日志 = 共享日志文件 + 字节偏移**：并发任务日志互串；backend 与 scrapy worker 跨机部署时永远返回空 | `spider_query_service.py:217-262`；`consumer.py:306-315` |
| 6 | **失败原因不可读**：爬虫关闭回调只上报 `"spider closed: finished/shutdown/cancelled"`——选择器取空/403/超时等真实病因不可见 | `scrapy/extensions/__init__.py:85` |
| 7 | **双进程心智模型无提示**：scrapy worker 不启动则任务静默 pending（提交时不校验 worker 心跳）；首个管理员需跑脚本但无文档 | `app/__init__.py:33-40`；`backend/scripts/set_admin_account.py` |
| 8 | **零预置模板、空库无引导**：模板表无 seed，Dashboard 空态只有空转图表 | 模板迁移无 seed；`Dashboard.tsx` |

### 6.4 UX 反模式清单（22 条）

| # | 反模式 | 证据 |
|---|---|---|
| 1 | 假分页（数据只拉前 50 条） | `Spiders.tsx:77`、`SpiderLogs.tsx:38` |
| 2 | 按钮语义与行为不符（"运行"实为新建） | `TaskList.tsx:118-128`、`Spiders.tsx:180,205` |
| 3 | 模板不回填参数 | `TaskModal.tsx:87-96` |
| 4 | 手写格式串：params JSON / cron / 静默时段 | `TaskEditModal.tsx:90-95`、`ScheduleTab.tsx:219-265` |
| 5 | 创建/编辑体验不一致（表单 vs JSON 断崖） | `TaskModal.tsx` vs `TaskEditModal.tsx` |
| 6 | 内部术语裸露：注册表/登记/`_strategy`/内容指纹/verdict/pending/queued | `FileTab.tsx:254,294`、`ScheduleTab.tsx:71-76`、`ResultDrawer.tsx:108`、`NewApiOps.tsx:42-46` |
| 7 | 死表单：viewer 可填不可提交、无权限提示 | `AiPlans.tsx:63-67`、`PlanDetail.tsx:100-104` |
| 8 | 路由级权限缺失（菜单隐藏≠拦截） | `App.tsx:29-49`、`Users.tsx:30-40` |
| 9 | 双页头/双退出 | `Dashboard.tsx:102-116` |
| 10 | 无行动入口的首页 | `Dashboard.tsx:101-277` |
| 11 | 成功反馈撒谎（"官网已实时同步"） | `Settings.tsx:46` vs 官网零 API 调用 |
| 12 | 中英混排空态（未配 ConfigProvider zh_CN） | `index.tsx:7-14` |
| 13 | 任务列表筛选维度不足 | `TaskList.tsx:230-241` |
| 14 | 结果无单条完整预览 | `ResultDrawer.tsx:81-115` |
| 15 | 导出隐性截断 100 条 | `Data.tsx:167-182` |
| 16 | 不可编辑实体（调度后端支持改 cron，UI 未接） | `ScheduleTab.tsx:146-170` |
| 17 | 冲突按钮（running 同时显示暂停+恢复） | `TaskList.tsx:129-163` |
| 18 | 过滤要求懂内部数字 ID（newapi 渠道） | `NewApiOps.tsx:329-338` |
| 19 | 终态后轮询不停（日志抽屉） | `LogDrawer.tsx:24-37` |
| 20 | 按钮动词不统一（提交/新增/登记/收藏/上线注册） | `TaskModal.tsx:77`、`FileTab.tsx:262,284` |
| 21 | 营销与实物不符（官网"一句话描述字段"） | `AiFlowSection.tsx:29` vs `PlanDetail.tsx:77-105` |
| 22 | 装了不用（react-query 在依赖中全站零使用） | `admin/package.json` + 全 src grep |

### 6.5 官网（official）

结构完整非空壳（Hero/功能卡/流程/架构/CTA + framer-motion 动效，约 1100 行），问题三条：静态假统计无"示意"标注（`Home.tsx:37-41`）；文案承诺与后台实物不符（UX-B7）；与后台设置页宣称的"同步"毫无关联。

### 6.6 做得好的（后续改造的基线，避免误伤）

1. 注册表驱动的动态任务表单 + JSON 字段中文校验报错（`formUtils.tsx:133-232`）；
2. 提交任务自动打开日志抽屉 + 3s 静默轮询（仅活跃任务时）+ 状态列转圈（`Spiders.tsx:103-121`）；
3. 关键术语 tooltip 解释（优先级/增量/cron 五段/温度等）；
4. 危险操作全部 Popconfirm + 后果说明 + 运行中禁删；
5. LLM 页交互基线（见旅程 D）；
6. AI 向导三步流 + 试采历史表 + 上线指路；
7. 多数列表中文 Empty 空态带行动指引；
8. 401 自动登出 + 登录回跳 + 独立 403 页（已有页面，只差路由接上）；
9. newapi 管理面不可达时的降级说明 Alert；
10. CSV 导出带 BOM 防 Excel 乱码；ResultDrawer 切换任务防闪现。

---

## 7. 优化方案：对标 EasySpider / crawlab / spider-flow

### 7.1 三款产品的易用性杠杆与借鉴结论

| 产品 | 核心杠杆 | 借鉴结论 |
|---|---|---|
| [EasySpider](https://github.com/NaiboWang/EasySpider) | 把"写选择器"变成"点页面"；分步编号引导内嵌产品；内置示例任务 | 借鉴**引导交互与示例模板**；点选生成选择器先做降级版（选择器实时试测），不搬其浏览器执行引擎 |
| [crawlab](https://github.com/crawlab-team/crawlab) | 运行/日志/结果/调度做成后台一级体验：实时日志 tail（WebSocket 分块增量）、Run 时参数对话框、结果在线表格、cron preset 下拉 | 四件套全部可**低成本**落地（见 U2/U3），对本系统收益最大 |
| [spider-flow](https://github.com/ssssssss-team/spider-flow) | 节点画布表达流程语义；多范式解析下拉（css/xpath/jsonpath/regex）；预置流程骨架 | flow_generic 已用代码+params 表达流程语义——只借鉴**只读画布、解析范式下拉、流程骨架模板**，不建通用流程引擎 |

### 7.2 设计原则（所有优化的裁判标准）

1. **任务为中心**：用户心智是"我要这份数据"，不是"定义/模板/调度/参数"四概念——内部概念只在"高级模式"出现；
2. **所见即所跑**：任何"运行/重跑/手动运行/试采"入口必须携带当前上下文的参数；
3. **错误可行动**：每条报错回答"哪里错了 + 下一步做什么"；
4. **不写格式串**：JSON/cron/时间段一律控件化，高级用户保留"JSON 模式"双轨；
5. **每个空态给一条出路**：空列表/空 Dashboard 必须附带一个可点的下一步。

### 7.3 分阶段落地

#### U1：修 bug 与快赢（≈1 周，全部低成本）

| 改造 | 对应问题 |
|---|---|
| 任务列表接通服务端分页（真分页） | UX-B1 |
| 「运行」「手动运行」「从模板创建」回填 params | UX-B2/B3 |
| 编辑任务复用创建的动态表单（JSON 留作"高级模式"折叠项） | UX-B6 |
| 路由级权限守卫（requireRole 包裹 /llm /newapi /users /settings /logs） | UX-B4 |
| Dashboard 去第二套页头 + 加"新建任务"与"最近任务"入口 | UX-B5 / 旅程 A1 |
| ConfigProvider zh_CN（空态/分页/日期中文化） | 反模式 12 |
| 任务列表加状态/爬虫/关键词筛选；失败错误提供直显入口（不再只 hover） | A5 / 旅程 B |
| 「恢复」仅对 paused 任务显示；日志抽屉任务终态后停止轮询 | A6 / 反模式 19 |
| new-api 渠道过滤改名称下拉 | 旅程 E |
| 官网假统计加"示意"标注或接真实统计接口；设置页"实时同步"文案改实际行为 | UX-B7 |
| 全站动词统一（运行/重跑/存为模板/启停/删除） | 反模式 20 |

#### U2：参数与引导体验（1-2 周，对标 EasySpider 引导 + crawlab 表单化）

| 改造 | 说明 | 来源 |
|---|---|---|
| 参数校验前移 + 报错修复 | API 层按爬虫类型校验 params（JSON 合法性 + 必填 + 字段类型），错误精确到字段；修复"params 缺少 urls"误导文案 | — |
| 参数元数据补全 | `store_to/incremental/render_js/wait_for/wait_timeout` 纳入 registry fields；前端做"高级选项"折叠区 | crawlab Options 化 |
| 隐式路由显式化 | 创建表单直接呈现"列表+翻页 / 进详情"结构化区块；任务行显示"通用采集（含翻页）"而非 flow_generic | — |
| cron 快捷 preset + 下次执行预览 | preset 下拉（每小时/每天 8:00/每周一…）回填表达式，创建时显示 next_run_at | crawlab |
| 静默时段控件化 | TimeRangePicker 多段选择替代手写 `02:00-06:00` | — |
| 调度可编辑 | UI 接通后端已有 updateSchedule（改 cron/参数不必删了重建） | — |
| 预置示例模板 | 内置 3 个开箱模板：单页抽取 / 列表+翻页 / 列表→详情两跳，配真实可跑示例 + "一键试运行" | EasySpider Sample |
| pending 引导 | 任务 pending > 30s 且无活跃 worker 心跳 → 提示"爬虫执行器可能未启动"并链接节点页 | — |
| 空库 onboarding | Dashboard 空态三步引导卡（配置 LLM → 跑第一个任务 → 查看数据） | EasySpider 分步引导 |
| AI 向导加需求描述 | 表单加"想提取什么字段"文本框并入 LLM prompt（对齐官网承诺）；支持改 URL 重新规划而非重置向导 | — |

#### U3：实时性与结果体验（2-3 周，对标 crawlab）

- **WebSocket 日志 tail**（分块增量拉取 + 日志内搜索 + 整份下载），替代"共享文件 + 字节偏移"读取；日志按 task_id 归档——同时根治 6.3-5 的并发串日志与跨机失效；
- **结果单条完整预览**：展开行 JSON 树展示（含 extra/item_type/source）；
- **服务端流式导出**：数据中心导出复用按任务导出的游标实现，去 100 条隐性上限；
- **新增 `GET /spiders/tasks/{id}` 单任务端点 + 任务详情页**（进度/日志/结果三标签，crawlab 任务详情模式）；
- **error_message 结构化**：爬虫侧上报失败分类（选择器取空 / 403 反爬 / 超时 / DOM 结构变化），替代 "spider closed: finished"。

#### U4：可视化进阶（可选，按需启动）

- **选择器实时试测**（推荐先做，成本中）：输入 css/xpath → 立即显示在目标页命中的前 N 条结果预览——EasySpider"点选"的降成本替代；
- **flow 流程只读画布**：React Flow 把 params 渲染为节点图（请求→解析→翻页/详情→过滤→输出），点击节点看参数；编辑仍走表单；
- **jsonpath 解析范式**：selectors.type 增加 jsonpath 选项（spider-flow 多范式）；
- **完整点选生成选择器**（iframe 代理 + 悬停高亮 → 自动生成 css 回填）：成本高，远期评估。

### 7.4 明确不照搬（避免过度工程）

| 模式 | 来源 | 不搬原因 |
|---|---|---|
| 多节点分布式 + 跨节点文件同步 | crawlab | 自研单 FastAPI+Scrapy 已有 Redis 队列分发，引入节点体系要解决文件一致性/版本漂移，收益为零 |
| 任意语言爬虫上传执行（zip/git + 子进程执行器） | crawlab | 等于自建代码沙箱（安全/进程管理/资源隔离全套），且与"注册表+params 实例化"体系冲突 |
| 内置 MongoDB 数据底座 | crawlab | 为在线表格引入新存储不值；结果页直接查现有 MySQL/存储层 |
| Electron 内嵌浏览器执行引擎 | EasySpider | 自研是 HTTP 级 Scrapy，引入渲染引擎等于重做一个产品；只借其点选交互层 |
| 完整节点流程引擎（变量作用域/子流程/双向画布编辑） | spider-flow | flow_generic 已用代码表达流程语义，重写引擎成本极高且灵活性反而低于代码 |
| 桌面端执行器打包 | EasySpider | Web 平台形态，执行视图做成页面即可 |

### 7.5 验收标准

- **U1**：前端 build 通过；viewer 直达受限路由得到 403 页；任务翻页正确；"从模板创建/运行"参数完整回填；
- **U2**：填错 JSON 在提交瞬间得到字段级中文报错；新用户用预置模板一键跑通；创建调度全程无需手写 cron；
- **U3**：任务详情页日志实时滚动（延迟 <1s）；结果可展开查看全字段；导出突破 100 条；
- **U4**：选择器试测可可视化验证命中结果。

### 7.6 与第 5 章路线图的关系

批次 5 = U1+U2，批次 6 = U3（U4 视需求插入）。UX-B4（路由守卫）属安全相关，建议提前并入批次 2 同期完成。

---

## 8. SaaS 化升级方案：多租户与企业子账号管理

> 目标（2026-08-31 决策）：系统升级为面向企业客户的 SaaS——企业自助开通、租户内自主管理子账号。**既有四大功能模块（爬虫 / LLM 管理 / new-api 调度 / 官网后台）与既有全部演进方案（4.1 LLM 故障转移、4.2 调度接线、第 7 章易用性 U1-U4）照常实施**，本章在其上叠加租户维度。

### 8.1 现状差距（SaaS 化要还的债）

| # | 差距 | 证据 |
|---|------|------|
| 1 | **users 表无租户概念**：username/email 全局唯一，只有全局 is_admin + role | `platform_core/models/user.py`（全文 24 行，无任何组织/租户字段） |
| 2 | **业务表几乎无归属字段**：spider_tasks / spider_results / spider_definitions / spider_schedules / alert_rules / llm_providers / operation_logs 全部全局共享；仅有的两个归属字段类型还不一致（ai_plan 存用户名字符串，task_template 存用户 ID 整数） | `platform_core/models/` 全量 grep（ai_plan.py:36、task_template.py:16） |
| 3 | **后台无法管理用户**：admin 用户页只读，无创建/禁用/改密/角色分配端点 | `v1/admin.py:33,43,55`（仅 3 个 GET） |
| 4 | **注册默认 operator**：开放注册即业务操作权限 | `models/user.py` default + `deps.py:47` |
| 5 | **配额/计量缺失**：无任务数/存储/LLM token 的租户维度计量（P0-3 的用量表是唯一基础） | `llm_client.py:35` 进程内存 |

### 8.2 租户模型选型

| 方案 | 结论 |
|------|------|
| **共享库 + `tenant_id` 行级隔离（推荐）** | 单 MySQL/单 FastAPI/统一 BaseRepository 是天然的过滤收口点，改造成本最低、运维不变 |
| 每租户独立 schema | Alembic 迁移要 ×N 执行，连接池按租户路由，成本高收益低 |
| 每租户独立库 | 面向大客户隔离合规场景，可作为未来"企业版"选项，不作为起步方案 |

### 8.3 数据与权限设计

**新表 `tenants`**：

```sql
tenants (id, name, slug UNIQUE, plan VARCHAR(16) DEFAULT 'free', status VARCHAR(16),
         quota JSON,            -- {max_members, max_concurrent_tasks, max_results_mb, llm_token_monthly}
         expired_at DATETIME NULL, created_at, updated_at)
```

**users 表改造**：`+ tenant_id INT NULL`（NULL = 平台超管，现有 is_admin 用户回填 NULL）、`+ tenant_role VARCHAR(16)`（owner / admin / operator / viewer），唯一约束改 `UNIQUE(tenant_id, username)`（email 保持全局唯一）；现有全局 `role` 保留过渡期并映射到 tenant_role。

**JWT claims 扩展**：`{user_id, tenant_id, tenant_role, is_platform_admin}`；`deps.py` 的 CurrentUser 快照同步扩展，现有 `require_operator/admin` 依赖改读 tenant_role。

**两级权限模型**：

| 层级 | 角色 | 能力 |
|------|------|------|
| 平台 | super_admin（tenant_id=NULL，现 is_admin 用户） | 租户管理、套餐配额、渠道调度（newapi 保持平台级）、全局监控、审计 |
| 租户 | owner（开通者） | 本租户全部 + 子账号管理 + 成员角色分配 |
| 租户 | admin | 本租户业务全权（现 operator+ 调度/告警） |
| 租户 | operator / viewer | 同现有语义，但仅限本租户数据 |

**行级隔离实现（本仓库的天然收口点）**：

1. `platform_core/repository.py` BaseRepository 增加租户过滤——asyncpg/SQLAlchemy 侧用 `with_loader_criteria` 对声明了 `tenant_id` 的模型全局追加条件，租户上下文经 `contextvars.ContextVar` 从请求中间件（解析 JWT）注入；
2. **平台级豁免清单**（不加过滤）：tenants、system_config、channel_events、channel_probe_results、users(tenant_id IS NULL 的超管由服务层处理)；
3. 豁免之外任何 Service/Repository 直接裸查询必须在 code review + check-arch 增设红线（R13：业务模型查询必须经过租户过滤收口）。

**业务表加 `tenant_id`（一次 Alembic 迁移 + 默认租户回填）**：spider_tasks、spider_results（随 task 冗余存列，数据中心直查免 join）、spider_definitions（增加 `scope: platform|tenant`——平台预置爬虫全租户可见，租户可私有注册/AI 注册的归租户）、spider_schedules、alert_rules、task_templates（created_by 顺带统一为 user_id）、ai_plans（同前）、llm_providers（租户自带 key，见 8.5）、operation_logs。

**子账号管理 API（补齐 8.1-3 的债）**：

- 租户侧 `/api/v1/tenants/me/members`：GET 列表 / POST 创建子账号 / PATCH 角色·启停 / POST 重置密码（owner·admin 可用，配额 max_members 校验，全程审计）
- 平台侧 `/api/v1/platform/tenants`：CRUD / 套餐与配额调整 / 停启用（super_admin）
- 前端：admin 增「成员管理」页（租户角色）与「租户管理」页（平台运营台）；现有用户只读页升级为成员管理

### 8.4 与既有模块/方案的叠加关系

| 模块 | 叠加方式 |
|------|----------|
| 智能爬虫 | 任务/结果/调度/模板/告警按租户隔离；配额在 `enqueue`（并发任务数）与结果回流（存储量）两处检查，超配额返回明确的业务码 |
| LLM 管理（cc-switch 式） | `llm_providers` 租户化——**企业自带 API Key**，每租户一张注册表；4.1 的故障转移/健康巡检/**用量表**（4.1.4）照做并加 `tenant_id` 维度；免费套餐可选回退平台公共 provider（平台承担成本时必须配 token 配额） |
| new-api 调度 | 渠道是**平台基础设施**，保持平台级（4.2 照做，不租户化）；远期（S4）套餐 → 渠道组分配，租户用量经 4.1.4 表 × new-api logs 对账 |
| 官网/后台 | 官网增「企业注册/定价」页与登录入口；admin 按登录租户自动限定数据范围（无需页面改造，行级隔离兜底） |

### 8.5 分阶段落地

| 阶段 | 内容 | 依赖 | 验收 |
|------|------|------|------|
| **S1 租户基座** | tenants 表 + users 租户化 + 全业务表 tenant_id 回填（默认租户承接存量数据）+ BaseRepository 行级过滤 + JWT/两级 RBAC + 中间件注入租户上下文 | **前置：批次 1（P0 安全）与 UX-B4 路由守卫必须先完成**——多租户会放大一切越权缺口 | 越权测试套件：A 租户 token 访问 B 租户任务/结果/模板/供应商全部 403/404；pytest 全绿 |
| **S2 子账号管理** | members CRUD + 角色分配 + 禁用 + 重置密码 + 成员配额 + 前端「成员管理」页 + 审计 | S1 | 租户 admin 可自助管理子账号（补 G4）；被禁用成员 token 立即失效（或短窗内） |
| **S3 配额与用量** | 任务并发/结果存储/LLM token 三类配额 + 租户用量看板（4.1.4 用量表加 tenant 维度）+ 超限业务码与前端提示 | S1 + 批次 1 的用量表 | 超配额任务被拒且文案可行动；用量看板按租户/成员双维度 |
| **S4 能力租户化** | llm_providers 租户自带 key；平台公共 provider 兜底策略；套餐→new-api 渠道组分配（远期） | S3 + 4.1/4.2 完成 | 租户各自配 key 各自计量；平台成本可控 |
| **S5 商业化闭环** | 官网企业注册/定价页、开通流程、到期停用与降级策略、平台运营台（租户/套餐/全局监控） | S1-S4 | 企业可从官网自助开通到跑通第一个采集任务，全程无人工介入 |

### 8.6 风险与前置条件

1. **顺序硬约束**：SaaS 放大安全缺口——批次 1（P0-2 webhook 守卫等）与 UX-B4（路由级权限）必须先行；B1（未知角色默认 operator）在租户语境下改为默认 viewer（S1 一并修）；
2. **存量数据回填**：迁移必须创建"默认租户"承接现有全部数据，保证升级零感知；
3. **check-arch 增红线 R13**（业务查询必须经租户过滤收口），否则行级隔离会被后续新增代码悄悄打穿；
4. **llm_providers 密钥加密密钥**（LLM_ENCRYPTION_KEY）平台统一持有即可，无需按租户派生（Fernet 加密已是列级，租户隔离靠 tenant_id 行级）。

---

## 9. 自动化脚本保留评估（2026-08-31 决策）

### 9.1 全量盘点（11 项）

| 脚本 | 行数 | 实际职责 | 依赖关系 | 决策 |
|------|------|----------|----------|------|
| `scripts/bootstrap-db.sh` | 106 | 新环境唯一推荐入口：建库 → create_all 基线 → alembic 收口（幂等） | 内部调用 `init_db_sync.py` + alembic | **保留** |
| `scripts/check-arch.sh` | 152 | 12 红线 + 3 边界扫描（pre-commit + CI 门禁） | CI `.github/workflows` + pre-commit | **保留** |
| `scripts/init_db_sync.py` | 53 | create_all 基线建表 | **bootstrap-db.sh Step3 的内部依赖**（bootstrap-db.sh:84 直接调用） | **保留**（标注"内部依赖，勿单独使用"） |
| `scripts/migrate.sh` | 4 | alembic upgrade head 薄封装 | 无 | **保留** |
| `backend/scripts/set_admin_account.py` | — | 初始管理员创建/重置（admin/123456，**已采纳为预期设计**，见 3.3-B3） | 独立 | **保留** |
| `scripts/init-db.sh` | 11 | root 交互建库建用户，`IDENTIFIED BY '123456'` 硬编码 | 功能被 bootstrap Step1/2 覆盖（应用账号创建改文档化 SQL） | **删除** |
| `scripts/init-database.sh` | 46 | 旧"调用 Python 初始化逻辑"入口 | 被 bootstrap 收编 | **删除** |
| `scripts/start.sh` | 4 | `uv run python run_backend.py` 薄包装 | 被 `run.py backend` 取代 | **删除** |
| `scripts/start_frontend.sh` | 8 | `npm start` 直启双前端 | 被 `run.py frontend` 取代（后者有端口预检/日志前缀/npm install 兜底） | **删除** |
| `scripts/run-spider.sh` | 4 | `run_spider.py --spider $1` 薄包装 | 被 `run.py spider --spider` 取代 | **删除** |
| `.claude/hooks/*.sh` | 3 个 | AI 协作层运行时 hook（inject/guard/suggest，fail-open） | `.claude/settings.json` 启用 | **保留**（非运维脚本，属协作层契约） |

### 9.2 删除收益

1. 收敛 F5（四套 DB 初始化脚本并存 → 一入口 bootstrap-db.sh + 一个内部依赖）；
2. 自然消除 B5 的 `scripts/init-db.sh:8` 硬编码 `123456`（check-arch R2 盲区中最实质的一条——删代码优于扩扫描）；
3. 消除"README 教的命令是被弃用脚本"的口径漂移风险；scripts/ 从 9 个文件收敛到 4 个。

### 9.3 执行步骤与验收

1. 删除 5 个脚本 + 在 `run.py:7` 修正指向不存在 `scripts/bootstrap.sh` 的注释（实为 bootstrap-db.sh，即 F3）；
2. README「运维脚本」表同步为保留清单；`init-db.sh` 的"创建应用账号"职责文档化为 bootstrap-db.sh 头注释中的一段 SQL 示例（密码取自 .env，不再硬编码）；
3. 验收：`grep -rn "init-db\.sh\|init-database\.sh\|start_frontend\.sh\|run-spider\.sh\|scripts/start\.sh"` 全仓无引用；`bash scripts/bootstrap-db.sh` 幂等重跑通过；CI 三阶段绿。

---

## 10. 附录

### 10.1 测试盲区清单（回归风险最高处）

- `SpiderScheduler` 后台触发链路（`schedule_service.py:156-371`：_tick_once/_fire/动态优先级/静默时段）**零测试**——智能调度核心无回归保护
- `tasks/consumer.py` 主循环：现有测试仅覆盖 `extract_start_urls/build_start_payload` 纯函数；`_dispatch`/`_flush_batch`/`_retry_loop`（含重试回滚兜底）未测
- 爬虫中间件/管道零测试（P0-1、P0-4 正是 mock 掩盖或零覆盖所致）
- `app/middleware/`（RequestID）、`app/responses/` 分页构造器、v2 health 多数端点、alembic 迁移（无 upgrade 测试）、`admin.py` 审计过滤分页

### 10.2 值得保留的优良实践（后续重构勿误伤）

- 统一异常信封 + 4 级处理器（`platform_core/exceptions/handlers.py`），500 兜底不泄内部信息
- Redis 异步化收口（R11）执行彻底；`distributed_lock`（`queues.py:97-202`）token + Lua 原子释放/续期实现规范
- LLM 密钥 Fernet 加密 + 掩码出参 + SSRF 元数据端点恒拒绝（`schemas/llm_provider.py:41-101`）
- `deploy/newapi/` 编排（版本锁定、`:?` 必填密钥、`$$` 转义健康检查、独立网络）是仓库内最佳实践范本
- `deps.py:30-36` CurrentUser 快照规避 async 惰性加载 MissingGreenlet、`db.py:14-16` pytest NullPool——真实踩坑沉淀
- httpx 客户端统一 `trust_env=False`（`backend/services/ai_planner/llm_client.py:76-77` 等），不读系统代理环境变量——规避本机代理软件（Clash 等）劫持请求返回 502 的陷阱；与附录 10.3 的 git 代理故障同源（代码层已防，shell/git 层未防）
- uv workspace 纪律（根 venv 唯一、uv.lock 提交、.dockerignore 排敏感文件）执行到位

### 10.3 开发环境问题：git 连接 GitHub 失败（本地代理未启动）

**现象**：

```
fatal: unable to access 'https://github.com/cloudxy/auto_agents.git/':
Failed to connect to 127.0.0.1 port 7897 after 0 ms: Couldn't connect to server
```

**根因（2026-08-31 本机实测诊断）**：

- git 全局与仓库局部均**无** `http.proxy`/`https.proxy` 配置（`git config --global --get-regexp proxy` 为空）——不是 git 配置问题；
- 但 shell 环境变量 `HTTP_PROXY=http://127.0.0.1:7897`、`HTTPS_PROXY=http://127.0.0.1:7897` 存在；
- `lsof -nP -iTCP:7897 -sTCP:LISTEN` 显示**无进程监听 7897**——代理软件（Clash Verge 系，7897 为其默认混合端口）未启动，或已改用其他端口；
- git 的 HTTPS 传输由 libcurl 实现，会遵循 `http_proxy/https_proxy/all_proxy` 环境变量 → 去连一个不存在的本机代理端口。"after 0 ms"（瞬间拒绝）正是本机端口无监听的典型特征，区别于远程超时。

**与项目代码的关联**：后端 httpx 客户端已统一 `trust_env=False` 防御同类问题（`llm_client.py:76-77` 注释自述"规避本机代理软件如 Clash 劫持 httpx 请求返回 502 的陷阱"）——同一网络环境问题在工具链的另一层表现：代码层防了，shell/git 层没防。

**解决方案（已采纳约定：提交跟随系统，不固化任何代理配置）**：

**约定**：`http_proxy`/`https_proxy` 环境变量由使用者**按需开启与关闭**（代理软件开则开、关则关）；git 层面**不做任何持久化代理配置**——不设 `git config http.proxy`、不设域名级代理、不把 unset 固化进 shell rc。提交/推送时 git 自动跟随当前系统环境：变量开启时走代理，关闭时直连，无需任何额外操作。

**故障处理**（报错出现 = 环境变量与代理软件状态不一致，对齐其一即可）：

1. 需要代理 → 启动代理软件（确认混合端口 7897 与环境变量一致）；
2. 暂不用代理 → 关闭当前会话的代理变量（仅本会话，不持久化）：
   ```bash
   unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy all_proxy
   ```
3. 一次性绕过（可选，不改变任何配置）：
   ```bash
   git -c http.proxy= -c https.proxy= push
   ```

**明确不采用**的方案（与"按需开关"的使用方式冲突）：`git config --global http.https://github.com.proxy ...`（域名级固化代理）、从 `~/.zshrc` 删除 export 行（使用者需要它们作为开关）。

**验收**：`git ls-remote origin` 正常返回引用列表即恢复。

**团队预防**：将"代理变量按需开关 + git 跟随系统不固化 + 故障特征（after 0 ms = 本机代理未启动）"写入 README 开发环境章节；CI/容器内不携带这些环境变量，不受影响。

---

*报告生成：2026-08-31（第一轮：架构与缺陷审计；第二轮：易用性专项走查 + 对标 EasySpider/crawlab/spider-flow 的优化方案；第三轮：SaaS 多租户升级方案 + 自动化脚本存废决策 + set_admin_account 定性修正）· 审计方式：静态深度阅读（并行扫描 + 关键证据人工复核）· 所有行号基于当前工作区 `feature/project-structure` 分支*
