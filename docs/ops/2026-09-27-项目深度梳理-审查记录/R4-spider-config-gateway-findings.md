# Findings — R4-spider-config-gateway（爬虫、配置体系与 LLM 网关部署）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(scrapy config deploy capability-library) + inputs → sha256 1dad2ae708e0…（97 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R4-spider-config-gateway.md
- 方式：静态阅读（全部 inputs、scrapy 全部 .py，另读 `spiders/generic.py`、`flow_generic.py`、`skill_harvester.py`、`zhihu_feed.py`、`dianping_home.py`、`deploy/litellm/{.env.example, config.yaml.example, README.md}`、`deploy/newapi/{.env.example, TOMBSTONE.md}`、根与子目录 .gitignore）；为核对契约少量读切片外 `backend/services/spider_task_service.py:500-551,760-789`、`backend/tasks/consumer.py:237-262` 并在 `backend/tests` 按类名搜测试；已记录执行只引 `evidence/arch.txt`、`ruff.txt`、`ruff-extended.txt`；reviewer 未复现任何命令，运行期结论均为静态推理。
- 首轮触达 24-turn 上限，经 manager 要求基于已读内容交付。未读：`config/scrapy/*/settings.yml`、`config/scrapy/default/sites.yml`、`config/prod/{log,mysql,redis,web,llm}.yml`、`config/default/newapi.yml`、`deploy/newapi/docker-compose.sqlite.yml`、`deploy/newapi/README.md`、`capability-library/adapters|index|backend`、`spiders/example.py`、`spiders/openweather.py`、`.github/workflows`、`.dockerignore`、`platform_core/logger`——依赖它们的结论标「未核实」。

**summary**：21 条（0 blocker——QA-3 可能升级；10 major QA-1..QA-10；11 minor）。最高风险三处：任务控制语义错误且跨任务/跨租户误伤（QA-1、2）；通用爬虫缺出站边界（QA-3）；配置与编排缺省时静默放行（QA-6..9）。`arch.txt` 红线全绿，但反爬红线实质上被 Playwright 路径与分布式放大突破（QA-4、10）——现有门禁以检查「配置存在」为主，需升级为行为检查。

---

## FINDINGS

### QA-1 任务「暂停」实际丢弃请求，超过 30 秒被当成「完成」收尾，无法恢复
- Dimension: 8 边界 / 9 产品价值 | Severity: **major** | 工作量: M
- Evidence：`scrapy/middlewares/__init__.py:461-463` pause 时 `raise IgnoreRequest()`，请求永久丢弃、不回队列，docstring（404）却写「爬虫继续运行，等待 resume」；`scrapy/extensions/__init__.py:196-214` IdleAutoClose 空闲达 `IDLE_CLOSE_SECONDS` 后以 `"finished"` 收尾；`scrapy/settings.py:108` 默认 30 秒；`extensions/__init__.py:100` finished 映射 completed；后端 pause 键 TTL 3600（`backend/services/spider_task_service.py:764,785`），到期后暂停静默失效。
- 后果：用户暂停超 30 秒 → 队列被排空 → 任务上报 `completed`、结果只剩部分数据；之后点「恢复」因任务已不在 running 被拒（`spider_task_service.py:775-776`）。暂停/恢复对用户说的是假话。
- Suggestion：pause 改为「挂起」而非丢弃（请求重放回 scheduler 并延迟重试，或 middleware 按任务维度把请求 park 到 Redis）；IdleAutoClose 判定空闲时排除仍持有 pause 键的任务；补 `TaskControlMiddleware` 单测「pause → 空闲 → 不应 completed」（`backend/tests` 目前搜不到该类名）。

