<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# Findings：B4 能力市场（第二轮 · G-fresh · 只读）

## 快照
- HEAD 82259f301c060dbf411424ec8775f29944e313e1，工作区只新增了 docs/ops/。explore_roots 的 sha256 是 manager 算的 405943133d99cb4951c0aa3b3b3467ef125eadd5a0fb403271a3b4716b0fe5bf，这里照抄，我没有重新计算。
- Packet：/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/B4-capability-market/packets/2026-09-27-2310-review-reviewer-B4-capability-market.md
- 我实际做了什么：
  - 读了 packet 的全部必需输入和 4 张截图（都打开看过）。
  - 为定位根因，用 Grep 和局部 Read 查了这些文件：`deps.py`、`admin.py`、`tenant_signup_service.py`、`member_service.py`、`skill_service.py`、`skill_import_service.py`、`capability_service.py`、`plugin_service.py`、`power_market/{installs,flag,types,listing,agents_hub}.py`、`market_events.py`、`platform_core/models/capability.py`、`app/__init__.py`、`Dockerfile`、admin 端的 `CatalogTab.tsx`、`Capabilities.tsx`、`marketCopy.ts`。
  - 核验方式只有两种：静态检查，以及查看 manager 已记录的执行（截图、ui-runtime-summary、devdb-readonly）。我自己没有复现任何东西。需要跑命令核验的写在文末。
- 去重：R5 QA-1（上传时 FormData 被转成 JSON）和 R7 QA-3（导入写进 `.agents` 中枢）已经报过，本报告不重复。QA-2 是对 R5 第 5 维「`capabilities.ts:43` 固定 50，未见无界请求」的更正和升级。只拿到了 R5/R7 两份，其它 R* 没读，QA-6 请 manager 去重。

**摘要**：共 12 条。blocker 1 条（QA-1），major 5 条（QA-2 到 QA-6），minor 6 条。

---

## FINDINGS

### QA-1 自助注册的企业 owner/admin 能通过 `require_admin` / `require_operator`，可以改平台全局技能库，还能让服务器去请求任意 URL（SSRF）
- Dimension: 4 安全 / 7 合规 / 8 权限边界 | Severity: **blocker** | 工作量: S（换守卫）+ M（SSRF 白名单）
- **现象**：`/api/v1/skills` 下的写接口只按 `user.role` 判权限，不区分平台和企业。
- **触发条件**：
  1. `POST /api/v1/public/tenant/signup` 自助注册（`module-inventory.md:153`）。
  2. 用 owner 账号登录。
  3. 直接调这些接口：`PUT /skills/{name}/meta`、`PUT /skills/manifests`、`POST /skills/import-url`、`PUT /skills/similar-confirm`、`POST /skills/similar-suggest`、`POST /skills/{name}/rescore`、`POST /skills/{name}/export-meta`、`GET /skills/{name}/check-update`。
- **根因**：
  - 注册时 owner 被写成 `role="admin"`（`backend/services/tenant_signup_service.py:93`）。
  - 企业成员里的 admin/owner 也映射成 `role="admin"`（`member_service.py:106,137`）。
  - `require_role` 只检查 `user.role in roles`（`backend/app/api/deps.py:132-140`），`require_admin = require_role("admin")`、`require_operator = require_role("admin","operator")`（`:145-146`）完全不看 `is_platform_admin`。
  - `skills.py` 里对应的守卫：`:59-77`（import-url）、`:89-99`（manifests）、`:114-137`（similar）、`:232-293`（rescore / meta / export-meta / check-update）。
  - `correct_meta` 会改 status（包括 blacklist）和 score，然后写回 meta.yaml 并追加 CHANGELOG（`skill_service.py:299-301,714,731-734`）。`update_manifest` 会写清单文件（`:653`）。
  - SSRF：`import_url` 的非 GitHub 分支直接 `client.get(url)`（`skill_import_service.py:114-128`）。客户端 `follow_redirects=True`（`:44-46`），没有主机白名单，也不拦内网或链路本地地址。出错时把 HTTP 状态码和 URL 原样返回（`:125`），可以拿来当内网端口探测。
