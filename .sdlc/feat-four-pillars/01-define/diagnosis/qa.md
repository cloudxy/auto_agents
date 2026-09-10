# QA 诊断 · 四支柱（定义帽刷新）

> 上游：`01-define/spec.md` v1（Wave 0/1 冻结）· `user-story.md` · `metrics-blueprint.md` · `05-review/findings.md` · 宪法 `sdlc.config.yaml` → `.claude/rules/project_rule.md`
> 作者：/qa｜日期：2026-09-07｜泳道：L4 `feat-four-pillars`
> 相对上一版：上一版在 spec 未出时用 D1–D21 临时代锚。本版改锚 **FR/GWT**。定义帽 **未关闭**（`state.yaml` G-fresh fail；QA-02 blocker 仍 open）→ **本波不写 FR↔TC 全矩阵**。
> 范围：测试缺口、GWT 可测性、分层、边界覆盖。**不写生产代码，不做 ship/block，不替 `/pm` 改 GWT。**

---

## 0. 结论先行（事实，非放行）

| 项 | 事实 |
|---|---|
| 套件规模 | 后端 `pytest --collect-only`：**103 文件 / 1050 条**（含 parametrize 展开）。前端 Jest：**7 文件 / 16 条 `it\|test`**。E2E：**无**（`sdlc.config.yaml` `e2e: null`）。 |
| 冻结 FR 对齐 | Wave 0 FR-01…16、Wave 1 FR-17…31 **没有**一张可执行的 FR↔用例映射。现网用例对准的是 P6 扫描+SaaS 隔离+中转 mock，不是 spec 的 GWT。 |
| GWT 可测性 | 多数 Then 是可观测的。挡住「直接写用例」的是：QA-02（FR-15 缺 WACT 排除字段）、QA-03/04/06/07/15/16/18/19（oracle 歧义或假越权）、Q-VOICE/Q-PRICE（文案出口未决）。**拿着 spec 仍要回来问** = 定义帽未关闭，矩阵不得假装闭合。 |
| 四支柱现覆盖 | 采集 / SaaS 隔离 / 中转管控面有回归；**Power Market 用户可见行为（FR-17…31）零专用用例**。仓库内 `listing_state` / `capability_sources` / `capability_installs` / `capability_aliases` / `POWER_MARKET` / `origin_ref` / `public_license_override` **零命中**。 |
| 假绿 | 若干旧用例把 **与 spec 互斥** 的行为锁进 CI（viewer 可扫描、无 MCP=`degraded`、公开只 `stable`）。另有空心断言：`or True`、`"backend" not in []`、EXPLAIN 对模拟 dict。 |
| 保真度 | 默认 SQLite 文件库。CI 主跑全量 pytest（SQLite）；MySQL 保真 **8 文件子集**，不含能力域公开面 / 新唯一键。`tenant_usage.py` 用 `datetime.utcnow()` 取月，与 FR-16 上海业务日冲突，**无 freeze_time 用例**。 |
| 矩阵 | **本波不交付**。原因：定义未关闭，填 File:Line 只会把未冻结 oracle 写成假覆盖。 |

**放行不由本角色做。** 本文件证明：哪些 GWT 现在就能写成用例、哪些必须回 `/pm`、现网格子对着哪条旧契约。

---

## 1. 闸门与环境保真

| 闸门 | 命令 | 对四支柱的含义 |
|---|---|---|
| test | `uv run pytest -x -q backend/tests` | 唯一后端门。市场新用例必须进此目录。前端 Jest **不在** constitution `test` 闸，只在 CI `frontend-build` job。 |
| lint | `bash scripts/check-arch.sh` | R1 路径、R7 API 不 import ORM、R13 豁免清单对拍。适配器 `uri` 硬编码 `/Users` 会被红。 |
| build | 双前端 `npm run build` | 过构建 ≠ 过 GWT。 |
| migration | `bash scripts/check-db-migrations.sh` | 市场表 autogenerate 后必须过。 |
| e2e | `null` | 「浏览→登录→订阅」无浏览器层；verify 帽 curl 补位。 |

**方言（红线：矩阵映射 ≠ 有效测试）**