### QA-2 「终止」一个任务会关掉整个爬虫实例，同实例并发的其他任务（可能是别的租户）被判失败并自动重跑
- Dimension: 8 边界（权限/隔离）/ 9 | Severity: **major** | 工作量: M
- Evidence：`middlewares/__init__.py:457-460` `engine.close_spider(spider, reason="user_stopped")` 关整个实例；`extensions/__init__.py:79-109` 对本实例见过的所有 task_id 统一回调同一 status，`user_stopped` 映射 `failed`（:100）；`config/default/settings.yml:49` `SPIDER_MAX_CONCURRENT_PER_SPIDER: 2`；后端对 failed 自动重试（`spider_task_service.py:519-551`）；被终止任务本身要靠 `consumer.py:244-247` 才落 failed，中间先回 pending 绕一圈。
- 后果：A 终止自己的任务 → 同实例 B 任务被判 failed 并从头重爬、结果重复入库、消耗 retry_count（跨任务、可能跨租户干扰）；用户看到「失败」而非「已终止」；`SCHEDULER_PERSIST=True`（`settings.py:54`）使未完成请求留在 Redis，下次 worker 重生后可能继续处理已终止任务残留请求（**未核实**，需集成测试）。
- Suggestion：stop 改为按任务粒度——丢弃该 task_id 请求并单独回调该任务，状态用 `stopped/cancelled`；仅当实例无其他活跃任务时才 close_spider；webhook 契约新增 `cancelled` 终态，后端不自动重试。

### QA-3 generic / flow_generic 对任务参数中的 URL 与正则完全信任：SSRF 回显与 ReDoS 风险
- Dimension: 4 安全 / 8 | Severity: **major**（若租户能提交 generic/flow 任务升 blocker，**未核实**） | 工作量: M
- Evidence：`scrapy/spiders/generic.py:30`、`flow_generic.py:79` 注释明写「不做域名白名单限制」；`flow_generic.py:85` 只查 http(s) 前缀；详情页/翻页链接任意跟随（`flow_generic.py:148,176`）；抽取结果回流入库（`utils/selector_engine.py:67-75`）可带回内部响应内容；任务参数正则直接 `re.findall` / `re.compile`（`selector_engine.py:42`、`flow_generic.py:56`），在 reactor 线程执行。
- 后果：可读 `127.0.0.1:9111`（backend）、`127.0.0.1:4000`（LiteLLM，其安全假设正是只绑回环）、`169.254.169.254` 云元数据等内网目标并经结果回显；一条灾难性回溯正则即可卡死整个 worker reactor，同实例任务一起停摆。
- Suggestion：downloader middleware 做出站校验——DNS 解析后拒绝 private/loopback/link-local/metadata，每次重定向重新校验；后端建任务时同样校验（两层兜底）；正则改 `re2` / `regex` 并设超时、限制表达式长度。
- 待核实：`grep -rniE "169\.254|is_private|ipaddress|ssrf|allowed_host" backend/`，以及租户角色能否调用 generic/flow 任务创建 API。

### QA-4 Playwright 渲染路径绕过全部反爬红线（延迟、并发、UA、代理）
- Dimension: 7 合规（反爬是底线）/ 4 | Severity: **major** | 工作量: M
- Evidence：`scrapy/middlewares/playwright_dm.py:132-161` 在 downloader middleware `process_request` 直接返回 Response 的 Deferred——发生在请求进入下载槽之前，`DOWNLOAD_DELAY` 与 `CONCURRENT_REQUESTS_PER_DOMAIN` 不生效（对 Scrapy Downloader 结构的静态推断）；`_render_page` 用 `new_context()` 未传 UA、`meta['proxy']`、cookies（117-120），实际发出 HeadlessChrome 默认指纹；任务参数 `render_js` 可由用户打开（`flow_generic.py:97-103`）；日志用 `%s`/`%d` 风格（102-106,157），若 `platform_core.logger` 是 Loguru 参数会被丢弃（**未核实**）；`_active_pages` 写了没人读（49,116,130）。
- 后果：JS 渲染请求以无延迟、无头指纹、直连方式打目标站，最易被封，也违反宪法「没有反爬策略的爬虫是 DDoS」。
- Suggestion：渲染改在下载槽内执行（自定义 download handler 或接 scrapy-playwright），保留延迟与并发语义；context 继承请求 UA/proxy/cookies；日志统一 `{}` 风格；补测试「render_js 请求仍受槽位延迟约束」。

