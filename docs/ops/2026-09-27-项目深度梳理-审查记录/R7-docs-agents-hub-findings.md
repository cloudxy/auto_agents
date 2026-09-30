# Findings — R7-docs-agents-hub（文档体系与 AI 协作中枢）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(docs .agents .claude .codex .grok capability-library) + inputs → sha256 8efd42fb73e6…（125 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R7-docs-agents-hub.md
- 备注：首轮触达 24-turn 上限，经 manager 要求基于已读内容交付；未完成项由 reviewer 标【未验证】。

---

## FINDINGS

### QA-1 常驻上下文中架构红线条数/门禁脚本路径自相矛盾且与实跑不符
- Dimension: 6 契约一致性 · 7 合规 | Severity: **major** | 工作量: S
- Evidence: 实跑 `evidence/arch.txt:2` 输出「13 条红线 + 4 条边界」，`arch.txt:22-26` 为 B4 五个子检查，另有 FR-14（:28-30）与 PL（:32-33）段。与之矛盾：
  - `README.md:371,377,442`「R1–R13 + B1–B3」；
  - `.claude/IDENTITY.md:12`「`scripts/check-arch.sh` 的 13 条红线 + 3 条边界（B1-B3）」，`:43` `bash scripts/check-arch.sh`，`:28,:45` `bash scripts/check-frontend.sh`；
  - `.claude/SOUL.md:3`、`.claude/MEMORY.md:11`「`scripts/check-arch.sh`（13 红线 + 3 边界）」；
  - 宪法 `.claude/rules/project_rule.md`「核心代码边界」表仅 B1–B3（「B1-B3 机械检查」），「相关 Skills」表写「12 条红线」，红线表无 R12/R13/FR-14/PL（按节标题定位，行号未取）；
  - 只有 `CLAUDE.md:103`、`AGENTS.md:28,38` 写对 B1–B4。
- 后果: IDENTITY/SOUL/MEMORY/rules 每会话载入 → agent 被引导执行错误路径（`scripts/check-arch.sh` 是否仍存在【未验证】；`README.md:401-402` 门禁表只列 `tools/check/*`）；宪法本身看不到 B4（四柱域 import 边界，ADR-0010）与 R13（租户收口），按宪法做审查/开发会漏掉这两条边界。
- Suggestion: 宪法 `project_rule.md` 补 B4、R12、R13、FR-14、PL，并删去「12 条」改为「条数以 `tools/check/arch.sh` 输出为准」；IDENTITY/SOUL/MEMORY 统一改为 `tools/check/arch.sh` / `tools/check/frontend.sh` 且不写条数；纳入文档漂移门禁（见 QA-12 / T1）。

### QA-2 文档体系缺 ADR/运维/部署/事故；「docs/ 不入库」说法与事实相反；关键依据指向仓库外
- Dimension: 1 标准符合 · 6 契约一致性 | Severity: **major** | 工作量: M
- Evidence:
  - `README.md:441`「docs/ 为本地私有内容不入库」、`AGENTS.md:118`「`docs/agents/issue-tracker.md` 为本地私有配置（不入库）」、`AGENTS.md:126` 同述；但 `.git/index` 含 `docs/claims.md`、`docs/agents/domain.md`、`issue-tracker.md`、`triage-labels.md`，`.gitignore` 也未忽略 `docs/`。
  - `docs/agents/domain.md:8,20` 要求 agent 先读 `docs/adr/`；工作树 docs 下仅 4 文件 + `.DS_Store`（Glob）。`AGENTS.md:38` 引 ADR-0010、`CONTEXT.md:13,39,42` 引 ADR-0001/0002——仓库内均不存在。
  - `CONTEXT.md:5` 权威产品设计为个人绝对路径 `/Users/xuyun/Documents/grok-files/power-market-design.md`；`README.md:417`「详见诊断报告附录 8.3」无处可寻。
  - `docs/agents/domain.md:11`「If a listed file does not exist, proceed silently. Don't flag absence」——制度化地让缺失沉默。
  - 工单/spec/审查全在被忽略的 `.scratch/`（`.gitignore:78`）与 `.sdlc/`（`:82`）。
  - 用户期望的 `docs/ops` 不存在（运维手册、部署文档、事故复盘均无落点）。
