<!-- manager 落盘：2026-09-27，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# Findings：F6 项目架构（第二轮，仅审查）

## Snapshot
- 代码版本：HEAD 82259f301c060dbf411424ec8775f29944e313e1。工作区只多了未跟踪的 docs/ops/。
- 快照哈希：explore_roots 的 `git ls-files -s` sha256 为 89c7cca58e5e5648f54b200a12072a010b8433dc1d3fd1c4e01ae254a3fadeb9，由 manager 计算，这里照抄。
- packet：`.sdlc/_review/2026-09-27-project-audit-r2/F6-architecture/packets/2026-09-27-2310-review-reviewer-F6-architecture.md`
- 审查方式：只做了静态阅读和 Grep，另外看了 3 张截图（admin_newapi、admin_llm、admin_relay）。
  - 引用的执行结果都是 manager 的记录（ui-runtime-summary.md、devdb-readonly.txt）。
  - **我没有执行或复现任何一条命令。** 需要跑的检查附在文末，由 manager 执行。
  - 我是被中途要求交稿的，没核实完的地方都标了【未验证】。
- 去重：第一轮 R1、R2、R6、R7 已报的问题这里不重复。确有新证据的，会在条目里写明是补充还是升级。

**结论：共 11 条，blocker 0 / major 9 / minor 2。**

架构层面最大的问题是**运行时事实分裂**，集中在三处：
1. LLM 数据面：4 个管理面，2 套网关客户端，3 组凭据键。界面显示的「默认供应商」在默认数据面下并不参与调用。
2. 开关：有的开关没有任何代码读取，有的只在进程内存里生效，都绕过了启动期的值班联系人闸。
3. 部署：代码暗含「只能单实例」的前提，但没有写成约束，也没有强制，部署清单也撑不起目标 LLM 数据面。

---

## FINDINGS

### QA-1 LLM 路由事实源分裂：`/llm` 页标的「默认供应商」在默认数据面下不参与调用
- Dimension: 1 / 6 / 9 | Severity: **major** | 工作量: M | 核验方式：静态 + 截图

**现象**
- 截图 `admin_llm-1440.png` 显示「当前默认供应商：DeepSeek（deepseek-v4-flash）」，说明文字是「未指定模型时，默认使用该模型」，两行都是「平台」行。
- 同一时刻 `admin_newapi-1440.png`（中转站管控）显示「不可用」，提示「LLM 网关管理面不可达」。
- 运营从这两个页面判断不出 AI 规划实际走哪条路。

**触发条件**：`LLM.DATA_PLANE` 为默认值 `litellm`（`config/default/llm.yml:14`、`backend/config_consts.py:58`），且当前企业没有自己的激活供应商行。

**根因**
- `ai_planner/llm_client.py:170-181`：litellm 平面只查本企业的激活行，查不到就直接走网关。
- `llm_common/runtime.py:151-166`：`resolve_own_tenant_config` 的注释写明「不打平台公共行」。
- 平台行（tenant_id 为 NULL）只在 `DATA_PLANE=providers` 的回滚窗口里生效（`runtime.py:116-124`）。

LLM 能力现在分散在 4 个面上，各管一部分：

| 面 | 负责什么 |
|---|---|
| `/llm` | 供应商 CRUD |
| `/litellm` | 虚拟键 / spend |
| `/relay` | 租户渠道组 + 令牌 |
| `/newapi` | 实际是 LiteLLM 值班台 |

没有任何一处声明「当前 AI 规划实际走哪条路径」。

**后果**
- 运营在 `/llm` 改默认供应商或测试连接，AI 规划不受影响。
- 网关不可达时，用户只看到「平台 LLM 网关不可达」，运营却以为已经配好了 DeepSeek，排障方向会错。

**修复方案**
1. 在 `/llm` 页顶部显示当前数据面，以及平台行在这个数据面下的作用（例如「仅作网关配置导出源，需要导出并重载网关才生效」）。
2. 后端加只读端点 `GET /api/v1/llm/effective-route`，返回 `plane / source / base_url 主机 / 可达性`。
3. 长期按 Q-ARCH-2 决定平台行的去留。

**应补测试**：在 `DATA_PLANE=litellm`、只有平台行的条件下调用 `_resolve_llm_runtime_config`，断言 `source=="gateway"`；前端断言平台行带「不参与运行时」的标识。

**核验**：本地是否覆盖了 DATA_PLANE【未验证】。命令：`grep -rn DATA_PLANE config/`。

### QA-2 同一个 LiteLLM 网关有两套 admin 客户端、三组凭据键，「backend 只持虚拟 Key」这条不变量不成立
- Dimension: 4 / 6 / 7 | Severity: **major** | 工作量: M | 核验方式：静态