### QA-5 scrapy 侧 Redis 访问全为同步且无超时，在 Twisted reactor 里阻塞；宣称的缓存未实现；结果队列无背压
- Dimension: 5 性能 / 8 | Severity: **major** | 工作量: M
- Evidence：`from_url` 均无 `socket_timeout`（`middlewares/__init__.py:171,187,426`、`pipelines/__init__.py:60`、`extensions/__init__.py:56`、`utils/redis_client.py:20`）；TaskControl 声明 `_CACHE_SECONDS=2` 与 `_cached_at`（411-416）从未使用，每个带 task_id 的请求都 GET 一次 Redis；ProxyMiddleware 每请求 HGETALL（206-222）、每响应 hget + 2×hset（224-259），每次刷新代理池新建客户端（187-191）；StorePipeline 在 `process_item` 里 `time.sleep` 退避（128）；`rpush` 结果队列无长度上限（120），与 scheduler 共用 `REDIS.DEFAULT`（`settings.py:56`）。
- 后果：Redis 网络分区或变慢时整个 reactor 无限阻塞（心跳、空闲收尾、回调全停，难诊断）；高并发吞吐被逐请求 RTT 拖垮；后端消费者宕机时队列无限增长，最终 OOM 共享 Redis。
- Suggestion：统一经 `utils/redis_client` 取客户端，设 `socket_timeout` / `socket_connect_timeout` 并复用；控制键真正做 2 秒缓存；代理评分本地缓存 + 批量写回；退避改非阻塞（`deferLater`）或放线程池；推送前检查 `LLEN`，超阈值暂停调度或告警。

### QA-6 Dynaconf 实际优先级与 docstring 相反：`.env` 覆盖真实环境变量
- Dimension: 6 契约一致 / 4 | Severity: **major** | 工作量: S
- Evidence：`config/__init__.py:9-16` 写「6. 环境变量 AUTO_AGENTS_* —— 最高优先级」；同文件 `:51` `dotenv_override=True`（Dynaconf 语义：`.env` 值覆盖已有环境变量）；`config/prod/.env` 在磁盘存在（Glob 可见，未读内容）。
- 后果：运维经容器/平台注入的 `AUTO_AGENTS_*`（如密钥轮换）被磁盘上过期 `.env` 静默覆盖，轮换「看起来成功」实际未生效。
- Suggestion：改 `dotenv_override=False`（环境变量优先，与文档一致）；加优先级单测。
- 待核实：临时目录构造 `Dynaconf(envvar_prefix="AUTO_AGENTS", dotenv_path=<tmp>/.env, load_dotenv=True, dotenv_override=True)`，`.env` 写 `AUTO_AGENTS_PROBE=file`，同时导出 `AUTO_AGENTS_PROBE=env`，打印 `settings.PROBE`。

### QA-7 环境选择「失败即放行」：`APP_ENV` 缺失静默落到 local；环境身份有两个来源
- Dimension: 4 / 8 | Severity: **major** | 工作量: S
- Evidence：`config/__init__.py:22` `os.getenv("APP_ENV", "local")`；`config/default/settings.yml:17` `ENVIRONMENT: "local"`，`config/prod/settings.yml:1-13` 未覆盖 ENVIRONMENT（其他 prod yml 未读，**未核实**）；`config/default/jwt.yml:6` `SECRET_KEY: "change-me-in-production"`，守卫是否拒绝、是否受环境开关控制 **未核实**。
- 后果：生产漏设 `APP_ENV` 时加载 local 的 MySQL/Redis/.env 并正常启动、不报错；若守卫按 ENVIRONMENT 判断还可能一并被绕过。
- Suggestion：`APP_ENV` 只允许 {local, dev, prod}，非法值拒启，容器镜像强制显式设置；删 `ENVIRONMENT` 键、统一由 `APP_ENV` 派生；密钥占位守卫不分环境无条件生效（local 告警、非 local 拒启）。
- 待核实：`grep -rn "ENVIRONMENT" config/ backend/app platform_core | head -30`，并定位 JWT 守卫。

### QA-8 LiteLLM compose 密钥缺失时回退到公开默认值，与 newapi 已采用的 `:?` 强制写法相反
- Dimension: 4 安全 | Severity: **major** | 工作量: S
- Evidence：`deploy/litellm/docker-compose.yml:43` `LITELLM_MASTER_KEY:-sk-CHANGE_ME_MASTER`、`:44` `LITELLM_SALT_KEY:-sk-CHANGE_ME_SALT`、`:42,75` `POSTGRES_PASSWORD:-changeme`；对照 `deploy/newapi/docker-compose.yml:52-53` `${SESSION_SECRET:?...}`；`.env.example:13-14,21` 占位值也能被原样接受启动；SALT「设一次，不可当普通回滚」（`.env.example:11-12`）。
- 后果：`.env` 缺失、命名错误或复制后未改 → 网关以公开 master key 与 salt 启动，provider 凭据被公开 salt 加密、事后轮换代价高；回环绑定只挡远程，挡不住本机进程与误配反代。
- Suggestion：三个变量改 `${VAR:?...}` 强制必填；entrypoint 或 CI 检查拒绝 `CHANGE_ME` 与中文占位；`arch.sh` FR-14 段加「compose 密钥禁止默认值」红线。

