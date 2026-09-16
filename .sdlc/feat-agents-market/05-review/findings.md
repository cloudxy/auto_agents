# Findings · implement G-fresh（2026-09-16，最新快照）

> 入口：`/sdlc-review`（人工入口，**report-only**，不推进 `hats_done`/`current_hat`）。
> 评审帽：`sdlc-workflow:reviewer` 不在 host spawn 表 → 按 recipe step 4 单次 `general-purpose` 回退
> （子代理读 `PLUGIN_ROOT/agents/reviewer.md` + `skills/findings/SKILL.md`）。`host_spawn` 已记 state.yaml。
> 上一份 shape r3 快照已归档为 `findings-shape-r3.md`。

## Snapshot

判据（contract/spec 侧）：

- 01-define/spec.md = 1fc48a67616f7564dbcd87c81dbe7ade191c0667c5a6d9cc26261e022c4b6867
- 02-shape/contract.md = b35a3a3150499efe6f1080214bcebe840cdb5c6ab4ae6054e22942aa3d46c2a0
- 02-shape/db-spec.md = 826ec32e7eb0c03f7ed0bafe361634760ae022e7b64ed854f9be8fdc4fcb02bb
- 02-shape/edge-states.md = 6d347382c405b178912e6f5b5712d978b8a23ebcc5c2fcad40ea6e2a0a7169d4

被判物（implement 侧）：

- 03-impl/T-00-evidence.md = d985285ba61bceef30d85ea801648a92226828fae0003f9eddc30f92d83ca89a
- 03-impl/T-06-evidence.md = 5fb8045618f60d00bf17144784144fd42b44c33d0362b343f596f8a26780b47d
- 03-impl/T-07-evidence.md = eb31dc3a6485aa3d779ee3d8ccd30964a0b3eb1538a621102c5a9e2e9edc1511
- 03-impl/T-12-evidence.md = f50081b514ccfb23f71e3a54bf280200cefff1723a149fcbac9126a5de0ae94a
- 03-impl/T-14-evidence.md = c6846d2823a1decf04c7c8a9f63be547de88c59602b68ef37f919e3a91e1f95c
- 03-impl/T-11-T-15-frontend-fix-evidence.md = 64a41b1296b05a68f357d1b131257a5838c112bdb780cab0a51375f05677b1f3
- state.yaml = 4728927e383f2ef1a1f9474c4e7c473a8a7de7a8fa55ef6901f532530ca147cb
- 工作区代码集（`git status` 去 .sdlc/ 与 package-lock 后逐文件 sha256 再取摘要）= 69b397870f4b1e71ff6d2bfbb8fe1425fd11042a3c2b0830044b52cb1c7228fd

## Verdict: **FAIL**（2 blocker + 6 major + 8 minor）

阻塞项 QA-1（安全）、QA-2（FR-03 验收通道不可执行）未修前，implement 阶段不得进 verify/qc。

## FINDINGS

### QA-1 `hub_import._land` 缺出口收容断言，经 `.agents/plugins/` 既有符号链接把导入内容写到仓库外（并可 rmtree 删除仓外真实目录）
- Dimension: 4 | Severity: **blocker** | Evidence: `backend/services/power_market/hub_import.py:252-268`（对照 `backend/services/asset_import_service.py:130-136` 的 `_contained_write`）
- 事实锚点：`AGENTS.md:90` + 实测 `ls .agents/plugins/` —— 本仓库 `.agents/plugins/*` **全部**是指向 `~/.zcode/local-plugins/*` 的符号链接（dev-team / drama-skills / mattpocock-skills / oh-story / sdlc-workflow / superpowers）。
- 复现（reviewer 在 /tmp 沙箱照抄 `_land` 逻辑）：上传名为 `dev-team` 的插件树 → 顶层 `_land` 因 `rmtree` 拒绝 symlink 而记 failed（**运气，不是设计**）→ 紧接着 bundled 子项 `_land(".agents/plugins/dev-team/skills/evil")` 的 `dst.parent.mkdir(parents=True)` 穿过符号链接，`copytree` 把内容写进了仓库外的真实插件目录。若同名子目录已存在，先执行的是 `shutil.rmtree(dst)` —— **删除仓外真实插件内容**。
- Root cause: AD-4a 只把路径清洗写在**入口**（`_clean_rel`，QA-8 处方），落盘**出口**没有对应条款；实现帽照处方办事，没把仓库既有的出口收容惯例（`_contained_write`）带过来。AD-4c 又把落盘根从沙箱式的 `capability-library` 换成**真实的、含符号链接的** `.agents`，威胁面随之变化，shape 阶段没有重做这段 STRIDE 走查——「入口已清洗」被当成了「全链路已安全」。
- Fix: `hub_import.py:252` 起，写入前加 `dst.parent.resolve().is_relative_to(real_agents.resolve())` 断言，并对 `dst` 或其任一父分量是 symlink 的情况直接判失败入 `failed`。更好的做法是把 `asset_import_service._contained_write` 的断言抽成 `power_market` 共享函数，两条导入通道共用（顺带消掉 QA-9）。
- Prevent: ① `test_tree_import.py` 加负向用例：夹具在 `agents_root/plugins/` 建指向 `tmp_path/outside` 的符号链接，导入同名插件树后断言 `outside` 树零变化且该项进 `failed`；② `tools/check/arch.sh` 加机械检查「服务层 `shutil.copytree|copy2|rmtree` 的目标路径同函数内必须出现 `is_relative_to(`」；③ `_lessons.md` 记 ESC：「换落盘根 = 换威胁模型，入口清洗不替代出口收容」。