- 后果: B4 等被 ADR 约束的边界除作者外不可追溯；`domain.md:36-40`「Flag ADR conflicts」无法执行；新人/其他 agent 无从获得决策依据，单人知识孤岛。
- Suggestion: 先由 owner 决定 docs 入库还是私有（Q-2，推荐入库）；建 `docs/adr/` 收录 ADR-0001/0002/0010；建 `docs/ops/`（runbook：启停/看门狗/LiteLLM 与 newapi 墓碑状态；部署；事故复盘模板），把「诊断报告」入库或删引用；power-market-design 入仓或保留摘要+ADR；`domain.md:11` 改为「缺失即报告」；README/AGENTS 的「不入库」表述与决定对齐。

### QA-3 产品运行时目录导入写入开发协作中枢 `.agents/`，与「中枢不是产品运行时」「只放指针」冲突
- Dimension: 1 · 4 安全 · 7 · 8 | Severity: **major** | 工作量: M
- Evidence: `config/default/skills.yml:5-6` `AGENTS_ROOT: ".agents"`；`backend/services/power_market/hub_import.py:212-230` `confirm_tree_import` → `_land`，`:262-290` 以 `copytree` 把上传的插件/技能/智能体/命令复制进真实 `.agents/<type>/<name>`，`:153` 插件暂存到 `.agents/plugins/<name>`。对照 `CONTEXT.md:25-30`「仓库协作层（开发者工作区，不是产品运行时）」、`.agents/README.md:3,10`「plugins/ 只放指针、不放正文」、`tools/check/plugin_refs.py:43-45`（PL-1：`.agents/plugins` 下非符号链接即违规）、`.gitignore:71` `.agents/*`。
- 后果（静态推理，未实跑）: ① 本地/dev 管理员导入一个新插件 → `.agents/plugins/` 下出现真实目录 → 下次 `arch.sh` PL 变红，且该副本不被 git 跟踪；② 导入的 skill 落到 `.agents/skills/<name>`，而 `.claude/skills` 链接到它、Codex 原生读 `.agents/skills` → 第三方上传的 SKILL.md 成为本仓库 AI 编码会话自动加载的项目 skill（提示词注入到有写权限的开发会话）。代码注释 `:265-268` 已处理 symlink 逃逸，但未处理此路径。
- Suggestion: 推荐产品运行时根与开发中枢分离（如 `runtime/agents-hub/` 或按环境配置，默认不指向 `.agents`）；若刻意共用，则 (a) 在 CONTEXT 与 `.agents/README.md` 写明，(b) 禁止导入写 `.agents/skills`，(c) PL 门禁加显式例外清单。属于架构决策（Q-1）。

### QA-4 `capability-library/plugins` 扫描入口与 `scan-plugins` 已不存在，8 处文档仍描述之；PL-5 检查空转
- Dimension: 3 证据有效性 · 6 | Severity: **major** | 工作量: S
- Evidence: Read `capability-library/plugins` → 不存在，`.git/index` 也无此路径；`backend/app/api/v1/capabilities.py:136-138`「POST /scan-plugins 已删除」，`plugin_service.py:3-5` 同步改走 `agents_hub`（`AGENTS_ROOT`）。仍描述旧入口：`.agents/plugins/README.md:10`（「scan-plugins 仍扫六个」）、`.agents/README.md:19`、`CLAUDE.md:30`、`README.md:124`、`AGENTS.md:17`、`CONTEXT.md:13,23`、`capability-library/README.md:21,33`。`plugin_refs.py:68-70` PL-5 仅在「存在且非符号链接」时报错——入口不存在也通过，`arch.txt:33` 的绿灯不证明任何事。
- 后果: `CLAUDE.md` 每会话注入 → agent/开发者寻找不存在的入口或调用会 404 的接口。
- Suggestion: 8 处统一改为「扫描/同步以 `.agents`（`AGENTS_ROOT`）为根，走 `capabilities_gov` sync」；PL-5 删除或改为「必须存在且为符号链接」。

