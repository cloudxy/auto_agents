# 实现证据 · T-13 公开商店/精选过滤测试种子（PIT-5 双公开端同 PR）

> 票：contract §11 T-13（FR-80）｜FR 锚点：FR-80（GWT-80.1…80.4）｜角色：/backend｜日期：2026-09-11
> 依据：contract §7.5 公开商店 + §1 现状测绘 PIT-5（双公开闸）+ spec FR-80（种子谓词三支）
> 范围闸：不做翻页/页大小 ≤20（T-14）、不动治理台与上架状态机（listing.py 未触碰）、`market_list_paged` 事件归 T-14。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 种子谓词常量（三支口径） | 读模型常量 | `backend/services/power_market/types.py` | `SEED_NAME_PREFIX="nfr01qc2-"` / `SEED_TITLE_PREFIX="NFR卡片"` / `SEED_DESC_MARKER="preprod nfr-01 seed"`，与 GWT-80.1 同口径 |
| 种子谓词（SQL 查询闸） | **读模型层（Service 单点）** | `backend/services/power_market/service.py::_seed_clause` | `lower(name) LIKE 'nfr01qc2-%'`（大小写不敏感）∨ `title LIKE 'NFR卡片%'` ∨ `description LIKE '%preprod nfr-01 seed%'` |
| 种子谓词（行级闸，详情/订阅） | 读模型层（同一文件） | `service.py::_row_is_seed` | 与 `_seed_clause` 同口径；`_row_is_fr33` 引用 |
| 接入点：列表/total/精选/includes | 查询闸 | `service.py::_fr33_clause`（追加 `not_(_seed_clause())`） | `_list_fr33`（列表+COUNT total）与 `_list_includes`（详情内含组件）共用 → **两公开端同一谓词同一闸** |
| 接入点：公开详情/订阅 | 行级闸 | `service.py::_row_is_fr33`（追加种子判定） | 种子详情 = 商店不存在句 HTML；订阅 = `MARKET_NOT_FOUND`（GWT-80.3 翻 listed 也不外泄） |
| Router | 不改 | `backend/app/api/v1/public_skills.py` 零改动 | `/public/skills` 与 `/public/capabilities` 本就同汇 `PowerMarketService.list_public`（读码确认），谓词收在读模型即两端同生效 |

**双公开端落点（PIT-5）**：
- `/api/v1/public/skills`（官网能力市场「技能」+ **首页能力精选数据源**）——精选无第三端点：`frontend/official/src/components/home/SkillsSection.tsx` L28-29 调 `listPublicSkills({page:1, page_size:50})`，即同一 `/public/skills` 列表调用；测试按该形态（page_size=50）单独断言。
- `/api/v1/public/capabilities`（官网能力市场「全部」/类型筛）——含跨类型验证（plugin 类种子同样被滤）。
- 两份测试同 PR（同一测试文件内两端口径各一份，9 测试）。