| 差异 | 现测 | 生产 | 冻结 FR 受影响 |
|---|---|---|---|
| 引擎 | SQLite 每测独立文件库 | MySQL 8 | 生成列 `alive_flag`、安装唯一键、NULL 不判重（FR-20 幂等） |
| JSON | 有限 | `JSON_CONTAINS(host_compat)` | FR-20 宿主筛选（QA-03 未冻 oracle） |
| `COALESCE(license,'')` | NULL 语义不同 | MySQL | FR-18/23 许可闸 |
| `VARCHAR` 长度 | SQLite 忽略 | 截断/报错 | origin_ref / 搜索超长（NFR-02） |
| 行锁 | 库级锁 | 行锁 | 同步 upsert、安装并发 |
| 排序 | SQLite 放行 `NULLS LAST` | MySQL 1064 | **ESC-2 已验证**；新列表排序必须复制 `test_t10_fix_regressions.py` 口径 |

CI MySQL 子集（`.github/workflows/ci.yml`）：`test_mysql_fidelity.py` / `test_db_fixtures.py` / `test_alembic_baseline.py` / `test_t10_fix_regressions.py` / `test_saas_members.py` / `test_auth_login_tenant.py` / `test_admin_users_crud.py` / `test_saas_rbac_deep.py`。**不含** `test_b1c_capabilities_coverage.py`、`test_skill_public_api.py`、`test_db_behavior_loop.py` 真 EXPLAIN。

`test_db_behavior_loop.py::test_explain_assertion_framework` 只对模拟 dict 断言 `type != ALL`，**不是**真实 EXPLAIN。NFR-01 / 设计 S4 的 `EXPLAIN type != ALL` 今日无对应用例。

---

## 2. GWT 可测性（本波主产出）

判定标准（`gwt-authoring.md`）：`/qa` 拿着 GWT 能直接写用例、不必回来问。需要回来问 = 不合格。下列只列 **挡住写用例** 的条目；可测且缺口仅在套件的放 §3。

### 2.1 定义未关闭 → 禁止当冻结 oracle

| ID | 挡住哪条 GWT | 为什么写不出用例 | 改进（回 `/pm`，本角色不代选） |
|---|---|---|---|
| **QA-02 blocker** | GWT-15.1；北极星 WACT | Then 未要求 `task_completed.is_marketplace_candidate`（或等价 source）、`login_failed`、登录-企业关联。蓝图验收「以事件为准」且字段含 spider/source。 | 把排除字段写进 FR-15 GWT，或删蓝图「FR-15 已含」断言。**关闭前不得写 WACT 验收用例。** |
| **QA-03** | GWT-20.2 宿主边界 | 选了不在 `host_compat` 的宿主：拒绝 / 灰掉 / 仍建订阅行，未冻。 | FR-20 补边界+越权 GWT；写清与「启用到宿主」差别。 |
| **QA-04** | GWT-20.3 | 权限矩阵「任意已登录成员」与「只读拒绝」并立；GWT-20.3 只覆盖未登录与超管无企业。 | 删前者；FR-20 增加只读：拒绝、**不新增安装行**、文案「请联系企业管理员」。 |
| **QA-05** | FR-17…31 整段 | T-27 把 XSS 标成已有能力并迁市场，但 Wave 1 **无** `<script>` GWT。唯一纯文本回归在 `SkillsSquare.test.tsx`。 | 并入 FR-18/19：不可信 SKILL.md 按纯文本；GWT 含不执行。 |
| **QA-06** | GWT-18.2；§3.1 矩阵 | 治理值集有「测试中」；公开矩阵与 GWT-18.2 丢掉该列，也无「已弃用」。 | 矩阵加「测试中」；GWT-18.2 补测试中与已弃用。 |
| **QA-07** | GWT-07.3 | 「只读查看若本期仍对租户关闭」把 Wave 0 冻结写权绑到未关闭的 Q-RELAY。 | Wave 0 只冻写=仅超管；租户读给默认，或拆出直到 Q-RELAY 关。 |
| **QA-10** | GWT-26.2 | 无 MCP→「未知」可上架，与 CONTEXT/ADR-0001「未经 verify 不得分发」双源。旧测试钉 `degraded`。 | §9.2 冻结「分发=上架 ≠ 验证/启用到宿主」，点名 superseded。 |
| **QA-15** | GWT-01.3、GWT-05.3 | 标了「越权」但测的是已登录成员看定价/点升级，无授权副作用。 | 改成边界/空态，或换成可断言的授权+审计。 |
| **QA-16** | FR-12 / 配额状态机 | 状态机有 ≥90%；GWT-12.1 只覆盖 70–89%。 | 补 ≥90% 一条，或删第三档。 |
| **QA-18** | GWT-26.2 后半 | 「启用到宿主」标进 Wave 1 冻结，frontend 诊断为 PR8；范围外禁止代写配置。 | Wave 1 只断言「订阅 ≠ 已在宿主运行 + 折叠说明」。 |
| **QA-19** | GWT-19.2/19.3 | 别名与存活目录名冲突的用户可见失败未冻（dba Q3）。 | FR-19 边界：冲突 → 可见失败，不静默覆盖。 |
| **Q-VOICE** | GWT-01.1 首屏句 | 未关前不得新写并列四柱承诺；Then 的「卖点」集合不稳定。 | 操作者关 Q-VOICE 后再写官网文案用例。 |
| **Q-PRICE** | GWT-01.2、GWT-05.1/05.2 | 空头是撤文案还是履约未决；定价主按钮出口分叉。 | 关 Q-PRICE 后才能钉 CTA 断言。 |