- **后果**：任何自助注册的企业都能把平台技能拉黑或降分，影响所有企业的货架；能往平台技能库写文件；能反复触发 rescore / similar-suggest，消耗平台的 LLM 费用；还能探测内网（LiteLLM、元数据地址 169.254.169.254 等）。企业隔离边界没有任何缓解措施，而且改动不可逆，按 STRIDE 规则定为 blocker。
- **修复方案**：
  1. `skills.py` 里所有平台全局写接口，以及 `/skills/jobs`、`/skills/manifests` 的 GET，统一改成 `require_platform_admin_or_404`，和 `capabilities_gov.py` 保持一致。
  2. 把 `require_admin` 改名为 `require_tenant_admin`，避免误用。
  3. `arch.sh` 新增一条规则：在全局资源路由（skills / capabilities / configs）里禁止使用 `require_admin` / `require_operator`。
  4. SSRF：只允许 `github.com`、`api.github.com`、`raw.githubusercontent.com`、`codeload.github.com` 这几个主机。解析 DNS 后拒绝私网、回环和链路本地地址。关闭自动重定向，或者每一跳重新校验。错误信息统一成通用句子。
- **应补测试**：
  - 用企业 owner 的 token 调上面 8 个接口，都应返回 404。
  - `import_url` 对 `http://127.0.0.1`、`http://169.254.169.254`、以及 302 跳到内网的 URL，都应拒绝。
- **核验方式**：静态。复现不需要改数据：
  - 用企业 token 调 `PUT /api/v1/skills/__nonexistent__/meta`，body `{"review_notes":"x"}`。返回 404「技能 … 不存在」说明守卫已放行（正确行为应是 404 同形或 403）。
  - 用企业 token 调 `POST /api/v1/skills/import-url`，body `{"url":"ftp://x"}`。返回 422「url 必须是 http(s)」同样说明守卫已放行。

### QA-2 后台治理目录和插件、命令、智能体、专家团各页签只拉前 50 条，界面上的「共 50 条」其实是请求上限
- Dimension: 8 超量边界 / 9 | Severity: **major** | 工作量: S–M
- **现象**：截图 `admin_capabilities-1440.png` 显示「共 50 条」、分 1/2/3 页。开发库里 `capability_assets` 有 207 行（`devdb-readonly.txt:8`，这是 information_schema 的估算值，含软删行）。
- **触发条件**：存活资产超过 50 条，或者某一类型超过 50 条。
- **根因**：
  - `listAssets` 固定 `page_size: 50`，不传 page（`frontend/admin/src/services/capabilities.ts:40-44`）。
  - `CatalogTab.tsx:65-66` 丢掉了服务端返回的 `data.total`，`:129-130` 在前端对这 50 行分页。
  - `marketCopy.ts:46-50` 的 `showTotal` 显示的是本地行数。
  - 同样的问题：`TypeLeafTab.tsx:36`、`PluginTab.tsx:38`、`TeamLeafTab.tsx:71-72`（专家团成员选择器也只有前 50 个）。
- **后果**：第 51 条以后的资产在界面上无法上架、下架、设精选或维护示例。运营看到的总数是错的。组建专家团时选不到后面的专家和智能体。
- **修复方案**：改成服务端分页。Table 的 `onChange` 把 page / page_size 传给后端，总数用 `data.total`。改用 `useQuery` 加 `keepPreviousData`，并加上搜索框（后端已经支持 `q`）。
- **应补测试**：
  - 服务层单测：`listAssets` 会带上 page 参数。
  - 页面测试：mock 的 total=207 时显示「共 207 条」，点第 2 页会发出 page=2 的请求。
- **核验方式**：截图加静态。manager 跑一条 SQL：`SELECT COUNT(*) FROM capability_assets WHERE deleted_at IS NULL;`，结果大于 50 即成立。

