# 实现证据 · T-19 治理收回技能/插件；目录不含已从源删除的行

> 票：contract §11 T-19（FR-88）｜FR 锚点：FR-88（GWT-88.1…88.5）｜角色：/backend｜日期：2026-09-11
> 依据：contract §1 现状测绘（命令收回已兑位置：`sync.py::_retract_missing_commands`）+ §11 T-19 行 + spec FR-88
> 范围闸：只做技能/插件同步收回 + 治理目录过滤；不动公开商店过滤设计（T-13 已做，仅一处 NULL 语义缺陷修复，见 §8）、不动上架状态机（`listing.py` 零改动）、不动公开页大小（T-14）。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 治理目录不含已收回行（GWT-88.1/88.2/88.3 列表+total） | **Service（读模型）** | `backend/services/capability_service.py::list_assets` | 基座加 `deleted_at IS NULL`；空态句/`empty` 由既有 Router 逻辑按 total=0 触发，Router 零改动 |
| skills/scan 路收回（GWT-88.1 第一方技能） | Service | `skill_service.py::scan_library` → `_retract_missing_assets` → `capability_service.py::retract_skill_assets` | 只动 `detail_id` 镜像行（本扫描创建）且 `source_id IS NULL`（未 attach 源）——单一归属 |
| scan-plugins 路收回（GWT-88.2 第一方插件） | Service | `plugin_service.py::scan_plugins` → `_retract_missing_plugins` | 只动 `source_id IS NULL` 的第一方插件行；软收不物理删文件/目录 |
| 源同步路收回（GWT-88.1/88.2 第三方；GWT-88.5 命令同构） | Service | `power_market/sync.py::_retract_missing_rows` | 替换原 `_retract_missing_commands` 为三类型统一收尾：整包删除时插件行+包内技能/命令随包收回（不留孤儿行）；同步失败的包保留不动（失败≠源删除） |
| 公开商店无已收回行（叠加断言） | 已兑（不新做） | `service.py::_fr33_clause`（`deleted_at IS NULL` 既有） | 测试叠加断言 `/public/skills`、`/public/capabilities` 收回前后行为 |
| 越权拒绝（GWT-88.4） | 已兑（不新做） | Router `require_platform_admin` + `listing.py::_load_asset`（软收行 404） | 租户 403 FORBIDDEN；平台超管对已收行上架也 404（行对上架写不存在）；测试断言公开商店不变 |
| 软收可逆（目录回归复活） | Service | `capability_service.py::upsert_skill_asset` / `plugin_service.py::_load_alive_or_revive` | 存活行优先；仅剩软收行取最新清 `deleted_at`——镜像行生死跟随源目录，不永久滞留 gone |