**现象**：两个模块各自调用网关的 admin API，两边都能签发虚拟键。

| 客户端 | 读取的配置 | 调用方 |
|---|---|---|
| `llm_gateway/_settings.py:12-21` | `LITELLM.BASE_URL` / `LITELLM.MASTER_KEY`（函数名叫 `_virtual_key`）/ `LITELLM.TIMEOUT`（60s） | `llm_gateway/admin.py` 调 `/model/info`、`/spend/logs`、`/global/spend` 及 generate_key；由 relay_service、relay_usage、channel_*、newapi_overview 使用 |
| `litellm/admin_client.py:24-36` | `LITELLM.ADMIN.BASE_URL` / `LITELLM.ADMIN.MASTER_KEY` / `ADMIN.TIMEOUT_SECONDS`（15s） | 同样调 `/key/generate`（`:51-53`） |

另有第三处：`llm_common/runtime.py:52-63` 的 `apply_proxy_route` 把 `LITELLM.ADMIN.MASTER_KEY` 当成 **chat 调用凭据**。

**触发条件**：任何一个 LiteLLM admin 功能被启用时。

**根因**
- 没有唯一的网关适配层。`config/default/litellm.yml:2` 写的「backend 只持虚拟 Key」只是注释，没有检查。
- 叫 `_virtual_key` 的键被拿去调 `/spend`、`/key/generate` 这类 admin 端点，实际拿的必然是管理员级别的密钥。【未验证：LiteLLM 各端点的鉴权级别】

**后果**
- 两处配置可能指向不同网关，或持有不同密钥，从而产生「签了键但列不出来」这类不一致。
- 管理员主密钥分散在 3 个配置键里，轮换时容易漏掉。
- chat 路径拿主密钥请求，网关侧的按键预算和审计会失效。
- R2 QA-8 报的成本闸问题会因此扩大，这是新增的一面。

**修复方案**
1. 合并为唯一的 `llm_gateway` 适配层：`LITELLM.SERVICE_KEY`（真正的虚拟键，只用于 chat）和 `LITELLM.ADMIN_KEY`（只用于 admin 调用）两个键名分开。
2. `litellm/admin_client.py` 改为委托 `llm_gateway.admin`。
3. `apply_proxy_route` 禁止使用 admin 密钥。
4. `arch.sh` 的 B4 加一条：`LITELLM.ADMIN` 只能在 `llm_gateway/admin.py` 里出现。

**应补测试**：用 httpx MockTransport 断言 chat 请求的 Authorization 等于 SERVICE_KEY，admin 请求等于 ADMIN_KEY；两者相同时启动失败。

**核验**：`grep -rn "LITELLM\.\(MASTER_KEY\|ADMIN\.MASTER_KEY\)" backend config --include=*.py --include=*.yml`

### QA-3 开关语义漂移：两个「总开关」没有读取方，`LLM.ENABLED` 在默认数据面上不生效，值班联系人启动闸因此被绕过
- Dimension: 1 / 7 / 8 | Severity: **major** | 工作量: S–M | 核验方式：静态 Grep

**现象**
- `config/default/litellm.yml:9` 的 `LITELLM.ENABLED`（注释「影子/网关总开关」）和 `:19` 的 `LITELLM.SHADOW.ENABLED`，在 backend 非测试代码里 Grep 不到任何读取。
- `CONTEXT.md:49` 声称这几个开关「默认关」。
- 实际情况是网关默认就是开的：数据面默认 litellm，而 `_gateway_runtime_config` 固定写 `enabled=True`（`llm_client.py:152-167`）。所以 `llm_chat` 在 `:456` 的 `if not cfg.enabled` 永远拦不住网关路径（`:462-467`）。

**触发条件**：默认配置（`LLM.ENABLED=false`）下，只要网关可达就会发起 LLM 调用。

**根因**
- 开关的定义、读取方和生效条件之间没有登记和校验。
- `_validate_enablement_duty_contact`（`backend/app/__init__.py:72-85`）只看 `LLM.ENABLED` 和 `POWER_MARKET.ENABLED`，不知道还有 DATA_PLANE 这条路。
- `LITELLM.ADMIN.ENABLED` 只管住了 `litellm/admin_service.py:18,59` 这一条 admin 路径；QA-2 里的另一条路径不受它控制。

**后果**
- 运营按文档关掉 LLM 后，平台仍会调用网关并产生成本，而且值班联系人没配也照样启动（Q-OPS-DUTY 闸失效）。
- 模块清单列了 24 个开关键，其中至少 3 个（LITELLM.ENABLED、SHADOW.ENABLED、墓碑 NEWAPI.ENABLED）改了没有任何效果，还会误导排障。

