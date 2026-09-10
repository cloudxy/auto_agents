# QA 诊断 · feat-four-pillars-v2

> 角色：`/qa`｜日期：2026-09-08｜泳道：L4｜性质：**定义帽并行诊断**，不是放行、不是 `04-verify/coverage.md`
> 范围（操作者点名）：现网测试与全新方案会冲突的点——**viewer 可扫、公开列表、权限**；覆盖缺口；会红用例；新方案验收必须钉的风险
> 拒绝：改测试代码 · 写覆盖矩阵 File:Line · 替 `/pm` 改 GWT · ship/block（`/qc`）
> 词汇：`CONTEXT.md`。旧程序 `.sdlc/feat-four-pillars/` 与 grok-files **只作输入**，不复制为现行合同。

---

## 0. 结论先行（事实，非放行）

| 项 | 2026-09-08 实测 |
|---|---|
| 套件 | 后端 `pytest --collect-only`：**103 文件 / 1050 条**。前端 Jest：**7 文件 / 16 条**。E2E：**无**（`sdlc.config.yaml` `e2e: null`） |
| 对准什么 | P6 扫描 + `status=stable` 公开 + SaaS 隔离 + 中转 mock。**不是** grok-files / 旧 spec 的上架∩治理∩许可、也不是 D14 超管写面 |
| 三处硬冲突 | **① viewer 可扫并落库**（文件头写死「无 403 分支」）**② 公开能力只 `stable`，公开技能含 `recommended`，两边金标互斥** **③ `require_login` / `require_admin` 把租户 admin 当平台超管；无 `platform_admin_client`** |
| 市场专用用例 | `listing_state` / `capability_sources` / `capability_installs` / `capability_aliases` / `POWER_MARKET` 在 `backend/` **零命中**（仅 `CONTEXT.md` 词表）。安装状态机 **0 格**；公开可见性矩阵 **0 格** |
| 矩阵 | **本波不交付**。v2 尚无现行 spec；填 File:Line 会把未冻结 oracle 写成假覆盖。本文件只保留缺口、会红清单、必须钉死的验收风险 |
| 旧 QA 诊断 | grok-files `feat-four-pillars-qa-diagnosis.md` **与** `.sdlc/feat-four-pillars/01-define/diagnosis/qa.md` 同文（2026-09-07，仍写 QA-02 blocker）。**相对仓库 spec v1.4 已过期**：GWT-15.1 已含 `is_marketplace_candidate`。本文件按现网测试 + v1.4 正文 + 设计 D14/D17/ADR-0018 重核，不抄那份 blocker 表 |

**放行不由本角色做。** 实现帽若按 D14/FR-18 改守卫与公开闸而不改写 §6 会红清单，CI 会逼着把泄漏留住。

---

## 1. 输入怎么用（结合，不继承合同）

| 输入 | 对本诊断的用法 |
|---|---|
| grok-files 设计 / plan / 旧 spec v1.4 GWT | **候选 oracle**。公开闸、超管写面、只读拒订、无 MCP=`unknown` 可上架，新方案大概率还要，但 v2 未冻结 |
| 旧 findings（审查到 v1.2/v1.3） | 独立第 3 轮 **不通过**（QA-29 major）。producer 称 v1.3/v1.4 已关，**第 4 轮从未跑**。v2 不得把「自称关闭」当过闸 |
| 旧 QA 诊断 §6 会红表 | **方向仍对**，行级已用现网源重核（见 §6） |
| 宪法 | `test` 闸 = `uv run pytest -x -q backend/tests`。Jest 只在 CI `frontend-build`。MySQL 保真 **8 文件子集**，不含能力公开面 |

旧 spec 里已经写进正文、**写用例不再需要回来问**的候选 Then（若 v2 继承）：GWT-06.3 租户 admin 扫描拒绝+目录不变+审计；GWT-18.2 六条资产只出预告那条；GWT-18.3 黑名单同 404；GWT-20.5/21.4 只读拒订/拒改安装且无行变化；GWT-26.2 无 MCP=`unknown` 可上架。挡住正向文案断言的仍是 **Q-VOICE / Q-PRICE**（操作者七问，禁止代选）。

---

## 2. 现网套件基线

### 2.1 闸门与方言