其余 findings（QA-08 AGPL、QA-09 首页失败装空、QA-11 护栏清单、QA-12 出站 Key、QA-14 故事表、QA-17 IA）影响范围或一致性，**不阻止**对已写清的 GWT 设计用例；QA-09 建议 Wave 0 补与 FR-28.3 同构的失败态，否则首页精选无法验收。

### 2.2 已冻且可测（不必问，只缺用例）

Wave 0：GWT-02.*（虚构数字）、GWT-04.*（注册成功页主按钮）、GWT-06.3（租户 admin 扫描拒绝+目录不变+审计）、GWT-08.*（跨租户任务/结果）、GWT-11.*（候选不占存储、不进「我的结果」）、GWT-13.2（未发布/黑名单公开同 404）、GWT-14.*（发布物无明文 Key）。

Wave 1：GWT-17.1/17.2（单入口+旧地址到达）、GWT-18.1/18.3（推荐可见、黑名单当不存在）、GWT-20.1（订阅默认启用开/信任关）、GWT-21.*（本企业安装+跨租户拒绝）、GWT-22.2（同步保持未上架、dev-team 422）、GWT-23.*（许可放行审计）、GWT-29.*（下架后安装保留/不可新订）。**前提是 §2.1 相关歧义关闭后，这些 Then 可直接变成断言。**

### 2.3 假越权 / 复合 When / 副作用

| 问题 | 例 | 改进 |
|---|---|---|
| 越权 GWT 不测授权 | GWT-01.3、05.3 | 见 QA-15 |
| 一条 GWT 两个 Given/When | GWT-20.2 预告不可订 **且** 重复订幂等 | 拆成两条，否则矩阵一格两主题 |
| 非法流转 Then 未写三件套 | spec §3.1 表有「无安装行」；多数越权 GWT 未写「审计 + 无副作用」 | 实现时每条非法边断言：状态未变 / 无记录 / **无 installs 行、不写源树、不改 listing** |
| When 偏实现 | 若干「请求管理详情」可接受（API 产品）；「点订阅」已是用户动作 | 保持用户视角；HTTP 用例是分层选择不是 GWT 正文 |

---

## 3. 测试缺口（相对现网套件，非矩阵）

> 下表是 **缺口清单**：现有文件能证明什么、对着哪条 FR、差在哪。不是 FR 全展开，不填 File:Line 全表。

### 3.1 Wave 0 — 停止说谎 / 停止泄漏