**修复方案**
1. 选一：让 `LITELLM.ENABLED` 成为网关路径的真正总闸（`_llm_chat_gateway` 前检查）；或者删掉它，改让 `LLM.ENABLED` 统一管所有路径。推荐后者，只保留一个用户可见的总闸。
2. 值班闸改用「是否会有真实 LLM 出站」的派生判断。
3. 新建开关登记表 `config/flags.yml`，每项记录 key、owner、默认值、读取方、到期日；`arch.sh` 加检查，yml 里的开关键必须能 Grep 到读取方。

**应补测试**：`LLM.ENABLED=false` 且 `DATA_PLANE=litellm` 时，`llm_chat` 抛 PLANNING_DISABLED，并且没有发出任何 HTTP 请求；打开 LLM 但 DUTY_CONTACT 为空时启动失败。

**核验**：`grep -rnE "LITELLM\.(ENABLED|SHADOW)" backend --include=*.py | grep -v /tests/`，预期无输出。

### QA-4 能力市场总开关只写进程内存：重启就丢、多进程之间不一致，并绕过值班闸
- Dimension: 4 / 6 / 8 | Severity: **major** | 工作量: S | 核验方式：静态

**现象**
- `PUT /api/v1/admin/power-market`（`admin.py:214-227`）调用 `set_power_market_enabled`。
- 这个函数的实现只是 `settings.set("POWER_MARKET.ENABLED", flag)`（`power_market/flag.py:20-24`），这是 backend 里唯一一处 `settings.set(`。
- 审计记录写的是「已切换」。

**触发条件**：超管在后台打开市场，之后后端重启，或者部署了多个进程或副本。

**根因**
- 需要运行时修改的业务开关没有持久化，却有现成的 `system_configs` / config_service 可用。
- 值班闸只在 lifespan 启动时校验一次（`app/__init__.py:72-85,99`）。

**后果**
- 重启后市场悄悄关闭，而审计里显示是开着的。
- 多副本下各副本的开关状态不同，公开列表时有时无。
- `OPS.DUTY_CONTACT` 为空时也能在运行时打开市场，违反「启用前必须有值班」的约束。
- 这也违背宪法「配置即代码」：运行期状态既不在配置里，也不在库里。

**修复方案**
1. 开关落库，放在 `system_configs` 的 `POWER_MARKET.ENABLED` 行；读取走带版本号的短 TTL 缓存，或者用 Redis pub/sub 失效。
2. PUT 前执行同一个值班校验，失败时返回 409。

**应补测试**：PUT 打开后新建 app 实例，GET 仍为 true；DUTY_CONTACT 为空时 PUT 返回 409。

**核验**：PUT 打开后执行 `uv run python run.py restart backend`，再 GET，预期变回 false【未验证】。

### QA-5 「只能单实例」是隐式前提，没有声明也没有强制；APP_ROLE 拆分只写了一半
- Dimension: 5 / 8 | Severity: **major** | 工作量: M | 核验方式：静态

**现象**
- 仓库里只有 `app/__init__.py:101` 一处读取 `APP_ROLE`。compose 和 runlib 都没有设置它（`docker-compose.yml:75-93`、`scripts/runlib/backend.py`），所以永远是 `all`。
- 即使设成 `api`，下面这些仍然跑在 API 进程里：
  - AI 规划和试采：`orchestrator.py:151` 在请求内 `asyncio.create_task`，`ai_planner/state.py:43-47` 的 `_spawn` 用进程内集合保存任务。
  - 启动对账 `reconcile_interrupted_plans`：没有按角色门控（`app/__init__.py:188-196`），会无条件把 planning/testing 全部置为 failed。代码自己在注释里写了「多副本部署会误伤其他副本正在执行的任务」（`state.py:112-113`）。
- 另外，retention（`retention_service.py:37,59`）和 proxy_health（`proxy_health_service.py:60`）两个循环没有 `distributed_lock`，而另外 6 个定时循环有。

**触发条件**：滚动发布时新旧两个进程并存、扩到 2 个副本以上，或者按 APP_ROLE 拆分部署。

**根因**
- 没有写成 ADR 或部署约束的「单实例」前提。
- 进程内保存的状态有：AI 计划任务、预算内存回退（R2 QA-8）、`_requeued_counts`（R2 QA-4）、市场开关（QA-4）。
- 长任务没有交给队列和 worker 执行。

