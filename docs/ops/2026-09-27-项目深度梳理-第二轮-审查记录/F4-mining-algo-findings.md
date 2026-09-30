<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# Findings：F4-mining-algo（数据挖掘与算法：排序打分、AI 规划、LLM 调用、评测）

## Snapshot
- HEAD：82259f301c060dbf411424ec8775f29944e313e1（工作区只新增了 docs/ops/）
- explore_roots `git ls-files -s` sha256：554b247b697181fee5946c77aeed3c645a2826868c9153215cd9d638de7fb399（由 manager 计算，我只是照抄）
- inputs：evidence/module-inventory.md、ui-runtime-summary.md、devdb-readonly.txt；skill_scoring_service.py、power_market/sorting.py、ai_planner/llm_client.py、config/default/llm.yml、power_market.yml；截图 admin_ai / admin_capabilities / official_skills / admin_dashboard（4 张都看过）；第一轮 R2-backend-services-findings.md
- 审查者：sdlc-workflow:reviewer（G-fresh，只读）。**做法**：静态阅读加看截图，另外引用 manager 已记下的 devdb 只读查询和 UI 运行记录。**我没有执行任何命令，下面没有一条是我自己复现的。**
- 第一轮 R2 已报过 QA-8（LiteLLM 路径的成本闸 fail-open）、QA-9（没有总时限）、QA-10（月度闸执行两次），本轮不再重复。

**结论**：共 12 条，blocker 1 / major 7 / minor 4。
- **QA-1（blocker）**：AI 规划试采时，采集侧完全没有 SSRF 防护，而且 html_snippet 这条路径连规划阶段的 DNS 校验也跳过了。结果是租户能读到内网内容。
- **QA-2**：数据质量分实际由 Item 的 schema 决定，不反映抽取质量。试采「质量分 < 40 判失败」这道闸永远触发不了。
- **其余**：列表页存成「一页一条、按列存」（QA-3）；正则 ReDoS（QA-4）；AI 规划、技能评分、市场排序三处都没有评测集，也没有能拿来评测的指标（QA-6、7、11）；「最热 / 最新」的口径能被人为操纵（QA-8）。
- **数据挖掘**：目前 7 个用户、5 个租户、292 条事件，做分群或预测不成立。先补埋点和快照（QA-11）。

---

## FINDINGS

### QA-1 AI 规划的试采与注册后采集走 Scrapy，这一侧没有 SSRF 防护；html_snippet 路径还跳过了唯一一次 DNS 校验
- Dimension: 4 / 8 | Severity: **blocker** | 工作量: M | 核验方式: 静态
- **现象**：服务层只在「规划阶段抓取目标页」时逐跳做 SSRF 校验。真正的采集（试采和注册后的定时采集）由 `flow_generic` 在 Scrapy 里发请求，初始 URL、详情链接、翻页链接和 30x 重定向一概不校验。
- **触发条件**：LLM.ENABLED=true，租户操作员执行以下三步：
  1. 创建计划。`target_url` 填一个解析到内网或元数据地址的域名（例如 `http://127.0.0.1.nip.io/`，或攻击者控制 DNS 的域名指向 `169.254.169.254`），同时附上 `html_snippet='<title>x</title><body>..</body>'`。
  2. 规划：因为有 snippet，不做在线抓取。
  3. 试采：`flow_generic` 直接请求 target_url，选择器（如 css `body` 或 regex `(?s)(.*)`）把内网响应抽出来写成采集结果，租户在「结果 / 导出」里就能看到。

  另外两个变体：公网页面 302 跳到内网；详情或翻页 href 指向 `http://10.x`。注册后的定时采集还会遇到 DNS rebinding。
- **根因**：
  - `platform_core/schemas/ai_plan.py:155` 的 docstring 写明创建入口「不做 DNS；域名目标由服务层抓取时逐跳校验」，把防护押在了服务层。
  - 但 `backend/services/ai_planner/orchestrator.py:218-221` 在有 snippet 时跳过 `_fetch_html`，`_assert_public_url`（`url_guard.py:86-123`）一次都不会执行。
  - `prompting.py:94` 把 target_url 原样写进 `urls`；`orchestrator.py:264-268` 把它交给 `flow_generic` 入队。
  - `scrapy/spiders/flow_generic.py:104`（初始请求）、`:148`（详情）、`:176`（翻页）都用 `response.urljoin` 直接发请求，也没有 `allowed_domains`。
  - 在 `scrapy/` 下 grep `ssrf|is_private|ip_address|_assert_public`，0 处命中。