### QA-3 市场总开关只存在进程内存里：重启就回到关闭，而且绕过了启动时的值班联系人检查
- Dimension: 1 / 7 / 8 | Severity: **major** | 工作量: S–M
- **现象**：超管在后台打开「能力市场」后，后端只要一重启（发布、崩溃后拉起、`run.py restart`），开关就静默回到 yaml 里的 `false`。
- **根因**：
  - `set_power_market_enabled` 只调用了 `settings.set(...)`（`backend/services/power_market/flag.py:20-24`）。
  - `PUT /admin/power-market` 没有落库，只写了审计（`admin.py:214-227`）。
  - 启动时的 `_validate_enablement_duty_contact` 要求打开市场前必须配置 `OPS.DUTY_CONTACT`（`app/__init__.py:72-85`），但运行时 PUT 不做这个检查。
  - 部署是单进程（`Dockerfile:60`、`runlib/backend.py:85`）。以后如果改成多 worker，各 worker 的开关状态会不一致。
- **后果**：官网突然显示「能力市场未开放」，订阅返回 409 MARKET_CLOSED，没有任何告警。审计记录写着「已打开」，和实际状态不符。没配值班联系人也能在运行时开市，违反了启用前置条件。
- **修复方案**：开关的真相源放到 `system_configs`（表已存在），读取时加短 TTL 缓存。PUT 时复用启动时的值班联系人检查。审计记录前后值。GET 返回值的来源（yaml 还是 runtime）。
- **应补测试**：
  - PUT true 后重新加载 settings，再 GET 仍为 true。
  - 值班联系人为空时 PUT true，应被拒绝。
- **核验方式**：静态。复现会改开发环境状态，由 manager 决定是否执行：PUT true，然后 `uv run python run.py restart backend`，再 GET 应为 false。

### QA-4 企业登录用户可以绕过上架闸和市场开关，读取未上架、黑名单、已软删资产的治理详情；资产一旦有软删「孪生行」，详情接口直接 500
- Dimension: 4 / 6 / 8 | Severity: **major** | 工作量: S
- **现象**：
  - `GET /capabilities/{t}/{n}`、`/capabilities/plugins/{n}`、`/experts/{n}`、`/teams/{n}`、`/teams/{n}/export` 只要求登录（`capabilities.py:141-150,176-234,414-441`）。
  - 列表接口却对企业只返回货架（`:57-61`），两者口径不一致。
- **根因**：
  - `capability_service.py:106-115` 的 `get_asset` 不过滤 `deleted_at`，不检查上架态和治理态，用的是 `scalar_one_or_none`。`plugin_service.py:48-77` 同样如此，并且会返回 `mcp_servers` 和 `verify_detail`。
  - 唯一约束是 `(asset_type, name, alive_flag)`（`platform_core/models/capability.py:102`），允许同名的软删行和存活行并存。
  - `agents_hub._load` 只找存活行（`agents_hub.py:271-278`），所以「清理失源（prune）后再同步」会新插一行，旧的软删行留着，形成孪生行。
- **后果**：
  - (a) 企业可以读到未上架或黑名单资产的 score、ai_suggested_score、similar_to、source_url、sync_state，以及插件的 MCP 配置。市场关闭时也能读。这和「隐藏未上架资产」的要求矛盾。
  - (b) 出现孪生行后，上面两个详情接口会抛 MultipleResultsFound，返回 500，超管也打不开。
- **修复方案**：
  - 查询都加 `deleted_at IS NULL`；兼容老数据时用 `order_by(id.desc()).first()`。
  - 非超管改走 `PowerMarketService.get_public`（带上架闸和市场开关），或者直接改成 `require_platform_admin_or_404`。
  - 对非超管隐去 `mcp_servers` 的 env 值。
- **应补测试**：
  - 企业用户 GET 一个 unlisted 资产，应返回 404。
  - 构造孪生行 fixture，GET 应返回存活那一行（200）。
- **核验方式**：静态。manager 跑 SQL：`SELECT asset_type,name,COUNT(*) c FROM capability_assets GROUP BY asset_type,name HAVING c>1;`，有结果就用 curl 请求该行的详情看是否 500。