**后果**
- 发新版时，新进程启动会把旧进程正在执行的 AI 计划标记为失败。
- retention 在多副本下重复执行。
- `APP_ROLE=all` 时 API、消费者、调度和巡检共用一个事件循环，一处阻塞就全部停摆。R2 QA-13 从阻塞 IO 的角度报过，这里补充故障域角度：没有隔离手段。
- 横向扩展的路径实际不可用。

**修复方案**
- 短期（S）：compose 和 runlib 显式设置 `APP_ROLE=all`，在 README/ADR 写明「当前仅支持单实例」；reconcile 移到 `_run_bg` 分支内；retention 和 proxy_health 加 `distributed_lock`。
- 中期（M）：AI 规划改成 Redis 队列加 worker 执行，用带心跳的租约行替代无条件对账（按 `updated_at` 加租约 TTL 判断孤儿）。拆出 `api`（无状态，N 副本）和 `worker`（单例，leader 锁）两个部署单元。

**应补测试**：`APP_ROLE=api` 时 lifespan 不启动任何后台组件，也不执行 reconcile；两个 worker 并发时 retention 只执行一次（fakeredis 锁）。

**核验**：`grep -rn APP_ROLE --include=*.py --include=*.yml --include=Dockerfile .`，预期只有 `app/__init__.py:101` 一处。

### QA-6 一个 Redis 实例承载需要持久的业务状态，部署却按易失缓存对待
- Dimension: 4 / 8 | Severity: **major** | 工作量: S（止血）/ M（拆分） | 核验方式：静态；运行期配置【未验证】

**现象**
- compose 的 redis 服务（`docker-compose.yml:45-61`）只有 `--requirepass`，没有 volume、没有 `appendonly`，内存上限 256m，没有设置 `maxmemory-policy`。
- 各环境只配了一个 `REDIS.DEFAULT` 实例（`config/prod/redis.yml:1-7`）。
- 同一个 DB 0 里混放了三类数据：
  - 不可丢：任务队列、结果回流、REDO、hold、死信（R2 已列）。
  - 可丢：限流计数、配额缓存、分布式锁。
  - 与计费相关：落库前的 LLM 日用量计数（`llm.yml:23-26`）。

**触发条件**：`docker compose down` 或重建容器、Redis 重启、OOM。

**根因**：没有按「持久性要求」划分 Redis 的用途，也没有规定 RPO。

**后果**
- 待执行任务、未入库的采集结果、未落库的 LLM 用量会整体丢失，计费和配额都会偏低。
- 内存打满时，默认 noeviction 会让写入失败，限流、锁、回流同时出错，故障面扩大。
- MySQL 同样是单实例，备份问题见 R6 QA-13，这里不重复。

**修复方案**
1. 止血：给 redis 挂 volume，加 `--appendonly yes --appendfsync everysec`，显式设 `maxmemory-policy noeviction`，并把内存上限调到与队列量匹配。
2. 拆分（M）：新增 `REDIS.QUEUE`（持久，AOF，noeviction）和 `REDIS.CACHE`（allkeys-lru），迁移 `platform_core/queues.py` 的键归属。
3. 在 docs/ops 写明 RPO。

**应补测试**：compose 冒烟流程：入队后 `docker compose restart redis`，队列长度不变。

**核验**：`docker compose exec redis redis-cli -a 123456 CONFIG GET appendonly`，以及 `CONFIG GET maxmemory-policy`、`docker inspect <redis> --format '{{json .Mounts}}'`。

### QA-7 能力资产域重叠：`skills` 与 `capability_assets` 双写 17 个治理字段，还有两条公开 API
- Dimension: 1 / 6 | Severity: **major** | 工作量: L | 核验方式：静态 + 已记录的只读库查询

**现象**
- `capability_service.py:15-24` 把 17 个治理列（status、score、tier、reviewed_by、similar_to 等）从 skills 复制到 asset。
- `skill_service.py:264,279` 在写 skills 后再调用 `upsert_skill_asset` / `retract_skill_assets`。
- 公开面有两套：`/public/skills*`（`public_skills.py:236-270`）和 `/public/capabilities*`（`:95-233`），各有自己的 subscribe 端点。
- 管理面也有两套：`/skills`（17 个端点）和 `/capabilities`（28 个端点）。
- 开发库里 skills 1 行，capability_assets 207 行（`devdb-readonly.txt:13,30`）。
- `skill_service.py:33` 跨包导入了 `power_market.identity._is_third_party` 这个私有函数。

**触发条件**：通过 `/skills/{name}/meta`、rescore 修改治理字段后，走没有同步的路径，或者同步失败。

**根因**
- `skill_service.py:4-6` 只说「治理真相源在 DB」，没说是哪张表。
- 统一目录（`CONTEXT.md:11`）落地之后，旧的技能域没有收缩。