**分层依赖核对**：☑ Router 未 import ORM（未触碰 Router） ☑ Service 未返回 ORM 对象（未改投影） ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（arch.sh 绿）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/types.py` | 修改 | +3 谓词常量（5 行） |
| `backend/services/power_market/service.py` | 修改 | +`_seed_clause()` / `_row_is_seed()`，接入 `_fr33_clause()` / `_row_is_fr33()`；模块头与两闸 docstring 注明 FR-80 |
| `backend/tests/test_t13_public_seed_filter.py` | 新增 | 9 测试：GWT-80.1…80.4 ×（技能端/能力端） |

**未触碰**：`listing.py`（上架状态机）、`capabilities.py` 管理端（治理台可见性不在 GWT-80.3 规定）、Router、ORM、迁移。**未 git commit**（票禁令）。

## 3. 关键实现决策

- **谓词收在读模型层，不散落**：单一 SQL 子句 + 单一行级函数，挂在 FR-33 公开闸上；无任何「if 测试租户」式散落，治理台/管理端列表不受影响（`CapabilityService.list_assets` 独立路径，未动）。
- **大小写不敏感只作用于短名**（契约原文仅短名带「大小写不敏感」）：SQL 用 `func.lower(name) LIKE`，行级用 `(name or "").lower().startswith`，两端同口径；标题「NFR卡片」前缀与描述标记按契约字面精确匹配。
- **列表/精选/total/详情/订阅五面同滤**：total 在 COUNT 子查询之前排除（先滤后 COUNT，不破坏 FR-33 查询侧闸）；精选=同一列表调用形态；详情/订阅经行级闸 → 种子与真 404 同形（HTML）。
- **GWT-80.3 防御深度**：种子行在夹具中先 unlisted 再直改 DB 翻成 listed（模拟任意路径的「对访客可见上架」），公开面仍全滤——谓词独立于 listing_state，租户/治理翻状态无法放进公开商店。

### 事务/幂等/并发/外部依赖

| 项 | 结论 | 理由 |
|---|---|---|
| 事务 | N/A | 纯读路径过滤，零写操作 |
| 幂等 | N/A | 无新增写入口 |
| 并发 | N/A | 无写竞争面 |
| 外部依赖 | N/A | 未新增外部调用 |

## 4. ORM 与 DBML 对齐

N/A——零模型/迁移改动（只读模型谓词）。

## 5. 可观测性

N/A 变更——`list_public` / `get_public` / `subscribe_public` 入口日志（R10）已存在，本票未动方法签名；谓词不记日志（无敏感数据）。

## 6. 自测证据（原样粘贴）

**红（TDD：实现前，谓词未落）**：

```
$ uv run pytest -q backend/tests/test_t13_public_seed_filter.py
=========================== short test summary info ===========================
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_1_skills_list_excludes_seeds
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_1_skills_featured_shape_excludes_seeds
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_1_capabilities_list_excludes_seeds
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_2_skills_empty_after_seed_filter
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_2_capabilities_type_empty_after_seed_filter
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_3_seed_flipped_listed_still_hidden_skills
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_3_seed_flipped_listed_still_hidden_capabilities
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_4_fixture_searchable_skills
FAILED backend/tests/test_t13_public_seed_filter.py::test_gwt_80_4_fixture_searchable_capabilities
9 failed in 3.57s
exit: 1
```

**绿（实现后）**：

```
$ uv run pytest -q backend/tests/test_t13_public_seed_filter.py
.........                                                                [100%]
9 passed in 3.73s
exit: 0
```

**Power Market 域全量回归（14 个读模型/公开端/目录测试文件）**：

```
$ uv run pytest -q backend/tests/test_t13_public_seed_filter.py backend/tests/test_skill_public_api.py backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_capability_catalog.py backend/tests/test_t22_list_filters.py backend/tests/test_t25_subscribe.py backend/tests/test_t26_installs.py backend/tests/test_t27_references.py backend/tests/test_t28_listing.py backend/tests/test_t29_sources.py backend/tests/test_t30_command_cards.py backend/tests/test_t31_license.py backend/tests/test_t32_market_events.py backend/tests/test_t33_aliases.py
.......................................                                  [100%]
183 passed in 109.49s (0:01:49)
exit: 0
```

**后端全量**：

```
$ uv run pytest -x -q backend/tests
1374 passed, 36 skipped, 7 warnings in 201.52s (0:03:21)
exit: 0
```

**架构红线**：

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

**Lint（改动文件）**：

```
$ uv run ruff check backend/services/power_market/service.py backend/services/power_market/types.py backend/tests/test_t13_public_seed_filter.py
All checks passed!
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试（两公开端各一份） | 结果 |
|---|---|---|
| GWT-80.1 列表/精选/total 不含种子 | `test_gwt_80_1_skills_list_excludes_seeds` / `test_gwt_80_1_skills_featured_shape_excludes_seeds`（首页精选形态 page_size=50）/ `test_gwt_80_1_capabilities_list_excludes_seeds`（全部+type=plugin） | ✅ |
| GWT-80.2 空态=正常空列表 | `test_gwt_80_2_skills_empty_after_seed_filter` / `test_gwt_80_2_capabilities_type_empty_after_seed_filter`（200 + total 0 + items [] + has_more False；空态句由前端既有文案承接） | ✅ |
| GWT-80.3 种子翻 listed 仍不出现 | `test_gwt_80_3_seed_flipped_listed_still_hidden_skills` / `..._capabilities`（列表 total 0 + 详情 404 与真 404 同形 HTML + 订阅 `MARKET_NOT_FOUND`） | ✅ |
| GWT-80.4 夹具对照 | `test_gwt_80_4_fixture_searchable_skills` / `..._capabilities`（q=pdf 含 `example-pdf-extractor`、不含会命中搜索的种子；未新开商店模型，夹具行直插） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（纯读路径，零写） |
| 幂等 | — | ➖ N/A（无新写入口） |
| 并发写 | — | ➖ N/A（无写竞争面） |
| 外部依赖失败 | — | ➖ N/A（未新增外部调用） |