### QA-5 目录导入确认时先写磁盘、后写数据库，且没有逐项 savepoint：任何一项数据库出错都会让整批入库回滚，但文件已经留在 .agents 里
- Dimension: 1 / 8 并发 | Severity: **major** | 工作量: M
- **现象**：docstring 里写的「单项失败不整批回滚（GWT-07.5）」只对文件层面的失败成立。
- **触发条件**：两个并发的 confirm 导入同一个资产（撞唯一约束），或者任一项 flush 失败。
- **根因**：
  - `hub_import.py:228-243` 的循环里先 `_land`（写盘，`:287-290` 是合并式覆盖），再 `_upsert_item_listing`，而后者内部会 flush（`agents_hub.py:236-237`）。
  - except 分支没有回滚，也没用 savepoint，session 进入失败状态，后面每一项都以 PendingRollbackError 记为 failed。
  - 最后 `:243` 的 flush 抛错，路由里的 `rollback`（`capabilities_gov.py:191-204`）把整批数据库写入撤掉，但已写的文件不会撤回。
- **后果**：磁盘和数据库不一致，被覆盖的文件无法恢复；前端看到的失败原因是 PendingRollbackError 这类不相关的报错。
- **修复方案**：
  - 每一项包在 `async with session.begin_nested()` 里。
  - 改成先写数据库、commit 成功后再原子 rename 落盘；或者记录已落盘的路径，失败时回滚。
  - 用 Redis 锁把导入串行化。
- **应补测试**：
  - 故障注入：第 2 项 upsert 抛 IntegrityError，第 1、3 项应成功，第 2 项计入 failed，且磁盘上没有第 2 项的文件。
  - 并发执行两次 confirm。
- **核验方式**：静态。

### QA-6 公开接口的限流按客户端可伪造的 X-Forwarded-For 计数；匿名 GET 每次都写 1–3 行 product_events，且没有缓存
- Dimension: 4 / 5 | Severity: **major** | 工作量: S–M
- **根因**：
  - `_client_ip` 无条件信任 XFF 头（`public_skills.py:51-55`）。
  - 限流的 INCR 和 EXPIRE 不是原子操作（`:67-69`）；Redis 出错时直接放行（`:74-75`）。
  - 每次列表或详情请求都会发事件（`:127-132,222-229,265`），`market_events.py:100-127,213-225` 最终都会插一行 product_events。
  - 查询里有前导通配的 LIKE 加子查询（`service.py:133-146`），每次都是全表扫。
  - 已落库的例子：market_list_viewed 87 行（`devdb-readonly.txt:38`）。
- **后果**：换 XFF 就能无限请求，每次都要做 COUNT 加全表扫再加 INSERT。product_events 表会膨胀，增长指标被污染。匿名用户的搜索词原样存进事件。
- **修复方案**：
  - 只信任已配置的代理网段（uvicorn `--proxy-headers --forwarded-allow-ips`），否则用 `request.client.host`。
  - 限流改成 `SET NX EX` 加 INCR，或用 Lua 保证原子。
  - list_viewed 事件改为按 anonymous_id 去重或抽样。
  - 匿名列表加 `Cache-Control: public, max-age=30`，并用 Redis 缓存页面，缓存键包含查询参数和开关状态。
- **应补测试**：
  - 同一客户端换不同 XFF 连续请求，超过上限应返回 429。
  - 100 次列表 GET 产生的事件数应不超过采样上限。
- **核验方式**：静态。复现命令：`for i in $(seq 1 70); do curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-For: 10.0.0.$i" http://127.0.0.1:9111/api/v1/public/capabilities; done | sort | uniq -c`，预期全部是 200，说明限流被绕过。

### QA-7 同名的 agent 和老类型 expert 同时存活时，公开详情、订阅和治理写接口都会 500
- Dimension: 6 / 8 | Severity: minor | 工作量: S
- **根因**：
  - `_load_named` 用 `asset_type IN (agent, expert)` 加 `scalar_one_or_none` 查询（`service.py:426-439`，类型映射见 `types.py:9-15,142-144`）。`listing._load_asset` 也是同样写法（`listing.py:44-55`）。
  - 唯一约束是按具体 asset_type 分开的（`capability.py:102`），所以两种类型可以同名并存。