- **后果**：不是盲 SSRF，而是能完整读回内容的 SSRF。云元数据凭据、内网 LiteLLM admin、Redis/HTTP 管理面的内容都会写进租户可见的结果表。凭据一旦泄露就收不回来。
- **修复方案**：
  - 把 `url_guard` 的 IP 判定下沉到 `platform_core`（B1 允许）。
  - 新增 Scrapy downloader middleware：每个请求先解析 DNS，拒绝私网 / 保留 / 链路本地地址。重定向在 `RedirectMiddleware` 之后逐跳重新校验，最好连接时固定已校验的 IP，防止 rebinding。
  - AI 流程默认限定在 target_url 的同一可注册域名下。
  - `AiPlanCreate` 在创建时也做一次 DNS 校验，别再只靠抓取阶段。
- **应补的测试 / 验收**：
  - middleware 单测：对 `127.0.0.1.nip.io`、`169.254.169.254`、302 跳内网、详情 href 指向 10.x 这几种情况，断言都不发出下载。
  - 集成测试：带 snippet 的计划，其 target_url 解析到私网时，在试采入队前就被拒绝。
- **manager 复现**：
  `cd /Users/xuyun/auto_agents && uv run python -c "from platform_core.schemas.ai_plan import AiPlanCreate as A; print(A(target_url='http://127.0.0.1.nip.io/', html_snippet='<title>x</title>'))"`
  预期：通过校验，说明静态检查拦不住。
  另外请确认租户能否经 `POST /api/v1/spiders/run` 直接用任意 urls 跑 `flow_generic` 或 `generic`。如果能，影响面还要超出 AI 规划，也可能和采集线评审的结论重叠。
- 说明：我没有加载 architecture 的 threat-model 参考，没有逐条走 STRIDE，只按「边界 → 缓解 → 测试锚点」定性。

### QA-2 数据质量分由 Item 的 schema 决定，而不是由抽取质量决定；试采「avg < 40 判失败」永远触发不了
- Dimension: 2 / 3 / 9 | Severity: **major** | 工作量: M | 核验方式: 静态 + 截图
- **现象**：`flow_generic` 产出的任何 Item，质量分最低也有 50（首次出现通常是 75，重复的是 55），和选择器有没有抽到有意义的字段无关。
- **根因**：
  - `scrapy/pipelines/quality.py:39-43`：完整率的分母是 `item.fields`，即 BaseItem 声明的全部 10 个字段（含 `id / created_at / updated_at / _quality_score` 这类管道从不填写的内部字段，见 `scrapy/items/__init__.py:9-31`）。
  - `selector_engine.py:68-72`：`title` 缺失时回退到 `<title>` 或 URL，`content = json.dumps(fields)` 恒不为空，所以 `quality.py:46-47` 的核心字段率恒为 1.0，固定拿 30 分。
  - `flow_generic.py:131` 只要有一个选择器命中任意内容就产出 Item，此时非空字段至少有 url/title/content/source 4 个，得分 ≥ 4/10×50 + 30 + 0 = 50。
  - 因此 `orchestrator.py:361` 的 `< 40` 判失败永远不会触发。
- **截图佐证**：admin_dashboard 显示「平均 / 最低 / 最高 75/100（1 条数据）」，恰好等于 5/10×50 + 30 + 20 = 75（task_id 由中间件注入）。这是静态推算，没有复现。
- **后果**：
  - LLM 幻觉出的选择器只要命中 `<title>` 或任意一个节点，试采就判「通过」，可以注册成定时采集，产出的是垃圾数据。
  - 仪表盘用绿色显示「75 分」，误导运营判断。
  - `test_ai_planner.py:98-106` 把 `get_task_quality` mock 成 90 分，这道闸从来没有用真实公式测过，属于空断言。
- **修复方案**：
  - 质量分只按业务字段算，排除 task_id/id/时间戳/`_quality_score`。
  - 按选择器统计命中率（命中的选择器数 / 声明的选择器数）。
  - 检查值是否有效：非空；不等于页面 `<title>` 或 URL；同一字段在多行中不全相同；长度分布合理。
  - `_judge_test` 改用明确条件，例如每个必需选择器至少命中 N 行，且各字段行数对齐。
  - 分数带上 `score_version` 落库，便于追溯。