### QA-5 `.gitignore` 忽略承载共享契约的四个目录，新增文件静默不入库
- Dimension: 3 · 7 | Severity: **major** | 工作量: S
- Evidence: `.gitignore:65` `.claude/*`、`:71` `.agents/*`、`:72` `.github/*`、`:73` `.grok/*`；同时 index 内有跟踪的契约文件（`.github/workflows/ci.yml`、`.claude/settings.json`、`.claude/rules/*`、`.agents/skills/*`、`.grok/config.toml`）。`.codex/` 未被忽略（与提交信息「.codex/ 与 .claude/ 对称」不一致）。
- 后果: 新增 skill、hook、`.claude/memory/<slug>.md`、`.claude/plugins/<name>` 链接、新 CI workflow 都不会出现在 `git status`（除非 `git add -f`）——直接违背 `.claude/IDENTITY.md:3`「本文件随仓库 git 走」、`.claude/MEMORY.md:3`「随 git 走、团队共享」与 `MEMORY.md:30`（memory-curator 产出新条目）。团队契约按机器悄然分叉。
- Suggestion: 目录级忽略改为精确忽略（`.claude/settings.local.json`、`.claude/**/*.local.*`、`.grok/` 私有文件等），其余跟踪；arch.sh 增加 `git check-ignore` 不得命中 `.claude/{rules,hooks,memory,agents}`、`.agents/skills`、`.github/workflows` 的检查。
- 【未验证】manager 请跑 `git check-ignore -v .claude/memory/x.md .github/workflows/x.yml .agents/skills/x/SKILL.md`。

### QA-6 新人上手与常驻上下文中的过时/错误事实
- Dimension: 1 · 9 | Severity: minor（单条影响小，但全部位于每会话注入的文件） | 工作量: S
- Evidence:
  - `CLAUDE.md:71`「`setup.sh` 已含 `npm ci` 与 `build:shared`」——入口是 `init_project.sh`（`README.md:147`）；`setup.sh` 存在性【未验证】。
  - `CLAUDE.md:111` 硬编码「当前分支：`feature/project-structure`」，会话开始时实际分支为 `feat/litellm-l1`；把分支写死在常驻上下文必然过时。
  - `.claude/IDENTITY.md:42` `run.py all`（后端+双前端）vs `README.md:158` 默认启动后端+Worker+双前端；`all` 子命令【未验证】。
  - `.claude/IDENTITY.md:4`、`.claude/MEMORY.md:4` 个人记忆路径 `-Users-xuyun-Projects-auto-agents`，仓库实际在 `/Users/xuyun/auto_agents`（本会话 auto-memory 在 `-Users-xuyun-auto-agents`）。
  - `README.md:188,414`「以当前后台为准」——文档自认不确定。
  - `README.md:151` 公开默认口令 `admin / 123456`，`:242` 仅写「生产必须修改」；是否有机械阻止进入生产【未验证】。
- Suggestion: 删除「当前分支」；改 `init_project.sh`；核对 run 子命令；修正个人记忆路径；两处「以…为准」补具体菜单路径；默认口令首登强制修改或 `APP_ENV=prod` 拒绝启动。

### QA-7 LLM 网关「现状/目标」在多份文档间冲突
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence: `.claude/IDENTITY.md:29` 自研 `llm_protocol` + 可选 LiteLLM sidecar（「L1 影子，不接生产流量」），`:34` 禁引 litellm SDK；`README.md:40`「平台路径的规划/评分应走 LiteLLM」读作现状，`:267`「平台路径规划/评分走网关」；而 `CONTEXT.md:49` `LITELLM.ENABLED`/`ROUTE_INTERNAL`/`ADMIN.ENABLED` 默认全关 → 默认配置下平台路径实际不走 LiteLLM。newapi 同一 README 三种说法：`README.md:37`「仍在树里，默认关闭」、`:269`「已墓碑…`NEWAPI.ENABLED` 恒 false 且读路径已删；`/api/v1/newapi` 一周期保留，列表来自 LiteLLM」、`:291`「遗留中转站管控面（默认关闭）」。
- 后果: agent 无法判断默认环境下 LLM 调用走哪条路，改动时易越界。
- Suggestion: 在 README 或 `docs/ops` 放一张「LLM 通路状态表」（组件｜默认开关｜当前流量｜目标｜退役期限），其余文档只链接。