### QA-9 导出器把上游明文 Key 写进仓库工作树，与「yaml 不得写明文 Key」约定矛盾
- Dimension: 4 / 6 | Severity: **major**（取决于 `.dockerignore`，**未核实**） | 工作量: S–M
- Evidence：`config/default/litellm.yml:13` 注释「含明文 key」，路径 `deploy/litellm/config.gen.yaml`；`deploy/litellm/README.md:255` 说明导出结果含明文 Key；与 `config.yaml.example:3`、`.env.example:32`「Do not put plaintext keys in either file」矛盾；该文件目前在工作树真实存在（Glob 可见，未读内容）；README §八 要求轮换「曾出现在已跟踪生成配置里的上游凭据」——说明之前已泄露过一次。
- 后果：FR-14 只保证不被 git 跟踪；明文 Key 仍可能随 docker build context、备份、打包外泄。
- Suggestion：导出器默认生成 `os.environ/<NAME>` 引用，另生成 env 注入清单放到 `0600` 仓库外路径；明文模式改显式 `--plaintext` 并输出到仓库外；`.dockerignore` 排除 `deploy/**`。
- 待核实：`grep -n "config.gen\|deploy" .dockerignore`。

### QA-10 分布式下按域名实际速率随 worker 数线性放大；反爬策略整体偏薄
- Dimension: 7 合规 / 3 | Severity: **major** | 工作量: M
- Evidence：`DOWNLOAD_DELAY` 为进程内按槽位生效（`settings.py:30`），scrapy-redis 多 worker 并行时无全局按域名限流；`config/prod/settings.yml:8` 生产延迟 0.5（比默认 1 更激进，无理由说明；`config/scrapy/prod/settings.yml` 可能覆盖，**未核实**）；`ROBOTSTXT_OBEY` 默认 False（`settings.py:35`）；未启用 AutoThrottle；`CONCURRENT_REQUESTS_PER_DOMAIN=16` 写死（`settings.py:28`）；UA 池硬编码在代码、为 2023 年 Chrome/120、桌面与 iPhone 混用、每请求随机切换（`middlewares/__init__.py:90-95,111-112`），无配套 `sec-ch-ua` / `Accept-Language`。
- 后果：N 个 worker 时目标站实际约 N×2 req/s；陈旧 UA 与逐请求切换本身就是明显机器人特征；门禁 R5/R6 只查「配置存在」（`arch.txt:8-9`），是空心断言，全过且发现不了 QA-4 的绕过。
- Suggestion：引入基于 Redis 的全局按域名令牌桶；启用 AutoThrottle，prod 延迟不得低于 default；robots 策略做成站点级显式配置（见 Q-4）；UA 池外置到配置并定期更新，同站点同会话保持 UA 不变并配齐请求头；R5 升级为行为检查（如对 settings 做 import 断言）。

### QA-11 两个 RetryMiddleware 都挂 550，行为依赖同优先级注册顺序；可重试状态码两处定义不一致；429 抬高的延迟永不回落
- Dimension: 6 / 1 | Severity: minor | 工作量: S
- Evidence：`settings.py:65` 自定义 550 与 Scrapy 内置 `RetryMiddleware:550` 并存、内置未置 None；`settings.py:44` `RETRY_HTTP_CODES` 含 408，`middlewares/__init__.py:337` `RETRY_STATUSES` 不含；`:385` 只上调 `slot.delay` 从不回落。
- 后果：重试语义由 Scrapy 内部排序偶然决定；408 由谁处理不透明；一次 429 后该站点在实例剩余生命周期内维持最高 60 秒延迟。
- Suggestion：显式 `"scrapy.downloadermiddlewares.retry.RetryMiddleware": None` 由自定义中间件承担异常重试（或反之只保留内置并子类扩展）；状态码只保留一份定义；延迟做衰减。