| FR | 现网能证明什么 | 缺口 | 层建议 |
|---|---|---|---|
| FR-01 承诺对齐 | 无。官网 Pricing/Home **零 Jest**（`App.test.tsx` 只断言首页有 h2）。 | 定价空头三项、主按钮出口。被 Q-PRICE 挡住。 | Jest（official Pricing/Home） |
| FR-02 虚构数字 | **无**。`Home.tsx` 仍硬编码 `128,000+` / `12 节点` / `3.2 亿条`。 | 字符串不得出现；超管登录官网仍不得渲染内部计数。 | Jest |
| FR-03 导出 | `test_export_csv/json` 有流式下载；`test_export_bad_format_raises` 对 **xlsx 抛 BusinessException**；`Data.tsx` 客户端 `page_size=100`。 | **没有** 100 条界上 / 0 条不生成空文件 / UI 不出现 Excel / 跨租户导出+审计。100 上限只在前端拼 page_size，后端未测硬顶。 | 集成（跨租户）+ Jest（格式选项） |
| FR-04 注册→登录 | `test_saas_signup_expiry.py` 测开通与重复邮箱。 | `Register.tsx` 成功主按钮是「再注册一家」，文案「即可登录开始第一次采集」——**与 GWT-04.1 相反，且无测试锁它**。 | Jest（Register） |
| FR-05 付费出口 | 无。 | 被 Q-PRICE 挡住。 | Jest |
| FR-06 目录写=超管 | `test_scan_plugins_ok` **锁 viewer 200**（与 GWT-06.3 互斥）。匿名 401 有。`test_create_tenant_plain_admin_403` 是正确样板但只测租户 PATCH。 | 租户 admin 扫描/验证：403 + **目录一行不变** + 审计。空目录可行动空态。 | 集成；**同期改写地雷** |
| FR-07 渠道/LLM 写 | `test_newapi_api.py` operator 403；守卫是 `require_admin`（租户 admin 可过）。远端全 mock。 | 租户公司管理员改窗口额度：拒绝且额度不变。GWT-07.3 读权限被 Q-RELAY 污染。 | 集成（真 JWT，禁止用 admin_client 冒充超管） |
| FR-08 隔离 | `test_saas_isolation.py` / `test_saas_r13_overwrite.py` 任务/定义/供应商强。 | **无** 结果导出跨租户、**无** 安装表（表还不存在）。`capability_assets` 有 `tenant_id` 却不在 `TENANT_EXEMPT_TABLES`（模型注释自称豁免）。 | 集成 |
| FR-09 入队带租户 | `test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects` 走 `SpiderTaskService.enqueue`。 | 定时/模板/AI 试采三条路径 **无** 对拍。且该用例末句 `or True` → 配额拒绝断言空心。 | 集成；先修空心 |
| FR-10 LLM 配额 | `QuotaService.check_llm_tokens_month` **仅测试调用**；`backend/` 生产路径 **零调用**（grep 仅 `quota_service.py` 定义）。 | GWT-10.1/10.2：规划成功路径必须扣量；尽额度不得打模型。现测的是一把没接上的闸。 | 集成：经 `ai/plans` 真路径，禁止只测 QuotaService |
| FR-11 候选不占存储 | 无。harvester 3 条，其中 `test_spider_contract` 空心。 | 用量=本租户采集条数；数据中心不见候选；导出拖不走候选库。 | 集成 |
| FR-12 用量文案 | 配额 429 业务码有；前端 Usage **零测试**。 | 70–89% 警告；满额中文下一步；**禁止** `QUOTA_EXCEEDED` 字样；≥90% 无 GWT。 | Jest + API 文案契约 |
| FR-13 路径/存在性 | `/public/skills` 未发布 404、字段白名单有；`/public/capabilities` 只钉 stable。管理详情 `capabilities.py` **回传 `file_path`**。 | 黑名单同 404 不泄露；租户看管理详情无本机路径。 | 集成 |
| FR-14 密钥 | 无扫描测试。sre 已证 `deploy/litellm/config.gen.yaml` 被跟踪。 | 发布树读不到可用上游 Key；页面掩码。 | 专项（gitignore/扫描）+ 前端掩码 |
| FR-15 漏斗事件 | 仓库 **零** `official_page_viewed` / `login_succeeded` / `task_completed` 产品事件（仅通知 type 字符串）。 | 整段不可测，直到 QA-02 关闭且查询面存在。 | 集成（查询面） |
| FR-16 时区 | `tenant_usage.py:26` `datetime.utcnow()` 取月。 | GWT-16.2 上海 00:30 月界；无 freeze_time。 | 单元（冻结 Asia/Shanghai） |

### 3.2 Wave 1 — 能力市场

现网能力域 ~90 条对准 P6「扫描 + stable 公开」，**不是** FR-17…31。