| 闸门 | 命令 | 对市场/权限的含义 |
|---|---|---|
| test | `uv run pytest -x -q backend/tests` | 市场新用例必须进此目录。改守卫而不改 `test_b1c` = 主闸红 |
| lint | `bash scripts/check-arch.sh` | R13 豁免清单对拍。`capability_assets` 有 `tenant_id` **不在** `TENANT_EXEMPT_TABLES`（模型注释自称豁免；`CONTEXT.md` 也写豁免） |
| migration | `bash scripts/check-db-migrations.sh` | 新表 autogenerate 后必须过 |
| build | 双前端 `npm run build` + CI 内 `npm test` | 过构建 ≠ 过 GWT。官网 Capabilities **0 Jest** |
| e2e | `null` | 「浏览→登录→订阅」无浏览器层；verify 帽 curl 补位 |

默认引擎：**SQLite 每测独立文件库**。CI MySQL 子集（`.github/workflows/ci.yml`）：`test_mysql_fidelity.py` / `test_db_fixtures.py` / `test_alembic_baseline.py` / `test_t10_fix_regressions.py` / `test_saas_members.py` / `test_auth_login_tenant.py` / `test_admin_users_crud.py` / `test_saas_rbac_deep.py`。**不含** `test_b1c_capabilities_coverage.py`、`test_skill_public_api.py`。新唯一键 / `JSON_CONTAINS(host_compat)` / `COALESCE(license,'')` 今日无保真格。ESC-2（`NULLS LAST` → MySQL 1064）已验证；市场 `ORDER BY` 必须复制 `test_t10_fix_regressions.py` 口径。

`test_mysql_fidelity.py:43` 注释仍写「14 表」；`ALL_ORM_TABLES` 实际 **40** 张，无 sources/installs/aliases/commands/components。PR1 加表不扩集合 → `test_all_orm_tables_on_mysql` / `test_db_engine_creates_all_orm_tables` 红。

### 2.2 身份夹具（权限测试的根缺陷）

`conftest.py` 特权快照：

```99:99:backend/tests/conftest.py
    return CurrentUser(id=1, username=f"test-{default_role}", role=default_role)
```

`is_platform_admin` 默认 **False**。因此：

| fixture | `role` | `is_platform_admin` | `require_login` | `require_admin` | `require_platform_admin` |
|---|---|---|---|---|---|
| `client` | — | — | 401 | 401 | 401 |
| `viewer_client` | viewer | **false** | 200 | 403 | **403** |
| `operator_client` | operator | false | 200 | 403 | 403 |
| `admin_client` | admin | **false** | 200 | **200** | **403** |
| （缺失）`platform_admin_client` | — | true | — | — | 200 |

**`admin_client` 不是平台超管。** 它模拟的是「租户公司管理员也能拿到 `role=admin`」——正是 D14 / GWT-06.3 要拒绝的身份。正确样板已存在：`test_create_tenant_plain_admin_403`（`admin_client` → 403 + **零落库**）。市场写路径今天全部没用这个样板。

真超管只在个别文件手造 JWT（`test_b1a_admin_coverage._platform_bearer`、`test_r5_r7_fixes._platform_admin_token`），**无统一 fixture**。`test_b1c` 用 `viewer_client` **副作用**把共享 `TestClient` 鉴权拨成 viewer，再经 `db_client.post` 发扫描——`viewer_client` 参数看起来未使用，删掉会变成匿名 401。这是负载夹具，不是死参数。

生产还有第二轴：`tenant_role ∈ {owner,admin,operator,viewer}`。GWT「只读成员」对的是 **tenant_role=viewer**，不是（仅）legacy `role=viewer`。现网能力域 **零 JWT 租户角色格**。

---

## 3. 冲突 A — viewer 可扫（含验证 / 组团）

### 3.1 锁死的旧契约

`test_b1c_capabilities_coverage.py` 文件头：

> 管理端（`/api/v1/capabilities`，**require_login——viewer 亦放行，无 403 分支**）

| 用例 | 文件:行 | 锁死行为 | 副作用断言 |
|---|---|---|---|
| `test_scan_plugins_ok` | `test_b1c_capabilities_coverage.py:96` | docstring：**viewer 扫描 200**；`total/succeeded=1` | `capability_assets` + `capability_plugins` 各一行 |
| `test_scan_plugins_bad_dir_counted_failed` | `:115` | 同一守卫下 200；坏目录 `failed=1` | 坏名零落库 |
| `test_scan_plugins_anonymous_401` | `:131` | 匿名 401 | 无（未查库） |
| `test_scan_experts_ok` | `:189` | 登录即可扫专家 200 | expert 资产+细节落库 |
| `test_plugin_verify_no_mcp_degraded` | `:160` | 登录即可 verify；无 MCP → **`health=degraded`** | `health_status` 持久化 |
| `test_team_upsert_create_then_update` | `:256` | 登录即可组团 | 团行+资产行 |