### QA-8 规则大量停留在口号；现有 lint 门禁过窄，放过真实缺陷
- Dimension: 3 · 7 | Severity: **major** | 工作量: M（F821 清零为 S，规则集渐进收紧为 M）
- Evidence: `AGENTS.md:86` lint 门禁仅 E9+F401、范围 `backend platform_core scripts`（`evidence/ruff.txt:1-3` exit 0）；scrapy/ 与 run.py 不在门禁内。同一代码库在放宽规则集下 `evidence/ruff-extended.txt` exit 1、4753 项，其中 `:15` F821 undefined-name 10 处（潜在运行时 NameError）、`:18` F811 重复定义 6 处、`:14,:27` ASYNC240/ASYNC230 共 12 处 async 内阻塞调用（与 `README.md:90`「异步优先」直接矛盾，R11 只覆盖 `redis_client()` 一种形态）、`:2` 一处非法 `# noqa`（`platform_core/models/llm_provider_model.py:48`）。`AGENTS.md:50`「单函数 ≤40 行 / 单文件 ≤500 行」无任何门禁；宪法日志规则写「code review」，而 `arch.txt:13` R10 实际已机械化——文本与门禁不一致。
- 后果: 绿色门禁制造「已合规」错觉，F821/async 阻塞这类真实缺陷被放行。
- Suggestion: 立刻把 F821、F811、ASYNC 加入门禁并纳入 scrapy/、run.py；其余规则按基线计数「只减不增」渐进收紧；规则文本逐条标注 `[gate: 命令]` / `[review]` / `[culture]`，行数上限接 ruff PLR0915 或自写脚本，否则降级标 `[review]`。
- 【未验证】F821 具体文件行号——manager 请跑命令确认（见文末）。

### QA-9 capability-library 分发脚本写用户级目录，违反「只在项目内生效」；README 描述已退役后台
- Dimension: 1 · 6 · 7 | Severity: minor（当前清单仅 `example-pdf-extractor`，影响面小） | 工作量: S
- Evidence: `capability-library/adapters/claude-code.sh:10` `TARGET_DIR="$HOME/.claude/skills"`；`adapters/codex.sh:14` `OUT="$HOME/.codex/capability-library.md"`——与 `tools/check/plugin_refs.py:2-3`、`.agents/README.md:20`「项目插件不挂用户级」冲突，`plugin_refs.py --local`（`:74-99`）不检查这两个位置。`codex.sh:2-7`、`manifests/codex.yaml:2-3`、`capability-library/README.md:92` 仍称「Codex 机制未确认」，而 `.agents/README.md:20` 已实测 Codex 读 `.codex/skills`。`README.md:41-43` 列出的 `backend/app.py`、`web/` 磁盘不存在（Glob），`:64,67-81` 仍介绍 8765 后台；`sync.sh:23-38` 先跑完所有适配器，再在遇到 `--serve` 时才 exit 1 → 按 README 操作会先产生副作用再报错。
- Suggestion: 适配器改写项目级 `.claude/skills` / `.codex/skills` 或退役（统一走 `.agents`）；`plugin_refs.py --local` 纳入这两个用户级位置；清理 README 退役段落；`sync.sh` 参数校验先于执行。

### QA-10 常驻上下文开销大且内容大量重复；与领域无关的插件在每会话启用
- Dimension: 5 性能（上下文/Token 开销）· 9 | Severity: minor | 工作量: S
- Evidence: 启动命令/红线清单/目录结构/技术栈在 README、CLAUDE、AGENTS、IDENTITY、SOUL、MEMORY、CONTEXT 七处各写一遍——QA-1/4/6 的漂移正是这种重复的直接后果；「Owner 四问」在 `pua.md`、`answer_rule.md`、`SOUL.md:34-38` 三处。`.claude/settings.json:17-22` 为本项目启用了 `drama-skills`、`oh-story`（短剧/网文写作插件，与数据平台无关），其 20+ skill 描述每轮注入并带来误触发风险，与 `.agents/README.md:20`「以隔离不同项目的 skill」的出发点相悖。`UserPromptSubmit` 的 `inject_context.sh`（`settings.json:24-33`）每轮注入量【未验证】（未读该文件）。
- Suggestion: 事实只保留 AGENTS.md 一处，CLAUDE/IDENTITY/SOUL/MEMORY 只保留各自独有内容 + 链接；若两写作插件仅为产品扫描，则留在插件农场、不在本项目启用（Q-3）；测量 hook 注入量并设上限。