- **应补的测试**：用真实的 `QualityCheckPipeline` 跑单测，断言「只有 title 命中」的 Item 得分 < 40；删掉 `_judge_test` 测试里 mock 的 90 分。
- **manager 复现**：
  ```
  cd /Users/xuyun/auto_agents/scrapy && PYTHONPATH=/Users/xuyun/auto_agents:/Users/xuyun/auto_agents/scrapy uv run python - <<'EOF'
  from types import SimpleNamespace
  from scrapy.http import HtmlResponse
  from scrapy.settings import Settings
  from utils.selector_engine import build_item
  from pipelines.quality import QualityCheckPipeline
  r = HtmlResponse(url="https://example.com/l", body=b"<html><title>t</title><body></body></html>", encoding="utf-8")
  p = QualityCheckPipeline(); p.open_spider(SimpleNamespace(settings=Settings()))
  for _ in range(2):
      it = build_item(r, {"price": [], "name": ["x"]}, source="flow"); it["task_id"] = 1
      print(p.process_item(it, None)["_quality_score"])
  EOF
  ```
  预期输出：75.0，然后 55.0。
  再跑一条 SQL 确认分数是否集中在个别离散值上：`SELECT quality_score, COUNT(*) FROM spider_results GROUP BY quality_score;`

### QA-3 列表页「一页一条、按列存」：字段不按行对齐，result_count 统计的是页数而不是记录数
- Dimension: 1 / 9 | Severity: **major** | 工作量: M–L | 核验方式: 静态
- **现象**：一个有 20 条新闻的列表页，只会存成 1 条结果，`content = {"title":[20个], "date":[18个]}`。
- **根因**：
  - `selector_engine.py:71` 把各字段的列表整体序列化；`flow_generic.py:129-132` 每页只 yield 一次。
  - FlowConfig 没有「行容器」选择器（只有 `detail.list_selector`，`ai_plan.py:93-105`）。
  - 提示词里的 `_SCHEMA_HINT`（`prompting.py:29-36`）也不要求 LLM 给出行容器。
- **后果**：
  - 某些行缺字段时，`title[i]` 和 `date[i]` 就错位了，而且下游看不出来。
  - 结果条数、配额和质量分都以「页」为单位，和用户理解的「采了 N 条数据」不一致。
  - QA-2 的质量分也只能在页一级计算。
- **修复方案**：FlowConfig 增加 `item_selector`（行容器）。字段在每一行内用相对路径抽取，每行 yield 一条；`result_count` 按行统计。口径改变要由产品确认（Q-3）。
- **应补的测试**：golden HTML 中一行缺一个字段，断言输出行数正确、字段不错位。

### QA-4 正则选择器和过滤器只校验能否编译就在 Scrapy reactor 线程里执行，存在 ReDoS 风险
- Dimension: 4 / 5 / 8 | Severity: **major** | 工作量: S–M | 核验方式: 静态
- **根因**：
  - `ai_plan.py:49-53`、`:115-121` 只做 `re.compile`，长度上限 500。
  - `selector_engine.py:42` 对整页 `response.text` 执行 `re.findall(expr, ...)`。
  - LLM 的输出（可以被目标页里的提示注入诱导）或租户在「方案预览与调整」里手工编辑的内容，都能写入 `(a|aa)+$` 这类灾难性回溯的模式。
- **后果**：Twisted reactor 是单线程的，一次灾难性回溯就能卡住整个 worker 进程，同一进程里其他租户的任务一起停摆。
- **修复方案**：
  - LLM 规划阶段不提供 regex（从 `_SCHEMA_HINT` 里去掉）。
  - 人工编辑的 regex 改用 `re2`，或者 `regex` 模块配合 `timeout=`。
  - 执行正则前截断输入长度。
- **应补的测试**：灾难性模式要么被 schema 拒绝，要么在 ≤ 1s 内超时。
- **manager 复现**：`python3 -c "import re,time;t=time.time();re.findall(r'(a|aa)+$','a'*34+'b');print(round(time.time()-t,2))"`（逐步增大 34 这个数，观察耗时指数增长），同时确认 `FlowConfig.model_validate({"selectors":[{"name":"x","type":"regex","expr":"(a|aa)+$"}]})` 能通过校验。

### QA-5 规划输入的 HTML 被粗暴截断，选择器没有离线预检，修复轮次得到的反馈也太粗
- Dimension: 1 / 5 / 9 | Severity: **major** | 工作量: M | 核验方式: 静态
- **根因**：
  - `url_guard.py:36, 57-66` 只去掉 script/style/注释，保留了 `<head>`、svg、全部属性，然后截取**前** 15000 字符。现代页面的列表区往往在截断点之后。
  - `orchestrator.py:229` 保存的 `html_sample` 就是这份截断后的内容；`:326-332` 修复轮次用的还是它，所以修复永远看不到缺失的区域。
  - `_judge_test` 的失败原因只有「结果为空」「任务失败」这类粗粒度信息（`:355-363`），没有细到每个选择器的命中数。
  - 规划的 system prompt（`prompting.py:24-27`）没有声明「HTML 是不可信数据」。对比技能评分那边的 `skill_scoring_service.py:37-38` 是有这条声明的。