**后果**
- 两张表里的 score、tier、status 可能不一致，公开页和治理页显示不同的等级。
- 两个订阅入口的计量和事件口径可能不同。
- B4 只限制 power_market 向外的依赖，不管别的模块向它的依赖，所以私有函数被跨域使用没有被拦住。

**修复方案**：按 expand-contract 分三步。
1. `capability_assets` 成为唯一的治理权威；skills 只保留技能特有字段（通过 `detail_id` 关联）。
2. 治理写入口统一收进 `power_market`；`/skills` 管理端点改为委托，`/public/skills*` 作为别名，加 `Deprecation`/`Sunset` 响应头（见 Q-ARCH-4）。
3. 迁移完成后删除 skills 表上的重复列。

**应补测试**：对同一个技能改分后，两个公开端点返回的 tier 相同；import-linter 合约禁止导入 `power_market` 的私有符号。

**核验**：`SELECT s.name,s.tier,a.tier FROM skills s JOIN capability_assets a ON a.asset_type='skill' AND a.name=s.name WHERE NOT (s.tier <=> a.tier);`【未执行】

### QA-8 凭据平面有 5 种，领域词汇表与实现冲突（中转令牌已经发给租户）
- Dimension: 1 / 4 / 6 | Severity: **major** | 工作量: M | 核验方式：静态 + 截图 + 已记录的只读库查询

**现象**：一共 5 种凭据。

| 凭据 | 来源 | 用途 |
|---|---|---|
| api-keys | `/api/v1/api-keys` | 外部数据 |
| outbound keys | `outbound_key_service.py:1-3`，FR-51/ADR-0020 | 出站拉数 |
| relay tokens | `relay_service.py:387` `gateway_admin.generate_key` | 租户网关虚拟键，由 SKU 门控（`relay_sku_gate.py:1-4`，ADR-0025） |
| litellm keys | `/api/v1/litellm/keys` | 平台自用 |
| 旧的平台静态 Key | `external_api/v1/public.py:37-39` | 退役中 |

- 同一个外部路由上有两套鉴权函数（`public.py:31-54`）。
- `CONTEXT.md:63-65` 却写着令牌「**不发给租户**」「租户渠道组 / 虚拟令牌仍待产品拍板」。
- 开发库里 `relay_tokens=2`，并有 `relay_token_call_succeeded` 事件（`devdb-readonly.txt:27,50`）。
- 截图 `admin_relay-1440.png`：平台超管看到的是租户视角的「未开通中转 / 去升级」。

**触发条件**：租户购买中转 SKU，签发令牌。

**根因**：代码引用的 ADR-0019、0020、0025 不在仓库里（R7 QA-2 已报 ADR 缺失，这里补充这 3 个编号），而仓库唯一的领域词汇表没有随之更新。

**后果**
- 「向租户出售网关令牌」这个带战略和计费性质的决定，仓库里查不到授权记录。
- 5 种凭据的签发、吊销、轮换和审计口径各不相同，增加了租户泄露面的评估成本。

**修复方案**
1. 由 operator 确认 Q-ARCH-3，然后更新 `CONTEXT.md`。
2. 建一张凭据平面表（用途、签发者、存储形式、吊销方式、到期、审计事件），放进 `docs/adr/`。
3. 旧静态 Key 定一个下线日期（R1 QA-10 已有建议，这里不重复）。

**应补测试**：凭据矩阵测试：每种 key 只能访问自己那个平面的端点，跨平面一律 401。

**核验**：静态，以及已记录的只读库查询。

### QA-9 compose 部署拓扑撑不起默认的 LLM 数据面；spider 与 LiteLLM 的接入都停留在注释里
- Dimension: 1 / 8 | Severity: **major** | 工作量: M | 核验方式：静态 + 截图

**现象**
- 默认 `DATA_PLANE=litellm`，网关地址是 `LITELLM.BASE_URL: http://127.0.0.1:4000`（`litellm.yml:10`）。
- compose 里的 backend 没有加入 `litellm-net`（`docker-compose.yml:112-120` 注释写着「Backend may join later」），容器里的 127.0.0.1 指向容器自己。所以按 compose 部署时，平台 LLM 调用全部是「网关不可达」。
- 本机截图 `admin_newapi-1440.png` 已经显示网关不可达（本机是直接进程部署，原因可能不同）。
- spider 没有 compose 服务，也没有镜像（R6 QA-14 已报），数据回流又依赖 backend lifespan 里的消费者。实际的部署单元只有一个 backend，谈不上宪法说的「独立部署」。
- `deploy/litellm/postgres-data/`（本地约 1700 个文件，已被 gitignore）是放在工作树里的网关数据库目录，里面有虚拟键和 spend。它是否会进入根目录 `docker build` 的上下文【未验证】（R6 QA-16 只提到 .env 和 config.gen.yaml）。