- **修复方案**：优先取规范类型那一行，用 `.first()`；或者做一次迁移，把老类型改成规范类型。
- **核验方式**：静态。manager 跑 SQL：`SELECT name FROM capability_assets WHERE deleted_at IS NULL AND asset_type IN ('agent','expert') GROUP BY name HAVING COUNT(*)>1;`

### QA-8 平台超管以平台企业身份拥有「我的安装」和订阅能力，和代码里写明的边界相反
- Dimension: 1 / 8 | Severity: minor | 工作量: S
- **证据**：
  - `deps.py:156-157` 注释写「不给超管开渠道组/我的安装等企业产品空间」。
  - 但 `installs.py:71-76` 只检查 `tenant_id is None`，超管挂在平台企业下，检查能通过。
  - 截图 `admin_capabilities_installs-1440.png` 里平台超管看到「还没有安装」和「去能力市场」按钮；`ui-runtime-summary.md:46` 显示这个页面没有 4xx。
- **后果**：超管的订阅会记到平台企业名下，污染 market_subscribe_succeeded 口径；界面在引导一个本不该存在的流程。
- **修复方案**：按 Q-3 的决定执行。推荐：`_require_tenant` 拒绝 `is_platform_admin`，同时对超管隐藏菜单。
- **核验方式**：截图加静态。

### QA-9 市场关闭时官网只剩死胡同，后台也看不出「已上架」的资产对外不可见
- Dimension: 9 | Severity: minor | 工作量: S
- **证据**：
  - 截图 `official_skills-1440.png` 和 `official_capabilities-1440.png`：顶部导航的主入口就是「能力市场」；关闭状态下页签、搜索、宿主、分类控件都还能操作；「返回首页」是浏览器默认的蓝色下划线链接，没用设计系统样式（`official/src/pages/Capabilities.tsx:180` 只替换了列表区域）。
  - 截图 `admin_capabilities-1440.png`：每行都选着「已上架」，全局开关「关」在左上角，行内没有任何「对外不可见」提示。
  - 默认配置 `power_market.yml:3` 是 `ENABLED: false`。
- **推断（未验证）**：market_list_viewed 最后一条是 09-16，official_page_viewed 一直到 09-27 还有（`devdb-readonly.txt:38-39`），可能说明市场关闭后访客仍在进入官网。
- **修复方案**：
  - 关闭时隐藏导航入口，或改成「即将开放」落地页并加留资或通知的 CTA（见 Q-2）。
  - 关闭时禁用筛选控件；链接改用设计系统的 Button。
  - 后台目录顶部加横幅「市场关闭中：已上架 N 项对外不可见」。
- **核验方式**：截图。

### QA-10 导入接口先把整个 multipart 读进内存，再检查文件数和大小
- Dimension: 5 / 8 | Severity: minor | 工作量: S
- **证据**：
  - `capabilities_gov.py:140-149` 的 `_read_parts` 先把所有 part 全部 `read()`，文件数检查在之后（`hub_import.py:184-186`）。
  - `capabilities.py:259` 的 `/import` 也一样。
  - 部署是单进程（`Dockerfile:60`）。
- **后果**：超管误选一个大目录（比如 node_modules），可能把后端进程内存撑爆（OOM），整个 API 挂掉。
- **修复方案**：先检查 `len(files)`；逐个 part 用 `read(MAX_FILE_BYTES+1)` 限量读取；在反向代理或 ASGI 层设置请求体上限。
- **核验方式**：静态。

### QA-11 治理目录里显示原始 ISO 时间（带微秒、没有时区）
- Dimension: 9 | Severity: minor | 工作量: S
- **证据**：截图里显示「最近上架 2026-09-14T09:45:04.535066」；后端直接 `isoformat()` 输出（`capability_service.py:58`）。
- **修复方案**：前端统一格式化为本地时间 `YYYY-MM-DD HH:mm`。
- **核验方式**：截图。