| FR 簇 | 现状 | 缺口（问题级） |
|---|---|---|
| FR-17 单入口 | 官网 `/skills` 与 `/capabilities` 双路由；Jest 钉 `listPublicSkills`。 | 导航只留「能力市场」；旧地址到达且筛技能；未登录不见「我的安装」。 |
| FR-18 可见性闸 | `test_public_capabilities_only_stable` 锁 **只 stable**；`test_public_list_only_published` 含 recommended。两套金标互斥（BUG-QA-01）。 | listing×治理×许可；coming_soon；blacklist 同 404。 |
| FR-19 搜索/别名 | 技能搜索旧 API 有分页；无 `origin_local_name`、无 alias。 | 短名命中前缀目录名；空搜文案；未上架猜别名 404。 |
| FR-20/21/29 订阅 | **路由不存在**。 | 安装状态机整表；幂等；预告 422 且无行；跨租户；下架后保留/不可新订。 |
| FR-22/25/27 治理与源 | 扫描=任意登录；无 Source 表。 | 超管同步；第三方保持未上架；撞名 parse_error；租户 403 且无同步任务。 |
| FR-23 许可 | 无 license 列测试。 | UNLICENSED 不可见；override 审计；非超管 403。需真库 COALESCE。 |
| FR-24 捆绑 | `test_expert_team.py` 团 CRUD，无 listing。 | 父未上架时专家独立卡片；未上架 child 不出现。 |
| FR-26 四件独立 | `test_plugin_verify_no_mcp_degraded` 锁 degraded。 | 未知可上架（待 QA-10）；租户不能 enable-host；Wave 1 勿把 PR8 当冻结。 |
| FR-28 六态 | 无。首页 SkillsSection 失败变空（QA-09）。 | 筛选空 ≠ 目录空 ≠ 加载失败。 |
| FR-30 市场埋点 | 无。 | 与 FR-15 同样：先有查询面。 |
| FR-31 闸门切换 | 无。 | 第一方已发布仍可见；第三方不借切换上架。 |

Wave 2–4 stub（FR-50…73）：本波不要求实现用例；FR-07 写权与 FR-61「伪装不自动停用」可在中转现网补负向，不挡 Wave 0 矩阵以外的缺口记录。

### 3.3 前端 / E2E

| 表面 | 现状 | 缺口 |
|---|---|---|
| official Home/Pricing/Register | Home 仅 smoke h2；Pricing/Register **0** | FR-01/02/04/05；Hero 数字；成功页 CTA |
| official SkillsSquare | 2 条：列表 + XSS 转义 | D19/FR-17 退役后 **必须**把 XSS 迁到 Capabilities，否则丢掉唯一前端安全回归 |
| official Capabilities | **0** | 预告标、搜索空态、失败态、订阅回跳 |
| admin Capabilities | **0**；验证按钮无 `usePermission` | FR-06 前端隐藏/禁用；listing 开关 |
| admin Usage/Data | **0** | FR-12 文案；FR-03 100 条说明 |
| E2E | 宪法声明无套件 | 不作为本帽阻塞；verify 帽 curl：「公开含预告 → 登录 → 订阅 200 → 预告 422」 |

---

## 4. 分层

现网形状偏「HTTP 集成厚、前端薄、E2E 零」，对 Wave 0 文案/FR-04 **放错层**：这些 Then 在 Jest 里测，不该等 pytest。

```
该测什么？
├─ 可见性纯函数（listing×status×license）     → 单元
├─ resolve_origin_path / hash 折叠 / uri 校验 → 单元
├─ 配额检查点（未接线的 LLM 闸）             → 先接生产路径，再集成；禁止只测未调用函数
├─ 租户隔离、安装幂等、许可闸、同步不改 listing → 集成（SQLite + MYSQL_FIDELITY 子集）
├─ 官网承诺/CTA/注册成功页/XSS               → Jest
├─ 浏览→登录→订阅主干                         → verify curl（本轮不新建浏览器套件）
└─ EXPLAIN / 生成列唯一 / 安装并发             → 专项真库
```

| 反模式（已发生） | 为什么有害 | 改进 |
|---|---|---|
| `check_llm_tokens_month` 只在测试里调用 | 绿的是死代码；GWT-10 仍失败 | 用例必须经规划/评分入口；未接线 = 缺口不是通过 |
| `test_saas_wiring` `or True` | 配额拒绝永远绿 | 删 `or True`；断言 code + 未入队 |
| `test_saas_byok` `"a-key" in cfg.source or True` | 密钥隔离断言可空心 | 删 `or True` |
| EXPLAIN 对 dict | S4 护栏假装存在 | MYSQL_FIDELITY 对真实 `EXPLAIN`；框架自证可留但不得顶替 |
| `test_spider_contract` `"backend" not in []` | 空心；R3 已由 check-arch 承担 | 改成解析 AST/源文件 import，或删除并依赖 R3 |
| 用 E2E 测 422 边界 | 宪法无 E2E；易碎 | 边界留集成 |
| `admin_client` 的 `is_platform_admin=false` | 用租户 admin 当超管会假绿 FR-06/07/14 | conftest 增 `platform_admin_client`；市场写路径禁止复用 `admin_client` |
| 远端 new-api 全 mock | FR-07.2 降级可测；真熔断测不出 | 保持 mock + 标注；真连通留 sre |