实现：`capabilities.py` 全部 `Depends(require_login)`。`scan_plugins` / `scan_experts` **不写审计**（`verify` / `teams` 才 `record_audit`）。GWT-06.1 候选 Then「审计记录操作者、动作、对象」——扫描路径今天即使超管 200 也缺审计格。

对照：`POST /api/v1/skills/scan` 已是 `require_admin`（`skills.py:43`），`test_scan_endpoint_returns_job_summary` 用 `admin_client` 锁 **租户 admin 等价身份 200**。同一「目录写」在两个路由上守卫不一致：技能扫=租户 admin 可过；插件扫=**viewer 可过**。D14 要把两者都收到 `require_platform_admin` → **两条都会红**。

### 3.2 新方案候选行为（设计 D14 / 旧 GWT-06 / plan T-02）

| 角色 | 扫描 / 验证 / 上架 / 源同步 |
|---|---|
| 匿名 | 401（已有） |
| viewer / 经办 / 只读 | **403**；目录一行不变；审计越权 |
| 租户公司管理员（`role=admin` ∧ `is_platform_admin=false`） | **403**；同上（GWT-06.3） |
| 平台超管 | 200 + 审计 |

前端：`Capabilities.tsx` 扫描/验证按钮 **无 `usePermission`**，旁注仍是「插件经 MCP 验证后方可分发（ADR-0001）」——与 CONTEXT / ADR-0018「上架是独立闸门」互斥。无 Jest。

### 3.3 会假绿的写法

只把 `test_scan_plugins_ok` 的 client 换成 `admin_client` 仍 403（`is_platform_admin=false`）。必须：

1. 新增 `platform_admin_client`（或复用 JWT 超管样板）
2. 超管 200 + 审计 + 落库
3. **viewer 403 + 零落库**（今日无此条）
4. **plain admin 403 + 零落库**（抄 `test_create_tenant_plain_admin_403`）
5. 匿名 401 保留
6. 无 MCP 健康枚举与 ADR-0018 同 PR（见 §6）

---

## 4. 冲突 B — 公开列表（双金标 + 无上架闸）

### 4.1 两条互斥的绿灯

| 表面 | 实现 | 锁死用例 | 今日集合 |
|---|---|---|---|
| `GET /api/v1/public/skills` | 先分页 `status=None`，再 Python 滤 `stable\|recommended` | `test_public_list_only_published` 断言 `names == {pub-stable, pub-rec}` | **含 recommended** |
| `GET /api/v1/public/capabilities` | SQL `status="stable"`（`public_skills.py:174`） | `test_public_capabilities_only_stable` 断言 `total==1` 且只有 `pub-skill` | **不含 recommended**；种子无 recommended 行 |

这是旧 BUG-QA-01，现网仍在。`test_public_capabilities_only_stable` **不能**证明「recommended 被排除」——种子只有 stable / experimental / expert-stable。若实现改成 `IN (stable, recommended)` 而不改种子，该用例 **继续绿**。名字叫 only_stable，断言测的是 experimental 不外泄。**改闸必须重写夹具为 GWT-18.2 六行，禁止只改一行 assert。**

### 4.2 候选公开闸（设计 §商店 SQL / 旧 spec §3.1）

公开出现 = 上架 ∈ {已上架, 预告} ∩ 治理 ∈ {已发布, 推荐} ∩ 许可过闸。黑名单即使 listed → 当不存在（与 404 同形，禁止「已被拉黑」）。

| 上架＼治理 | 实验 | 测试中 | 已发布 | 推荐 | 已弃用 | 黑名单 |
|---|---|---|---|---|---|---|
| 未上架 | 不出现 | 不出现 | 不出现 | 不出现 | 不出现 | 当不存在 |
| 已上架 | 不出现 | 不出现 | 可订 | 可订 | 不出现 | 当不存在 |
| 预告 | 不出现 | 不出现 | 可见不可订 | 可见不可订 | 不出现 | 当不存在 |

许可未过闸：上表「可订/可见」全改不出现。**今日 18 格全空。**

### 4.3 现网公开面还锁了什么