- **后果**：幻觉选择器的比例高。每次迭代都要花一次 LLM 调用加一次完整的试采任务（默认最多 3 轮），成本和等待时间都浪费在注定失败的试采上。
- **修复方案**：
  - 按 DOM 结构压缩页面：去掉 head/nav/footer/svg；属性只保留 id/class/href；重复的兄弟节点只留 2–3 个样例；优先保留重复结构最密集的子树。
  - 规划之后先在样本上用 parsel 预检每个选择器的命中数，全部 0 命中就直接进入修复，不入队试采。
  - 修复 prompt 里带上每个字段的命中数和样例值。
  - 两个 system prompt 都加上不可信数据声明。
- **最小评测**：见 QA-6 的评测集，对比改造前后「首轮试采通过率」和「平均迭代次数」。

### QA-6 AI 规划没有评测集和回归测试，也没有计划级的成本、延迟、成功率数据
- Dimension: 3 / 9 | Severity: **major** | 工作量: M | 核验方式: 静态 + devdb
- **根因**：
  - `backend/tests/test_ai_planner.py` 把 LLM 和质量报告都 mock 掉了（`:98-106`、`:300-301`），没有 golden HTML，也没有期望的抽取结果。
  - `plan_json` 只存了 `flow/test_history/html_sample`（`orchestrator.py:229`），没有 model、prompt 版本、token、耗时。
  - `_llm_chat` 调用时不传 `usage_dim`（`:199-201`），规划的用量和其他默认调用方混在一起，无法单独核算。
  - devdb 里 `ai_plans` 只有 6 行，没有任何成功率统计。
- **后果**：改一次提示词或换一个模型，完全不知道效果是变好还是变坏；也无法回答「每注册成功一个爬虫要花多少 token、多少时间」。
- **修复方案**：
  - 建 20–30 个保存下来的页面（列表 / 详情 / 翻页 / JS 渲染各若干），每个标注期望的字段值。
  - 离线 harness：计算字段级 precision/recall、首轮通过率、迭代次数、token 数、延迟。
  - `plan_json` 写入 `prompt_version / model / tokens / latency_ms`，`usage_dim="ai_planning"`。
  - 埋点 `plan_created → planned → test_passed/failed(reason) → registered` 这条漏斗。
- **应补的验收**：CI 用录制的 LLM 响应（离线）跑 harness，设定阈值门禁；真实模型评测做成手动任务，并控制预算。
- **manager 查询**：`SELECT status, iteration_count, LEFT(error_message,120) FROM ai_plans;`

### QA-7 技能 AI 评分：四个维度中有两个无法从输入中观测，overall 与分维度没有约束，也没有和人工分做过校准
- Dimension: 1 / 2 / 6 | Severity: **major** | 工作量: M | 核验方式: 静态
- **根因**：
  - `capability-library/taxonomy/rubric.md:19-27` 把 maintenance 定义为「来源仓库最近更新时间」，把 real_world_effect 定义为「实际用过之后的效果」。
  - 但 prompt 只给了 SKILL.md 全文，外加一句「maintenance 可结合其活跃度推断」（`skill_scoring_service.py:48`）。模型拿不到仓库活跃度，也不可能实际试用，这两个维度只能靠编造。
  - completeness 要求「脚本 / 资源齐全」（rubric `:9-12`），但 `_read_skill_md`（`:191-201`）只读 SKILL.md，也不看目录结构。
  - `overall` 由 LLM 单独给出（`platform_core/schemas/skill.py:125`），没有按 rubric `:5`「四项平均」来约束。
  - 评审人记为 `reviewer="llm:default"`（`:180`），不记录模型；`SKILLS.SCORING.MODEL` 被忽略，每次调用只打一条告警（`:130-134`）。
  - SKILL.md 没有长度上限，大文件会让单次调用的成本失控。
  - `skills.rubric_human` 与 `ai_suggested_score` 同表共存（`models/skill.py:39-40`），却没有任何一致性检验。
- **后果**：后台「AI 建议」一列（`Skills.tsx:112`）看起来可信，实际上一半依据是编造的；换模型后分数也无法横向比较。
- **修复方案**：
  - AI 只评 completeness 和 doc_quality（输入改为 SKILL.md 加文件树）。
  - maintenance 由同步时拿到的源仓库最近提交时间确定性计算。
  - real_world_effect 只接受人工评分或安装 / 使用信号。
  - overall 在服务端按固定加权计算。
  - 记录 `model / prompt_version / content_hash`，SKILL.md 截断到 N 个 token。
  - 维度口径需要产品确认（Q-2）。