### QA-12 账号会话 cookie 注入在默认配置下不生效；与「会话体系未实现」说法自相矛盾
- Dimension: 1 / 6 | Severity: minor | 工作量: S
- Evidence：`settings.py:36` `COOKIES_ENABLED` 默认 False → CookiesMiddleware 不加载、`request.cookies` 被忽略（`middlewares/__init__.py:77-78`；`config/scrapy/*` 是否覆盖 **未核实**）；`spiders/base.py:60-63` 称「账号会话体系未实现」，但 `AccountSessionMiddleware` 已注册在 250；`utils/session_manager.py:16-27` 明文存 cookie、无 TTL、key 不在 `platform_core.queues` 命名空间。
- 后果：需登录站点（如 `zhihu_feed`）静默产出 0 条；会话凭据在 Redis 长期明文存放。
- Suggestion：要么完成能力（站点级 `COOKIES_ENABLED` + 会话 TTL + 会话失效 fail-fast），要么把中间件与 session_manager 标为实验性、暂不注册。

### QA-13 关闭路径同步阻塞；pipeline 里抛 `CloseSpider` 是否被 Scrapy 接受（待核实）
- Dimension: 3 / 8 | Severity: minor（疑问） | 工作量: S
- Evidence：`pipelines/__init__.py:111-113` 在 `process_item` 里 `raise CloseSpider(...)`——Scrapy 历来只在 spider 回调处理 CloseSpider，pipeline 里抛出可能只被记为「Error processing」（**未核实**）；`extensions/__init__.py:139-153` 在 `spider_closed` 里同步 `httpx.post`（timeout 10s）并 `time.sleep(2)` 共 3 次，每任务最多阻塞约 36 秒。
- 后果：若 CloseSpider 不生效，P1-4 修复所称「停止采集，防止继续静默丢数据」不成立，退化为「连续丢数据」。
- Suggestion：改用 `crawler.engine.close_spider_async(reason=...)` 主动关闭；回调放线程池。
- 待核实：`backend/tests/test_scrapy_store_pipeline.py` 是否有断言引擎被关闭的用例，或用 `scrapy.utils.test.get_crawler` 实跑一次。

### QA-14 scrapy 不在 CI lint 范围；scrapy 测试寄居 backend，关键中间件与管道无测试
- Dimension: 3 | Severity: minor（若 scrapy 内存在 F821 升 major） | 工作量: S
- Evidence：`evidence/ruff.txt:1` CI 等价命令只查 `backend platform_core scripts`；`ruff-extended.txt:1,15` 纳入 scrapy 后共 4753 条，其中 F821 10 条（归属未核实）；`scrapy/pyproject.toml:17-20` 声明 pytest 但 scrapy 下无 tests 目录；`backend/tests` 搜不到 `TaskControlMiddleware`、`CleanPipeline`、`QualityCheckPipeline`、`UserAgentMiddleware`、`AccountSessionMiddleware`、`PlaywrightMiddleware` 的测试。
- 后果：QA-1、4、12 这类缺陷无任何门禁拦截。
- Suggestion：CI lint 纳入 `scrapy`（至少 `F`）；新建 `scrapy/tests/` 并从 `backend/tests` 迁入相关测试；为上述 6 个组件各补一个行为测试。

### QA-15 已退役 new-api 编排仍可一键启动且默认值不安全
- Dimension: 4 / 7 | Severity: minor（退役件） | 工作量: S
- Evidence：TOMBSTONE 写明「不是运行时，不要 up」（`deploy/newapi/TOMBSTONE.md:3-8,19-26`；compose 第 27 行）；但 compose 仍可启动且：`NEWAPI_BIND:-0.0.0.0`（`docker-compose.yml:39`，与 `.env.example:50` 的 127.0.0.1 相反）、`SESSION_COOKIE_SECURE:-false`（`:56`，与 `.env.example:44` 的 true 相反）、初始账号 root/123456（`:10-11`）、`mysql:8.0` 浮动版本线且注释自写 2026-10 EOL（`:18-20,75`，即下个月）、`--requirepass` 出现在命令行（`:100`，`docker inspect` 可见）；`config/default/newapi.yml` 仍在，是否死配置 **未核实**。
- 后果：误执行 `up` 会在全网卡以弱口令暴露整个管理面。
- Suggestion：L5 退役时直接删 compose（git 历史即文物）；必须保留则所有服务加 `profiles: ["retired"]`、密钥改 `:?`、默认绑回环；同步清理 `newapi.yml`。