| 用例 | 锁死 | 新闸冲击 |
|---|---|---|
| `test_public_capabilities_fields_whitelist` | 白名单无 `listing_state` / `installable` / `license`；禁 `file_path` | 扩白名单会红；**`file_path` 禁令必须保留** |
| `test_public_capabilities_invalid_type_falls_back_skill` | `type=bogus` → 当 skill、200、不含 expert | 五类平级后 bogus 是 400 还是兜底，必须钉；`expert`→`agent` 回填必须钉 |
| `test_public_unpublished_detail_404` | 技能 experimental 详情 404 | 未上架/黑名单必须 **同形 404**（无公开 capabilities 详情路由——今日只有 list） |
| `test_public_fields_whitelist_enforced` | 技能详情无 `file_path` | 迁市场后 XSS/正文白名单必须仍在 |
| `SkillsSquare.test.tsx` | mock `listPublicSkills`；XSS 纯文本 | 页退役则 **唯一前端安全回归消失**（GWT-32） |

`public_list_skills` **页内再滤发布态**：`total=len(published)`，页刚好塞满未发布时公开页可空。现网种子 4 条、默认页 20，测不到该边界。plan 已点名：公开闸必须 **SQL 内完成后再分页**。

PR1 若给 `listing_state` 默认 `unlisted` 且 PR6 才加 SQL 闸：公开列表在闸门打开瞬间若无第一方回填，`test_public_*` 全空红（GWT-31 空窗）。回填规则（仅第一方已发布/推荐 → listed；第三方保持 unlisted）必须有专用用例，不能靠 only_stable 碰巧还绿。

---

## 5. 冲突 C — 权限（写面过宽 + 矩阵 0 格）

### 5.1 现网 vs 候选矩阵（目录/渠道写）

| 角色＼动作 | 扫插件 | 扫技能 | 验证插件 | 改渠道窗口 | 公开逛 | 订阅 |
|---|---|---|---|---|---|---|
| 匿名 | 401 ✅ | 401 | 401 ✅ | 401 | 200（仅 stable 能力 / stable+rec 技能） | 路由不存在 |
| `viewer_client` | **200 锁死** | （无 403 用例） | **200 锁死** | 403（newapi 有） | 同匿名 | — |
| `admin_client`（非超管） | 200（require_login） | **200 锁死** | 200 | **200**（`require_admin`） | 同匿名 | — |
| 平台超管 JWT | 无专用用例 | 无 | 无 | 与 admin 混 | — | 无企业时应 403（GWT-20.3） |
| tenant_role=viewer | **无 JWT 格** | 无 | 无 | 无 | — | 候选：拒订+无行（GWT-20.5） |

`newapi.py` 文件头写死全部 `require_admin`。`test_newapi_api.py` 用 `admin_client` 当正例、operator 403——**把泄漏锁成金标**。GWT-07.4 候选：租户公司管理员改额度 → 拒绝且额度不变。今日无「plain admin 改额度 403 + 原值不变」。

`llm_providers.py` 写面同样 `require_admin`。`PERMISSION_CATALOG` 有 `btn:skill:admin` / `menu:newapi` / `menu:skills`（「能力资产」），**无 `btn:market:*`**。按钮码不进 FastAPI Depends（plan 也承认 Wave 0 用户可见只需超管拒绝）。验收不能只测前端藏按钮。

### 5.2 三类越权（市场写/订 今日全缺）

| 类 | 该测 | 现网 |
|---|---|---|
| ① 换角色 | viewer / 租户 admin / 只读 做超管扫描、上架、许可放行 | 扫描锁的是放行；上架路由不存在 |
| ② 换数据范围 | 租户 B 改 A 的安装行 | 安装表不存在 |
| ③ 直接调接口 | 绕过前端 `usePermission` POST scan/verify/listing | 前端按钮无权限码，后端 `require_login` |
| ④ 跨租户 | A token + B install id | 0 |

非法边三项断言（状态未变 / 无成功审计 / **无 installs 行、不写源树、不改 listing**）：现网越权用例里，租户创建公司那条有「零落库」；**能力域扫描越权零落库 = 0 条**。

### 5.3 管理详情泄漏路径

`get_capability_detail` 对任意登录回传 `file_path`（`capabilities.py:193`）。`test_capability_detail_ok_and_404` **不断言其不存在**——改掉不会红。GWT-13.3 候选：租户看管理详情无本机路径。这是缺口，不是会红项。公开白名单已禁 `file_path`，不要在扩 listing 字段时把路径放回来。

### 5.4 只读 vs viewer 词冲突