- **最小评测**：
  - 在有 rubric_human 的技能上计算 AI 与人工的 Spearman / Kendall 相关系数。
  - 同一份内容评 3 次，看分数方差（重测信度）。
  - 这两个数都达标后，「AI 建议」才在界面上显示。

### QA-8 市场「最热 / 最新 / 综合」三个口径都能被人为操纵，也没有冷启动策略
- Dimension: 4 / 9 | Severity: **major**（开放市场前必须修；当前 ENABLED=false） | 工作量: S–M | 核验方式: 静态 + 截图
- **根因**：
  - 最热：`sorting.py:45-55` 数的是未删除的安装**行数**，而唯一约束是按「租户 × 资产 × 宿主」（`models/capability.py:224-227`），一个租户对一个资产最多能贡献 4 次计数。统计没有时间衰减，也不排除内部 / 测试租户（虽然 `internal_fixture_tenants` 表已经存在）。
  - 由于 `/api/v1/public/tenant/signup` 公开可用，批量注册租户刷榜的成本很低。
  - 最新 / 综合的次级排序键是 `updated_at`（`sorting.py:40-42`），它是 `onupdate=func.now()`（`capability.py:55`）。任何同步、改示例、改上架状态、改精选的写操作都会刷新它，所以「最新」实际等于「最近被人或同步动过」。
  - 截图 admin_capabilities 里「最近上架」全部是 2026-09-14T09:45:04.5x 同一秒批量写入，说明现有时间字段里没有真实的新鲜度信号。
  - 新上架的资产计数为 0，在「最热」里永远垫底。
- **后果**：市场开放后，「最热」可以被廉价操纵，「最新」没有真实含义，新资产曝光不到。
- **修复方案**：
  - 最热改为 `COUNT(DISTINCT tenant_id)`，只统计近 30 天，按指数衰减（半衰期约 14 天），排除内部 / 试用 / 注册未满 N 天的租户。口径需产品确认（Q-1）。
  - 最新改用 `listed_at`（`capability.py:73-76`，这个字段已经存在），或者用源内容 `content_hash` 最后一次变化的时间。
  - 冷启动：新上架资产给一个曝光窗口，或者用 Bayesian 平滑。
- **应补的测试**：同一租户在 4 个宿主安装同一资产，热度计数应为 1；只改 examples 不应改变「最新」的顺序。

### QA-9 提示词里的约束没有在代码里强制执行（max_pages、同域名）
- Dimension: 6 / 7 | Severity: minor | 工作量: S | 核验方式: 静态
- **根因**：
  - 提示词写的是「max_pages 固定为 2」「pagination 用 css」（`prompting.py:38-41`），schema 却允许 xpath 和 1–100 页（`ai_plan.py:84-85`）。
  - `_build_generated_params` 原样透传（`prompting.py:96-97`）。
  - 每个列表页的详情链接数量没有上限（`flow_generic.py:139-148`）。
- **后果**：被提示注入的页面可以让一次试采扩大到 100 页 × N 个详情请求。这既违背宪法「反爬是底线」，也会消耗租户配额。
- **修复**：服务端硬性截断（试采 max_pages ≤ 2，注册时用配置上限），每页详情链接数设上限，限定同一可注册域名。

### QA-10 手动重评没有幂等保护：可以反复「重掷」AI 分数，也会重复消耗预算
- Dimension: 5 / 8 | Severity: minor | 工作量: S | 核验方式: 静态
- **根因**：
  - `skills.py:232-246` 只要求 require_operator，每点一次就入队一次。
  - `enqueue_rescore` 直接 lpush，不去重（`skill_scoring_service.py:93-98`）。
  - `score_skill` 不检查同一 `content_hash + prompt_version` 是否已经评过（`:119-145`），并且直接用最新一次覆盖 `ai_suggested_score`（`:166`）。
  - `skill_service.py:248-254` 绕过 `enqueue_rescore`，直接压入不带 tenant 的纯文本载荷，同一个队列里因此有两种格式。
- **修复**：幂等键为 `(skill, content_hash, prompt_version, model)`，已评过就跳过（管理员可强制重评）；待评队列用 Redis SET 去重；界面展示历史分数和方差，而不只是最后一次。