### QA-11 claims 对账表所称的 CI 测试可能不存在；即使存在也仅校验文件存在
- Dimension: 3 | Severity: minor | 工作量: S
- Evidence: `docs/claims.md:3`「CI `test_claims_anchors.py` 校验锚点文件存在」；在 `backend/tests` grep「claims」仅命中 4 个文件、均非该名（其他目录未查，【未验证】）。按 `claims.md:3` 自述，测试只校验文件存在、不校验 `assert_tenant_login_allowed` 等符号——符号被改名/删除时仍通过。
- Suggestion: 确认测试存在；改为校验文件 + 符号（grep `def <symbol>` / `class <symbol>`）；在 claims.md 写明测试实际路径。

### QA-12 缺文档漂移门禁；元文件保护可能被 `.agents` 路径绕过【需确认】
- Dimension: 7 · 8 | Severity: minor（取决于 hook 实际内容可能升级） | 工作量: S
- Evidence: `.claude/IDENTITY.md:35` 称 PreToolUse hook 拦截 `.claude/rules/*`、`.claude/skills/*` 等；而 `.claude/skills` 是指向 `.agents/skills` 的链接——若 `guard_meta.sh` 只匹配 `.claude/skills` 路径，直接经 `.agents/skills/...` 编辑即可绕过（`guard_meta.sh` 未读，【未验证】）。QA-1/4/6/7 类漂移没有任何机械检查；`AGENTS.md:30`「不要靠记忆数条数」是好原则但只落在 AGENTS.md 一份。
- Suggestion: `guard_meta.sh` 同时匹配 `.agents/skills/`；新增 `tools/check/docs.sh`（接入 arch.sh），grep 一组已知过时模式（`scripts/check-arch.sh`、`B1–B3`、`B1-B3`、`setup.sh`、`scan-plugins`、`capability-library/plugins`、「当前分支」、`12 条红线`）命中即失败。

---

## Dimensions checked
1. 标准符合 ⚠️ — 文档与事实不一致（QA-2/3/6/9）
2. 标准质量 ➖ — 本切片无 FR/GWT；规则可执行性在 7/3 评判
3. 证据有效性 ⚠️ — PL-5 空转（QA-4）、lint 门禁过窄（QA-8）、claims 测试可疑（QA-11）、gitignore 静默吞文件（QA-5）
4. 安全 ⚠️ — 导入 skill 变成编码 agent 自动加载内容（QA-3）、默认口令 admin/123456（QA-6）、hook 绕过可能（QA-12，未验证）；无新增密钥泄露（`arch.txt` FR-14 段通过）
5. 性能 ⚠️ — 常驻上下文/每轮注入开销（QA-10）；N+1/全表扫描在本切片 ➖
6. 契约一致性 ⚠️ — 红线条数/脚本路径（QA-1）、扫描入口（QA-4）、LLM 通路（QA-7）
7. 合规 ⚠️ — 宪法逐条：宪法自身缺 B4/R12/R13/FR-14/PL（QA-1）；gitignore 违背「随 git 走」（QA-5）；用户级写入违背「只在项目内生效」（QA-9）；`arch.txt` 实跑全过
8. 边界 ⚠️ — 缺失路径被当作通过（PL-5）；导入落盘越界进中枢（QA-3）
9. 产品价值与体验（本切片的「产品」= 新人上手与 AI 协作体验；无截图，以 CLI/文档为证）⚠️ — README 从初始化到第一个采集任务的路径基本完整，但被 `setup.sh`/`run.py all`/写死分支/「以…为准」削弱（QA-6）；运维与 ADR 文档缺失（QA-2）

## Strengths（改进时应保留）
1. 单一机械门禁 + 退出码即违规数：`tools/check/arch.sh` 覆盖 R1–R13、B1–B4、FR-14、PL，有实跑记录（`evidence/arch.txt:1-36`，exit 0）；`AGENTS.md:30` 明确「权威清单是脚本，不要靠记忆数条数」。
2. 插件「只引用不复制」设计扎实：指针农场 + PL 检查以词法方式解析链接目标，CI 无 `~/.zcode` 也可跑（`plugin_refs.py:28-30,40-71`）；`--local` 检查各工具缓存副本（`:74-99`）；硬约束写明实测过的工具版本（`.agents/README.md:22-27`）。
3. 对外宣称与实现锚点对账：`docs/claims.md:5-14` 将营销宣称逐条对应到代码符号，值得推广。
4. CONTEXT.md 词汇表区分精确：上架 vs 停用两道闸（`CONTEXT.md:17-18`）、配额错误码不得直出（`:67`）、表名↔产品名词对应（`:15`）。
5. README 上手叙事对用户友好：先讲双进程心智模型（`README.md:81`），再走第一个任务（`:177-189`），FAQ 按「现象→原因」组织（`:407-418`）；AGENTS.md 验证与交付约定可直接执行（`AGENTS.md:83-91`）。