README / 部分测试仍是 `viewer/operator/admin`。产品矩阵：租户只读不能提交任务、不能订、不能改启用/信任/卸载。`test_b1b_templates` 等已证明 viewer 不能建模板——**能力订阅必须抄同一「角色×写」格，且用 tenant_role**。禁止用「任意已登录成员可订」填空（旧 QA-04/QA-20/QA-21；spec v1.4 已删该句，v2 不得写回）。

---

## 6. 会红用例清单（守卫/公开闸/健康枚举/表 同 PR 改写）

实现按 grok-files PR4/PR6 + D14/FR-18/ADR-0018 落地时，下列 **会红或变成假绿**。**不得先改产品、后补测试**——plan 已写「同 PR 改 `test_b1c`」。

| # | 旧用例 | 锁死的旧行为 | 候选新行为 | 改法 |
|---|---|---|---|---|
| R1 | `test_scan_plugins_ok` | viewer 200 + 落库 | 超管 200；viewer **403 + 零落库 + 审计越权** | 拆成 3 条；`viewer_client` 改成负向 |
| R2 | `test_scan_plugins_bad_dir_*` / `test_scan_experts_ok` | 同一 require_login | 超管才能 200 | 换 `platform_admin_client` |
| R3 | `test_plugin_verify_no_mcp_degraded` | `health=degraded` | ADR-0018：无 MCP → **`unknown` 可上架**；`degraded` 仅「声明了 MCP 但探测不完整」 | 同 PR 改断言；`test_mcp_bridge` 未锁 degraded（已有 unknown/down），以 b1c 为准 |
| R4 | `test_plugin_verify_*` / `test_team_upsert_*` | 登录可写 | 写=超管；组团是否算「目录变更」必须钉（旧 GWT-06 含组团） | 负向 + 零落库 |
| R5 | `test_scan_endpoint_returns_job_summary` | `admin_client` 扫技能 200 | `require_platform_admin` 后 plain admin **403** | 抄 plain_admin_403 + 超管正例 |
| R6 | `test_public_capabilities_only_stable` | 只 stable | listed∩(stable\|recommended)∩许可；预告可见 | **整夹具换成六行 GWT-18.2**，不要只改名字 |
| R7 | `test_public_list_only_published` | `/public/skills` 含 recommended、无 listing | 转调后必须带上架闸；未上架 recommended **不得**出现 | 锁兼容转调或删旧路径留一条等价 |
| R8 | `test_public_capabilities_fields_whitelist` | 无 listing/installable/license | 扩白名单，仍禁 `file_path`/`sync_state` | 更新集合 |
| R9 | `test_public_capabilities_invalid_type_falls_back_skill` | bogus→skill | 五类 + `expert` 别名 | 等 PM 钉 bogus 语义 |
| R10 | `test_scan_marks_missing_directory` | 任意缺目录 → missing | 仅第一方；第三方 writable=0 不标 missing 去写盘 | 加第三方夹具 |
| R11 | `test_correction_writes_db_then_meta_yaml_and_changelog` | `written_back is True` 必写盘 | 第三方 `written_back:false`，源树不变 | 按 writable 分正/负 |
| R12 | `SkillsSquare.test.tsx` 列表 + XSS | `listPublicSkills` | 新页 `listPublicAssets`；**XSS 必须先迁再删** | 同 PR 迁 Capabilities |
| R13 | `ALL_ORM_TABLES` / `test_all_orm_tables_on_mysql` | 无 sources/installs/aliases | PR1 加表 | 扩集合；注释删「14 表」 |
| R14 | `TENANT_EXEMPT_TABLES` 对拍 | 无 `capability_assets` | 平台目录应豁免；**禁止豁免 `capability_installs`** | 豁免测试 + 反例：installs 必须注入 tenant_id |
| R15 | Admin 文案 / 无 Jest | 「验证后方可分发」 | 上架≠验证 | 前端改写；Jest 锁按钮权限码 |
| R16 | `test_newapi_api` 正例 `admin_client` | 租户 admin 可读/可配渠道 | 写=超管；读对租户 = 隐藏+直打同 404（GWT-07.3） | 正例改超管；plain admin 写 403+原值；读路径与 404 同形 |

D16 回退：`ENABLED=false` 或 SOURCES 空时 `scan_plugins(root=tmp)` 仍只扫夹具——**HTTP 守卫变更与扫描根回退不是同一用例**。回退扫描 **≠** 公开闸全开（NFR-03）。

---

## 7. 覆盖缺口（相对候选 GWT，非全矩阵）

> 现网 1050 条绿灯 **0 条**对齐旧 Wave 0/1 GWT。下表只记与本波三焦点 + 验收主干相关的空洞。

