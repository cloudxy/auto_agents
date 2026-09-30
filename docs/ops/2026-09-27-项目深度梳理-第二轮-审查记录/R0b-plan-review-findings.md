<!-- manager 落盘：2026-09-28，R0b 复核 reviewer（G-fresh）最终交付原文逐字提取；packet 见 ../packets/ -->

# R0b 复核报告：第二轮修订后的汇总方案（G-fresh，只读）

- 被审对象：`/Users/xuyun/auto_agents/docs/ops/2026-09-27-项目深度梳理与改进方案.md`，快照 sha256 前缀 075eec130a1985d4，代码 HEAD 82259f3。其余输入的哈希沿用 packet 中 manager 给出的清单。
- 做了什么：
  - 完整读了方案（854 行）、manager-执行记录和全部 15 个 evidence 文件。
  - 用 Grep 列出了第二轮 12 个切片的全部标题和严重度行，并按 ID 抽查了 B1、B3、B4、B5、F2、F3、F7、R1 的原文。
  - 在 explore_roots 里静态核对了 `admin.py`、`skills.py`、`llm_secret_vault.py`、`platform_core/schemas/llm_provider.py`，以及出站 httpx 的调用点。
- 没做什么：我不能执行命令，下文所有结论都是静态阅读或对已有执行记录的检查，没有独立复现。
- 按指令提前收尾，没核完的项在 QA 条目里标了「未核实」，并汇总在 Open questions。

## 已核对、结论成立的部分（非空泛通过）

- **计数**：
  - 263 = 118 + 145；9/137/117 与两轮分项加总一致。
  - 第二轮 12 个切片的数量和 B/M/m，与各文件的标题及严重度行逐一对得上，例如 F4 为 1/7/4，F5 的 major 为 QA-1、2、4、5、6。
  - 「8 类 blocker 对应 9 个来源」成立。
- **决策**：D1–D33 编号齐全，没有缺号，按档分为 9/14/10。
- **其他数字**：
  - S9 表有 6 行。
  - P0 有 11 行。
  - `alembic check` 的 12 列可空性差异是 10 张表的 `tenant_id` 加 2 列（alembic-check-summary.txt:7-18）。
  - BUG-01 的「7 个端点」成立（`backend/app/api/v1/admin.py:145,235,246,263,285,298,322`）。
  - 「第 12 周约 2026-12-20」成立：2026-09-28 是周一，往后第 84 天是 12-20。
- **第二轮 major 的去向**：81 条 major 和 5 条 blocker 逐条对照标题，都在 §4、§5、§6 找到了去处。没有发现静默丢弃；唯一的例外是 QA-6 里指出的一个修复要点丢失。
- **证据与说法一致的例子**：
  - B1-1 的 9 条路径（verify-r2-B1-1-takeover.txt:1-9）；
  - F4-1、F4-2、F4-4（verify-r2-F3F4.txt:2-14）；
  - B4-2 与 B4-4b（verify-r2-B4.txt:3-12、verify-r2-F7-B4.txt:9-10）；
  - 570 行审计记录（verify-r2-B1-6-auditpollution.txt:22-23）；
  - 时钟差 479–480 分钟（verify-r2-F2.txt:55-59）。

## FINDINGS

### QA-1 「P0-1 到 P0-3 不依赖任何决策」与 §8 自相矛盾：P0-2、P0-3 实际上提前落实了 D23 和 D32
- Dimension: 6 / 9（战略决定） | Severity: **major**
- Evidence：
  - 方案 :90 和 :826 写「P0-1 到 P0-3 不依赖任何决策」，但 :745 把 D23 标为「阻塞 P0-2」。
  - :602 的 P0-2 写「admin 只能管理 operator 和 viewer（D23 定案前的最小限制）」，这就是 D23 边界 A 的原文。来源 Q-B1-1 标的是「战略，待确认」（B1-identity-tenant-findings.md:294）。
  - :603 的 P0-3 把「清单读取改为平台守卫」。企业用户能不能读平台技能库，正是 D32 / B4 Q-1 的问题（B4-capability-market-findings.md:220，「战略，待确认」），而 D32 被放在 B 档（:764）。
  - 当前 `GET /skills/manifests` 的守卫是 `require_login`（`backend/app/api/v1/skills.py:80-82`）。