### QA-11 市场埋点撑不起排序评测，可变特征也没有快照，将来按时间点建特征会有泄漏
- Dimension: 3 / 9 | Severity: minor（开放前必须补） | 工作量: S | 核验方式: 静态 + devdb
- **根因**：
  - `market_events.py:105-112` 的列表曝光事件只带 type/host/category，不带 `sort_applied`、page、曝光顺序里的 asset id。
  - `:122-127` 的详情事件只带 type 和 listing_state，**连资产名都没有**。
  - 从列表到详情再到订阅，没有 `list_id` / 位置信息把几步关联起来。
  - devdb：market_list_viewed 87 条、detail 13 条、subscribe 2 条，彼此无法关联。
  - `featured`、`updated_at`、`ai_suggested_score` 都是原地覆盖、不留历史。将来如果把它们当特征做「按时间点」建模，会用到未来的信息。
- **修复**：
  - 事件补充 `sort_applied / page / impressions[asset_id 顺序] / list_id / position / asset_name`。
  - 订阅事件带上来源的 `list_id`。
  - 对 featured、score、listing_state 建日快照或变更日志表。
- **最小评测**：分档位统计 CTR@k 和订阅转化；数据够了以后做离线 NDCG 回放。

### QA-12 （待核实）仪表盘「质量分布」和「平均分」在同一屏上互相矛盾，而且时间窗口口径混用
- Dimension: 9 / 6 | Severity: minor | 工作量: S | 核验方式: 截图 + 静态，原因未定
- **现象**：
  - admin_dashboard 截图显示「平均 75 / 1 条数据」，但质量分布四档全部为空（应该在「良好 60-80」有 1 条）。
  - 「采集结果 Top5」里 `example` 这一行也没有柱子。
  - 质量卡片用的是「最近完成任务 #3」，其余卡片用的是近 7 日（近 7 日结果为 0），同一屏的口径不一致。
- **静态核对**：键名在两端是一致的（`spider_query_service.py:299-304`、`Dashboard.tsx:292-295`），原因可能是截图时 Recharts 动画还没播完，也可能是数据本身的问题，目前无法区分。
- **manager 核实**：
  - `curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:9111/api/v1/spiders/tasks/3/quality`，确认 `good(60-80)=1`。
  - 等页面加载 3 秒后重新截图。
  - 如果确认是数据问题，升级为 major；如果只是动画，关闭此条，但仍建议质量卡片标明所用的时间窗口。

---

## 算法组件卡片（现状 → 问题 → 原因 → 方案 → 最小评测）

| 组件 | 现状 | 问题 | 原因 | 方案 | 最小评测 |
|---|---|---|---|---|---|
| 市场排序（sorting.py） | smart = 精选 + updated_at；hot = 未删除安装行数；latest = updated_at | 能刷榜，「最新」没有含义，无冷启动（QA-8） | 计数单位是安装行；updated_at 被任何写操作刷新 | 按去重租户、30 天、指数衰减计热度；最新用 listed_at；新品曝光窗口 | 分档位 CTR@k 和订阅转化；刷榜模拟测试（1 租户 4 宿主 → +1） |
| 技能 AI 评分 | LLM 给四维加 overall，经 schema 校验后只写建议字段 | 2 个维度不可观测；overall 无约束；未校准；可重掷（QA-7、10） | prompt 输入不足；没有确定性计算 | AI 只评可观测维度，其余用元数据或人工；服务端计算 overall；幂等键 | 与人工分的 Spearman ≥ 阈值；3 次重测方差 |
| AI 规划（prompting/orchestrator） | 截断 HTML → LLM → FlowConfig → 试采 → 修复 ≤ 2 次 | 幻觉率高、无评测、成本看不见（QA-5、6、9） | 截断取前 15k 字符；无离线预检；无记录 | DOM 压缩、parsel 预检、按字段反馈、记录 model/tokens | 20–30 页 golden 集：字段 P/R、首轮通过率、token 和延迟 |
| 试采判定与质量分（quality.py） | 完整率 50 + 核心字段 30 + 去重 20 | 分数由 schema 决定、恒高，< 40 闸永远不触发（QA-2、12） | 分母含内部字段；content/title 有兜底值 | 只算业务字段；选择器命中率；值有效性；带版本号 | 构造「只命中 title」的 Item，断言 < 40；分数分布直方图 |
| 抽取引擎（selector_engine / flow_generic） | 一页一条、按列存；regex 作用于整页 | 行不对齐；ReDoS；SSRF（QA-1、3、4） | 没有行容器；只做编译校验；下载侧无防护 | item_selector 按行抽取；re2 或超时；SSRF 下载中间件 | golden 行对齐测试；ReDoS 超时测试；内网 URL 零下载测试 |
| 数据挖掘 / 分群 | 7 用户、5 租户、292 事件；指标注册表 5 项 | 没有足够样本做分群或预测；关键事件不可关联；特征原地覆盖 | 业务处于早期；埋点字段不全 | 先补埋点和快照（QA-11），暂不建模；分群先用规则（套餐 × 活跃度） | 事件可关联率（detail 带 asset_name 的比例）；快照覆盖率 |