### 7.1 必须先有、否则「修对了 CI 仍逼你写错」

| 空洞 | 为什么现在写不出有效用例 | 层 |
|---|---|---|
| viewer/租户 admin 扫描 **403 + 零落库 + 审计** | 旧用例锁 200；无负向 | 集成 |
| 公开六行夹具（GWT-18.2） | 无 listing 列、无许可、无「测试中」行 | 集成 |
| 黑名单公开详情与 404 **字节级同形** | capabilities 无公开详情路由；技能 404 未对拍 body | 集成 |
| 预告 POST 订阅 → 无安装行 | 路由不存在 | 集成 |
| 只读订/改启用/信任/卸载 | 无 tenant_role 夹具 | 集成（JWT） |
| 跨租户改安装 | 表不存在 | 集成 |
| SQL 闸后再分页；页大小=命中数的 `has_more` | 页内滤发布态 | 集成 |
| 第一方回填 listed、第三方保持 unlisted | 无 Source / listing | 集成 |
| XSS 在能力市场详情 | 只活在即将退役的 SkillsSquare | Jest |
| `file_path` 不对租户出现 | 管理详情正例不断言缺字段 | 集成 |
| 扫描空目录可行动空态（GWT-06.2） | 只有 succeeded 计数，无「没有可同步的包」文案 | 集成 |
| 扫描审计 | scan-plugins 不记审计 | 集成 |

### 7.2 安装 / 宿主（0 格，新方案一写路由就必须有）

合法：无记录 → 已订阅（启用开/信任关）→ 关启用 / 确认开信任 / 卸载；同一能力第二宿主 **新行不覆盖**。  
非法（每条三项断言）：预告/未上架/未过闸订、超管无企业、只读、跨租户、开信任不确认、订阅写回资产信任、不兼容宿主、已声明空名单、黑名单改启用。

### 7.3 前端 / 其它柱（会在同一程序里被问「测了没」）

| 面 | 现状 | 缺口 |
|---|---|---|
| official Home/Pricing/Register | Home 1 条 h2 smoke；Pricing/Register **0** | 虚构数字 `128,000+`（`Home.tsx:32`）；注册成功主按钮「再注册一家」（`Register.tsx:54`）。Q-PRICE 未关前只测负向 |
| official Capabilities | **0** | 预告标、搜索空态、失败≠空、订阅回跳 |
| admin Capabilities | **0**；验证无 `usePermission` | 超管才见扫描；租户隐藏源/上架 |
| Usage/导出 | 配额 429 有；前端 0 | 100 条界上/界外；跨租户导出；禁止 `QUOTA_EXCEEDED` 字样 |
| 埋点 FR-15/30 | 产品事件 **0** | 有查询面之前标 ❌ 不是 ✅；禁止用审计日志冒充分母 |
| LLM 月度闸 | `check_llm_tokens_month` **仅测试调用** | 经规划入口才算覆盖 |
| 时区 | `tenant_usage.py:26` `datetime.utcnow()` | 无 freeze_time 上海月界 |

### 7.4 空心断言（假绿，与市场冲突独立，碰配额/密钥时会误导）

| 位置 | 行为 |
|---|---|
| `test_saas_wiring.py:49` | `... or True`：配额拒绝主题永真 |
| `test_saas_byok.py:45` | `"a-key" in cfg.source or True` |
| `test_skill_harvester.py:93-95` | `"backend" not in [str(m) for m in ()]` |
| `test_db_behavior_loop.py:66-79` | EXPLAIN 对模拟 dict；CI 保真子集不含真 SQL |

---

## 8. 全新方案验收必须钉的风险

下列是 **写用例前必须在 v2 spec/契约出现的 oracle**。缺任一条，`/qa` 只能写「待补 GWT」，不能把格子标 ✅。本角色不代选。

### 8.1 身份（不钉则所有 403 用例会对错人）

1. **平台超管 = `is_platform_admin=true`**，不是 `role=admin`。GWT 里「租户公司管理员」必须能映射到 `admin_client` / JWT `tenant_role=admin ∧ is_platform_admin=false`。
2. **只读 = `tenant_role=viewer`**（或产品点名的只读码），与 legacy `role=viewer` 是否等价要写死。订阅/改安装与「能创建任务」同级。
3. 超管无企业空间订阅：403「需要企业空间」+ **无安装行**（旧 GWT-20.3）。商店验收是否挂 platform 租户，矩阵按 403。