- 后果：operator 读到的是「可以立即开工」，实际开工却会替他定下 D23 和 D32 的一部分。
- 修正：
  1. P0-2 注明「止血期临时采用 D23 边界 A（最严）；若 D23 选 B 再放宽」。
  2. D23 的「阻塞」列改为「不阻塞 P0-2 开工」。
  3. P0-3 里的清单读取要么拆出来等 D32，要么把 D32 升到 A 档，并写明 P0-3 临时采用 D32-A。

### QA-2 「运营性默认」越界：至少 4 项切片标为「战略，待确认」的问题被改写成运营性默认
- Dimension: 9 / 6 | Severity: **major**
- Evidence（方案行号，后面是来源里的战略标注）：
  - :793「平台超管不能以平台企业的身份订阅」，来源 B4 Q-3，B4-capability-market-findings.md:219,222 标「战略，待确认」。
  - :794「未登录访问平台路由仍显示 404，外加『登录后继续』」，来源 B5 Q-1，B5-frontend-pages-findings.md:276-280。
  - :787「内部流量用 traffic_class 标注、不丢弃、指标默认排除」，来源 F3 Q-4，F3-data-collect-warehouse-findings.md:358-361。
  - :789「live e2e 在合并 main、夜间和打 tag 前跑，PR 只跑桩」，来源 F7 Q-3，F7-test-accept-release-findings.md:230。
  - 另外，B4 Q-4「市场开关的真相源放哪」（B4:223，战略）在 BUG-32（:568）和 P1-14（:663）里被直接写成「落库」。
- 问题：方案 :781 说「以下按审查员的推荐写进了方案」，但没有披露审查员把这些问题定性为战略、需要 operator 回答。
- 修正：把这 5 项移入 §8，新增 D34 起的编号，C 档即可；或者在运营性默认下逐条写明「来源标为战略，manager 改判为运营的理由」，并请 operator 确认。

### QA-3 在收费闸和 BUG 行里，定价与账期规则被写成既定事实，而 D22 和 D19 都还没答复
- Dimension: 9 / 6 | Severity: **major**
- Evidence：
  - :559 BUG-23 的修复写「订阅到期只降档，不锁企业」，回归测试写「+31 天后配额恢复为免费档」。
  - :618 收费闸写「到期只降档，不锁企业」；:620 写「顺延续期；年付按年」。这些都是 D22 推荐项（:744）的原文，而来源 Q-B2-2 的严重度是 blocker（B2-billing-llm-findings.md:280）。
  - :545 BUG-09 写「续期即恢复」，这里合并了 Q-B1-3「企业到期后的策略」（B1:302）。
  - :364 写「D19 拍板前隐藏定价条目、菜单和 `relay` 商品」，等于在拍板前先执行了 D19-A。
- 修正：
  1. 相关修复方案和回归测试改为「按 D22 答复实现；测试断言以 D22 为准」。
  2. 收费闸只保留「到期必须可执行、且续费入口不被锁死」这种与选项无关的要求。
  3. :364 改为「D19 答复前是否隐藏由 operator 决定」，或者把它明确列为 D19 的临时选项请 operator 确认。

### QA-4 P0-3 / BUG-04 的回归清单漏了一个平台级写接口 `POST /skills/sync-adapters`
- Dimension: 4 / 2 | Severity: **major**
- Evidence：
  - `backend/app/api/v1/skills.py:102-111` 的 `sync_adapters` 使用 `require_admin`，会「触发 sync.sh 分发」。
  - B4-1 列出的 8 个接口里没有它（B4-capability-market-findings.md:26,41）。
  - 方案 :540 BUG-04 的回归测试写「8 个接口」，:603 P0-3 的完成标准只引用了 verify-r2-B4-1（这份记录只测了 4 个请求，verify-r2-B4-1-skills.txt:1-5）。
  - skills.py 里用 `require_admin` 或 `require_operator` 的路由实际是 9 个（:62,92,104,116,129,235,253,273,286）。另有 `GET /jobs`、`GET ""`、`GET /{name}` 用的是 `require_login`（:184-217）。
- 后果：P0-3 按清单验收可以通过，但企业负责人仍能在服务端触发平台脚本；是否可达取决于 `SKILLS.ADAPTER_SYNC.ENABLED`，这一点**未核实**。
- 修正：
  1. BUG-04 改为「skills.py 中全部 9 个 admin/operator 路由，加上 manifests 和 jobs 的读取（按 D32）」。
  2. 完成标准改为按路由表自动枚举：企业身份请求全部返回 404。
  3. P1-1 的 arch 规则同时覆盖 `require_login` 挂在全局资源上的情况。