### QA-16 镜像只按 tag 锁定；README 记录的 digest 属于另一个仓库
- Dimension: 3 / 7 | Severity: minor | 工作量: S
- Evidence：`deploy/litellm/docker-compose.yml:31` 拉 `ghcr.io/berriai/litellm:v1.100.0`，README 第 6 行记录的是 docker.io `litellm/litellm` 的 digest，与实际仓库不一致；postgres 同样只锁 tag（`:70`）。
- 后果：tag 被重推或供应链被篡改无法察觉；文档「已核对 digest」不能证明实际运行的镜像。
- Suggestion：compose 改 `image@sha256:<ghcr digest>`；`guard.py` 或版本守卫测试同时断言 digest。

### QA-17 看门狗开启自动重启时缺少重启预算，依赖故障时会反复杀 backend
- Dimension: 8 | Severity: minor | 工作量: S
- Evidence：`deploy/watchdog.sh:271-276` 处置后计数清零重新计数 → 每 FAILURES×INTERVAL（默认 30 秒）再触发；深探测在 MySQL/Redis 故障时同样失败（`:26-28` 自认）；无最大重启次数、无指数退避。
- 后果：`WATCHDOG_RESTART=1` 下数据库宕机被放大为 backend 每 30 秒重启一次，掩盖根因。
- Suggestion：增加 `WATCHDOG_MAX_RESTARTS` / 时间窗与退避；能区分探测结果时，依赖故障（503 且 body 标明依赖失败）只告警不 kill。

### QA-18 capability-library README 与实现漂移；sync.sh 先产生副作用后校验参数
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：`capability-library/README.md:1` 声明 8765 后台已退役，正文 `:42-43,63-64,67-73,81` 仍把 `--serve` 与后台功能当可用流程描述；`sync.sh:23-28` 先执行全部 adapters，`:30-45` 才解析参数 → `--serve` 或拼错参数会先分发再报错；README `:91-92` 写 adapter 会写入 `~/.claude/skills` 与 `~/.codex/...`，与 82259f3「插件 skill 只在本项目生效」冲突（adapter 脚本未读，**未核实**）；内容真相源（meta.yaml）与治理真相源（DB）双写回写（`:5-7`），有一致性风险。
- Suggestion：README 删退役章节；sync.sh 先校验参数再执行；adapter 只写项目级目录；meta.yaml 与 DB 加一致性对账命令。

### QA-19 scrapy 内死配置、错误语义与文档漂移
- Dimension: 6 / 1 | Severity: minor | 工作量: S
- Evidence：`settings.py:22,24` `SITE_CONFIG` 与 `SPIDER_SITES` 同值；`FingerprintMiddleware` 称「辅助去重」实际只打日志（`middlewares:391-397`）；`CleanPipeline` docstring 写「脱敏」但未实现，且把所有文本字段换行压成空格（`pipelines:21,26`）；在 spider 回调里抛 `DropItem`（`generic.py:52`、`flow_generic.py:191`，这是 pipeline 语义，在回调会被记为 spider error）；generic 与 flow_generic 继承 `RedisSpider` 而非 `TaskAwareRedisSpider`（`generic.py:25`、`flow_generic.py:74`），站点级延迟（`base.py:45-64`）对它们不生效；`dianping_home.py:17` 自称「逻辑演示」却作为正式爬虫注册；`pyproject.toml:12-13` 声明 selenium、drissionpage，已读文件未见使用（**未核实**），实际用到的 Playwright 却未声明；`scrapy/README.md` 只有一行、无运维手册。
- Suggestion：一次性清理；generic/flow_generic 改继承 `TaskAwareRedisSpider`；`DropItem` 改 `return` + 统计；README 补队列契约、反爬配置、新增爬虫步骤与本地运行方式。

### QA-20 Redis 连接串中的密码未 URL 编码，也不支持 TLS
- Dimension: 8 | Severity: minor | 工作量: S
- Evidence：`config/__init__.py:69-70` 直接拼 `f"redis://{auth}{host}:{port}/{db}"`。
- 后果：密码含 `@ / : # %` 时连错主机或认证失败，报错难懂（LiteLLM `.env.example` 对 Postgres 专门提醒了此类问题，这里没有）。
- Suggestion：`urllib.parse.quote(password, safe="")`；`SSL: true` 时用 `rediss://`。