---

## Dimensions checked
1. **标准符合** ⚠️：没有 spec，也没有产品层，只能对照代码内的契约来判。提示词与 schema 不一致（QA-9）；评分实现与 rubric.md 不一致（QA-7）；SSRF 的 docstring 所依赖的前提被 snippet 路径打破（QA-1）。
2. **标准质量** ⚠️：试采的验收条件是空的，< 40 永远达不到（QA-2）；列表数据的形态没有定义（QA-3）。
3. **证据有效性** ⚠️：试采判定的测试 mock 了 90 分（`test_ai_planner.py:98-106`），真实公式从未被测到；规划和评分都没有评测集（QA-6、7）。我全部是静态检查，没有复现。
4. **安全** ⚠️：QA-1（blocker）、QA-4。做得好的地方：规划阶段的抓取逐跳校验 SSRF、拒绝整数编码 IP（`url_guard.py:86-156`）；技能评分声明了注入边界。没有走 STRIDE。
5. **性能** ⚠️：ReDoS（QA-4）；修复轮次都要跑真实试采（QA-5）。hot 排序每次请求都聚合一遍安装表，以目前 2 行的规模没有问题，不列为 finding。
6. **契约一致性** ⚠️：QA-9、QA-10（两种队列载荷格式）、QA-12（窗口口径）。
7. **合规（宪法）** ⚠️：「反爬是底线」—— AI 流程可以放大请求量、跨域抓取（QA-9）。「日志即证据」—— sorting 纯子句按设计不打日志，可以接受；评分服务的 public 方法都有入口日志。其余红线由 R2 覆盖，本轮不重复。
8. **边界** ⚠️：超长 SKILL.md 无上限（QA-7）；灾难性正则（QA-4）；并发重评（QA-10）；空样本或被截断的样本（QA-5）。
9. **产品价值与体验** ⚠️：
   - AI 采集向导（admin_ai 截图）的三步流程清晰，支持粘贴 HTML 降级。
   - 但核心的「试采通过」不可信（QA-2），用户会把垃圾选择器注册上线。
   - 官网能力市场显示「未开放」（official_skills 截图，ENABLED=false），排序目前用户看不到。
   - 仪表盘的质量卡片误导用户（QA-2、12）。
   - 没有租户负责人视角的截图，这部分标为 ➖。

## Strengths（改进时应保留）
1. **AI 永远不写权威分**：`_apply_result` 只写 `ai_suggested_score / rubric_ai`，每次评分都留一条 `SkillReview`，带 `content_hash + prompt_version`（`skill_scoring_service.py:164-189`），可以追溯。
2. **LLM 产物落库前经过严格 schema 校验**：FlowConfig 有选择器白名单、XSS 片段黑名单、xpath 起始字符约束、长度上限（`ai_plan.py:43-142`）；SkillScoringResult 限定每维 1–10（`skill.py:121-127`）。
3. **规划阶段抓取的 SSRF 防护做得扎实**：只允许 80/443；逐跳手动跟随重定向；拒绝字面量和整数编码 IP；DNS 解析放进 to_thread（`url_guard.py:86-156`）。这套逻辑应该下沉到 platform_core，供 QA-1 复用。
4. **规划状态机严谨**：用条件 UPDATE 原子抢占，防止并发双跑（`orchestrator.py:160-169, 185-193`）；修复迭代有上限；注册前校验最近一次试采通过，并且可以幂等续跑（`:381-408`）。LLM 不产出 URL，只产出选择器。
5. **排序实现稳定、可回显**：id 兜底保证分页稳定（`sorting.py:40-42`）；没有计数时 hot 降级为 smart，并返回 `sort_applied`（`:76-85`）；安装计数统一用 deleted_at IS NULL 这一个口径（`:58-73`）。

## Improvement themes
1. **T1 采集侧安全出口**（QA-1、4、9）。目标：所有下载都经过 SSRF 中间件，AI 流程限定同域名，正则有超时。顺序：QA-1（先止血：snippet 路径在创建时做 DNS 校验 + Scrapy 中间件）→ QA-4 → QA-9。
2. **T2 重建数据质量分和抽取形态**（QA-2、3、12）。目标：质量分反映字段级抽取质量并带版本号；一行一条。顺序：QA-2（公式和判定）→ Q-3 定口径 → QA-3 → QA-12。
3. **T3 AI 规划可评测**（QA-5、6）。目标：有 golden 集 harness 和 CI 门禁，每个计划可查 model/tokens/延迟，有漏斗埋点。顺序：QA-6（先建评测集，作为基线）→ QA-5（压缩和预检，再用评测集证明效果）。
4. **T4 排序和评分可信、可度量**（QA-7、8、10）。目标：维度可观测、overall 确定性计算、与人工分完成校准；热度去重租户并衰减；最新用 listed_at。顺序：Q-1/Q-2 → QA-10（S）→ QA-7 → QA-8（在开放市场之前完成）。
5. **T5 数据挖掘前置**（QA-11）。目标：事件可以把「曝光 → 详情 → 订阅」关联起来；可变特征有日快照。在样本够之前不建模，分群先用规则。