### QA-5 P0-8 的止血动作达不到它自己的完成标准：LLM 供应商这条路径只有静态判定
- Dimension: 4 / 6 | Severity: **major**
- Evidence：
  - 方案 :608 的完成标准要求 `*.nip.io` 等地址「全部零下载或被拒绝」，但对 LLM 供应商只写了「prod 强制 `PROVIDER_BLOCK_PRIVATE_URL=true`」。
  - 实际守卫 `llm_secret_vault.py:84-92` 调用 `is_private_base_url`（`platform_core/schemas/llm_provider.py:60,78`），它只对字面量 IP 做 `ipaddress.ip_address`，不解析 DNS。
  - B2-7 的标题本身就写了「只做静态校验，不解析 DNS」（B2-billing-llm-findings.md:131）。
- 后果：开关打开后，`http://127.0.0.1.nip.io` 仍能通过供应商配置和连通性测试。完成标准要么验不过，要么被误判为已覆盖。
- 修正：P0-8 为供应商的 base_url 和探测路径补上「解析 DNS 后逐个 IP 校验」，至少复用 `ai_planner/url_guard.py:74` 的 getaddrinfo 逻辑。或者把完成标准按入口拆开写，明确供应商路径到 P1-6 才闭环。

### QA-6 B4-4 是正在发生的越权读，却被放到「能力市场开放闸」；修复要点「隐去 MCP env」在方案里丢失
- Dimension: 4 / 8 / 1 | Severity: **major**
- Evidence：
  - B4-4 原文：详情接口只要求登录，企业「市场关闭时也能读」未上架、黑名单资产的治理详情「以及插件的 MCP 配置」。修复方案之一是「对非超管隐去 `mcp_servers` 的 env 值」（B4-capability-market-findings.md:81,88,93）。
  - 方案把「详情接口按上架状态隔离」放在市场开放闸（:638）。按 :590 对 P0 的定义「可被利用的越权」，这一条应该入选。
  - 通读全文，方案没有任何地方提到 MCP 或 env 脱敏。
- 未核实：dev 或 prod 的 `mcp_servers` env 里是否真有密钥。
- 修正：
  1. 把 B4-4 的授权部分移到 P0-3（或同批的 P1 立即项）：非超管改走 `get_public`，或者直接返回 404。
  2. 补上 env 脱敏。
  3. 请 manager 只读查一次 capability_assets 中 mcp_servers 的 env 键。

### QA-7 R1-3 的升级条件已被第二轮事实触发，但方案没有把两者联系起来；P0-11 仍完全等 D1
- Dimension: 4 / 8 | Severity: **major**
- Evidence：
  - R1-3 原文：「若 default 租户有真实业务数据应升 blocker」；匿名注册者进入共享租户后，彼此数据可见，并可签发外部 API Key 导出数据（R1-backend-api-findings.md:47,49）。
  - 第二轮核验显示 dev 的平台超管就挂在 `default` 租户（verify-r2-B5.txt:11-13；方案 :187 ✏️）。
  - P0-11 写「等 D1」，只有 D1 选 A 时才关闭入口（:611）；D1 仍保留「C 保持现状」选项（:737）。
  - 方案没有任何行动项把超管迁回 platform 租户，而这正是 `deps.py:50` 注释写明的设计意图。
- 修正：
  1. P0-11 的止血部分不依赖决策：先禁止匿名注册进入承载平台账号的租户，或者先关闭入口，同时盘点 default 租户的数据。
  2. D1 的选项 C 加上前提「default 租户无业务数据、无平台账号」。
  3. 新增一项：超管迁到 platform 租户，或者给 default 租户加停用保护。

### QA-8 §1.3「如实说明副作用」没有覆盖第二轮的临时 pytest，而 B1-6 的机制恰好适用于这些运行
- Dimension: 3 | Severity: **major**（以问题形式提出，待 manager 核验）
- Evidence：
  - 方案 :136 称第二轮隔离临时测试「用测试库，跑完即删」。:193-196 的副作用披露只列了第一轮 pytest 和截图。
  - B1-6 的根因是：pytest 的任何请求路径都会触发 `init_all()`，覆盖注入的 DEFAULT 连接，`record_audit_standalone` 因此写进 dev 库（B1-identity-tenant-findings.md:154-159）。
  - B1-1 的复现包含建成员、重置密码、登录（verify-r2-B1-1-takeover.txt:1-9），会触发审计写入和 login_succeeded 事件。
  - 没有第二轮运行前后的计数对比；verify-r2-B1-6 的查询只按测试夹具用户名（`m-*`）过滤。
