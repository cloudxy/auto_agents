# 实现证据 · T-37 专家团成员域扩 expert∪agent

> 票：contract §7.9「能力资产导入与专家团（FR-100/101）」+ §11 T-37 行｜FR 锚点：FR-101（GWT-101.1…101.5）｜角色：/backend（api+ui 联动票）｜日期：2026-09-11

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 成员域扩 expert∪agent（(type,name) 引用校验） | Service | `backend/services/expert_service.py::TeamService._normalize_members` / `_validate_team_refs` | 业务规则唯一落点；str 兼容旧调用（按 expert） |
| 组长仍仅专家（GWT-101.3 校验句中文） | Service | `_validate_team_refs` 团长前置分支 | 「团长必须从专家中选择: {name}（团长不支持智能体）」 |
| 成员去重（同 type+name 拒绝） | Service | `_normalize_members` | 「成员重复：{专家/智能体} {name}（同一成员只能加入一次）」 |
| 详情成员行类型标注（GWT-101.1/101.2/101.4） | Service 读模型 | `get_team_detail`（echo 存储形态）+ `export_team_md`（`name（专家/智能体）`） | 新数据 dict 形态带 type；旧字符串数据原样（全专家，前端按专家渲染） |
| 越权 404 同形（GWT-101.5） | Router 依赖 | `capabilities.py::upsert_team` 改挂 `require_platform_admin_or_404` | 与同文件 `/import`（T-35/GWT-100.6）同构；GWT-20.3 Then「拒绝且行不变」同时保持（404+零行+越权记录） |
| 成员选择器数据源（GWT-101.3 UI） | 前端组件 | `TeamLeafTab.tsx`：`listAssets('expert') ∪ listAssets('agent')`，分组+类型标签；组长仅专家 | 提交 payload `members: [{type, name}]`（value 编码 `type::name`，专家/智能体可同名） |
| agent 空态句（GWT-101.4 UI） | 前端组件 | 智能体分组空 → 禁用项 + Form.Item extra「还没有智能体资产」 | 纯专家组建路径不依赖 agent 存在 |
| 无执行承诺词 | 前端文案 | placeholder「并行执行」→「成员协同」；测试断言弹窗无 /执行\|运行/ | 不引入执行引擎（§5 保持） |