### QA-2 前端从不发送 `preview=true`，AD-5c/T-13 的超管预览旁路端到端不可达 —— FR-03 的「验收路径声明」整条通道是死的
- Dimension: 1 | Severity: **blocker** | Evidence: `frontend/admin/src/services/capabilities.ts` 的 `PublicListQuery`（无 `preview` 字段）与 `compactPublicQuery`（无 `preview` 键）；`fetchPublicCapability` 无 query 参数；`frontend/admin/src/pages/Capabilities.tsx:108-113` 预览态与租户态渲染同一个 `<TenantShelf>`、不传任何 preview 标志。后端 `backend/app/api/v1/public_skills.py:117/:159-162/:210-213` 要求 `request.query_params.get("preview") == "true"`。
- manager 复核：`capabilities.ts` 里出现的 `preview?: boolean` 全部在**响应**类型（`PublicShelfList` / 详情）上，请求侧确无该键。claim 成立。
- 后果链：`TenantShelf.tsx:150` 的 `previewBadge` 恒 false（T-13 badge 永不出现）；`:177` 的 `canSync` 恒 false；`AssetDetailDrawer.tsx:67` 的 `unlistedPreview` 恒 false（OQ-D1 的「未上架」标签永不出现）。叠加附加 c 的默认闸关 → 超管点「货架预览」看到的仍是关闭态货架，**spec FR-03「未标闸后的货架 UI 类 GWT 经超管预览入口验收」这条验收路径声明本身无法执行**，GWT-03.1/03.2/03.3、04.1–04.4、05.1/05.3、06.1–06.3 全部失去可用验收通道。另：导入行一律 `unlisted`（AD-4e），治理表格点名称开抽屉 → 无 preview → 404 → 抽屉关闭 + 「详情加载失败」——刚导入的资产在治理面永远看不到详情。
- Root cause: 票表把旁路切成两半（T-04 后端参数 / T-13 前端入口），而「谁把 `preview=true` 放进 query」既不在 AD-5c 也不在两票的验证列里 —— 契约 §4 #7/#8/#9 只写了**响应**里的 `preview:true`，没写**请求**契约。两侧各自按自己那半实现、各自用 mock 测绿（`TenantShelf.test.tsx:416-422` 直接 mock 返回 `preview:true`；`test_public_detail_preview.py` 直接构造带 query 的请求），跨帽交接处无人持有整条线。
- Fix: 三处最小 diff —— `PublicListQuery` 加 `preview?: boolean` + `compactPublicQuery` 里 `if (params.preview) query.preview = 'true'`；`fetchPublicCapability` 增第三参并拼 `params`；`Capabilities.tsx` 把 `shelfPreview` 透传给 `TenantShelf`（再到 `listPublicAssets` 与 `ShelfCard→AssetDetailDrawer`）与 `CatalogTab`（治理面开抽屉恒 `preview=true`）。
- Prevent: ① 契约「API 契约」表拆**请求**/**响应**两栏，新增请求参数必须点名调用方票号；② 「后端加参数、前端加消费」的跨 lane 改动，下游票验证列写死「断言请求实参含该参数」——组件测试应断言 `fetchList` 被调用时的实参，而不是 mock 的返回值；③ `_lessons.md` 加 ESC：「mock 服务层的组件测试不能证明请求侧契约」。

### QA-3 `ExamplesModal` 用无 preview 的公开详情读示例，闸关/unlisted 时读到空，保存即用空列表覆盖已维护内容（静默数据丢失）
- Dimension: 8 | Severity: major | Evidence: `frontend/admin/src/pages/market/ExamplesModal.tsx:37-47`（`.catch(() => setItems([]))`）与 `:63-72`（`submit` 用当前 `items` 整体 PATCH）
- 该文件注释自称「读源 = 公开详情 payload 的 examples（预览态豁免后 unlisted 也可读）」——注释与代码不符（没传 preview）。默认闸关 → closed payload 无 `examples` → `items=[]`；unlisted → 404 → catch → `items=[]`。管理员看到「还没有示例」，随手保存 = `PATCH {examples: []}` = 抹掉库里已有示例。
- Root cause: QA-2 的请求契约缺口；叠加一个独立缺陷——「读失败」与「读到空」在状态机里被合并成同一个态。edge-states §7 定了「失败保留用户输入」，没定「读失败时写操作必须锁」。
- Fix: `.catch(() => { setLoadError(true); setItems([]) })`；`submit` 开头 `if (loadError) return`；保存按钮 `disabled={loading || loadError}`，渲染「示例读取失败，请重试后再保存」。
- Prevent: edge-states 六态表加通用条款「Error 态下同面的写动作一律禁用」+ designer 自检勾项；`ExamplesModal` 补用例：`fetchPublicCapability` reject → 保存按钮 disabled。

### QA-4 治理目录端点不投影 `featured`/`examples`，CatalogTab 星标刷新即丢，GWT-04.5 的治理面 oracle 在真实端点上不成立
- Dimension: 1 | Severity: major | Evidence: `backend/services/capability_service.py:47-62`（`list_catalog` items 字典白名单无 `featured`/`examples`）；消费方 `frontend/admin/src/pages/market/CatalogTab.tsx:150-158`
- `AssetRow.featured` 恒 `undefined` → 星标恒 `StarOutlined`、非超管 Tag 恒 `—`。乐观更新在 `patchFeatured` 返回后短暂显示精选，一点「刷新」或切筛选触发 `load()` 就回退。GWT-04.5 的 Then 有两半（货架置顶 + 治理面回显），只成立一半。
- Root cause: T-05 只交「列」，T-06 只交「公开读投影 + PATCH 端点」，而 `list_catalog` 属既有治理端点、不在任一票的改动面清单里（contract §3 模块边界表没列 `capability_service.py`）。FR×票矩阵按 FR 查漏，不按**字段的全部读路径**查漏。
- Fix: `capability_service.py:60` 附近加 `"featured": int(getattr(r, "featured", 0) or 0),`；`capabilities.ts:22` 的 `featured?: boolean` 同步改 `number`（见 QA-12）。
- Prevent: contract §5「数据契约需求」表加「读路径清点」栏，新列必须列出所有展示它的端点；coverage-matrix 加「新列 × 读端点」交叉表。CatalogTab 用例改用契约夹具（从 `list_catalog` 真实投影键集生成），不要在 mock 返回里硬塞 `featured`。

### QA-5 `projection._md_path` 的 legacy 分支丢掉 `rel`，`SKILLS.LIBRARY_ROOT` 为绝对路径时读错文件 —— 相对 HEAD 是回归
- Dimension: 1 | Severity: major | Evidence: `backend/services/power_market/projection.py:67-74` vs `git show HEAD:backend/services/power_market/service.py`（原 `Path(LIBRARY_ROOT) / rel / "SKILL.md"`）
- manager 复核：HEAD 原式对绝对/相对两种配置都正确；迁出后写成 `return library if library.is_absolute() else Path.cwd() / library / rel`，**绝对分支整个 `rel` 被丢弃** → 去读 `<LIBRARY_ROOT>/SKILL.md`（通常不存在 → 恒空正文；恰好存在则返回**别的资产**的正文）。claim 成立。
- Root cause: AD-5a 的处方是「按前缀分流」，实现帽在写分流时顺手把「绝对/相对」归一化也重写了一遍，而这段归一化在原代码里根本不存在（`Path / rel` 天然处理两种情况）。默认配置 `LIBRARY_ROOT: "capability-library"` 是相对路径 → 绝对分支零覆盖 → 回归静默通过。
- Fix: 一行：`return (library if library.is_absolute() else Path.cwd() / library) / rel`。
- Prevent: `test_public_detail_preview.py` 加参数化用例，把 `SKILLS.LIBRARY_ROOT` 分别设成相对与 `tmp_path` 绝对路径，断言同一 legacy 行都读到正文。规则化：**「迁出/重构」票的自检清单加一条「逐行与 `git show HEAD:<原文件>` 对拍，行为差异必须在 AD 里有出处」**。

### QA-6 OQ-2「落盘统一 .agents」缺存量数据迁移：磁盘源仍在的 capability-library 行会被 prune 当失源软删
- Dimension: 1 | Severity: major | Evidence: `backend/services/power_market/agents_hub.py:79-97`（候选 = live ∩ 四类 ∩ `source_id IS NULL`，磁盘集只来自 `.agents`）；`backend/services/asset_import_service.py:354-372`（只有**新**导入带 `.agents/` 前缀）；仓库实存 `capability-library/skills/example-pdf-extractor`
- `_expert_legacy_clause`（:47-65）只为 **agent** 型 legacy 行做了 `file_path NOT LIKE '.agents/%'` 保护；skill/command/plugin 型 legacy 行毫无保护。且这会与 AD-5a 明文要求保留的 `_read_skill_md` legacy 兜底分支互相矛盾：要么 legacy 行存在（兜底有意义、prune 不该删），要么不存在（prune 该删、兜底是死代码）。
- Root cause: OQ-2 被裁为「执行统一」，但裁定只覆盖**写路径**（落盘根 + 新行前缀），没覆盖**存量**。AD-3 的 prune 候选谓词在 OQ-2 裁定**之前**定稿（那时 `.agents` 与 capability-library 并存是既定事实），QA-7R 返工又只收窄了 agent 型判别式，没推广到其余三类。三次局部修补，没有一次做全量口径复盘。
- Fix: 最小改法是给 `prune_missing_assets` 候选加 `or_(file_path.is_(None), file_path.like(".agents/%"))`（NULL 按 QA-14 裁定仍视为可清），并把 `_expert_legacy_clause` 退化为只保 agent 侧行；T-03 补正向用例：legacy skill 行（无前缀 + 磁盘源在 capability-library）prune 后仍 live。
- Prevent: 凡「真相源切换」类决策，contract 的 OQ 条目强制填三格：**新写路径 / 存量数据处置 / 读路径兼容期**，缺任一格不得标「执行」。`_lessons.md` 加 ESC：「切根 = 写路径 + 存量迁移 + 读兼容三件套，缺一即产生对账黑洞」。

### QA-7 `_persist_event` 的主会话兜底反转了「事实与主路径解耦」的设计承诺；失败路径上事件仍会丢，GWT-08.2 的用例只覆盖了安全路径
- Dimension: 3 | Severity: major | Evidence: `backend/services/product_event_service.py:59-93`（:61 注释仍写「主路径 rollback 不得带走已发生的事实」，:91-93 兜底把事实写回主会话）；`backend/app/api/v1/capabilities_gov.py:195-202`；`backend/services/power_market/hub_import.py:234`
- 三条路径复核：①`sync_completed` 端点随后 commit，兜底可落盘 —— 无问题；②`import_failed` 走 `_guard_count`/`_collect` 的 422，主会话零脏写 → 独立会话正常提交 —— 无问题，这正是现有用例覆盖的那条；③**`import_failed` 走 `hub_import.py:234` 的 `await session.flush()` 抛错**（该 flush 在 try 之外）：主会话已脏 → SQLite 下 250ms 后 `OperationalError` → 兜底 `add+flush` 落在已失败事务上 → `PendingRollbackError` → 被宽 except 吞掉 → **事件永久丢失**。CI 主 job 正是 SQLite，即 GWT-08.2 在最需要它的失败模式下不成立。
- MySQL 侧：`PRAGMA busy_timeout=250` 只对 sqlite 生效（显式判方言），MySQL 走 `innodb_lock_wait_timeout`（默认 50s），一旦撞上就是 50 秒同步阻塞，无对应短等处理。
- Root cause: D-1 修的是真问题（CI 口径 100% 丢事件 + 每次 30s 干等），但选的是「降级保证」而非「改变发射时机」。真正的分叉（outbox / commit 后发射 / 降级）在设计层没被记录：实现帽在票内做了架构级取舍，contract 无对应 AD，G-fresh 之外无人复核。
- Fix: ① 立刻改正注释与 docstring，让它描述实际保证；② 把 `confirm_tree_import` 的最终 `flush()` 移进 `try`，并在端点 `except` 里先 `await session.rollback()` 再 `emit_import_failed`（回滚后主会话干净，独立会话就能提交）；③ MySQL 分支加 `SET SESSION innodb_lock_wait_timeout = 1` 与 sqlite 的 250ms 对齐；④ 中期改 outbox 或「commit 后发射」。
- Prevent: ① `_lessons.md` 记 ESC：「实现帽在票内做了架构级降级（弱化既有保证）必须回写 AD 并标注」；② `test_governance_events.py` 补用例：monkeypatch 让最终 flush 抛 `IntegrityError`，断言 `import_failed` 仍可检索；③ arch.sh 弱检查：保证词出现处必须有同名回归用例。

### QA-8 FR-01 GWT-01.3「不存在能造成软删的扫描入口」不成立，也没有任何用例验证它
- Dimension: 1 | Severity: major | Evidence: `backend/services/power_market/sync.py:99/:241-282`（`SourceSync._retract_missing_rows` 写 `row.deleted_at`，由 `POST /capabilities/sources/{name}/sync` 触发）；另有 `backend/services/capability_service.py:147-172` `retract_skill_assets`
- contract §1 断言「旧扫描端点（**唯一**破坏入口）」——该事实锚点是错的。`test_sync_endpoint.py` 只测了 `sync-agents-hub` 自己不软删，没有一条用例按 GWT-01.3 的字面口径遍历全部扫描/同步入口。
- Root cause: shape 的 §1 事实锚点只清点了「导致本次 bug 的那条通道」，没做「全部写 `deleted_at` 的代码路径」的机械清点（一条 `grep -rn "deleted_at = " backend/services/` 就能列全）。GWT 用全称量词（「所有…入口」），票表用存在量词（「删掉 scan-plugins」），二者没对齐，qa 也没把全称量词翻译成可执行用例。
- Fix: `test_sync_endpoint.py` 加守卫用例：遍历 OpenAPI 里路径含 `sync|scan` 的 POST 端点逐个以超管调用，断言 `capability_assets` 新增 `deleted_at` 行数为 0；对 `sources/{name}/sync` 这条已知例外，要么显式 xfail + spec 写明豁免理由，要么改成 retract 需显式 `?retract=true`。
- Prevent: ① 帽子清单加：**GWT 出现「所有/任一/全部」等全称量词时，验证列必须是遍历式断言而非举例断言**；② shape 的「代码事实锚点」章节加强制项：凡断言「唯一 X」，必须附产生该结论的 grep 命令与输出。

### QA-9 `_land` 的覆盖式 `rmtree + copytree` 会静默删除真实 `.agents/<type>/<name>` 下不在上传树里的文件，预览只标 "update" 不告警
- Dimension: 8 | Severity: minor | Evidence: `backend/services/power_market/hub_import.py:262-268`；预览侧 `:271-287` 的 `_actions` 只产出 `create|update`
- 典型伤害面：`.agents/skills/<name>/icon.png`、`background.png`（049/媒体端点依赖）不在上传树里时被一并删掉 → 卡片图回落占位、`row.logo` 指向不存在的文件。edge-states §6 的向导六态完全没有这一态。
- Root cause: AD-4e 只定义了**DB 行**的 upsert 语义，没有定义**磁盘**的 upsert 语义；实现帽把最省事的「整目录替换」当成了 update 的自然落地。
- Fix: 保守改法 `dst.mkdir(parents=True, exist_ok=True)` + `shutil.copytree(src, dst, dirs_exist_ok=True)`，不再 rmtree。
- Prevent: contract 里凡出现 upsert 的票，AD 必须分列「DB 语义」与「磁盘/外部副作用语义」两行；`test_tree_import.py` 补用例：先落带 `icon.png` 的 skill，再只上传 `SKILL.md` 重导，断言 `icon.png` 仍在。

### QA-10 契约 §4 #4 要求 confirm 响应含 `batch_id`，实现不返回
- Dimension: 6 | Severity: minor | Evidence: `backend/services/power_market/hub_import.py:235-237` vs contract §4 第 4 行；前端 `capabilities.ts:163-169` 把 `batch_id` 声明为 optional 从而「自圆其说」
- Root cause: 契约字段清单与实现之间没有机械核对；TS 侧用 `?:` 把缺口吸收掉，于是三方都「没错」。
- Fix: `confirm_tree_import` 返回值加 `"batch_id": uuid4().hex[:12]`，端点传给 `emit_import_completed(batch_id=...)`（该形参已存在但从未被传值；db-spec §10 裁定回执号不入库、走 `product_events.props`）。
- Prevent: 为治理端点补一份**响应 data 键集金标**（类比 `openapi_routes_golden.txt`）进 CI；TS 侧对契约必填字段禁用 `?:`。

### QA-11 抽屉渲染 `install_count` 但后端从不返回；唯一用例传 `install_count: 0` 走的是隐藏分支（空洞断言）
- Dimension: 3 | Severity: minor | Evidence: `frontend/admin/src/pages/market/AssetDetailDrawer.tsx:142-144`（`!= null && >= 1`）；`AssetDetailDrawer.test.tsx:146`（`install_count: 0`）；后端 `projection.py:17-44` 与 `service.py:get_public` 全程无该字段
- 用例传 0 恰落在「n≥1 才显示」的隐藏分支，断言「没有计数」恒真 —— 把未实现当成了已实现。
- Root cause: OQ-D3 由 designer 提出、state.yaml 记为「预览态显示订阅计数」，但没落进任何 AD、任何票、任何 API 契约行；前端按 edge-states 文案表把 UI 做了，后端没人被告知要加字段。
- Fix: `get_public` 在 preview 分支查 alive 订阅计数写入 `item["install_count"]`（`sorting._install_counts` 可复用）；用例改为传 3 断言可见 + 传 0 断言不可见（两分支都钉）。
- Prevent: ① designer 的 OQ 一旦被裁定，必须由 architect 回写成 AD 或票，`state.yaml.shape_rulings` 不是交付载体；② 组件用例对「条件渲染」必须同时钉真假两分支。

### QA-12 `featured` 三方类型不一致：DB/后端 `int(0|1)`、TS `boolean`
- Dimension: 6 | Severity: minor | Evidence: `projection.py:34`、`curation.py:54`（均 `int(...)`）vs `capabilities.ts:22/:276/:308`（`boolean`）；`CatalogTab.tsx:85-92` 乐观更新写 boolean 后被 PATCH 返回的 int 覆盖
- 当前靠 JS 真值语义侥幸不炸，但同一 `rows` 数组里会同时存在 `true` 与 `1`，任何 `=== true` 的后续改动都会踩雷。
- Root cause: db-spec 选 smallint（仓库布尔惯例），契约 §4 只写「行快照」没写字段类型，前端按语义命名猜成 boolean。
- Fix: `capabilities.ts` 三处改 `number`；`CatalogTab.tsx:85` 用 `row.featured ? 0 : 1` + `patchFeatured(..., Boolean(next))`（请求体契约仍是 bool）。
- Prevent: 契约 §4 响应要点栏补类型标注（`featured:int(0|1)`），并纳入 QA-10 的响应金标。

### QA-13 ORM 缺 db-spec §8 明写的 `default=0`；`projection.py` 对 050 列的 `getattr(..., 0)` 是空洞防御
- Dimension: 6 | Severity: minor | Evidence: `platform_core/models/capability.py:86-91`（只有 `server_default="0"`）；`projection.py:5` 注释 +`:34`
- 模型一旦声明列，`select(CapabilityAsset)` 在 050 之前的库上就直接 unknown column —— `getattr` 永远到不了它声称保护的场景，而 `sorting._apply_sort` 直接用 `CapabilityAsset.featured.desc()` 毫无防御。防御强度不一致本身就是「没想清楚」的信号。
- Root cause: T-05（dba）与 T-06（api）并行，api 帽在列还没合进来的窗口期写了临时兼容代码，合流后没清理；db-spec 的 ORM 片段是逐字规格但没机械比对。
- Fix: `capability.py:88` 加 `default=0`；`projection.py:34` 改 `int(row.featured or 0)`，删注释。
- Prevent: `tools/check/db_migrations.sh` 加检查：迁移里 `nullable=False + server_default` 的列，ORM 侧必须同时有 `default=`（AST 可判）；impl 帽清单加「并行票合流后清理临时兼容代码」。

### QA-14 prune 响应的 `live_total` 不是存活行数，而是「对账候选数 − 剪除数」，T-15 的 toast 逐字用它当「存活」呈现
- Dimension: 6 | Severity: minor | Evidence: `agents_hub.py:88`（`live_before = len(rows)`，rows 已排除 team / `source_id` 非空 / legacy agent / 非四类）、`:104-108`；文案 `edge-states.md:495`；消费方 `PruneConfirmModal.tsx:71`
- 作为**对账** oracle（`live_total == disk_total`）是对的；作为呈现给人的**存活**数字是错的 —— 管理员会看到一个比治理目录小的数。
- Root cause: AD-3 用「live_total」给一个对账中间量命名，designer 直接把这个名字写进成品文案，语义漂移没人拦。
- Fix: 后端同时返回 `reconcile_total`（oracle）与真 `live_total = count(live rows)`（文案用后者）。
- Prevent: edge-states 引用后端字段名入文案时，必须在 §10 文案表标注字段来源与口径；contract 响应要点栏给聚合量注明「口径」。

### QA-15 游离 agent 用 frontmatter `name` 作 slug，同目录两文件同名会静默互相覆盖并使 prune 对账少算
- Dimension: 8 | Severity: minor | Evidence: `agents_hub_scan.py:251-258`（`local = meta.get("name") or stem`；`slug = local`）；去重发生在 `agents_hub.py:79` 的集合推导
- 「游离 vs 插件内」撞名风险已排除（插件内一律 `plugin__` 前缀）。真正的窗口是**游离资产之间**：两份 md 的 frontmatter 同 `name` 时，第二个 `_upsert_item` 会 `_load` 到第一个刚 flush 的行并 update 它（不抛 IntegrityError），磁盘两份文件对应一行，`disk` 集合去重后也只有一项 —— 对账仍为 0 却掩盖了一份资产不可见。
- Root cause: AD-4g 只说「游离资产 name 不带 `plugin__` 前缀」，没定义游离资产的**唯一性来源**；插件内靠前缀 + 目录名保证唯一，去掉这层保护后没补替代品。
- Fix: `slug = f"{plugin}__{local}" if plugin else stem`（磁盘文件名唯一），并在 `_scan_loose` 返回前对 `(asset_type, name)` 做重复检测写 `logger.warning`。
- Prevent: `test_tree_import.py` 补用例：两个游离 agent 同 frontmatter name → 断言两行都入库（或其一进 failed）。规则化：凡引入新的「资产身份来源」，必须在 db-spec §3 唯一键章节写明它如何映射到既有唯一约束。

### QA-16 证据文件互相矛盾，且 T-00 的门禁证据是中间态（违反 `_lessons.md` ESC-8）
- Dimension: 3 | Severity: minor | Evidence: `T-11-T-15-frontend-fix-evidence.md` §3 遗留项「T-12 的 GWT-07.x 前端用例仍未写」 vs `T-12-evidence.md` §3「10 passed」+ `state.yaml.implement_progress.done` 含 T-12；`T-00-evidence.md` §3 贴的是 `1 failed, 1868 passed`，全文再无一次「0 failed」的全量输出，§6 自检却勾了「pytest 全量绿」
- `_lessons.md` ESC-8 逐字是「证据=最终通过的那次运行，中间态输出禁入」—— 同一条教训在同一仓库再次发生。
- Root cause: 跨会话接手（上一会话 quota 中断）导致证据是增量追加的，接手帽没回头复核前序证据的遗留段；ESC-8 的「新增检查」当时只写进 `impl.md` 清单（人工项），没有脚本化。
- Fix: 重跑全量并把终态输出替换进 T-00 §3；T-11/T-15 §3 改为「已由 T-12 补齐」。
- Prevent: 把 ESC-8 升级为脚本 —— `check-sdlc.sh` 扫 `03-impl/*-evidence.md` 的代码块，凡出现 `failed`/`error`/`exit: [1-9]` 且同文件内无后续同命令的 0 失败输出即 exit≠0。

## Dimensions checked

1. 标准符合性 ⚠️ — FR-01 验收线未真正成立（QA-8）；FR-03 验收路径不可执行、FR-05 抽屉默认闸态拿不到正文（QA-2）；GWT-04.5 治理面半个 oracle 不成立（QA-4）；OQ-2/OQ-D3 有裁定无落地（QA-6/QA-11）。无明显范围蔓延。
2. 标准质量 ⚠️ — GWT 本身可测；GWT-01.3 的全称量词没被翻译成可执行断言（QA-8）。§3.1 状态机与 prune/import 实际流转一致，未发现 GWT vs GWT 矛盾。
3. 证据有效性 ⚠️ — reviewer 独立复跑 `test_tree_import.py`（13 passed / 8.38s）、`test_shelf_sorting.py + test_prune_missing.py`（21 passed / 10.97s），后端证据数字可信；但 T-00 贴中间态（QA-16），前端「绿」有两处建立在 mock 掉请求侧（QA-2）与空洞分支（QA-11）之上。
4. 安全 ❌ — QA-1 blocker（符号链接路径逃逸，已本地复现）。复核通过项：`MarkdownBody.tsx` 未引 rehype-raw、react-markdown ^10 默认 `defaultUrlTransform` 拦 `javascript:`；`public_skills._safe_media_file` 的三重校验成立；越权 404 门面在 6 个治理端点齐全且有负向用例。
5. 性能 ✅ — hot 档左联复核无误：`_install_counts()` 已按 `asset_id` GROUP BY，每资产至多一行，`offset/limit` 不被放大；总数查询走 `stmt.subquery()` 不经 `_apply_sort`；`_q_clause` 的 `id.in_(子查询)` 与左联无冲突。未见 N+1（`_command_sides` 已批量）。
6. 契约一致性 ⚠️ — QA-2/QA-4/QA-10/QA-12/QA-13/QA-14 六处三方不齐。
7. 宪法合规 ✅ — 逐条对 `.claude/rules/project_rule.md`：R1 新键落 config、R10 服务入口 logger 齐全、API 层不 import ORM、B1–B3 无新增跨界 import、F-7 与 500 行（`service.py` 491 净减、`capabilities.py` 净减 13、最大新前端组件 326 行）、新端点全走 `responses.ok`、Q5 依赖走根 workspaces。
8. 边界 ⚠️ — QA-1/QA-3/QA-6/QA-9/QA-15 五处未闭。复核通过项：并发（GWT-01.7）「整轮回滚 + 重试两轮」实现与注释诚实；失效符号链接跳过（GWT-01.4）实现与日志在 `agents_hub_scan.py:123-126`；`curation` 的 `session.commit()` 与既有 `ListingWriter.set_listing` 同款、`record_audit` 走独立短事务不受影响 —— **原怀疑点排除，此处无 finding**。

## 越界观察（out-of-slice，不计入 FINDINGS 编号）

- **「扫描通道隐式软删」同类缺陷仓库至少三处并存**：`power_market/sync.py:241-282`、`capability_service.py:147-172`（`retract_skill_assets`）、以及本轮删掉的 `plugin_service.scan_plugins`。本轮只拆了第三处。`POST /capabilities/scan-experts` 仍指向已不存在的 `capability-library/experts`，随 OQ-2 切根后更是必然空扫 —— spec 的 Q-SCAN-EXPERTS 标为「下一轮」，但 OQ-2 使它从「行为未复现」变成「必然空扫」，建议提前判。
- **「路径收容」仓库里有三份互不相同的实现**：`asset_import_service._contained_write`（resolve + is_relative_to，最强）、`public_skills._safe_media_file`（前缀 + `..` 分量 + 后缀白名单，中）、`hub_import._land`（仅前缀，最弱 = QA-1）。建议抽 `platform_core` 级 `assert_contained(dst, root)` 并用 arch.sh 钉住「服务层写文件必须过它」。
- **`record_audit(session, ...)` 的 `session` 形参已不被使用**（`_helpers.py:48-56` 自述待机械工单移除），本轮 6 个新治理端点又新增 6 处传值。会随时间放大的机械债，建议下一张 L1 票一次性清掉。