**分层依赖核对**：☑ Router 未 import ORM（Router 零改动） ☑ Service 未返回 ORM 对象（未改投影） ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（arch.sh 绿）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/capability_service.py` | 修改 | `list_assets` 加非软删基座；`retract_skill_assets()` 新增；`upsert_skill_asset()` 存活优先+复活（133 行） |
| `backend/services/skill_service.py` | 修改 | `scan_library` missing 行挂收回钩子（best-effort，与 `_sync_asset` 同口径）；job detail/summary 增 `retracted`（737→758 行，超 500 为既有债，见 §3） |
| `backend/services/plugin_service.py` | 修改 | `scan_plugins` 收尾收回；`_load_alive_or_revive()`；result/job detail 增 `retracted`（274 行） |
| `backend/services/power_market/sync.py` | 修改 | `_retract_missing_commands` → `_retract_missing_rows`（plugin+skill+command 统一收尾）；`_sync_package` 返回 keep 集；`_run_packages` 汇总（376 行） |
| `backend/services/power_market/service.py` | 修改 | `_seed_clause` 三支 `coalesce`——NULL 语义缺陷修复（见 §8，T-13 区域最小修复） |
| `backend/tests/test_t19_governance_retract.py` | 新增 | 7 测试：GWT-88.1×2（scan/src_sync）、GWT-88.2×2（scan-plugins/src_sync）、88.3、88.4、88.5 |

**未触碰**：`listing.py`（上架状态机）、`capabilities.py`/`skills.py`/`public_skills.py` Router、ORM/迁移（零 schema 改动）、公开页大小。**未 git commit**（票禁令）。

## 3. 关键实现决策

- **与已兑命令收回同构（软收）**：统一 `deleted_at = now` + `sync_state = 'gone'`，不物理删 DB 行、不物理删源文件/目录；软删行靠 `alive_flag` 生成列脱离 `(asset_type, name)` 唯一键（迁移 025 语义），源回归时按路径各自复活或重建。
- **三路单一归属，防互踩**：每行只归一路收回——skills/scan 只收 `detail_id IS NOT NULL AND source_id IS NULL` 镜像行；scan-plugins 只收 `source_id IS NULL` 第一方插件行；src_sync 只收 `source_id = source.id` 行。本机 plugins/ 与源注册表指向同一棵树时两路互不误收。
- **src_sync 收尾移到 run 末**：原命令收回在包内（`_upsert_commands` 尾），整包删除时其技能/命令成孤儿。现 `_run_packages` 收集每包 keep 集（skill/command）+ 包名集，run 末统一收尾：包删 → 插件行 + 包内技能/命令随包收回；包在但同步失败（在包名集、不在 keeps）→ 保留（解析/DB 失败≠源删除）。
- **目录过滤收在 `list_assets` 单点**：治理台列表、可上架列表、total、空态（`还没有目录项`）一次收口；总件数不被 gone 行顶满即 COUNT 前置过滤的自然结果。
- **既有债标注**：`skill_service.py` 改前 737 行已超单文件 500 行红线（仓库既有，非本票引入）；不在此拆分（他票在途文件，拆动冲突面大）。权威闸 `tools/check/arch.sh` 绿。
- **软收可逆**：skills/scan 与 scan-plugins 两路复活软收行（目录回归→清 `deleted_at`，保留人工治理字段）；src_sync 路保持既有「删后重建新行」语义（`_load_named` 只找存活行 + `alive_flag` 唯一键放行，模型注释明示的 harvester 重建口径），不改。

### 事务/幂等/并发/外部依赖

| 项 | 结论 | 理由 |
|---|---|---|
| 事务 | N/A 新增 | 三路收回均在既有扫描/同步事务内（`scan_library`/`scan_plugins`/`SourceSync` 自持事务，ADR-0007 D3），无新事务边界 |
| 幂等 | 天然幂等 | 收回是条件置位（`deleted_at` 已置则查询不命中）；重复同步无新增副作用 |
| 并发 | N/A | 单写者（主后端扫描/超管同步入口），无新增读改写竞争面 |
| 外部依赖 | N/A | 未新增外部调用 |

## 4. ORM 与 DBML 对齐

N/A——零模型/迁移改动（软收用既有 `deleted_at`/`sync_state`/`alive_flag` 列）。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 收回日志 | `capability.retract_skill_assets` / `plugin.scan 收回缺失插件` / `src_sync 收回缺失行`（R10 入口日志，含 count，无敏感数据） |
| 扫描摘要 | `scan`/`scan_plugins`/`src_sync` job detail 与返回值均增 `retracted`，可审计收回量 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token（只记名称与计数）

## 6. 自测证据（原样粘贴）

TDD（packet companion_skills=[tdd]）：先红后绿，红测证明测试确实钉住缺口（目录含已删行/无收回）。

```
$ cd /Users/xuyun/auto_agents && uv run pytest -q backend/tests/test_t19_governance_retract.py --log-cli-level=ERROR
============================== 7 failed in 3.74s ===============================
exit:1
# 红因（各测试断言点）：目录仍含已删行（'t19-scan-skill' not in ['t19-scan-skill'] 失败）、
# scan-plugins/src_sync 无收回、total 被 gone 行顶满（2 != 1）、空态不可达、软收行可再上架

$ cd /Users/xuyun/auto_agents && uv run pytest -q backend/tests/test_t19_governance_retract.py --log-cli-level=ERROR
============================== 7 passed in 9.90s ===============================
exit:0

$ cd /Users/xuyun/auto_agents && uv run pytest -x -q backend/tests
1414 passed, 37 skipped, 7 warnings in 519.59s (0:08:39)
exit:0

$ cd /Users/xuyun/auto_agents && bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit:0