**分层依赖核对**：☑ Router 未 import ORM（服务层查 CapabilityAsset）☑ Service 未返回 ORM 对象（名称快照 dict，ADR-0007 D2）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（零 DDL，未动模型）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/expert_service.py` | 修改 | TeamService：`_normalize_members` / `_validate_team_refs` / upsert 存储归一形态；export 成员带类型；模块常量 `_TEAM_MEMBER_TYPES` / `_MEMBER_TYPE_LABELS` |
| `backend/app/api/v1/capabilities.py` | 修改 | POST /teams 守卫 `require_platform_admin` → `require_platform_admin_or_404`；members 透传（不再 str() 强转）；docstring 更新 |
| `backend/tests/test_expert_team.py` | 修改 | 新增 GWT-101.1..101.4 后端域 5 例（混合/纯专家+旧形态/团长守卫/去重/悬空+非法类型）；既有 3 例零改动 |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 金标改写：operator 403 → 租户 404 同形（PIT-2 同 PR，GWT-101.5）；新增混合成员路由 1 例 + 智能体悬空 422 路由 1 例；模块 docstring 同步 |
| `frontend/admin/src/services/capabilities.ts` | 修改 | 新增 `TeamMemberRef` / `TeamDetail` 类型 + `getTeamDetail` |
| `frontend/admin/src/pages/market/TeamLeafTab.tsx` | 修改 | 成员选择器 expert∪agent（分组+类型标签+编码）、团长仅专家、agent 空态句、详情弹窗（成员类型 Tag）、文案去「执行」 |
| `frontend/admin/src/pages/market/TypeLeafTab.tsx` | 修改 | 通用可选 prop `onDetail`（操作列「详情」按钮，与「订阅」并列；不改既有叶子行为） |
| `frontend/admin/src/pages/market/marketCopy.ts` | 修改 | 新增 `TEAM_AGENT_EMPTY = '还没有智能体资产'`（仅追加） |
| `frontend/admin/src/pages/market/TeamLeafTab.test.tsx` | 新增 | 组件面 5 例（见 §6 GWT 表） |

**与票里「会改哪些文件」一致**：☑ 是（后端 upsert_team 校验域 + 前端 TeamLeafTab 联动）。超出票面：详情弹窗（TypeLeafTab onDetail + getTeamDetail）——GWT-101.1/101.4 Then「团队详情中该成员可见且类型标注」要求 UI 呈现面，admin 此前无团队详情 UI，属票面 GWT 直含交付。

**未触碰「不许改的文件」**：☑ 确认（专家资产本体/扫描管线 `ExpertService.scan_experts`、`CapabilityTeam` 模型与 DDL、执行引擎相关零改动；`git status` 域内核对）

## 3. 关键实现决策

### 数据形态（零 DDL，members JSON 既有列）

| 入参形态 | 存储 | 详情 echo | 导出 |
|---|---|---|---|
| `["code-reviewer"]`（旧/兼容） | 原样字符串 | 原样字符串 | 裸名（无类型后缀） |
| `[{"type":"agent","name":"researcher"}]` | dict 原样 | dict（带 type） | `researcher（智能体）` |

既有金标 `teams[0].members == [EXPERT_NAME]` / `data["members"] == [EXPERT_NAME]` 因此零回退；旧数据全部为专家成员，前端 `normalizeMember`（str→expert）统一渲染。专家与智能体可同名：前端 value 编码 `type::name` 区分，后端按 (type,name) 二元组校验/去重。

### 事务边界 / 幂等 / 并发

| 项 | 结论 |
|---|---|
| 事务 | 单表（capability_assets + capability_teams 同域 upsert）沿用既有 flush+commit 形态，无多表跨域写 |
| 幂等 | 团队名 upsert 既有语义（二次提交 created=False，金标保持）；成员引用校验在写库前完成（422 零落库有断言） |
| 并发 | 无新增读-改-写竞态（members 整列覆写，无部分更新） |
| 外部依赖 | 无新外部依赖 |

## 4. ORM 与 DBML 对齐

☑ 零 DDL、零字段变更（票面「零 DDL（members JSON 既有）」兑现；未加索引/约束）。

**未自行加字段/改类型**：☑ 确认（需要变更回 /dba——无）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `upsert_team` 既有 `logger.info("专家团 upsert \| team=… leader=… members=N")` 保持（R10） |
| 越权记录 | `require_platform_admin_or_404` 内 `record_authz_denied`（authz.denied 落库，测试断言） |
| 日志脱敏 | ☑ 无密码/无 token（仅团队名/团长名/成员计数） |

## 6. 自测证据

> 命令与退出码原样粘贴。串行纪律：pytest 先定向后全量；前端 jest 因套件重（单套 60–600s）用 `--maxWorkers=2` 防资源争抢（见 §8 注记）。

### TDD 红（实现前）

```
$ uv run pytest -x -q backend/tests/test_expert_team.py -k "team_mixed or team_expert_only or team_leader_must or team_duplicate or team_agent_dangling"
...
E  sqlalchemy.exc.ProgrammingError: (sqlite3.ProgrammingError) Error binding parameter 2: type 'dict' is not supported
FAILED backend/tests/test_expert_team.py::test_team_mixed_members_expert_union_agent
1 failed, 3 deselected in 1.52s
```

```
$ npx jest src/pages/market/TeamLeafTab.test.tsx   # 旧组件（无团长（专家）标签/getTeamDetail）
Tests:       5 failed, 5 total
```

### 绿（定向 → 模块 → 全量）

```
$ uv run pytest -q backend/tests/test_expert_team.py backend/tests/test_b1c_capabilities_coverage.py
65 passed in 7.43s
exit: 0

$ uv run pytest -x -q backend/tests
1493 passed, 38 skipped, 7 warnings in 860.25s (0:14:20)
exit: 0
```

（全量基线 T-35 后 1486/38 → 1493/38：+7 = 本票新增后端用例，零既有失败。）

```
$ npx jest src/pages/market/TeamLeafTab.test.tsx
Tests:       5 passed, 5 total
exit: 0

$ npx jest --maxWorkers=2 src/pages/Capabilities.governance.test.tsx src/pages/Capabilities.subscribe.test.tsx \
    src/pages/Capabilities.command.test.tsx src/pages/Capabilities.import.test.tsx src/pages/market/TeamLeafTab.test.tsx
Test Suites: 5 passed, 5 total
Tests:       32 passed, 32 total
exit: 0