## 7. NFR 验证

票内无 NFR 指派本票（NFR-01/02 计时归 T-14/verify）。种子滤后公开体量只降不升，COUNT 仍在查询侧闸内完成。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① MySQL 方言复核点：短名大小写不敏感用 `lower(name) LIKE`（CI 测试在 SQLite；MySQL utf8mb4 下同语义）。② 预发清污验证：现存 400 张 `nfr01qc2-*` 行无需删库，本闸直接滤；`example-pdf-extractor` 需在预发为 listed 才可对照（GWT-80.4 Given）。③ 全量套件在本共享工作树上有跨票漂移失败（其他泳道并行编辑 auth/billing 文件，见 §9）；本票域回归 183/183 绿。 |
| `/frontend`（T-14） | 后端行为已定：0 结果正常返回空列表（GWT-80.2 后端半）；`PAGE_SIZE_MAX` 公开端仍为 50——收到 20 归 T-14，本票未动（票禁令）。首页精选与市场列表共用 `/public/skills`，无需第三端点。 |
| `/architect` | 无契约歧义。一处口径确认已按契约字面执行：大小写不敏感仅修饰短名支（标题/描述支按字面精确匹配）。 |

## 9. 过程记录（共享工作树的跨票干扰，非本票缺陷）

全量套件在并行泳道共编的工作树上多次出现**漂移失败**，逐一向独立运行求证均绿、且都在其他泳道正在编辑的文件（git status `M`）：`test_auth_service.py`（auth 改动中）、`test_billing_relay.py`（T-01/02 改 `ORDER_ONLINE_UNAVAILABLE` 中）、`test_db_fixtures.py`、`test_outbound_migration_041.py`（T-04 新增，全量序中曾因 fixture 顺序尝试真 MySQL 报 Access denied；与本票二文件同跑验证为干净 skip）。最终一次全量（含本票改动）exit 0（§6 引用）。判定：与本票无关；留档供 qa 复跑参考。

## 10. 交票自检

- [x] 每条验收项（GWT-80.1…80.4 × 两公开端）有 evidence（命令 + 退出码原样）
- [x] 自测全绿（红→绿留档；域 183/183；全量 1374 passed exit 0；arch exit 0；ruff exit 0）
- [x] 契约落位表已核对，分层无违规（Router 零改动，谓词收读模型单点）
- [x] ORM 与 DBML 一致（零模型改动）
- [x] 无硬编码连接串/密钥/端口/阈值（谓词常量为契约冻结口径，非环境值）
- [x] async 上下文无同步阻塞调用（未新增调用）
- [x] 无 `except: pass`
- [x] 日志已脱敏（未新增日志）
- [x] 事务里无外部调用（无事务）
- [x] 四类易漏测试 N/A 已给理由
- [x] 未做 T-14 翻页 / 未动治理台与上架状态机 / 未 commit（票禁令全遵守）
