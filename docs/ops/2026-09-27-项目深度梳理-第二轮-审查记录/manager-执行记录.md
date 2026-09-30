# 2026-09-27 项目深度梳理 第二轮（review-only）— manager 记录

## Intent
- class: review-only（全职能 × 全功能模块深度审查 → 完善既有方案；operator 未回复 D1–D15，仍待确认）
- quote: 「再次深度梳理项目结构，包括产品、产品运营、数据挖掘、设计、项目架构、前端、后端、数据库、数据采集、数据搭建、测试、验收、发布、独立review、bug检查、bug修复方案。也就是说，将项目的所有功能模块深度整理一遍，找出问题，给出问题原因，给出解决方案，将当前方案完善。」
- at: 2026-09-27 22:54（北京时间）
- delivery_goal: proposal_ready；产出：原方案文件原地更新（一份方案一个文件）+ 第二轮审查记录目录 docs/ops/2026-09-27-项目深度梳理-第二轮-审查记录/

## 路由说明
- 用户点名的职能（pm/ops/miner/designer/architect/data-collector/data-warehouse-engineer/qa/sre/reviewer）在 registry 中均无「全项目审计」任务；其 feature 任务需要 spec/contract 等前置产物（不存在）。按合同不为不同任务猜用角色默认 skill，因此以 reviewer G-fresh 承载各职能视角，由 reviewer 加载对应职能 skill 作为评判标准。bug 修复只出方案（debug 视角），不写代码（review-only）。
- 产品层 docs/product 仍不存在；产品/运营视角发现的战略问题以 Q-* 待确认形式返回。

## manager 证据（evidence/）
- 运行中的构建：backend :9111 / admin :9112 / official :9113 / MySQL 8.0.42 / Redis 均在运行（run.py status）
- capture.js：Playwright 只读导航截图 44 张（admin 23 页平台超管视角、官网 8 页；1440 + 部分 375），记录运行期错误 → ui-runtime-summary.md
  - 发现：rememberMe=false 时 token 不持久化 → 刷新/新标签即登出；登录时 /auth/permissions 401（R5 QA-2 实测确认）；结账页 400；设置页 useForm 未连接
  - 副作用披露：浏览与登录写入少量 product_events（official_page_viewed / login_succeeded / duty_entry_opened，22:55–22:58）与登录审计；未标记为测试流量
- MySQL 保真测试（CI 未跑的 7 个 + baseline）：5 failed / 6 passed / 1 skipped / 1 error；根因统一：downgrade 穿过 merge 迁移 048 → NotImplementedError（mysql-fidelity-full.txt）
  - 首跑失败遗留本次 2 个空 schema（pid 29527）已删除；另有 3 个 2026-09-02 旧残留（非本次）保留未动
- alembic check（临时 schema upgrade head → check → drop）：模型 ≠ 迁移；12 列可空性漂移（10 张表 tenant_id + spider_tasks.priority/retry_count）、索引/外键差异、656 处注释噪声（alembic-check-summary.txt）
- devdb 只读统计：head 050；5 租户 / 7 用户 / 1 个爬虫任务 / 207 资产 / 13 种事件 292 条（devdb-readonly.txt）
- module-inventory.md：184 paths / 229 ops 路由组、admin 23 页、官网 9 页、服务模块、功能开关、metrics.yaml

## 派单
- 12 个 G-fresh reviewer：F1 产品、F2 产品运营、F3 数据采集+数据搭建、F4 数据挖掘+算法、F5 设计、F6 架构、F7 测试+验收+发布、B1 身份租户、B2 计费LLM、B3 爬虫链路、B4 能力市场、B5 前端页面；check_packet ✓ ×12（F5 INPUTS 警告：44 张截图）
- 分三批，每批 4 个（第一轮 7 并发触发过账户限流）

## 进度（2026-09-27 23:1x → 2026-09-28）
- 第一批：F1（12 条）、F6（11 条，触达轮次上限后交付）、B1（12 条 + R1 补充 3 条）、B3（14 条）已交付并逐字落盘（extract_report.py 从交付记录提取）
- F2、F3 首派即遇账户限流（00:30 重置）→ 重置后 SendMessage 续跑；F4、B2 已派
- manager 核验（隔离临时测试，跑完即删；git 仅 docs/ops/ 未跟踪）：
  - ✅ B1-1：平台租户非超管 admin 能列出并重置平台超管密码，随后以超管登录成功（is_platform_admin=True）；租户 admin 重置 owner 密码并登录、PATCH 自己为 owner、POST 新 owner 均 200（verify-r2-B1-1-takeover.txt）
  - ✅ B3-1：真实 AsyncSession 下调度 _fire 抛 MissingGreenlet，last_run_at 仍 NULL、next_run_at 不推进（verify-r2-B3-1-scheduler.txt）
  - ✅ B1-6：dev 库 operation_logs 有 570 行测试特征审计（m-owner 等），其中 2026-09-27 18:23 两行由 manager 第一轮 CI 等价 pytest 写入（披露）（verify-r2-B1-6-auditpollution.txt）
  - ✅ F1/F6 只读核验：plans 3 行（企业档 ¥999 / 50 并发，与定价页「定制 / 不限并发」矛盾）；LITELLM.ENABLED / SHADOW 无读取方；APP_ROLE 仅 app/__init__.py:101 一处；settings.set 仅 power_market/flag.py:23（verify-r2-F1F6*.txt）