## Improvement themes（建议落地顺序：T2 → T4 → T1 → T3 → T5）
- **T2 修正 git 跟踪策略（QA-5）｜S｜第 1 步** — 目标：共享契约目录全部被跟踪，仅精确忽略私有文件；arch.sh 用 `git check-ignore` 防回退。先做的理由：成本最低，且不修的话后续主题新增的文件会静默丢失。
- **T4 产品运行时与开发中枢分离（QA-3、QA-9）｜M｜第 2 步** — 目标：`AGENTS_ROOT` 在产品运行时不指向开发中枢 `.agents`；capability-library 不再写 `~/.claude`、`~/.codex`；PL 门禁覆盖这些位置。前置：owner 回答 Q-1。
- **T1 事实只放一处 + 漂移门禁（QA-1、4、6、7、11、12）｜S–M｜第 3 步** — 目标：AGENTS.md 为唯一事实源，CLAUDE/IDENTITY/SOUL/MEMORY 只放独有内容与链接；宪法与 arch.sh 同步（补 B4/R12/R13/FR-14/PL）；`tools/check/docs.sh` 拦截已知过时模式。顺序：先修文本，再加门禁防回退。
- **T3 补齐文档体系（QA-2）｜M｜第 4 步** — 目标：先决 docs 入库/私有（Q-2）；`docs/adr/` 收录 ADR-0001/0002/0010；`docs/ops/` 包括 runbook、部署、事故复盘模板、LLM 通路状态表；产品设计入仓或以 ADR 摘要代替；`domain.md` 改为「缺失即报告」。
- **T5 规则可执行性分级 + 上下文预算（QA-8、QA-10）｜M｜第 5 步** — 目标：每条规则标注 `[gate]`/`[review]`/`[culture]`；ruff 先加 F821/F811/ASYNC 并纳入 scrapy/、run.py，其余按基线计数只减不增；常驻规则去重；领域无关插件不在项目级启用；hook 注入量设上限。

## Decisions / Open questions
- **Q-1（战略，待确认）** `.agents` 是否刻意同时作为产品运行时根目录与开发协作中枢？A 分离运行时根目录（**推荐**：消除 PL 冲突、提示词注入路径与 git 盲区）；B 继续共用，写入文档 + 禁止导入写 `.agents/skills` + PL 门禁例外清单。
- **Q-2（战略，待确认）** `docs/` 入库还是私有？A 入库（**推荐**：用户本次要在 docs/ops 出方案，claims.md 已入库，与现状和意图一致）；B 私有，gitignore `docs/` 并移除 CI/agent 对它的依赖。
- **Q-3（战略，待确认）** `drama-skills`、`oh-story` 是否需要在本项目 AI 会话启用？A 仅留插件农场供产品扫描、不在项目会话启用（**推荐**）；B 保持启用并写明理由。
- 运营性默认：无（只读审查，未替任何人应用默认决定）。

## 需要 manager 代跑的验证
1. `git check-ignore -v .claude/memory/x.md .github/workflows/x.yml .agents/skills/x/SKILL.md .codex/skills/x`
2. `ls -la scripts/check-arch.sh scripts/check-frontend.sh setup.sh capability-library/plugins; uv run python run.py --help`
3. `git ls-files | grep -n claims_anchors`
4. `uv run ruff check --select F821,F811,ASYNC backend platform_core scrapy scripts run.py`
5. `grep -n 'agents\|skills' .claude/hooks/guard_meta.sh; wc -c .claude/hooks/inject_context.sh`

## Product-delta rows
- 无（docs/product 未建立，本次审查不产生 product delta）。

## Lesson rows（仅已核实陷阱）
- 用目录级 `.gitignore`（`.claude/*`、`.github/*`）管理「部分文件已被跟踪」的目录，会让新增契约文件静默不入库——已核实 `.gitignore:65-73` 与 `.git/index` 跟踪条目并存。
- 「不存在即通过」的门禁是空转门禁——已核实 `plugin_refs.py:68-70` PL-5 + `capability-library/plugins` 不存在 + `arch.txt:33` 仍通过。