### 8.2 公开闸（不钉则 only_stable 改写会各写各的）

4. 公开公式：上架∩治理∩许可；**测试中 / 已弃用** 列必须在矩阵里（旧 GWT-18.2 ⑤⑥）。
5. 黑名单详情与「页面不存在」**同形**（状态码+body 不得多「已被拉黑」）。
6. `coming_soon` 在列表、`installable=false`、POST 订 **422 且无行**。
7. `/public/skills`：兼容转调（带 listing 闸）还是 301/到达市场且筛技能？**XSS Jest 迁徙路径必须同时指定**。
8. 公开闸 **SQL 内完成后再分页**；`page_size` 界上 50（NFR-02）；非法 `type` 语义；`expert` 请求是到达智能体还是 404。
9. 第一方已发布回填 listed；第三方同步 **不得** listed（GWT-31/22.2）。默认 `unlisted` 切闸空窗有专用空态，不是把未上架第三方填空。
10. 白名单允许 `listing_state`/`installable`/`license`；**永远禁止 `file_path`**。租户管理详情同样禁路径。

### 8.3 写面与健康枚举

11. 扫描/验证/上架/源/许可放行 = `require_platform_admin`；**禁止** `require_admin` 顶替。越权三项：403、目录/listing/源树不变、审计越权。扫描本身要审计（今日没有）。
12. 无 MCP：`unknown` 可 listed；`degraded` 仅 MCP 探测不完整。CONTEXT 已写 unknown，**代码+b1c 仍是 degraded**——新方案必须点名 superseded ADR-0001 那一行（旧 ADR-0018 已写，v2 要么继承要么重开）。
13. Wave 1 **无**「启用到宿主」按钮。详情禁止「已在你的宿主里运行」。
14. 组团 upsert 是否算 FR-06「目录变更」：算则 viewer/租户 admin 403；不算则另写 GWT，避免测试各写各的。

### 8.4 安装与宿主

15. 宿主名单：**NULL/未声明 = 四宿主可订**；**已声明空数组 = 四个都不可订**（旧 QA-23 / GWT-20.7/20.8）。第一方默认走未声明，不走空数组。
16. 不兼容宿主：选项灰掉；提交拒绝；无行。≠ 启用到宿主。
17. 同一能力多宿主：**多行共存**，再订不覆盖（GWT-20.9）。
18. 下架后安装保留、不可新订；黑名单安装只读可卸（GWT-29）。
19. 订/卸只作用于这一行，不级联子卡（D24/FR-34）。

### 8.5 测法纪律（写进契约/票，否则矩阵有格无效力）

20. listing×治理×许可×override：**pairwise** + 高危全组合（listed+blacklist、coming_soon+POST、UNLICENSED±override、dev-team+listed、测试中）。权限/支付类不 pairwise。
21. 新表唯一键 / 许可 `COALESCE` / `JSON_CONTAINS(host_compat)` / 生成列 `alive_flag` → **MYSQL_FIDELITY 子集必须纳入**，否则 ESC-2 同类逃逸。
22. Q-VOICE/Q-PRICE 关闭前：允许只测「不得出现硬编码数字 / 付费档不得与免费注册同一出口」负向；正向 CTA 标 ➖。
23. `capability_installs` **禁止**进 `TENANT_EXEMPT_TABLES`；`capability_assets` 豁免必须与 R13 清单同时改。
24. 空心 `or True` 不得进回归；非法边不断言「无行」= 漏测一半。

---

## 9. 夹具（缺则市场票不可测）

已有：`client` / `admin_client`（非超管）/ `viewer_client` / `operator_client` / SQLite `db_*` / 各文件重复的 `cap_library` / 分散的 `_platform_admin_token`。

必须新增（实现帽，不在本诊断创建）：

- `platform_admin_client`
- 双租户 JWT（经办 / 只读 / 公司管理员）安装 client
- 六行公开夹具（GWT-18.2）+ license 四态 + override 0/1
- `writable` 0/1；第一方 vs 第三方树
- `dev-team` 包；git 单插件 `"."` 与 monorepo
- uri 逃逸负例；`ALLOWED_LOCAL_PREFIXES` overlay
- `build_source` / `asset` / `install` / `alias`
- 公开限流桩与现 `rate_redis` 收敛，避免第三份

---

## 10. 分层与裁剪