**触发条件**：`docker compose up`，并且用默认数据面。

**根因**：目标拓扑（backend、worker、spider、LiteLLM 四个故障域）没有落成部署清单，只存在于注释和 ADR 编号里。

**后果**：发布清单实际上无法运行目标 LLM 数据面；R6 QA-20 的 external 网络声明只有代价、没有收益。这一条在 R6 QA-20 基础上升级：不只是新机器可能启动失败，而是功能不可用。

**修复方案**
1. compose 的 backend 加入 `litellm-net`，并设置 `AUTO_AGENTS_LITELLM__BASE_URL=http://litellm:4000`；放在 profile `llm` 后面，避免新人必须先起网关。
2. 新增 `spider` 和 `worker` 两个 compose 服务（同一个镜像，不同 APP_ROLE 和命令）。
3. 把 `postgres-data` 改成 named volume，移出工作树；`.dockerignore` 加上 `deploy/`。

**应补测试**：CI 的 docker job 执行 `docker compose --profile llm up -d --wait`，然后在 backend 容器内请求 `http://litellm:4000/health/liveliness`，预期 200。

**核验**：`docker compose exec backend python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:4000/health/liveliness',timeout=3)"`，预期失败【未执行】。

### QA-10 SaaS 共享内核 `quota_service` 成了跨域枢纽，混入了 LLM 文案和计费意图
- Dimension: 6 | Severity: minor | 工作量: S–M | 核验方式：静态

**现象**
- 有 13 个非测试文件导入 `quota_service`，横跨四个域：
  - 采集：consumer、spider_task、spider_query、retention
  - LLM：llm_client、orchestrator、llm_usage
  - 计费：billing、billing_fulfill、billing API、tenant_usage
  - 中转：relay_service、relay_sku_gate
- 它里面同时放了：网关的用户文案（`quota_service.py:32-34`，`llm_client.py:132-133` 从这里导入）、时间工具（`:62`）、升级意图（`:141`）。

**触发条件**：修改任意一个域的文案或配额逻辑。

**根因**：没有把「租户权益（套餐 → 配额）」建成独立的共享内核。

**后果**：改动牵连面很大，四个域都依赖同一个文件，B4 类的边界规则无从下手。

**修复方案**：拆成 `entitlement`（套餐和配额判定，纯领域逻辑）、`user_copy`（各域文案登记）和 `platform_core.time`；import-linter 合约规定各域只能依赖 `entitlement` 的公开 API。

**应补测试**：import-linter 合约测试。

**核验**：静态 Grep。

### QA-11 域边界门禁只覆盖 5 个业务域中的 2 个，而且只查向外的依赖
- Dimension: 3 / 7 | Severity: minor | 工作量: M | 核验方式：静态

**现象**
- `arch.sh:235-257` 的 B4 只约束 `power_market` 和 `ai_planner`。采集、SaaS（租户/计费/RBAC）、LLM 数据面这三个域没有任何边界规则。
- `backend/services` 下平铺了约 70 个模块，只有 5 个包有域目录。
- 反向依赖没人检查，例如 QA-7 的 `skill_service` 导入 `power_market` 的私有函数。
- R6 QA-11 已指出 grep 行首锚定可以绕过，这里只补充覆盖面的问题。

**触发条件**：新增跨域导入。

**根因**：边界规则靠 grep 硬编码，按事后发现的问题逐条补。

**后果**：宪法「面向接口」「解耦边界」在 5 个域里只有 2 个受机械检查。

**修复方案**：用 import-linter 声明 5 个域（collection / llm / market / saas / platform），给出 layers 和 forbidden 合约，并禁止导入其他包的 `_private` 符号；先以告警加基线的方式上线。

**应补测试**：lint-imports 进 CI。

**核验**：静态。

---