**金字塔：** 实现帽应按「单元（折叠/可见性/路径逃逸）> 集成（同步/安装/RBAC）> 个位数 curl 主干」。不要倒过来。

---

## 5. 边界 / 状态机 / 权限 — 边覆盖（不填全格）

### 5.1 公开可见性（spec §3.1，产品规则）

公开 = 上架∈{已上架,预告} ∩ 治理∈{已发布,推荐} ∩ 许可过闸。黑名单即使 listed → 当不存在。

今日：`test_public_capabilities_only_stable` 只钉 stable；**recommended 空且与 `/public/skills` 矛盾**。listing 三列、许可闸、「测试中」列 **全空**。GWT-18.2 四条资产只出现预告那条 — 可测，未写。

非法边必须三项断言：预告订阅 → 无安装行；黑名单详情 → 与 404 相同（禁止「已被拉黑」）；同步 → listing 不变。

### 5.2 安装（FR-20/21/29）

合法：无记录→已订阅（启用开/信任关）→关启用/开信任（确认）/卸载。  
非法：预告/未上架/未过闸订阅、超管无企业、只读（待 QA-04）、跨租户改行、开信任不确认、订阅写回资产信任。

**今日 0 格。** 重复订幂等（GWT-20.2 后半）是界上，优先。

### 5.3 配额带（FR-12）

`<70` / `70–89` / `≥90` / `100`。只测了 QuotaService 超限抛错。将满文案、第三档、禁止内部错误码 — 未测。市场候选计入存储 — 未测（FR-11）。

### 5.4 导出（FR-03）

界内 30 行 CSV 部分有（任务导出 2 行）。界上 100、空 0、xlsx 选项不出现、跨租户 — 缺。`Data.tsx` 100 是请求参数不是服务器强制，缺「page_size=101」契约。

### 5.5 权限三角

| 角色＼写目录/渠道 | 现网 | spec |
|---|---|---|
| 匿名 | 扫描 401 | 401 |
| viewer | **扫描 200（锁死）** | 403 |
| 租户 admin | 中转 `require_admin` 可进 | 403 |
| 平台超管 | 无统一 `platform_admin_client` | 200 + 审计 |

三类越权：换角色 / 换数据范围 / 直接调接口 — 市场写路径全缺。`PERMISSION_CATALOG` 无 `btn:market:*`。

### 5.6 裁剪（有意，非遗漏）

| 项 | 策略 |
|---|---|
| listing×治理×许可×override×host | **pairwise** + 高危全组合：listed+blacklist、coming_soon+POST、UNLICENSED±override、dev-team+listed、测试中（待 QA-06） |
| 插件清单格式 | 代表值：plugin.json / .zcode-plugin / kimi.plugin.json 各一 |
| E2E | 不新建浏览器套件 |
| 真 superpowers / 真 Kimi 桌面 | 禁止 vendor；file:// + tmp + PREFIX overlay |

---

## 6. 实现时会假红 / 假绿的旧用例

| 旧用例 | 锁死的旧行为 | spec 新行为 |
|---|---|---|
| `test_scan_plugins_ok` | viewer 200 | FR-06：非超管 403 |
| `test_plugin_verify_no_mcp_degraded` | health=degraded | 未知（QA-10 关闭后） |
| `test_public_capabilities_only_stable` | 公开只 stable | FR-18：stable\|recommended + listing |
| `test_public_capabilities_fields_whitelist` | 无 listing/installable/license | 扩白名单，仍禁 `file_path` |
| `test_scan_marks_missing_directory` | 任意缺目录 → missing | 仅第一方 |
| `test_correction_writes_db_then_meta_yaml_and_changelog` | 必写盘 | 第三方 `written_back:false` |
| `test_public_list_only_published` | `/public/skills` 含 recommended | FR-17 转调后须带 listing 闸 |
| `SkillsSquare.test.tsx` 列表 | mock `listPublicSkills` | 新页 `listPublicAssets`；XSS 用例必须迁走 |
| `ALL_ORM_TABLES` | 无 sources/installs/aliases | PR1 不扩则 `test_all_orm_tables_on_mysql` 红 |
| `TENANT_EXEMPT_TABLES` 对拍 | 无 capability_* | 豁免平台目录；**禁止豁免 installs** |

D16 回退：`scan_plugins(root=tmp)` 仍只扫夹具（无论 ENABLED）；HTTP 守卫与 health 枚举改写；ENABLED=true+非空 SOURCES 走 src_sync。**守卫变更与测试同 PR。**