- 后果：
  - 副作用披露可能不完整。
  - 方案引用的开发库统计（292 条事件、570 行审计、87 条市场事件）可能混有本轮写入。
- 修正：manager 只读统计 operation_logs 和 product_events 在第二轮复现时间窗内（约 09-27 23:00 至 09-28 01:00）新增的行，按结果补充披露；:136 的「用测试库」加上限定语。

### QA-9 路线图的人力与依赖不自洽
- Dimension: 6 | Severity: **major**
- Evidence：
  - :80 和 :597 按 2 人计。
  - P1 共 20 项，全部没有估算工作量，其中大量「沿用第一轮内容」（:650-669）。第 3–6 周只有约 40 人日。
  - 「收费上线闸约 2 周（2 人）」与 P1、P2 并行（:703、:711），同一批 2 个人被重复排期。
  - 收费闸依赖 P1-18 的 live e2e 和 J-2（:626），路线图却只标注依赖 D17/D18/D22（:703）。
  - D26「同时影响计费」（:760），D4 决定计数口径（:753），但两者都不在收费闸里。F4-3 被放进 P2-11（:389、:685），而 D26 位于标为「阻塞 P1」的 B 档。
  - P0 的「约 12–13 人日」无法从 S/M 档位推出：按 :595 的定义，区间约为 6–18 人日。
- 修正：
  1. 给 P1 和三道闸估算工作量，并给出容量表。
  2. 路线图补上依赖箭头：P1-18 → 收费闸，P1-1 → 各闸。
  3. 把 D4、D26（计量单位）列为收费闸的前置决策。
  4. 写明 12–13 人日的推算过程。

### QA-10 部分核验标记比证据说得更满
- Dimension: 3 | Severity: minor
- Evidence：
  - F1-1 在 :177 标为 🔍，在 :362 标为 ✅，同一证据标记不一致。
  - §0 B3（:47）以 ✅ 声称「改分、拉黑、写清单、触发 LLM 重评」，但证据只覆盖了 meta、rescore、import-url 和 GET manifests（verify-r2-B4-1-skills.txt:1-5），「拉黑」「写清单」没有实跑。
  - B6（:50）「入队成功后……每 30 秒重复入队」标为 ✅，但复现把 enqueue 桩掉了，只证明了时刻不推进（verify-r2-B3-3-scheduler.txt 实为 verify-r2-B3-1-scheduler.txt:1-3；B3:42）。重复入队是推断。
  - F6 的「LITELLM.ENABLED / SHADOW 没有任何代码读取」：首次 grep 因 zsh 通配报错（verify-r2-F1F6.txt:9），重跑的记录只有空输出，没有命令文本（verify-r2-F1F6-b.txt:1-2），证据是空心的。这一条我**未核实**。
- 修正：
  1. 统一 F1-1 的标记。
  2. B3 的 ✅ 限定到「守卫放行」，其余标 🔍 或 📖。
  3. B6 的重复入队改标 🔍。
  4. 重跑 F6 的 grep，并把命令原文写进 evidence。

### QA-11 数字和引用的小矛盾
- Dimension: 6 | Severity: minor
- Evidence：
  - BUG-31 的回归测试写「total=207 时显示 207」（:567），但存活资产是 195（verify-r2-B4.txt:3-4；方案 :157）。207 含非存活行，这个测试会鼓励把软删行也计入。
  - P0-4「计数口径临时按 D4-A」（:604），但 §8 的 D4 已经没有选项（:753），D4-A 成了悬空引用。
  - A 档定义为「阻塞 P0 或收费上线」（:731），但 D10 阻塞的是 P1-9，D21 阻塞的是 J-1（:739、:743）。
  - P0-10 的成本闸 fail-open 不符合 :590 对 P0 的定义。
  - §10 的 lane 分配漏了 P0-7 和 P0-11（:819-822）。
- 修正：
  1. 207 改为 195，或改成「等于存活行数」。
  2. D4 补回选项。
  3. A 档的定义与成员保持一致，或者调整成员。
  4. P0-10 注明入选 P0 的例外理由。
  5. 补上两个 P0 的 lane。