## Dimensions checked
1. **标准符合** ⚠️：代码与自身声明不一致。词汇表说默认关，实际网关默认开（QA-3）；词汇表说令牌不发租户（QA-8）；注释说只持虚拟 Key（QA-2）；宪法要求独立部署（QA-9）。
2. **标准质量** ➖：这是 review-only 的架构审计，范围内没有 FR/GWT。判断依据是宪法、CONTEXT.md、代码 docstring 和 manager 给的清单。
3. **证据有效性** ⚠️：开关没有读取方校验，B4 覆盖不全（QA-3、QA-11）。arch.sh 全过是第一轮记录的执行结果，我没有复现。我的全部结论来自静态阅读和截图。
4. **安全** ⚠️：凭据分散，主密钥被当成 chat 凭据（QA-2）；值班闸被绕过（QA-3、QA-4）；凭据平面多且缺少授权记录（QA-8）；网关数据库在工作树里（QA-9）【部分未验证】。
5. **性能** ⚠️：单个事件循环没有隔离，不能横向扩展（QA-5）；Redis 内存上限和淘汰策略（QA-6）。
6. **契约一致性** ⚠️：QA-1、2、7、8、10。
7. **合规** ⚠️：「配置即代码」被运行期内存开关违反（QA-4）；「独立部署优于耦合」没有落地（QA-5、QA-9）；「面向接口」下同一网关有两套客户端（QA-2）。R1–R13 和 B1–B4 以第一轮的执行记录为准，本轮未复现。
8. **边界** ⚠️：多实例和滚动发布（QA-5）；Redis 重启或内存打满（QA-6）；进程重启（QA-4）。
9. **产品价值与体验** ⚠️：
   - 截图显示，`/llm` 标着「默认供应商 DeepSeek」，同时 `/newapi` 显示网关不可达，运营无法判断 AI 规划走哪条路（QA-1）。
   - `/relay` 给平台超管显示的是租户的「去升级」页（QA-8）。
   - 市场开关重启后失效，运营会误以为市场已经上线（QA-4）。

## Strengths
1. **依赖方向靠机械检查**：B1–B4、R13 的豁免清单单一事实源双向校验、FR-14 发布物密钥检查（`tools/check/arch.sh:180-257`）。
2. **LiteLLM 是独立的故障域**：根 compose 禁止声明 litellm 服务，只能通过 external 网络接入（`docker-compose.yml:112-120`）；禁止持有 DSN 和 create_async_engine（`arch.sh:250-257`）；HTTP 客户端设置了 `trust_env=False` 和 `follow_redirects=False`（`llm_gateway/_settings.py:43-45`）。
3. **退役纪律清楚**：`newapi.yml:1-8` 是明确的墓碑，`relay.yml:9-10` 写明「禁止第三套前缀、禁止 NEWAPI.* 当运行时」。这可以作为其他遗留面退役的模板。
4. **多实例改造已有基础**：6 个定时循环已经复用同一个分布式锁（schedule_service:234、channel_scheduler:170、channel_probe:194、llm_health_patrol:58、llm_usage:211、skill_scoring:254）；`APP_ROLE` 的切分点已经存在（`app/__init__.py:101`）；各后台组件各自开关、失败只告警。
5. **导入环用依赖注入解开**：`llm_common/seam.py:1-49` 用显式 bind/seam 替代「文件末尾 import 门面」的做法，未装配时直接抛错，不会静默拿到错值。

## Improvement themes
各阶段的风险与回滚：

| 阶段 | 内容 | 风险 | 回滚 |
|---|---|---|---|
| 阶段 0（本周，均 S） | QA-4 开关落库和值班校验；QA-3 删掉死开关或让它成为真正的总闸；QA-5 显式 `APP_ROLE=all`、reconcile 按角色门控、retention 和 proxy_health 加锁；QA-6 Redis 加 volume 和 AOF | 低 | 每项单独 revert；AOF 可以在线 `CONFIG SET appendonly no` |
| 阶段 1（M） | T2 的 LLM 数据面收敛；compose 接入 litellm-net（profile） | 网关凭据切换可能导致 401 | 保留旧键名只读兼容一个发布周期，`DATA_PLANE=providers` 作为回滚窗口 |
| 阶段 2（M–L） | 进程拆分：api（N 副本）+ worker（单例 + leader 锁）+ spider 镜像；AI 规划改走队列；Redis 拆成 QUEUE 和 CACHE | 消息迁移和双消费 | worker 与 all 共存期间用 leader 锁互斥；回滚时 compose 改回 `APP_ROLE=all` |
| 阶段 3（L） | 能力资产收敛（QA-7）；import-linter 五域合约；队列迁移到 Streams | 公开 API 变更 | 别名期同时保留两个路径，删除重复列放在最后一步 |

1. **T1 运行时拓扑显式化**（QA-5、6、9）
   - 目标：部署单元为 api / worker / spider / litellm；每个单元的故障域、副本数和 RPO 写进 ADR。
   - 顺序：显式单实例 → Redis 持久化 → compose 接入网关 → 拆 worker → AI 规划改走队列。
2. **T2 LLM 数据面单一事实源**（QA-1、2、3）
   - 目标：一个网关适配层；两个键 SERVICE_KEY / ADMIN_KEY；一个总闸；页面上能看到实际生效的路由。`/newapi` 改名为 llm-ops（R1 QA-9），`litellm/admin_client` 合并进去。
   - 顺序：凭据分离 → 总闸统一 → effective-route 端点和页面提示 → 合并客户端。