### QA-12 几处小的契约不一致
- Dimension: 6 | Severity: minor | 工作量: S
- **证据**：
  - (a) 企业调 `GET /capabilities`：参数声明 `page_size ≤100`（`capabilities.py:52`），但 `list_public` 超过 20 就报 422（`service.py:392-398`、`types.py:31`）。
  - (b) `detail_opened` 事件记的是请求里的名字，用别名访问时记的是别名而不是规范名（`public_skills.py:227`），同一资产的访问统计会被拆开。
  - (c) meta 校正失败时 `field="url"`，字段名写错了（`skills.py:264`）。
- **修复方案**：Query 的上限对齐为 20；事件改用 `data["name"]`；field 改成 `payload`。
- **核验方式**：静态。

---

## Dimensions checked
1. 标准符合 ⚠️：GWT-07.5 只在文件层面成立（QA-5）；「超管不开企业空间」与实现相反（QA-8）；开关的启用前置条件被绕过（QA-3）。
2. 标准质量 ➖/⚠️：没有 spec 输入；现有测试在服务层 mock 掉了请求（R5 已报），分页、孪生行、跨企业守卫都没有反例测试（QA-1、2、4）。
3. 证据有效性 ⚠️：用的是 manager 记录的截图、运行期摘要和库查询；我自己没有复现任何东西，需要执行的核验见下文。
4. 安全 ⚠️：QA-1（blocker：跨企业越权 + SSRF）、QA-4、QA-6、QA-10。路径清洗和出口收容做得扎实（见 Strengths）。
5. 性能 ⚠️：QA-6（前导通配 LIKE、每次请求都写事件、没有缓存）、QA-10；安装列表不分页，目前规模可以接受。
6. 契约一致性 ⚠️：QA-4、QA-7、QA-12；上架闸在列表和详情之间口径不一致。
7. 宪法合规 ⚠️：「配置即代码」——开关只在内存里，不可追溯（QA-3）；「日志即证据」——service 入口都有 logger，满足；B1–B4 依赖方向在本切片没有发现违规。
8. 边界 ⚠️：超量 QA-2、QA-10；并发 QA-5；权限 QA-1、QA-4、QA-8；空态和关闭态都有处理（但见 QA-9）。
9. 产品价值与体验 ⚠️：按截图判断。默认关闭时官网主导航通向死胡同（QA-9）；后台目录总数失真（QA-2）；时间格式（QA-11）；没有企业负责人视角的截图，货架、订阅、安装主路径的界面效果**未验证**。

## Strengths
1. 上架闸在查询层先过滤再做 COUNT / LIMIT；种子谓词用 coalesce 避开了 NULL 三值逻辑的坑（`service.py:91-121,400-424`）。
2. 平台治理接口统一用 404 同形隐藏存在性，并记录越权审计（`deps.py:190-206`，`capabilities_gov.py` 全部接口）。
3. 目录导入入口做路径清洗，出口做 `assert_contained` 收容，更新用合并覆盖而不是 rmtree（`hub_import.py:61-69,262-290`）。
4. 订阅靠唯一约束加 IntegrityError 实现幂等；安装的改和删都按企业范围查询（`installs.py:111-155,210-222`，`capability.py:224-227`）。
5. 破坏性操作都要显式开启：源同步默认不收回（`capabilities.py:96-119`），清理失源支持 dry_run（`capabilities_gov.py:57-84`）；路由注册顺序的约束写在了文件头。