---

## 7. 夹具（仍缺则 D3b/D13/D14/D10 不可测）

已有：`client` / `admin_client`（**不是**平台超管）/ `viewer_client` / SQLite `db_*` / 各文件重复的 `cap_library` / 三处复制的 `_platform_admin_token` / `build_user` 等（无能力域）。

必须新增：`platform_admin_client`；双租户安装 client；D3b 双路径同/异 hash 树；git 单插件 `"."` 与 monorepo 两清单；Kimi `managed/<id>`；`ALLOWED_LOCAL_PREFIXES` overlay；uri 逃逸负例；`dev-team` 包；license 四态；writable 0/1；`build_source/asset/install/alias`。

`test_mysql_fidelity.py`「14 表」注释已过时。PR1 加表必须扩 `ALL_ORM_TABLES`。

---

## 8. 问题 / 原因 / 改进

| # | 问题 | 为什么 | 改进 |
|---|---|---|---|
| P1 | 不能写覆盖矩阵却已有 1050 条绿灯 | 用例从实现长出，不从 GWT 长出；spec 现已存在但 GWT 仍有 blocker/major 歧义 | 定义关闭（至少 QA-02 + 市场 oracle）后再由实现帽按 FR 切片填矩阵；本波只保留缺口与可测性 |
| P2 | Wave 0 文案/激活 FR 几乎无前端测试 | constitution `test` 闸不含 Jest；官方页只有 3 条 smoke | 把 Home 数字、Register CTA、Pricing 出口放进 Jest；CI 已跑 `npm test`，缺的是用例不是门 |
| P3 | FR-06/07 会被旧测试逼着保持泄漏 | viewer 扫描、`require_admin` 中转被当成金标 | 同 PR 改写 §6；新增 `platform_admin_client` |
| P4 | FR-10 测试测了未接线函数 | 规划/评分不调用 `check_llm_tokens_month` | 先接线再测；未接线期间矩阵标 ❌ 不是 ✅ |
| P5 | 空心断言在 CI 里 | `or True`、空 import 列表、EXPLAIN mock | 删空心；回归集注释写清对应缺陷 |
| P6 | 方言子集不含能力域 | ESC-2 同类：SQLite 绿、MySQL 1064 | 市场唯一键/许可闸/JSON 进 MYSQL_FIDELITY；复制 0e0aaf8 排序断言 |
| P7 | XSS 回归绑在将退役的 SkillsSquare | FR-17 一迁，安全格子消失 | Capabilities 详情必须先有等价用例再删旧页 |
| P8 | 安装/listing 状态机 0 格 | 表与路由都不存在 | 实现前先工厂+夹具；非法边三项断言 |
| P9 | 埋点 FR 不可测 | 无事件 SDK、GWT-15 缺排除字段 | 等 QA-02 + 查询面；不要用审计日志冒充漏斗分母 |
| P10 | 100 条导出上限只在前端 | `Data.tsx` page_size=100；后端任务导出无条数闸测试 | 产品若「现行上限 100」，后端必须拒绝或截断并有界上/界外用例 |

现存产品缺陷（相对今日代码，非放行）：

| 编号 | 严重度 | 现象 | 证据 | 指派 |
|---|---|---|---|---|
| BUG-QA-01 | major | 公开 capabilities 只 stable，skills 含 recommended | `public_skills.py` vs `test_public_capabilities_only_stable` | `/backend` |
| BUG-QA-02 | major | `capability_assets.tenant_id` 不在豁免清单 | `tenant_isolation.py`；模型注释自称豁免 | `/backend` |
| BUG-QA-03 | major | scan/verify 仅 `require_login` | `test_scan_plugins_ok` | `/backend` |
| BUG-QA-04 | minor | 插件验证无 `usePermission` | `Capabilities.tsx` | `/frontend` |
| BUG-QA-05 | minor | `test_spider_contract` 空心 | `test_skill_harvester.py:93-95` | `/qa` 改写 |
| BUG-QA-06 | major | 注册成功页主按钮「再注册一家」 | `Register.tsx:54` vs GWT-04.1 | `/frontend` |
| BUG-QA-07 | major | Hero 虚构规模仍在 | `Home.tsx:31-35` vs GWT-02.1 | `/frontend` |
| BUG-QA-08 | minor | 配额/BYOK 断言 `or True` | `test_saas_wiring.py:49`；`test_saas_byok.py:45` | `/qa` |
| BUG-QA-09 | major | LLM 月度配额检查点未接规划 | 生产零调用 `check_llm_tokens_month` | `/backend` |
| BUG-QA-10 | major | 管理详情回传 `file_path` | `capabilities.py:193` vs GWT-13.3 | `/backend` |