3. **T3 开关治理**（QA-3、4）
   - 目标：`config/flags.yml` 登记每个开关的 owner、默认值、读取方和到期日；需要运行时修改的开关一律落库；arch.sh 校验每个开关都有读取方。
   - 顺序：登记表 → 死开关清零 → 落库 → 门禁。
4. **T4 能力资产域收敛**（QA-7、11）
   - 目标：`capability_assets` 为唯一治理权威，`/skills` 退为别名，import-linter 五域合约。
   - 顺序：写入口统一 → 别名加 Sunset → 删除重复列 → 合约由告警转为阻断。
5. **T5 SaaS 共享内核与凭据平面**（QA-8、10）
   - 目标：拆出 `entitlement` 共享内核；凭据平面表入 ADR；词汇表与实现一致。
   - 顺序：Q-ARCH-3 拍板 → 更新 CONTEXT.md → 拆 quota_service → 凭据矩阵测试。

## Open questions（战略，待 operator 确认，未默认采用）
- **Q-ARCH-1 部署形态**
  - (a) 声明只支持单实例，并用启动锁强制；
  - (b) 拆成 api 与 worker，api 多副本；
  - (c) 维持现状。
  - **推荐**：近期 (a)，中期 (b)。现状（c）在滚动发布时就会误杀 AI 计划。
- **Q-ARCH-2 `/llm` 平台供应商行在 litellm 数据面下的定位**
  - (a) 只作为 LiteLLM 配置的导出源（`litellm/exporter.py` 已存在），页面注明「需要导出并重载才生效」；
  - (b) 退役平台行，只保留企业自带供应商；
  - (c) 回到 providers 数据面。
  - **推荐** (a)。前提是 exporter 确实读取 llm_providers【未验证】。
- **Q-ARCH-3 中转 SKU 向租户出售网关令牌，是否已获产品授权？**（CONTEXT.md:63-65 写的是未拍板，代码和开发库已经在签发）
  - (a) 已授权：补 ADR-0025 入库并更新词汇表；
  - (b) 未授权：用开关关闭 `/relay/tokens` 签发。
  - **推荐**：先确认；确认前按 (b) 默认关闭签发。
- **Q-ARCH-4 `/public/skills*` 公开 API 是否可以退为 `/public/capabilities` 的别名，并设 Sunset？** 推荐可以，别名保留 2 个迭代。
- **Q-ARCH-5 Redis 里的待执行任务和未入库结果，RPO 是多少？** 推荐「任务和结果不可丢，缓存可丢」，以此决定 QA-6 的拆分方案。

## 需要 manager 执行的验证（我都未执行）
1. QA-3：`grep -rnE "LITELLM\.(ENABLED|SHADOW)" backend --include=*.py | grep -v /tests/`（预期无输出）；`grep -rn DATA_PLANE config/`
2. QA-4：`curl -X PUT :9111/api/v1/admin/power-market -d '{"enabled":true}'`（用超管 token），再 `uv run python run.py restart backend`，然后 GET，预期 false。
3. QA-5：`grep -rn APP_ROLE --include=*.py --include=*.yml --include=Dockerfile .`
4. QA-6：`docker compose exec redis redis-cli -a 123456 CONFIG GET appendonly`；`CONFIG GET maxmemory-policy`
5. QA-7：执行 QA-7 里的 JOIN 查询，比较两张表的 tier。
6. QA-9：在 compose 的 backend 容器里请求 `http://127.0.0.1:4000/health/liveliness`；`grep -n "deploy" .dockerignore`

## Decisions
- 只做审查，没有推进任何状态，也没有替 owner 做决定。
- 严重度按「影响 × 可达性」判断。没有定 blocker：这些问题在默认配置下不会造成数据越权。QA-3 和 QA-4 如果在生产开启后被触发，影响的是成本和值班约束。

## Product-delta
- 无（产品层未建立）。

## Lessons（已由静态证据证实）
- 用 `settings.set` 修改 Dynaconf 只影响当前进程，不能当作运行时业务开关（`power_market/flag.py:23`）。
- 一个开关写在 yml 里、文档称其为「总开关」，却没有任何读取方，比没有这个开关更危险（`litellm.yml:9`，backend 里 Grep 不到）。
- 新增数据面时，如果对该路径固定写 `enabled=True`，原来的启用闸和依赖它的启动校验会一起失效（`llm_client.py:163,456-462`、`app/__init__.py:72-85`）。