### QA-12 §2「身份在每次请求时从数据库快照重算」没有吸收 B1 的更正
- Dimension: 6 / 4 | Severity: minor（未核实）
- Evidence：
  - 方案 :202 的原文如上。
  - B1 的更正（B1-identity-tenant-findings.md:253，标注「待核」）：非超管令牌的 `tenant_scope` 取自 JWT claim（`middleware/tenant_context.py:154`）。用户被迁到别的租户后，旧令牌仍保留原租户作用域。
  - 这条既没进 §1.3 的更正，也没进 P1-2 的 token_version 吊销范围。
- 修正：manager 核对 `tenant_context.py:154` 之后的代码。如果更正成立，修改 §2 第 1 条，并在 P1-2 里加上「迁移租户时吊销令牌」。

## Dimensions checked
1. 标准符合 ⚠️：QA-4、QA-6（修复要点丢失）。第二轮 major 与 blocker 的去向逐条抽查全部有着落。
2. 标准质量 ⚠️：P0 完成标准与动作不匹配（QA-4、QA-5）。
3. 证据有效性 ⚠️：QA-8、QA-10。主要数字都能回溯到 evidence。
4. 安全 ⚠️：QA-4、QA-5、QA-6、QA-7。
5. 性能 ✅：性能类发现（B4-6、F3-5、B4-10、B3-2 全文件轮询）都有去向；方案本身不引入无界查询。
6. 契约一致性 ⚠️：QA-1、QA-9、QA-11、QA-12。
7. 合规（宪法红线）✅：
   - 出站守卫下沉到 `platform_core`，依赖方向为 backend → platform_core，符合 B1；
   - Scrapy 中间件不 import backend；
   - 没有违反爬取与存储分离的方案。
8. 边界 ⚠️：QA-7（共享租户权限）、QA-6（关闭态绕过）。
9. 产品价值与体验 ⚠️：
   - 战略越界见 QA-2、QA-3；
   - 产品层（docs/product）不存在，旅程 J-1 到 J-5 只停留在方案文字，方案已如实承认；
   - 原型、E2E、验收属于 ➖：这是 review-only 的方案阶段，还不需要。

## Verdict
**修正后可交付**。计数、决策编号、blocker 追溯和第二轮 major 的去向整体可信。需要修正的有三类：
- **安全缺口（必须补）**：P0-3 漏掉 sync-adapters（QA-4）；P0-8 的供应商路径达不到自身完成标准（QA-5）；B4-4 和 R1-3 这两处正在发生的越权被延后（QA-6、QA-7）。
- **决策越界**：「不依赖决策」与 D23、D32 自相矛盾（QA-1）；战略问题被改写为运营默认或写成既定事实（QA-2、QA-3）。
- **证据披露与排期**：副作用披露待核（QA-8）；路线图人力与依赖不自洽（QA-9）。

以上 major 修正后即可交付给 operator，minor 可以一并顺手修。

## Open questions / 需 manager 执行的核验（均未执行）
- V-a：只读查询 capability_assets 中 `mcp_servers` 的 env 是否含密钥（QA-6）。
- V-b：`SKILLS.ADAPTER_SYNC.ENABLED` 在各环境的取值（QA-4 的可达性）。
- V-c：第二轮复现时间窗内 operation_logs 和 product_events 的新增行数（QA-8）。
- V-d：用 `rg -n "LITELLM\.ENABLED|SHADOW" backend --glob '!**/tests/**'` 重跑，并把命令和输出一起落盘（QA-10）。
- V-e：`tenant_context.py:154` 之后的逻辑，以及迁移租户后旧令牌的作用域（QA-12）。
- 战略相关：QA-2 列出的 5 项需要进入 §8，由 operator 回答。