## 待 manager 执行的验证（以下都是静态结论，均未复现）
- QA-1：上面的 `AiPlanCreate(... nip.io ...)` 命令；另外确认 `POST /api/v1/spiders/run` 是否允许租户对 flow_generic/generic 传任意 urls。
- QA-2：上面的质量分脚本（预期 75.0 / 55.0）；以及 `SELECT quality_score, COUNT(*) FROM spider_results GROUP BY quality_score;`
- QA-4：灾难性正则计时，以及 FlowConfig 能否接受 `(a|aa)+$`。
- QA-6：`SELECT status, iteration_count, LEFT(error_message,120) FROM ai_plans;`
- QA-7：`SELECT reviewer_type, COUNT(*), AVG(score) FROM skill_reviews GROUP BY reviewer_type;`，以及 `SELECT COUNT(*) FROM skills WHERE rubric_human IS NOT NULL;`（看有没有可用于校准的样本）。
- QA-12：上面的 curl，并延时重新截图。

## Decisions
- 只做审查，没有推进任何状态，也没有采用任何默认值。

## Open questions（战略，待 PM / owner 确认）
- **Q-1 「最热」的口径？**
  - (a) 安装行数（现状）
  - (b) 去重租户数
  - (c) 去重租户、30 天、指数衰减，并排除内部 / 试用租户

  推荐 (c)，否则公开注册会让刷榜成本接近零。
- **Q-2 AI 评分覆盖哪些维度？**
  - (a) AI 只评 completeness 和 doc_quality；maintenance 按源仓库元数据计算；real_world_effect 只接受人工或使用信号
  - (b) 保留四维，但在界面上标注「推断」

  推荐 (a)。
- **Q-3 flow 列表页的数据口径？**
  - (a) 一页一条（现状）
  - (b) 一行一条（需要 item_selector）

  推荐 (b)。这会影响结果计数、配额和计费口径，需要产品和计费负责人一起确认。
- **Q-4 AI 规划是否允许 regex 选择器？**
  - (a) 允许
  - (b) LLM 规划时禁用，人工编辑时可用，但走带超时的引擎

  推荐 (b)。

## Product-delta
- 无（产品层 N/A，未 bootstrap）。

## Lessons（已用代码互证）
- 质量分的分母如果取 schema 声明的全部字段，并且内容 / 标题有兜底值，分数就只由 schema 决定，任何低分阈值都会成为空闸（`quality.py:39-47` 与 `selector_engine.py:68-72`、`orchestrator.py:361` 互证）。
- 把 SSRF 防护押在「服务层抓取时逐跳校验」上，一旦存在不抓取的路径（html_snippet），或者真正的抓取发生在另一个进程（Scrapy），防护就会整体失效（`ai_plan.py:155` 与 `orchestrator.py:218-221`、`flow_generic.py:104/148/176` 互证）。

相关文件（绝对路径）：
- /Users/xuyun/auto_agents/scrapy/pipelines/quality.py
- /Users/xuyun/auto_agents/scrapy/utils/selector_engine.py
- /Users/xuyun/auto_agents/scrapy/spiders/flow_generic.py
- /Users/xuyun/auto_agents/platform_core/schemas/ai_plan.py
- /Users/xuyun/auto_agents/backend/services/ai_planner/orchestrator.py
- /Users/xuyun/auto_agents/backend/services/ai_planner/prompting.py
- /Users/xuyun/auto_agents/backend/services/ai_planner/url_guard.py
- /Users/xuyun/auto_agents/backend/services/skill_scoring_service.py
- /Users/xuyun/auto_agents/capability-library/taxonomy/rubric.md
- /Users/xuyun/auto_agents/backend/services/power_market/sorting.py
- /Users/xuyun/auto_agents/platform_core/models/capability.py
- /Users/xuyun/auto_agents/backend/services/market_events.py
- /Users/xuyun/auto_agents/backend/app/api/v1/skills.py
- /Users/xuyun/auto_agents/frontend/admin/src/pages/Dashboard.tsx
- /Users/xuyun/auto_agents/backend/tests/test_ai_planner.py