- F2（10 条）已交付并落盘；F5 已派（此刻在跑：F3、F4、B2、F5）
- manager 核验：
  - 🔍 F2-1：NotifyService 渠道仅来自 yml NOTIFY.CHANNELS（默认 [log]），设置页只存 3 个 URL 键（verify-r2-F2.txt）
  - ✅ F2-3：dev product_events 中 09-27 18:23 的 sync_completed 由 manager 第一轮 pytest 写入、22:55–22:58 的 official_page_viewed / login_succeeded / duty_entry_opened 由 manager 截图写入，全部 is_internal_fixture=0（披露）
  - ✅ R3 QA-5 升级为已复现：同一事件行 occurred_at（UTC）与 created_at（本地 CST）相差 479–480 分钟
- B2（11 条）、F4（12 条）、F3（14 条）已交付并落盘；B4、B5、F7 已派（此刻在跑：F5、F7、B4、B5；全部 12 个已派出）
- manager 核验（verify-r2-B2.txt / verify-r2-F3F4.txt）：
  - 🔍 B2-1：backend/app/__init__.py 无 TenantExpiry 注册（grep exit=1）；B2-6：relay_service 无 max_budget/budget_duration/blocked；B2-7：PROVIDER_BLOCK_PRIVATE_URL 仅 default=false、无覆盖
  - ✅ F4 QA-1：AiPlanCreate 接受 http://127.0.0.1.nip.io/ + html_snippet
  - ✅ F4 QA-4：FlowConfig 接受 (a|aa)+$；回溯 n=24/28/32 → 0.04/0.25/1.74s（指数）
  - ✅ F4 QA-2：只命中 1 个字段的 item 质量分 75.0 / 重复 55.0（<40 失败闸不可达）
  - ✅ F3 V2：market_list_viewed 87 条 anonymous/actor/tenant 全空；✅ F3 V7：retention 不覆盖 product_events；F3 V4：Redis 月值与 DB 当前一致（786），cost=0
  - 历史项（不列待办）：ai_plans#1（2026-09-14）试采 1792 READ ONLY——当前 db.py:155-161 已有连接复位修复
- B4（12）、F7（8）、B5（12）已交付并落盘；仅 F5 在跑
- manager 核验：
  - ✅ B4-1：自助注册 owner 调 /skills 写接口均越过守卫进入业务层（meta/rescore 返回业务 404「技能不存在」、import-url 返回 422 参数校验、GET manifests 200）；对照 /capabilities-gov 正确 404（verify-r2-B4-1-skills.txt）
  - ✅ B4-2：存活资产 195 > 界面「共 50 条」；✅ B4-4b：6 个插件各有 3 行孪生行，超管 GET 详情 live 返回 500（verify-r2-B4.txt、verify-r2-F7-B4.txt）；🔍 B4-6：_client_ip 无条件信任 XFF
  - ✅ F7：0 个 git tag / 230 次提交；`-m mysql_fidelity` 选不到 t42（grep -c=0）
  - ✏️ B5-4 自锁风险证伪：assert_tenant_active / 登录对 is_platform_admin 豁免；另注意 dev 超管挂在 default 租户（与 deps.py:50 注释「挂 platform」不一致），default 不受停用保护
  - B5-10：租户均创建于埋点上线前，「注册事件丢失」无法判定（保持 minor/待观察）
- F5（17）交付并落盘；12/12 齐；按标题重统计：第二轮 145（5/81/59），两轮 263（9/137/117）
- manager 复拍（recapture.js，只读）：首页减少动效后完整渲染 → F5-3「首页空白」为截图伪影；仪表盘等待 3s 后 recharts 柱 2 根 → 图表无柱为截图时机（F3-14/F4-12/F5-5 部分）；375 宽 scrollWidth=513 → 横向溢出 ✅
- 第二轮记录与证据复制到 docs/ops/2026-09-27-项目深度梳理-第二轮-审查记录/（7.0M，截图 6.0M）
- 方案原地修订：新增 §4 按职能问题/原因/方案、§5 Bug 清单 44 条、§6.2 三道上线闸、S7–S9 根因、决策扩至 D1–D33（A 9 / B 14 / C 10）、P0 扩至 11 项、P1 至 20 项、P2 至 13 项
- R0b 复核 packet（check_packet ✓，INPUTS 警告 36）→ 派 fresh reviewer 复核修订稿
- R0b 复核交付（触达轮次上限一次后交付）：12 条（0/9/3），Verdict 修正后可交付；落盘 R0b-plan-review/05-review/findings.md 并复制到 docs/ops
- manager 补跑 V-a..V-e（verify-r2-R0b.txt）：V-a 开发库 0 个插件配置 MCP；V-b ADAPTER_SYNC 默认 false；V-c 第二轮临时 pytest 未写开发库，直接操作写入 09-27 22:55–22:58 与 09-28 00:46–00:48 事件，登录不写审计（更正）；V-d rg 重跑无读取方；V-e 非超管 tenant_scope 取自 JWT claim（更正成立）
- 方案按 QA-1..12 全部修订：P0-2/3 临时 D23-A/D32-A；D34–D38 新增（38 项，A10/B16/C12）；收费闸与 BUG-09/23/26 按 D22；P0-3 覆盖 9 路由 + BUG-45；P0-8 按入口验收 + 供应商 DNS 校验；P0-11 拆 a/b；容量表（P0≈13、P1≈60、收费闸≈12 人日）；BUG-46；§11 填写处置表
- 状态：proposal_ready，等待 operator 审核与 A 档决策；未改源码，git 仅 docs/ops/ 未跟踪