$ npx jest --maxWorkers=2     # 全量（独占窗口复跑）
Test Suites: 1 failed, 29 passed, 30 total
Tests:       1 failed, 176 passed, 177 total
exit: 1
```

全量唯一失败 = `NewApiOps.test.tsx › GWT-98.4 manual probe`（60s 超时）。定界：该套件属 T-31/32/33 泳道，与本票零 import 关系；单跑 `npx jest src/pages/NewApiOps.test.tsx -t "GWT-98.4"` → `2 passed`（本例 17.5s）——本机负载型 flake，非本票回归（首跑全量时与本票 pytest/build 并行更是 19 假红；涉改面 5 套件在限并发下 32/32 全绿）。

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend/services/expert_service.py backend/app/api/v1/capabilities.py \
    backend/tests/test_expert_team.py backend/tests/test_b1c_capabilities_coverage.py
All checks passed!
exit: 0

$ npm run build --prefix frontend/admin
Compiled successfully (warnings = 既有 LogDrawer.tsx eslint，非本票文件)
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-101.1 agent 成员入队+详情标注 | 后端 `test_team_mixed_members_expert_union_agent` / 路由 `test_team_mixed_members_expert_union_agent_route` / 组件 `team detail lists members with type tag` | ✅ |
| GWT-101.2 混合成员各自标注 | 同上三处（两类成员均保存，详情/导出分型） | ✅ |
| GWT-101.3 可选域=两类；组长仅专家 | 组件 `member domain is expert∪agent, leader stays expert-only`；后端 `test_team_leader_must_be_expert_not_agent`；前端组长选择器仅灌专家列表 | ✅ |
| GWT-101.4 无 agent 资产空态句+纯专家可组建 | 组件 `zero agent assets shows empty copy and expert-only team still works`；后端 `test_team_expert_only_when_no_agent_assets` | ✅ |
| GWT-101.5 越权 404 同形不产生团队 | `test_team_upsert_tenant_404_same_shape_zero_rows`（operator+admin 双角色：404、无 FORBIDDEN 信封、零 CapabilityTeam/expert_team 行、authz.denied 落库） | ✅ |
| 成员去重（票面） | `test_team_duplicate_member_rejected` | ✅ |
| 智能体悬空引用（票面） | `test_team_agent_dangling_and_bad_type` + 路由 `test_team_agent_dangling_route_422` | ✅ |
| 无执行措辞（票面） | 组件 `no execution wording on the create-team modal`（/执行\|运行/ 不出现；placeholder 已改「成员协同」） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（单域写，沿用既有 upsert 事务形态；422 路径零落库有断言） |
| 幂等 | `test_team_upsert_create_then_update`（既有金标，二次提交 created=False 零回退） | ✅ |
| 并发写 | ➖ N/A（members 整列覆写，无部分更新竞态） |
| 外部依赖失败 | ➖ N/A（无新外部依赖） |

## 7. NFR 验证

票面无 NFR 锚点。成员校验为 N+1 主键点查（成员数个位数量级），无列表页逐行查询新增。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① GWT-101.5 金标已按契约改 404 同形（operator 403 旧金标作废，GWT-20.3 Then 不变）；② members 返回为 **union 形态**（旧数据字符串=按专家，新数据 {type,name}），消费侧需 `normalizeMember` 同款归一；③ jest 全量在本机与 pytest/build 并行会争 CPU 出假红，建议 `--maxWorkers=2` 或独占窗口跑；④ 专家/智能体同名成员允许共存（(type,name) 二元组身份），抽检时可构造同名用例 |
| `/architect` | 无契约歧义。一处口径说明：GWT-101.5「页面不存在同形」按 404 落地（与 §7.9 FR-100.6 同构），原 `require_platform_admin` 403 信封被替换——若四柱侧仍需 403 语义请回签（GWT-20.3 原文只锁「拒绝且行不变」，未锁状态码） |
| `/frontend` | 详情弹窗经 `GET /capabilities/teams/{name}`；`TeamDetail.members` 为 union 形态（见上） |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（后端 1493/38 skip；前端涉改面 32/32、全量 176/177——唯一失败为本机负载 flake 且已定界非本票，见 §6）
- [x] 契约落位表已核对，分层无违规（Router 不 import ORM）
- [x] ORM 与 DBML 一致，未自行加字段（零 DDL）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（守卫/服务均为既有 async 形态）
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」（团队名 upsert 既有语义；引用校验是拒绝性校验非幂等键）
- [x] 条件更新 rows== 0 — N/A（无条件更新）
- [x] 外部依赖四件套 — N/A（无新外部依赖）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8 /architect 行）
- [x] 票状态：done（evidence 落盘即交）