## Improvement themes
1. **平台和企业两套权限分开**（QA-1、4、8）。目标：全局资源只允许平台超管写；企业角色和平台角色用不同名字；每个路由都有企业负例测试。顺序：先换 skills 的守卫（S，立即做）→ 修 SSRF 白名单（M）→ arch 门禁禁止在全局路由里用 `require_admin`（S）→ 根据 openapi 自动生成企业负例测试矩阵（M）。
2. **市场开关持久化，关闭态做成可用的产品状态**（QA-3、9）。目标：开关真相源在库里，并受值班联系人前置条件约束；关闭时官网有明确的落地页，后台有横幅提示。顺序：落库和前置检查（S–M）→ 关闭态界面（S）。
3. **导入的事务一致性**（QA-5、10）。目标：逐项 savepoint，先写库后原子落盘，流式读取并限量。顺序：限量读取（S）→ savepoint 加落盘顺序调整（M）→ 并发锁（S）。
4. **公开接口防护和指标可信**（QA-6、12b）。目标：可信的客户端 IP、原子限流、事件去重或抽样、匿名列表缓存。顺序：代理头和限流（S）→ 事件抽样（S）→ 缓存（M）。
5. **治理台数据完整**（QA-2、4b、7、11、12）。目标：服务端分页和搜索；查询统一过滤存活行，孪生行不再导致 500。顺序：查询加存活过滤（S）→ 服务端分页（S–M）→ 老类型迁移（M）。

## 需 operator 决定的事项（战略，待确认）
- **Q-1** 企业用户能不能读平台技能库（`/skills` 列表和详情）以及治理详情？A：全部改为平台专属（**推荐**）；B：企业只读，但要经过上架闸和市场开关。
- **Q-2** 市场关闭时官网要不要显示入口？A：隐藏导航和首页入口（**推荐**）；B：保留入口，改成「即将开放」落地页加留资。
- **Q-3** 平台超管能不能以平台企业身份订阅？A：禁止，与 `deps.py:156-157` 一致（**推荐**）；B：允许，并写进契约。
- **Q-4** 市场开关的真相源放哪？A：`system_configs` 持久化（**推荐**）；B：只认 yaml，去掉运行时开关。
- 运营性默认：无。本轮只出报告，没有替任何人应用默认决定。

## 需 manager 代跑的验证
1. QA-1（不改数据）：注册一个临时企业并拿到 token $T，然后：
   - `curl -s -X PUT -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"review_notes":"x"}' http://127.0.0.1:9111/api/v1/skills/__nonexistent__/meta`
   - `curl -s -X POST -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"url":"ftp://x"}' http://127.0.0.1:9111/api/v1/skills/import-url`
   - 如果分别返回「技能…不存在」和「url 必须是 http(s)」，说明守卫已被放行，QA-1 成立。
2. QA-2：`SELECT COUNT(*) FROM capability_assets WHERE deleted_at IS NULL;`
3. QA-4：`SELECT asset_type,name,COUNT(*) c FROM capability_assets GROUP BY asset_type,name HAVING c>1;` 有结果就 curl 对应详情看是否 500；再用企业 token 请求一个 unlisted 资产的 `GET /api/v1/capabilities/skill/<name>`。
4. QA-6：上面 QA-6 里的 XFF 循环命令。
5. QA-7：上面 QA-7 里的 SQL。
6. QA-3（会改运行态，由 manager 决定）：PUT /admin/power-market true，重启后端，再 GET。

## Product-delta
- 无（docs/product 产品层不存在）。

## Lesson rows（只记已核实的陷阱）
- 平台和企业共用一个 `users.role` 命名空间时，`require_role("admin")` 会放行企业 owner。已核实 `tenant_signup_service.py:93` 和 `deps.py:146`。
- 唯一约束 `(type, name, alive_flag)` 加上「只找存活行」的 upsert，必然会产生软删孪生行；任何不过滤 `deleted_at` 的 `scalar_one_or_none` 都会 500。机制已静态核实（`capability.py:102`、`agents_hub.py:271-278`、`capability_service.py:106-112`）；库里是否已经有孪生行还没验证。
- antd 的 `showTotal` 配上「请求有上限、在前端分页」，界面会把上限当成总数显示。已由截图和 `marketCopy.ts:46-50` 核实。

## 输出路径
- 本报告由 manager 保存到 `/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/B4-capability-market/05-review/findings.md`（我没有写任何文件）。