```
可见性纯函数（listing×status×license）     → 单元
resolve_origin_path / hash 折叠 / uri      → 单元
租户隔离、安装幂等、许可闸、同步不改 listing → 集成（SQLite + MYSQL_FIDELITY）
扫描/验证 RBAC（含零落库）                 → 集成，真 JWT，禁止 admin_client 冒充超管
官网承诺/CTA/XSS                         → Jest
浏览→登录→订阅主干                       → verify curl（不新建浏览器套件）
EXPLAIN / 生成列唯一 / 安装并发           → 专项真库
```

| 裁剪 | 策略 |
|---|---|
| listing×治理×许可 | pairwise + §8.5 高危全组合 |
| 插件清单格式 | plugin.json / .zcode-plugin / kimi.plugin.json 各一 |
| E2E | 不新建；宪法 `e2e: null` |
| 真 superpowers / 真 Kimi 桌面 | 禁止 vendor；file:// + tmp |

---

## 11. 给下游

| 给谁 | 内容 |
|---|---|
| `/pm` | v2 spec 必须显式继承或重开 §8 的 24 条。旧 findings 第 4 轮没跑，不要把 v1.4 自称关闭当 v2 冻结。Q-VOICE/Q-PRICE 未关则文案正向 ➖ |
| `/architect` | 公开闸 SQL 形状；`file_path` 不进协议；`require_platform_admin` 不得写成 `require_admin`；host_compat HTTP 语义跟 PM |
| `/backend` | **同期改写 §6**；先落地 `platform_admin_client`；LLM 配额勿只测未接线函数 |
| `/frontend` | XSS 先迁 Capabilities 再删 SkillsSquare；扫描/验证走权限码；F5 水合抄 `usePermission.test.tsx`（ESC-3） |
| `/dba` `/sre` | 新表进 `ALL_ORM_TABLES` + MYSQL_FIDELITY；真 EXPLAIN；installs 禁止豁免 |
| `/qc` | 定义未关闭；市场 0 覆盖；本文件不是放行。全矩阵留给定义关闭后的实现帽 |

---

## 12. open_questions（本角色仍要答案才能写用例）

1. v2 是否继承 D14：扫描/验证/上架 = `require_platform_admin`，组团 upsert 是否同一守卫？
2. `/public/skills` 四条：锁兼容转调还是迁 capabilities + 一条等价？XSS 迁徙文件名？
3. 无 MCP：一次性改 `unknown`，还是过渡双枚举？（CONTEXT 已 unknown，b1c 仍 degraded）
4. 非法 `type` 与旧值 `expert`：400 / 兜底 skill / 映射 agent？
5. CI MYSQL_FIDELITY 是否在加 sources/installs 的同一 PR 纳入唯一键？延迟 = ESC-2 同类。
6. pairwise 是否接受为 listing×治理×许可的裁剪（高危组合见 §8.5）？
7. Q-VOICE/Q-PRICE 关闭前，FR-01/05 是否允许只测负向？
8. 超管无企业订阅：商店验收挂不挂 platform 租户？

已有候选冻结、v2 若推翻必须显式重开：订阅不占三类配额；下架后安装保留；探针伪装不熔断；只读拒订；NULL 名单=四宿主可订。

---

## 13. 覆盖统计（基线，非质量结论）

| 项 | 数量 |
|---|---|
| 后端收集用例 / 文件 | 1050 / 103 |
| 前端 Jest / 文件 | 16 / 7 |
| E2E | 0 |
| 旧 Wave 0/1 GWT 对齐且断言仍成立 | **0** |
| listing×治理 格子 | **0** |
| 安装状态机格子 | **0** |
| 已知锁错契约（§6） | 16 处 |
| 空心断言 | ≥4 |
| 需真库 ⚠️ | 许可闸、JSON_CONTAINS、生成列唯一、EXPLAIN、安装并发 |

能力域看似 `test_b1c` 一整文件，对准的是 P6 扫描 + stable 公开，不是能力市场。

---

## 14. 自检

- [x] 未写 `04-verify/coverage.md` / 未填 FR↔TC 全矩阵（定义未关闭）
- [x] 未改测试代码
- [x] viewer 可扫 / 公开列表 / 权限 三冲突有文件:行证据
- [x] 会红清单与「只改 assert 仍假绿」的夹具陷阱分开写了
- [x] 缺业务规则回 `/pm` `/architect`，未代选 Q-VOICE/PRICE
- [x] 非法边三项断言、三类越权、方言保真已点名
- [x] 裁剪策略已声明
- [x] 未替 `/qc` 做放行
- [ ] 全矩阵行号：等 v2 spec 冻结后实现帽回填