---

## 9. 给下游

| 给谁 | 内容 |
|---|---|
| `/pm` | 先关 QA-02 与 §2.1 市场 oracle，否则 QA 只能写「待补 GWT」不能写用例。GWT-20.2 拆条；越权 GWT 要副作用。公开 recommended 口径分裂（BUG-QA-01）进 Wave 1 验收。 |
| `/architect` | 事件查询面形状；host_compat 不匹配的 HTTP 语义（待 PM）；`file_path` 不进协议。测试拒绝自行假设。 |
| `/backend` | 先 FXT-PADM/D3b/GIT；**同期改写 §6**；LLM 配额走规划入口；安装非法边无副作用。 |
| `/frontend` | Register/Home/Pricing Jest；Capabilities XSS 迁徙；验证按钮权限码。 |
| `/dba` / `/sre` | 新表进 `ALL_ORM_TABLES` + MYSQL_FIDELITY；真 EXPLAIN；许可闸 COALESCE。 |
| `/qc` | 定义未关闭；D/FR 市场零覆盖；不在此放行。全矩阵留给定义关闭后的实现帽。 |

---

## 10. open_questions

1. QA-02：`task_completed` 如何标记市场入站候选？不关则 WACT 用例无法写。  
2. QA-03：host 与 `host_compat` 不匹配的用户结果？  
3. QA-04：只读成员订阅的唯一口径？  
4. `test_scan_plugins_ok`：改为超管 200+viewer 403，还是服务层 `root=` 扫描另留 D16？倾向前者同 PR。  
5. 无 MCP：一次性改 `unknown`，还是过渡双枚举？（QA-10）  
6. `/public/skills` 四条：锁兼容转调，还是迁 capabilities + 一条等价？XSS Jest 迁徙路径必须同时指定。  
7. CI MYSQL_FIDELITY 是否在 PR1 纳入 sources/installs 唯一键？延迟 = ESC-2 同类逃逸。  
8. pairwise 是否接受为 listing×治理×许可的裁剪？高危组合见 §5.6。  
9. 超管无企业订阅 403（GWT-20.3 已冻）— 商店验收是否挂 platform 租户？矩阵按 403。  
10. Q-VOICE/Q-PRICE 关闭前，FR-01/05 是否允许只测「不得出现的硬编码数字/不得三档同注册」负向，把正向 CTA 标 ➖ 直到关问？

已冻结、不再问：订阅不占三类配额（spec 9.2）；下架后安装保留（FR-29）；探针伪装不熔断（FR-61）。

---

## 11. 覆盖统计（基线，非质量结论）

| 项 | 数量 |
|---|---|
| 后端收集用例 / 文件 | 1050 / 103 |
| 前端 Jest / 文件 | 16 / 7 |
| E2E | 0 |
| Wave 0 冻结 FR 有对应用例且断言对齐 GWT | **0 / 16**（隔离/导出/注册 API 是旧契约部分重叠，不是 GWT 对齐） |
| Wave 1 冻结 FR 专用用例 | **0 / 15** |
| listing×治理 格子 | **0**（「测试中」列 GWT 还缺） |
| 安装状态机格子 | **0** |
| 已知锁错契约的旧用例 | §6 共 10 处 |
| 空心断言 | ≥4（harvester、wiring、byok、EXPLAIN 框架） |
| 需真库 ⚠️ | 许可闸、JSON_CONTAINS、生成列唯一、EXPLAIN、安装并发 |

能力域看似 90+ 条，对准的是 P6 扫描+stable 公开，不是能力市场。

---

## 12. 自检

- [x] 未写 FR↔TC 全矩阵（定义未关闭）
- [x] GWT 可测性：挡住写用例的条目有原因 + 回 `/pm` 的改进
- [x] 四支柱均有现网文件级引用
- [x] 状态/权限/导出/配额边界点名空缺，未假装已测
- [x] 分层反模式有例证（死代码配额、`or True`、SQLite 方言）
- [x] 裁剪策略已声明
- [x] 需真库已点名转 `/sre`
- [x] 未替 `/qc` 做放行、未写生产代码
- [x] 每条空洞有问题 / 为什么 / 改进（§8）
- [ ] 全矩阵行号：等定义关闭后实现帽回填