### QA-21 LiteLLM master key 配置键名三处不一致（待核实）
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：`deploy/litellm/README.md:12-13,161,171-173` 与 `config/default/litellm.yml:5` 注释写 `LITELLM.MASTER_KEY`（`AUTO_AGENTS_LITELLM__MASTER_KEY`），yml 实际只定义 `LITELLM.ADMIN.MASTER_KEY`（`:23`）；`BASE_URL` 也有两份（`:10` 与 `:22`）。
- 后果：运维按 README 设键、代码读另一个键 → Admin 客户端静默拿到空 key。
- Suggestion：键名只留一个，README / yml 注释 / 代码三处对齐，加配置契约测试。
- 待核实：`grep -rn "MASTER_KEY" backend/services/litellm backend/app | head`。

---

## Dimensions checked
1. 标准符合 ⚠️ — 多处 docstring 承诺与实现不符（QA-1 暂停、QA-5 缓存、QA-6 优先级、QA-12 会话、QA-19 脱敏）。
2. 标准质量 ⚠️ — 无 GWT；按「行为是否可测」判断，关键控制路径无测试（QA-14）；与 GWT 对照 ➖（review-only，无 spec 输入）。
3. 证据有效 ⚠️ — arch/ruff 记录有命令与退出码可采信；R5/R6 为只查「配置存在」的空心断言（QA-10）；CI lint 未覆盖 scrapy（QA-14）。
4. 安全 ⚠️ — SSRF 与 ReDoS（QA-3）、compose 密钥回退公开默认值（QA-8）、明文 Key 在工作树（QA-9）、退役件默认值（QA-15）、会话明文存放（QA-12）。
5. 性能 ⚠️ — reactor 内同步 Redis 无超时无背压（QA-5）；Playwright 并发不受槽位约束（QA-4）。
6. 契约一致 ⚠️ — QA-6、11、18、19、21。
7. 合规 ⚠️ — `arch.txt` R1–R13、B1–B4、FR-14、PL 全过；「反爬是底线」实质被 QA-4、QA-10 突破；「配置即代码」UA 池硬编码（QA-10）；「爬取与存储分离」✅；「scrapy 禁止 import backend」✅（R3、B2）。
8. 边界 ⚠️ — 暂停/终止/并发任务（QA-1、2）；Redis 挂起（QA-5）；超大或恶意正则（QA-3）；密码特殊字符（QA-20）。
9. 产品价值 ⚠️ — 无截图与产品层，按用户/运维可见 API/CLI 语义：「暂停」变「完成」、「终止」变「失败并重跑、殃及他人」，直接损害任务控制可信度；账号型爬虫静默 0 条（QA-12）。

## Strengths（改进时应保留）
1. 爬取与存储分离扎实：`StorePipeline` 只写 Redis `ITEM_QUEUE`、带重投与熔断；内置 `RedisPipeline` 被禁用并写明理由（`scrapy/settings.py:76-79`、`pipelines/__init__.py:40-129`）；`arch.txt:6-7,20` R3、R4、B2 通过。
2. 密钥卫生有机械门禁：`.gitignore` 忽略 `config/**/.env`、只白名单 `prod/.env.example`（`.gitignore:38-42`）；FR-14 门禁（`arch.txt:28-30`）；`prod/.env.example:5-10` 讲清 Dynaconf 键名规范与 `${}` 不展开的坑。
3. 网关按故障域独立部署：独立 compose/网络/Postgres，默认绑回环，Postgres 不发布端口，镜像 tag 锁定并注明查阅日期，有健康检查与日志轮转（`deploy/litellm/docker-compose.yml:14-19,34-36,52-67`）；B4 禁止 `LITELLM.DB_DSN`（`arch.txt:25`）。
4. 看门狗的安全缺省与演练经验：默认只告警、告警冷却、kill 前 SIGTERM 排空、支持 dry-run、把 bash 3.2 的坑写进注释（`deploy/watchdog.sh:25-51,159-231`）。
5. 爬虫侧防御性细节：翻页上限封顶（`flow_generic.py:35-37,65-71`）；重试有上限、修复了 P0-1（`middlewares/__init__.py:325-371`）；task_id 经 meta 精确归属（`:35-48`）；QUALITY_CHECK 用平铺键并解释了 Scrapy Settings 的坑（`settings.py:86-97`）。

## Improvement themes