```result
{
  "methods_used": [
    {"skill": "sdlc-workflow:findings", "reason": "G-fresh 9 维复核方案文档", "provenance": "reported"}
  ],
  "reported_reads": [
    "/Users/xuyun/auto_agents/docs/ops/2026-09-27-项目深度梳理与改进方案.md",
    "/Users/xuyun/auto_agents/docs/ops/2026-09-27-项目深度梳理-第二轮-审查记录/manager-执行记录.md",
    "evidence/verify-r2-B1-1-takeover.txt", "evidence/verify-r2-B1-6-auditpollution.txt", "evidence/verify-r2-B2.txt",
    "evidence/verify-r2-B3-1-scheduler.txt", "evidence/verify-r2-B4-1-skills.txt", "evidence/verify-r2-B4.txt",
    "evidence/verify-r2-B5.txt", "evidence/verify-r2-F1F6-b.txt", "evidence/verify-r2-F1F6.txt", "evidence/verify-r2-F2.txt",
    "evidence/verify-r2-F3F4.txt", "evidence/verify-r2-F7-B4.txt", "evidence/recapture-result.txt", "evidence/alembic-check-summary.txt",
    "B1/B3/B4/B5/F2/F3/F7 findings（按 ID 抽读）", "R1-backend-api-findings.md（QA-3）", "R0-plan-review-findings.md（D4 相关）"
  ],
  "unresolved": [
    {"id": "V-a", "owner": "manager", "blocks": "QA-6", "item": "mcp_servers env 是否含密钥", "severity": "major"},
    {"id": "V-b", "owner": "manager", "blocks": "QA-4", "item": "SKILLS.ADAPTER_SYNC.ENABLED 各环境取值", "severity": "major"},
    {"id": "V-c", "owner": "manager", "blocks": "QA-8", "item": "第二轮复现时间窗 dev 库新增审计/事件行数", "severity": "major"},
    {"id": "V-d", "owner": "manager", "blocks": "QA-10", "item": "重跑 LITELLM.ENABLED/SHADOW 读取方 grep 并落盘命令", "severity": "minor"},
    {"id": "V-e", "owner": "manager", "blocks": "QA-12", "item": "tenant_scope 取自 JWT claim 的更正是否成立", "severity": "minor"},
    {"id": "Q-R0b-1", "owner": "operator", "blocks": "QA-2", "item": "B4 Q-3 / B5 Q-1 / F3 Q-4 / F7 Q-3 / B4 Q-4 五项战略问题需进入 §8 答复", "severity": "major"}
  ],
  "proposed_changes": [
    {"target": "方案 §0 :90、§6.1 P0-2/P0-3、§8 D23/D32", "change": "声明 P0-2/P0-3 临时采用 D23-A、D32-A，或拆出依赖 D32 的读接口部分", "evidence_refs": ["方案:602-603,745,764", "skills.py:80-82"]},
    {"target": "方案 §8 运营性默认", "change": "5 项来源标为战略的问题移入 §8（新增 D34 起）", "evidence_refs": ["B4-capability-market-findings.md:219-223", "B5-frontend-pages-findings.md:276-280", "F3-data-collect-warehouse-findings.md:358", "F7-test-accept-release-findings.md:230"]},
    {"target": "方案 BUG-09/23/26、§6.2 收费闸、§4.1 :364", "change": "到期、续费规则改为「按 D22 答复」；中转条目隐藏改为按 D19 答复", "evidence_refs": ["方案:545,559,618,620,364"]},
    {"target": "方案 BUG-04、P0-3", "change": "补 POST /skills/sync-adapters，完成标准改为按路由表自动枚举", "evidence_refs": ["skills.py:102-111", "B4-capability-market-findings.md:26,41"]},
    {"target": "方案 P0-8", "change": "LLM 供应商 base_url 与探测路径加 DNS 解析校验，或按入口拆分完成标准", "evidence_refs": ["llm_secret_vault.py:84-92", "platform_core/schemas/llm_provider.py:60,78"]},
    {"target": "方案 §6.1/§6.2", "change": "B4-4 授权部分和 MCP env 脱敏移入 P0-3 或 P1 立即项", "evidence_refs": ["B4-capability-market-findings.md:81-93", "方案:638"]},
    {"target": "方案 P0-11、D1", "change": "不依赖决策的止血措施；超管迁到 platform 租户；D1 的 C 选项加前提", "evidence_refs": ["R1-backend-api-findings.md:47-49", "verify-r2-B5.txt:11-13"]},
    {"target": "方案 §1.2 :136、§1.3 :193-196", "change": "补充第二轮临时 pytest 的副作用核验与披露", "evidence_refs": ["B1-identity-tenant-findings.md:154-159"]},
    {"target": "方案 §6.3、§7", "change": "P1 与各闸估算工作量、容量表、依赖箭头；D4/D26 列为收费闸前置", "evidence_refs": ["方案:597,650-669,703,753,760"]},
    {"target": "方案 §1.3/§4.1/§0 标记、BUG-31、P0-4、A 档定义、§10、§2 第 1 条", "change": "按 QA-10、QA-11、QA-12 逐条修正", "evidence_refs": ["方案:47,50,177,362,567,604,731,819-822,202"]}
  ],
  "product_delta": [],
  "lessons": [
    "B1-6 这类「测试连上开发库」的缺陷会反过来污染审查自身的复现，凡是在同一台机器上跑临时 pytest 取证的，都要记录前后计数"
  ],
  "check_records": []
}
```