$ cd /Users/xuyun/auto_agents && uv run ruff check backend/services/capability_service.py backend/services/plugin_service.py backend/services/skill_service.py backend/services/power_market/sync.py backend/services/power_market/service.py backend/tests/test_t19_governance_retract.py
All checks passed!
exit:0
```

**全量跑批次说明**：本票全量首跑（03:56）在 `test_b1b_templates_coverage.py::test_run_from_template_viewer_403` 红一次——非本票回归：该测试文件彼时正被并行泳道改写（失败输出断言 `400 == 403`，盘上即时已是 `== 400`；单跑绿）。差分归因时 `git stash push -- power_market/service.py` 会连 T-13 未提交的种子过滤一起暂存（同文件），导致 t13 测试假红——两处均为共享工作树并发编辑假象。复跑（当前树，本票改动在位）1414 全绿。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-88.1 正常·技能（scan 路与 src_sync 路各一） | `test_gwt_88_1_skill_retract_after_scan` / `test_gwt_88_1_skill_retract_after_src_sync` | ✅ |
| GWT-88.2 正常·插件（scan-plugins 路与 src_sync 路各一） | `test_gwt_88_2_plugin_retract_after_scan_plugins` / `test_gwt_88_2_plugin_retract_after_src_sync` | ✅ |
| GWT-88.3 空态 + 总件不顶满 | `test_gwt_88_3_catalog_empty_state` | ✅ |
| GWT-88.4 越权（租户改收回/上架已收行） | `test_gwt_88_4_tenant_cannot_touch_retracted` | ✅ |
| GWT-88.5 命令收回不回潮 | `test_gwt_88_5_command_retract_no_regression` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（收回在既有扫描事务内，无新多步写） | |
| 幂等 | `test_gwt_88_5_command_retract_no_regression`（第二次同步不回潮=重复收回幂等） | ✅ |
| 并发写 | ➖ N/A（单写者扫描入口，无新增竞争面） | |
| 外部依赖失败 | ➖ N/A（无新增外部依赖；`_retract_missing_assets` best-effort 同 `_sync_asset` 口径） | |

## 7. NFR 验证

票无 NFR 条目（FR-88 无性能锚点；收回路径随扫描/同步任务跑批，不进请求热路径）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/architect` | **T-13 区域缺陷修复报备**：`_seed_clause` 原 `or_(nameLIKE, titleLIKE, descLIKE)` 在 description/title 为 NULL 时经 SQL 三值逻辑得 `not_(NULL)=NULL` → 任意 listed+stable+MIT 但 description NULL 的行（如全部 src_sync 技能行）整行被挡出公开列表，而详情/订阅行级闸 `_row_is_seed`（Python None 容忍）判为非种子——列表与详情对同一行结论相反，违反 FR-33 闸的自洽。本票以 `coalesce(col, '')` 最小修复（匹配语义不变，NULL=非种子）。若认为该行为是 T-13 有意设计请回滚该 hunk 并重认口径。 |
| `/qa` | 已知边界：软收行的治理详情 `GET /capabilities/{type}/{name}` 仍可读（`get_asset` 未滤软删——GWT 只约束列表，详情口径待产品裁定）；`skill_service.py` 737→758 行超 500 红线为既有债；MySQL 保真通道未跑（`MYSQL_FIDELITY=1`，SQLite 全绿）。 |
| `/frontend` | 无差异：治理目录 API 形状不变，仅行集与 total 收紧；空态复用既有 `empty`/`message` 字段。 |
| 管理窗 | 并行泳道共享工作树：全量跑曾被 `test_b1b_templates_coverage.py` 在途改写打断（03:56）；`power_market/service.py` 同文件多票叠加，`git stash -- <file>` 差分法对该文件失效（连 T-13 未提交改动一起暂存）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（7/7 新测试 + 全量 1414 passed + arch.sh + ruff）
- [x] 契约落位表已核对，分层无违规（Router 零改动）
- [x] ORM 与 DBML 一致，未自行加字段（零 schema 改动）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（未新增 Redis/IO 用法）
- [x] 无 `except: pass`（best-effort 均记 warning 日志）
- [x] 日志已脱敏（只记名称/计数）
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」（收回=条件置位，天然幂等）
- [x] 条件更新的 `rows == 0` 已处理（集合过滤，无 rows 计数依赖）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（§8 `_seed_clause` NULL 缺陷报备 architect）
- [x] 票状态：done（证据落盘）