| # | 主题 | 目标状态 | 覆盖 | 落地顺序 |
|---|---|---|---|---|
| T1 | 任务控制与生命周期正确性 | pause/resume/stop 按单任务生效；终态区分 completed / failed / cancelled；终止不影响同实例其他任务；关闭路径不阻塞 | QA-1, 2, 13, 11 | 1️⃣ 最先：直接影响用户可见语义与跨租户隔离；先补测试固定问题（红）再修 |
| T2 | 不可信任务输入的出站边界 | 出站前 DNS 解析 + 拒绝名单（含重定向）；正则有超时；render_js 路径与普通下载共用限流/UA/代理 | QA-3, 4 | 2️⃣ 与 T1 并行；先核实租户能否提交 generic/flow 任务以定 blocker/major |
| T3 | 配置默认即安全（fail-closed） | APP_ENV 白名单并强制设置；环境变量优先于 .env；compose 密钥 `:?`；导出器不产明文；键名唯一；Redis URL 编码 | QA-6, 7, 8, 9, 20, 21 | 3️⃣ 多为 S 级，可一次 PR 打包，并在 `arch.sh` 加「compose 密钥禁止默认值」红线 |
| T4 | reactor 安全的 I/O 与反爬治理 | Redis 客户端统一、有超时、有缓存、有背压；全局按域名令牌桶 + AutoThrottle；UA 外置到配置 | QA-5, 10 | 4️⃣ 需设计全局限流（M），用压测与 Redis 故障注入验证 |
| T5 | 门禁与文档说真话 | scrapy 纳入 CI lint 与 tests；R5/R6 行为级检查；清理死配置死代码；README 与实现对齐；删除或封存退役 new-api；镜像锁 digest；看门狗有重启预算 | QA-12, 14, 15, 16, 17, 18, 19 | 5️⃣ 贯穿全程；CI 纳入 scrapy 应最先做（T1–T4 回归底座） |

## 返回给 manager 的验证请求（reviewer 未执行）
1. Dynaconf 优先级探针（QA-6，见条目）
2. `uv run ruff check scrapy --select F821,F811,F841`（QA-14）
3. `grep -n "config.gen\|deploy" .dockerignore`（QA-9）
4. `grep -rniE "169\.254|is_private|ipaddress|ssrf|allowed_host" backend/`，并确认 generic/flow 任务创建 API 的角色限制（QA-3）
5. `grep -rnE "COOKIES_ENABLED|ROBOTSTXT_OBEY|DOWNLOAD_DELAY|AUTOTHROTTLE" config/scrapy/`（QA-10、12）
6. `grep -rn "ENVIRONMENT" config/prod/ backend/app platform_core | head -30` + 定位 JWT 占位守卫（QA-7）
7. `grep -rn "MASTER_KEY" backend/services/litellm backend/app | head`（QA-21）
8. `get_crawler` 实跑 StorePipeline 连续推送失败，确认 CloseSpider 是否真的关闭引擎（QA-13）
9. `grep -rn "loguru" platform_core/logger*`（QA-4 日志格式）
10. `grep -rniE "selenium|drissionpage" scrapy --include=*.py`（QA-19）

## Decisions
- 审查员不做决策；唯一操作性默认：严重度 = 影响 × 可能性，依赖未核实事实的条目已写明升降级条件。

## Open questions
- **Q-1（generic/flow 目标 URL 是否对租户开放）** a) 仅平台超管；b) 租户可用、平台强制出站边界；c) 租户可用、仅白名单域名。建议 b；无论哪个，内网拒绝名单必须实现。
- **Q-2（「暂停」产品语义）** a) 真挂起可恢复；b) 取消「暂停」只留「终止」；c) 暂停有时限、到期自动取消并如实告知。建议 a，成本高时退回 b，不能保留现状。
- **Q-3（new-api 目录）** a) 立即删除、历史留 git；b) 保留但加 `profiles: retired` 与 `:?` 守卫。建议 a（与 L5 退役一起）。
- **Q-4（robots.txt 默认策略，涉及法务与品牌，属战略）** a) 默认遵守，站点级显式豁免并注明理由；b) 维持默认不遵守。建议 a；本审查不替业务方决定。

## Product-delta rows
- 无（docs/product 未建立）。

## Lesson rows
- 无经执行验证的陷阱。「downloader middleware 在 process_request 返回 Response 会绕过槽位延迟」为静态推断，验证后可沉淀。
