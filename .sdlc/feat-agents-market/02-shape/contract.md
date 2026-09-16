# Contract · feat-agents-market（02-shape）

> 泳道：L3｜FR=8（≤20，单 architect 拍）｜作者：architect 帽｜日期：2026-09-15｜**v1.2**（shape G-fresh r2 返工，修订记录见 §11）
> 输入：`01-define/spec.md` v1.2（define r3 PASS，sha256=1fc48a67…）· `00-discover/{briefing,recon}.md`（frozen）· `05-review/findings.md`
> 下游：implement（§7 票表为交付单位）· dba（§5 数据契约需求）· qa（GWT 是验收唯一来源，本文不重定义）
> 宪法：`.claude/rules/project_rule.md` + `tools/check/arch.sh`（R 系/B1–B3/F-7 全程有效）

---

## 0. WIP 基底（不回退清单 + T-00）

工作区未提交 WIP 是本 feature 的既有能力，**全部保留、禁止回退**：

| WIP 文件 | 作用 |
|---|---|
| `backend/services/power_market/agents_hub_scan.py` | collect：.agents 四类资产判型 + icon/background + content_hash |
| `backend/services/power_market/agents_hub.py` | 按 asset_type+name 增量 upsert（非破坏），dev-team 强制 unlisted |
| `backend/alembic/versions/049_asset_logo_background.py` | logo/background 列 |
| `backend/app/api/v1/public_skills.py`（M） | media 端点 + 闸门 |
| `backend/services/power_market/service.py`（M） | `_project` 注入 media href、`get_media_path` |
| `backend/services/capability_service.py`（M）· `platform_core/models/capability.py`（M） | 模型列 + 读路径 |
| `scripts/sync_agents_hub.py` · `scripts/runlib/ctl.py`（M） | CLI + 启动自动同步（失败不阻断） |
| `backend/tests/test_agents_hub_sync.py` · `backend/tests/openapi_routes_golden.txt`（M） | 单测 + 路由金标 |
| `frontend/admin/src/pages/market/TenantShelf.{tsx,css}`（M）· `services/capabilities.ts`（M） | 货架图渲染 |

**T-00（首票）**：跑 `uv run pytest -x -q backend/tests`（含 test_agents_hub_sync.py 与 golden）+ `uv run ruff check backend platform_core scripts` + `bash tools/check/arch.sh`，全绿才算基底成立；后续任何票不得使这些用例转红。

## 1. 代码事实锚点（决策依据，已逐条读码核实）

| 事实 | 位置 |
|---|---|
| bug 根因：root 不存在 → `_retract_missing_plugins(set())` 软删全部 `source_id IS NULL` 存活 plugin 行 | `backend/services/plugin_service.py:46-88`（:75 调用）、:150-174 |
| 旧扫描端点（唯一破坏入口）；admin 前端唯一调用方 | `backend/app/api/v1/capabilities.py:128-140`；`frontend/admin/src/services/capabilities.ts:117-118` |
| agents_hub upsert：只 insert/update，无 deleted_at 写路径；并发兜底 = DB `uq_asset_type_name_alive`（asset_type+name+alive_flag） | `agents_hub.py:56-106`；`platform_core/models/capability.py` `__table_args__` |
| 公开读模型三闸（list/detail/media 均 `is_power_market_enabled()` 短路，与用户身份无关） | `service.py:193-266` |
| **WIP 缺陷 A**：`_read_skill_md` 拼 `LIBRARY_ROOT/<file_path>/SKILL.md`，而 agents_hub 行 `file_path=".agents/skills/<name>"` → .agents 来源 skill 详情正文恒为空串 | `service.py:482-502` vs `agents_hub_scan.py:46-54` |
| **WIP 缺陷 B**：agent 正文 `persona_md` 存于 `CapabilityExpert` 但 `get_public` 不投影；plugin 无 md 正文（预期空态） | `service.py:233-251`；`agents_hub.py:148-157` |
| **侧行/前缀判别事实（QA-7R 锚）**：hub 入库对**每个**同步 agent 行都建 `capability_experts` 侧行（`_upsert_agent` 缺则建）→「有侧行」不构成遗留判别；hub 行 `file_path` 恒 `.agents/` 前缀（`_repo_rel` 的 repo 相对与兜底两路径产出同前缀；`_agent_item` 落库），legacy 导入行落 LIBRARY_ROOT（capability-library）→ 非 `.agents/` 前缀 | `agents_hub.py:148-157`；`agents_hub_scan.py:46-54`、`:200-235` |
| 货架读单入口：admin TenantShelf 与 official 同调 `/api/v1/public/capabilities`（带 Bearer） | `capabilities.ts:213-217`；`api.ts:12-13` |
| 存在性隐藏门面（越权 404 非 403） | `backend/app/api/deps.py:176-192`；`CurrentUser.is_platform_admin` deps.py:50-60 |
| 事件基建已存在：`emit_product_event`（product_events 表，可检索）；market_events.py 仅常量+封装层 | `backend/services/product_event_service.py:74`（封装层 `market_events.py:53-64`） |
| 现有导入：multipart .md/.zip 或服务器路径，落盘根 `SKILLS.LIBRARY_ROOT=capability-library`（与 .agents 真相源分叉）；同名已存在 = skipped 非 update | `asset_import_service.py:59,:160-180,:320-321,:341-353`；`config/default/skills.yml:4` |
| 货架现状：类型 tab（含 team）已有、卡片无 onClick、无排序、无占位 | `TenantShelf.tsx:71-103,:219-226`；`shelfCopy.ts PUBLIC_TYPES` |
| 导入向导现状：`<input type=file multiple accept=".md,.zip">` + 手填服务器路径 | `ImportWizard.tsx:178-186,:205-217` |
| 行数预算临界：`capabilities.py` 458/500、`power_market/service.py` 495/500 | wc -l 实测 |
| 路由挂载点（静态先于动态的顺序约束见 capabilities.py 文件头） | `backend/app/api/v1/__init__.py:36` |

## 2. 架构决策（AD）

### AD-1（FR-01）旧 scan-plugins **删除**，非改指
- 删除端点 `POST /capabilities/scan-plugins`（capabilities.py:128-140）与服务方法 `PluginService.scan_plugins` + `_retract_missing_plugins`（plugin_service.py）。保留 `_plugin_manifest_path`/`_MANIFEST_CANDIDATES`（agents_hub_scan 与 walk.py 依赖）；`get_plugin_detail`/`verify_plugin` 不动。
- 理由：验收线是「不存在能造成软删的扫描入口」（spec FR-01），删除强于改指；旧端点无 admin 前端以外的消费方（§1）。`scan-experts` 不在本轮（Q-SCAN-EXPERTS 范围外）。
- 同步 golden：`backend/tests/openapi_routes_golden.txt` 随路由增删同步更新（test_openapi_routes_golden.py 门禁）。

### AD-2（FR-01）手动同步端点 + 并发/失效链接兜底
- 新增 `POST /api/v1/capabilities/sync-agents-hub`（`require_platform_admin_or_404`）→ `sync_agents_hub(session, agents_root())`（WIP 函数复用，不重写）。返回 `{inserted, updated, unchanged, failed, total, failed_items}`。
- 并发（GWT-01.7）：`_upsert_item` 捕获 `IntegrityError` → 重读存活行按 unchanged 记（DB uq 兜底，模式同 asset_import_service.py:334-335）。
- 失效符号链接（GWT-01.4）：collect 侧对 `plugins/` 下 `is_symlink() and not exists()` 的子项记 `logger.info` 跳过原因后跳过（现静默跳过）。

### AD-3（FR-02）失源行清理 = 对账差剪除，显式、可重复
- 新增 `POST /api/v1/capabilities/assets/prune-missing`（admin 门面），可选查询参数 `dry_run=true`（QA-9）：返回与执行态**同构**的 pruned 预览但不落库（deleted_at 不变）。
- 规则：候选 = live 行 ∩ `asset_type ∈ {skill, plugin, command, agent}` ∩ `source_id IS NULL`；磁盘集 = `collect_agents_hub(agents_root())` 的 `(asset_type, name)` 集；剪除 = 候选 − 磁盘集 → `deleted_at=now, sync_state='gone'`。
- 排除：`team`（人工定义、非磁盘源）、source 注册表行（source_id 非空，归属 src_sync）、**expert 遗留型（判别谓词，QA-7R 收窄）**：`asset_type='agent' AND EXISTS (SELECT 1 FROM capability_experts e WHERE e.asset_id = capability_assets.id) AND file_path NOT LIKE '.agents/%'`（侧行 1:1 唯一约束 `uq_capability_experts_asset`；`platform_core/models/capability.py:133-143`）——的行不进候选集。**file_path 分量不可省（§1 判别事实锚点）**：hub 入库对每个同步 agent 行都写侧行（agents_hub.py:148-157），仅凭 EXISTS 会把全部 hub agent 行（含未来）永久排除出 prune 候选（QA-7R 缺陷形态：对账差恒为 hub agent 总数、北极星不可达）；hub 行 file_path 恒 `.agents/` 前缀、legacy 遗留行非该前缀，故 `NOT LIKE '.agents/%'` 才是 legacy/hub 判别式。要保护的是 legacy 形态行（persona_md 正文存于侧行，剪除即丢正文且无磁盘源可恢复）；hub 来源 agent 失磁盘源属正常失源，应被 prune。测试夹具口径见 T-03（AD 与票表不重复维护断言清单）。
- 响应含 `{pruned:[{asset_type,name}], live_total, disk_total}`（dry_run 与执行态同构）→ 直接充当 GWT-02.2 对账 oracle。幂等：二次执行 pruned=[]。

### AD-4（FR-07）目录导入：无状态两段式（preview→confirm）+ 落盘统一 .agents
- **a. 上传形态**：multipart `files`，每个 part 的 filename = `webkitRelativePath`（前端契约：`form.append('files', f, f.webkitRelativePath || f.name)`），后端按树结构判型，不嗅探内容（S2）。**相对路径清洗（服务端强制，判型/落盘前置，QA-8）**：filename 含 `..` 路径分量、绝对路径形态（前导 `/` 或盘符）、或任何反斜杠 `\` 分量 → 判非法路径，入跳过清单 `skipped[{path, reason:"非法路径"}]`，不参与判型与落盘——webkitRelativePath 是前端可控输入，服务端不得信任。
- **b. 判型**（与 agents_hub_scan 同规则，抽公共函数复用，禁止两份实现）：目录含 `SKILL.md` → skill；目录含 plugin.json（含 `_MANIFEST_CANDIDATES` 嵌套位）→ plugin + 展开 bundled（`skills/*/SKILL.md`、`walk._fold_commands`、`agents/*.md`）；游离 `agents/*.md` → agent；游离 `commands/*.md` → command。
- **c. 落盘根 = `.agents`**（新配置 `SKILLS.AGENTS_ROOT`，默认 `.agents`）：skill → `.agents/skills/<name>/`，plugin → `.agents/plugins/<name>/`，游离 agent → `.agents/agents/<name>.md`，游离 command → `.agents/commands/<name>.md`。**legacy 导入（.md/.zip/服务器路径）落盘根一并切至 .agents**（能力不回退，GWT-07.8；仅换落盘根，沙箱/限额逻辑不动）。
- **d. 两段式无状态**：preview 与 confirm 各自上传同一棵树，服务端判型确定性 → 结果一致；无服务端暂存态/TTL/清理问题；取消 = 不发 confirm（GWT-07.2 天然满足）。
- **e. upsert 语义**（GWT-07.3）：confirm 对同名同类型行执行 update（updated_at/content_hash 变化），不是 legacy 的 skipped。走 `agents_hub._upsert_item` 同族逻辑；新建行 `listing_state='unlisted'`。
- **f. 限额**（NFR-03）：≤500 文件（>500 整批拒，GWT-07.6）、单文件 ≤5MB、SKILL.md ≤1MB；白名单扩展名 `.md/.json/.png/.webp/.svg/.jpg/.jpeg/.gif`，非白名单入跳过清单不入库（GWT-07.9）。
- **g. 顶层识别扩展**：`collect_agents_hub` 增加 `.agents/agents/*.md` 与 `.agents/commands/*.md` 顶层扫描（目录不存在即零行为变化）——保证落盘后的游离资产可被同步通道识别、对账不破。
- 新模块 `backend/services/power_market/hub_import.py`（判型/预览/落盘），不塞进 asset_import_service（383 行，会破 500 上限）。

### AD-5（FR-05 + FR-03 验收路径）公开读模型 = 详情唯一来源；平台管理员预览旁路
- **a. 修 WIP 缺陷 A**：`_read_skill_md` 按 `file_path` 前缀分流——`.agents/` 开头 → 仓库根相对读取；否则维持 LIBRARY_ROOT 兜底（legacy 行）。
- **b. 补投影**（WIP 缺陷 B）：detail 增加 agent 型 `persona_md`（CapabilityExpert side）；plugin 型无 md 正文 → 走 GWT-05.3 空态「暂无正文」。
- **c. 预览旁路**：新依赖 `optional_current_user`（无 Authorization → None；有且有效 → CurrentUser；有且无效 → 401 不变）。公开 list/detail/media 三端点：请求者为平台管理员 → `preview=True` → 跳过 `is_power_market_enabled()` 短路（service.py:237），payload `{market_closed:false, preview:true, gate_open:<实际闸值>}`。**listed 过滤豁免（OQ-D1 裁定落地，QA-1）**：`preview=True` 时 detail/media 额外跳过 listed 过滤——闸与 listed 是两道独立检查（service.py:237 vs :241 `_row_is_fr33`），只豁免其 `listing_state` 分量：unlisted 资产对管理员预览态可读，payload 附未上架标记（抽屉渲染「未上架」提醒标签，edge-states.md:488 OQ-D1 默认）；`_row_is_fr33` 其余分量（deleted_at / status 黑名单 / seed FR-80 / license）对预览态仍全部生效。租户/匿名完全不变（GWT-03.4/03.5/03.7 oracle 不动：unlisted 对非管理员仍 404，正文与媒体均不返回）。
- **d. gate_open 字段**：detail payload 恒带实际闸值——抽屉 CTA 闸语义（附加 e）以它为准（预览态下 CTA 仍按真实闸显示禁用文案）。
- **e. detail_opened 事件**：公开详情端点出 payload 后发射（preview 与正式均发），props `{actor_role, asset_type, asset_name}`；现有 `MARKET_DETAIL_VIEWED` 保持不动。

### AD-6（FR-04）排序服务端三档 + featured 治理
- `list_public(..., sort)`：`smart`（默认）= featured DESC, updated_at DESC；`latest` = updated_at DESC；`hot` = 订阅计数（capability_installs，deleted_at IS NULL）派生表 LEFT JOIN，`ORDER BY COALESCE(cnt,0) DESC, updated_at DESC`——MySQL 无 `NULLS LAST` 语法（db-spec §9 :306 明示不可照抄，QA-3），左联 NULL 归零与「无计数不显示数字」语义一致。全库计数为 0 → 服务端实际按 smart 排序并回 `sort_applied:"smart"`（GWT-04.4）；本轮前端不渲染任何计数数字。
- featured 开关：`PATCH /capabilities/{asset_type}/{name}/featured`（admin 门面）。列由 dba 交付（§5）。

### AD-7（附加 d）示例区：examples JSON 列 + 治理端点
- 存储为 `capability_assets.examples`（JSON，list[str]，0–N，上限 20 条 × 200 字，超出 422）；未维护（空/NULL）→ 投影空列表，前端隐藏区块（GWT-05.3）。
- 维护入口：`PATCH /capabilities/{asset_type}/{name}/examples`（admin 门面）+ 治理表格行操作弹窗（T-11）。

### AD-8（S4/FR-05.2）md 渲染依赖与 XSS 防线
- `frontend/admin/package.json` 增 `react-markdown` + `remark-gfm`（仓库根 npm workspaces 安装，根 package-lock.json 提交）。**禁止引入 rehype-raw**——raw HTML 默认禁用即 GWT-05.2 防线；渲染异常降级 `<pre>` 纯文本（NFR-04/K2）；大文档（≤5000 行）渲染期显示 Skeleton（NFR-02）。

### AD-9（FR-08）事件复用 product_events 基建
- 四事件名与字段按 GWT-08.1–08.4：`import_completed`（actor_role/source/files/assets_created/assets_updated/assets_skipped）、`import_failed`（error_type）、`sync_completed`（actor=manual|startup/added/updated/unchanged）、`sync_failed`（error_type）、`detail_opened`（见 AD-5e）。
- 落点：`sync_agents_hub` 增 `actor` 参数（端点传 manual，CLI/ctl 传 startup）；导入事件在 hub_import 确认路径；全部走 `emit_product_event` + 同名 `logger.info`（结构化可检索，R10）。startup 同步失败 = `sync_failed`，不阻断启动（现状保持）。

### AD-10（FR-06）占位纯前端
- `AssetVisual.tsx`：`hash(asset_type+name)` → 确定性渐变 + 展示名首字母；卡片/抽屉共用；`<img onError>` 回落占位（GWT-06.3）。同一资产两次渲染一致（GWT-06.1）由纯函数保证。

### AD-11 行数/边界预算（F-7 与单文件 ≤500）
- `capabilities.py`（458 行）：只删不加（AD-1 删 13 行）；新路由全部进新文件 `backend/app/api/v1/capabilities_gov.py`，在 `api/v1/__init__.py:36` **之前**挂载（静态段先于动态段约束，文件头已注明）。
- `power_market/service.py`（495 行）：读模型增量（sort/gate_open/examples/persona_md）以抽出新模块落地——`projection.py`（`_project`/`_media_href`/`_read_skill_md` 迁出 + 新字段）与 `sorting.py`（排序子句 + 计数子查询）；service.py 净行数不得增加。
- 前端新组件：`AssetDetailDrawer.tsx`、`MarkdownBody.tsx`、`AssetVisual.tsx`、`ImportTreePicker.tsx`（向导目录模式抽出，ImportWizard.tsx 286 行不破 400）；各 ≤400 行（F-7）。
- 全部新 API 用 `backend.app.responses.ok`；API 层只 import services（禁 import ORM——现状模式沿用）；服务公开方法入口 `logger.`（R10）。

## 3. 模块边界

```
backend/app/api/v1/capabilities_gov.py   [新] 治理动作路由：sync-agents-hub / assets/prune-missing /
                                          import/tree/preview / import/tree/confirm /
                                          {asset_type}/{name}/featured / {asset_type}/{name}/examples
backend/app/api/v1/capabilities.py       [删] scan-plugins；[新] 无（路由冻结在 gov）
backend/app/api/v1/public_skills.py      [改] 三公开端点接 optional_current_user 预览旁路 + detail_opened
backend/app/api/deps.py                  [改] optional_current_user（无头→None，坏 token→401）
backend/services/power_market/agents_hub.py      [改] prune_missing_assets() + agents_root() + actor 参数 + IntegrityError 兜底
backend/services/power_market/agents_hub_scan.py [改] 顶层 agents/commands 扫描 + 失效符号链接日志
backend/services/power_market/hub_import.py      [新] 树判型（公共函数供 collect 复用）/ preview / confirm / 落盘
backend/services/power_market/projection.py      [新] _project/_media_href/_read_skill_md 迁出 + examples/gate_open/persona_md
backend/services/power_market/sorting.py         [新] smart|latest|hot 排序子句 + installs 计数子查询
backend/services/asset_import_service.py         [改] 落盘根切 .agents（_land/_library_root 限定），其余不动
scripts/sync_agents_hub.py                       [改] 复用 agents_root() + actor=startup
config/default/skills.yml + backend/config_consts.py [改] SKILLS.AGENTS_ROOT；ASSET_IMPORT.MAX_TREE_FILES=500、
                                                  MAX_TREE_FILE_BYTES=5MB、MAX_SKILL_MD_BYTES=1MB

frontend/admin/src/services/capabilities.ts [改] scanPlugins→删；syncAgentsHub/pruneMissingAssets/
                                            previewTreeImport/confirmTreeImport/patchFeatured/patchExamples [新]
frontend/admin/src/pages/market/TenantShelf.tsx [改] 卡片四要素 + onClick + 排序条 + tab 空态文案
frontend/admin/src/pages/market/AssetDetailDrawer.tsx [新] 抽屉（复用公开详情 payload）
frontend/admin/src/pages/market/MarkdownBody.tsx      [新] react-markdown+remark-gfm 封装 + 降级
frontend/admin/src/pages/market/AssetVisual.tsx       [新] 确定性占位 + onError 回落
frontend/admin/src/pages/market/ImportTreePicker.tsx  [新] webkitdirectory 选择 + 预览清单 + 确认
frontend/admin/src/pages/market/PluginTab.tsx         [改] 扫描按钮→同步 .agents
frontend/admin/src/pages/market/CatalogTab.tsx        [改] 精选星标 + 示例维护入口（行操作）+ 失源清理按钮/确认弹窗（T-15）
frontend/admin/src/pages/Capabilities.tsx             [改] 超管「货架预览」入口
```

不触碰：`platform_core/` 依赖方向（B1）、backend→scrapy（B2）、config 无业务依赖（B3）、official 前端（S3 范围外）、P-02 双公开闸金标、`is_platform_admin` 布尔模型（NFR-06）。

## 4. API 契约

全部响应走 `ok()` 信封；全部治理端点挂 `require_platform_admin_or_404`（越权 404 存在性隐藏，GWT-01.5/02.5/02.6/03.8/04.6/07.7/07.10 同一 oracle）。

| # | 端点 | 请求 | 响应 data 要点 | 错误 |
|---|---|---|---|---|
| 1 | `POST /capabilities/sync-agents-hub` | — | `inserted/updated/unchanged/failed/total/failed_items[]` | 500→sync_failed 事件 + error 日志 |
| 2 | `POST /capabilities/assets/prune-missing` | 可选查询参数 `dry_run=true`（QA-9） | `pruned[{asset_type,name}]/live_total/disk_total`（dry_run 返回同构预览、不落库） | — |
| 3 | `POST /capabilities/import/tree/preview` | multipart `files`（filename=相对路径） | `assets[{asset_type,name,action:create|update,origin_path}]`、`skipped[{path,reason}]`、`counts{skill,plugin,command,agent}`、`files_total` | >500 文件或超量 → 422「单次最多导入 500 个文件，请改用服务器路径导入」；0 可判型 → 422「未识别到可导入资产」 |
| 4 | `POST /capabilities/import/tree/confirm` | 同 #3 | `created/updated/failed[{name,reason}]/skipped[{path,reason}]`、`batch_id` | 同 #3；单项失败入 failed 清单不整批回滚（GWT-07.5） |
| 5 | `PATCH /capabilities/{t}/{n}/featured` | `{featured: bool}` | 行快照 | 404（资产不存在） |
| 6 | `PATCH /capabilities/{t}/{n}/examples` | `{examples: string[]}`（≤20×200 字） | 行快照 | 422 超限 |
| 7 | `GET /public/capabilities` | +`sort=smart|latest|hot`；可选 Bearer | items（+`featured`）+`sort_applied`；管理员预览态 `preview:true` | 非法 type 422（现状） |
| 8 | `GET /public/capabilities/{t}/{n}` | 可选 Bearer | +`persona_md`(agent)/`examples`/`gate_open`；管理员预览态 `preview:true` + 豁免 listed 过滤（unlisted 可读 + 未上架标记，AD-5c） | 租户/匿名：未上架/黑名单 → 商店不存在句（现状不变）；管理员预览：黑名单/不存在 → 仍 404（豁免仅限 listing_state 分量） |
| 9 | `GET /public/capabilities/{t}/{n}/media/{kind}` | 可选 Bearer | FileResponse（管理员预览态不受闸、亦豁免 listed 过滤，AD-5c） | 404 HTML（现状） |
| 删 | `POST /capabilities/scan-plugins` | — | — | golden 同步删除 |

排序细节（#7）：`hot` 且全库计数 0 → 实际 smart 序 + `sort_applied:"smart"`；租户/匿名在闸关时仍得 `closed_list_payload`（不变）。

## 5. 数据契约需求（dba 帽输入；本帽不写 DDL）

| 需求 | 说明 | 服务票 |
|---|---|---|
| `capability_assets.featured` | 列型以 db-spec §8 迁移 050 规格为准（smallint，与迁移/DBML/实测三方一致；QA-6 对齐）；索引无需（排序全表扫量级小，NFR-01 由分页限定） | T-05 |
| `capability_assets.examples` | JSON NULL；list[str] ≤20×200 字（应用层校验） | T-05 |
| 迁移 050 | 049 之后；upgrade/downgrade 对称；走 alembic 门禁 | T-05 |

既有列/约束不改：`uq_asset_type_name_alive`（并发兜底依赖）、`logo/background`（049）、`listing_state` 三态机器（§3.1 不改）。

## 6. UI 契约要点（六态 × 新面；文案为成品句）

| 面 | Empty | Loading | Error | Boundary | Permission | Offline |
|---|---|---|---|---|---|---|
| 货架 tab/排序 | 某类型空 tab：「暂无该类资产」（区别于整架「暂无已上架能力」） | MarketSkeleton（现状） | LOAD_FAIL+重试（现状） | 排序三档即边界；hot 无计数不显示数字 | 非管理员=货架（闸语义）；治理动作 404 同形 | LOAD_FAIL_HINT（现状） |
| 详情抽屉 | 正文空：「暂无正文」；示例未维护：区块隐藏 | Skeleton（大文档 <3s 渲染，NFR-02） | 纯文本降级（K2） | ≤5000 行 md；图损坏回落占位 | 闸关 CTA 禁用：「市场暂未开放，开放后可订阅」 | 请求失败=关闭抽屉 + toast |
| 目录导入向导 | 无可判型：「未识别到可导入资产」 | 上传进度条 + 解析 Skeleton（现状模式） | 逐项失败中文原因清单（GWT-07.5） | >500 文件 / >5MB / SKILL.md>1MB → 预检拒绝文案（含上限数字） | 仅超管可见入口；越权 404 | IMPORT_RETRY/RESELECT（现状） |

卡片四要素（NFR-U1）：icon（真图/占位）、主标题=展示名、副标题=所属插件（`origin_plugin_name` 无则类型标签）、≤2 行描述 + 底部标签（类型/预告）。tab 集维持现状五类（含 team；spec 未要求移除，OQ-3）。视觉基调走 antd 既有 token（管理后台不另立视觉方向）。

## 7. 票表（每票独立交付；lane ∈ api/ui/dba/verify）

| 票 | lane | 标题与范围 | FR/GWT 锚 | 依赖 | 验证 |
|---|---|---|---|---|---|
| T-00 | verify | WIP 基底验证：pytest 全量 + ruff + arch.sh + golden 全绿；记录 live 行数基线 | §0 | — | 命令退出码 0 |
| T-01 | api | AD-1/2：删 scan-plugins（端点+服务方法+golden）、sync-agents-hub 端点、IntegrityError 兜底、失效链接日志、sync_completed/sync_failed(actor) | FR-01 全部 GWT（01.1–01.7） | T-00 | 新增 test_sync_endpoint.py；pytest+golden |
| T-02 | ui | PluginTab「扫描插件目录」→「同步 .agents」（调 syncAgentsHub，完成 toast 显示 inserted/updated）；capabilities.ts 删 scanPlugins 增 syncAgentsHub | GWT-01.6 | T-01 | 组件测试 + lint |
| T-03 | api | AD-3：prune-missing 端点（含 `dry_run` 参数）+ agents_hub.prune_missing_assets（排除 team/source 行 + expert 遗留谓词含 `file_path NOT LIKE '.agents/%'` 判别式） | FR-02 全部 GWT（02.1–02.6） | T-00 | 新增 test_prune_missing.py（QA-7R 夹具口径）：负向断言——legacy 形态行（file_path 非 `.agents/` 前缀 + 有 capability_experts 侧行 + 无磁盘源）prune 后仍 live；正向断言——hub 来源 agent 孤儿（file_path `.agents/` 前缀 + 有侧行 + 无磁盘源）被 prune；dry_run=true 返回同构 pruned 预览且 deleted_at 不变 |
| T-04 | api | AD-5：projection.py 迁出 + _read_skill_md 分流修复 + persona_md/examples/gate_open 投影 + optional_current_user 预览旁路（三公开端点跳闸；detail/media 额外豁免 listed 过滤 + 未上架标记）+ detail_opened | FR-05 GWT-05.1/05.3/05.6 回归 + GWT-03.4/03.5/03.7/03.8 不变回归（03.7/03.8 点名，QA-4）+ GWT-08.4 | T-00 | 新增 test_public_detail_preview.py：管理员可见 unlisted 详情（payload 带未上架标记）；租户/匿名对 unlisted 详情与媒体仍 404（GWT-03.7 负向）；上下架端点越权 404 门面回归（GWT-03.8） |
| T-05 | dba | §5：迁移 050（featured + examples），db-spec/schema.dbml 交 dba 帽 | FR-04/附加 d 存储 | —（可与 T-01..T-04 并行） | alembic 升降级 + 迁移门禁 |
| T-06 | api | AD-6/7：sorting.py + list_public(sort) + sort_applied 降级 + featured/examples PATCH 端点 | FR-04 GWT-04.1–04.4/04.6 + 附加 d 端点 | T-05 | 新增 test_shelf_sorting.py |
| T-07 | api | AD-4：hub_import.py（判型复用 collect 规则）+ preview/confirm 端点 + 落盘统一 .agents（legacy _land 切根）+ 顶层 agents/commands 识别 + import_completed/import_failed | FR-07 全部 GWT（07.1–07.10）+ GWT-08.1/08.2 | T-00 | 新增 test_tree_import.py（含取消零写入、白名单跳过、upsert） |
| T-08 | ui | 货架卡片四要素 + onClick 打开抽屉 + 排序条（综合/最热/最新）+ tab 空态文案 | FR-03 GWT-03.1–03.3 + 03.6 + FR-04 UI | T-04, T-06 | TenantShelf.test.tsx 扩展 + GWT-03.6 货架侧断言（QA-4 锚定本票：下架后该资产不再出现在货架 tab；治理目录仍可见半句为既有 list_assets 行为、本 feature 无改动面；公开详情 404 半句与 T-04 的 GWT-03.7 同批验收） |
| T-09 | ui | AD-10：AssetVisual 占位 + onError 回落（卡片+抽屉） | FR-06 GWT-06.1–06.3 | T-08 | 组件测试（两次渲染一致断言） |
| T-10 | ui | AD-8：react-markdown 依赖（根 workspaces）+ MarkdownBody + AssetDetailDrawer（icon/背景/标签/示例区/正文/CTA 闸语义） | FR-05 GWT-05.1–05.5（XSS 断言在前端测试） | T-04 | 抽屉测试（含 `<script>` 载荷不执行）+ npm ci/build |
| T-11 | ui | 治理面精选星标 + 示例维护弹窗（CatalogTab 行操作） | GWT-04.5 + 附加 d 维护面 | T-06 | 组件测试 |
| T-12 | ui | AD-4a：ImportTreePicker（webkitdirectory + 相对路径 append）+ 预览清单（数量/新建更新标注/跳过清单）+ 确认/取消 + 高级选项保留 | FR-07 UI 面 + NFR-08 | T-07 | ImportWizard 测试扩展（Capabilities.import.test.tsx） |
| T-13 | ui | 超管「货架预览」入口（Capabilities 治理壳）+ 预览 badge（preview payload 驱动） | FR-03 验收路径声明（空态/排序 GWT 闸关验收通道） | T-04, T-08 | 组件测试 |
| T-14 | api | 埋点收口验收：四事件字段逐项对 GWT-08.1–08.4 + product_events 可检索断言 + 结构化日志行核对 | FR-08 全部 GWT | T-01, T-04, T-07 | 新增 test_governance_events.py |
| T-15 | ui | prune 治理面入口（QA-2；流程含 dry_run 预检，QA-9）：CatalogTab 工具栏「清理失源资产」按钮（超管可见）→ 弹窗打开**先 `dry_run=true` 取计数 {n}**（取数中为加载态）→ 二次确认弹窗（确认句「将下线 {n} 个无磁盘来源的资产」，edge-states.md:489）→ 确认后**不带 dry_run** 执行 → toast 显示 pruned 数与 live_total/disk_total 对账 | FR-02 GWT-02.1–02.4 的操作入口（API 语义归 T-03） | T-03 | 组件测试：弹窗打开即发 dry_run 请求断言 + 确认句文案断言 + 取消不发执行（非 dry_run）请求 + 执行后 toast 对账数字 |

**Effort 复核**（spec §1 委托；QA-11 口径修正）：appetite 以 spec 头部为准 = **3–5pw 等效、上界 5pw（spec.md:3；v1.1 所引 5.5pw 基数无出处，废弃）**。FR-01/02 ≈ 0.75pw（T-01..T-03 + T-15 治理面入口）、FR-05 ≈ 1.5pw（T-04+T-10）、FR-07 ≈ 1.5pw（T-07+T-12）、FR-03/04/06 ≈ 1.5pw（T-05/06/08/09/11/13）、FR-08 ≈ 0.5pw（T-14 分布+收口）≈ **合计 5.75pw 等效，超上界 0.75pw（15%，未触发 spec「超 50%（=7.5pw）停下重判」线）**。弹性组合（超预算先砍，不伤 GWT，各自回收量）：T-11 示例维护弹窗缩为端点+最小编辑回收 ~0.25pw（落地后 5.5pw，示例区 GWT 只验「有维护时展示/空隐藏」）；T-09 并入 T-08 回收 ~0.25pw（落地后 5.5pw）；**双落地 5.25pw 仍余 0.25pw 溢出——是否接受该溢出或追加第三回收项由 manager 批复，本段不再留无出处基数**。不可砍：T-00/T-01/T-03/T-04/T-07/T-15（验收主体；T-15 为 QA-2 裁定的 FR-02 显式操作入口）。

## 8. FR × 票覆盖矩阵（design 自检：无漏 FR）

| FR | 票 |
|---|---|
| FR-01 | T-01, T-02 |
| FR-02 | T-03, T-15 |
| FR-03 | T-04（字段/预览）, T-08, T-13 |
| FR-04 | T-05, T-06, T-08, T-11 |
| FR-05 | T-04, T-10（T-11 提供示例维护） |
| FR-06 | T-09 |
| FR-07 | T-07, T-12 |
| FR-08 | T-01, T-04, T-07, T-14 |
| NFR-01–11 | 落点：NFR-01→T-06/T-08；NFR-02→T-10；NFR-03→T-07；NFR-04→T-10/T-09；NFR-05→T-07/T-10；NFR-06→全部治理端点门面；NFR-08→T-12；NFR-09→T-14；NFR-11→T-05/各票 |

## 9. 开放问题（不阻塞票表启动）

| id | 问题 | 默认（无否决即执行） | 需谁拍板 |
|---|---|---|---|
| OQ-1 | `.agents` 顶层新增 `agents/`、`commands/` 目录属仓库协作契约变更（AGENTS.md 加一行说明，随 T-07） | 接受 | operator |
| OQ-2 | legacy 导入落盘根统一切 `.agents`（AD-4c）。回退方案：保留 capability-library 落盘 + prune 采用与 AD-3 **同款 file_path 判别式**——排除 `file_path NOT LIKE '.agents/%'` 的行、候选收窄为 `.agents/` 前缀行（QA-7R 口径一致；弱化对账北极星） | 执行统一 | manager |
| OQ-3 | 货架 team tab 保留（现状五类）还是收敛为 spec FR-03 四类 | 保留（GWT 只抽检四类） | manager |

## 10. 自检

- [x] contract.md 存在于 02-shape/（check-sdlc --hat shape 唯一必交件）
- [x] FR-01–08 与 NFR 全部落票（§8 矩阵无空行）；每票标 lane + 依赖 + 验证命令
- [x] WIP 基底显式保护（§0 + T-00 首票）
- [x] 可行性 = 读码：全部决策带 file:line 锚点（§1）；两处 WIP 潜伏缺陷（skill_md 空读、persona_md 不投影）已被 AD-5 修复入票
- [x] 宪法红线：R1（新配置键落 config）/R10（服务入口日志）/API 禁 ORM import（AD-11 模式）/B1–B3 不触碰/F-7 与 500 行预算（AD-11）/responses.ok/Q5 依赖走根 workspaces（AD-8）
- [x] 越权口径统一 404 门面（§4）；闸语义对租户零变化（AD-5c 明示回归项）
- [x] 范围外未越界：Q-SCAN-EXPERTS 无票；official 不动；无表结构 DDL（§5 归 dba）

## 11. 修订记录

| 版本 | 日期 | 变更 | 触发 |
|---|---|---|---|
| v1 | 2026-09-15 | 初版：AD-1..AD-11 + 票表 T-00..T-14 | — |
| v1.1 | 2026-09-15 | shape G-fresh r1 返工（05-review/findings.md QA-1..QA-5/QA-7/QA-8，仅修本文件；QA-6 featured 列型归 dba 并行修 db-spec，本文件 §5 不再写死列型口径）。QA-1：AD-5c/API #8/#9/T-04 落实 OQ-D1——管理员预览豁免 listed 过滤（unlisted 可读 + 未上架标记），租户/匿名仍 404。QA-2：新增 T-15（prune 治理面按钮+确认弹窗，确认句引 edge-states.md:489）+ §8 FR-02 行 + effort 重算 5.75pw。QA-3：AD-6 hot 排序改 `COALESCE(cnt,0) DESC` 并引 db-spec §9。QA-4：GWT-03.7/03.8 点名入 T-04 测试清单；GWT-03.6 锚定 T-08（选定理由见该票验证列）。QA-5：§1 事件锚点改 product_event_service.py:74。QA-7：AD-3 增 expert 遗留排除谓词（capability_experts.asset_id EXISTS）+ T-03 负向断言。QA-8：AD-4a 增相对路径清洗（`..`/绝对路径/反斜杠 → 跳过清单） | qa（复审新快照） |
| v1.2 | 2026-09-15 | shape G-fresh r2 返工（findings QA-7R/QA-9/QA-11 + OQ-2 口径同步，仅修本文件；QA-10 edge-states 归 designer 并行修）。**QA-7R**：§1 新增「侧行/前缀判别事实」锚点（agents_hub.py:148-157 每个同步 agent 行都建侧行；agents_hub_scan.py:46-54/:200-235 hub 行 file_path 恒 `.agents/` 前缀）；AD-3 expert 遗留谓词收窄——`EXISTS(侧行)` 追加 `AND file_path NOT LIKE '.agents/%'` 分量（仅 EXISTS 会豁免全部 hub agent 行，对账差恒为 hub agent 总数）；T-03 夹具口径重写：负向断言改 legacy 形态行（非 `.agents/` 前缀 + 有侧行 + 无磁盘源）prune 后仍 live，新增正向断言 hub 来源 agent 孤儿（`.agents/` 前缀 + 有侧行 + 无磁盘源）被 prune；OQ-2 回退方案（:220）改用同款 file_path 判别式保持口径一致。**QA-9**（manager 裁定 dry_run 方案）：API #2 增 `dry_run=true` 查询参数（同构响应返回 pruned 预览、不落库）；T-03 增 dry_run 不落库断言；T-15 流程改「弹窗打开先 dry_run 取 {n}，确认后不带 dry_run 执行」。**QA-11**：effort 段按 spec 头部上界 5pw 重述（5.75pw 超 0.75pw、未触发超 50% 重判线；废弃无出处 5.5pw 基数）+ 弹性组合各自回收量（T-11 缩减 / T-09 并入各 ~0.25pw，双落地 5.25pw 仍余 0.25pw 溢出归 manager 批复） | qa（r2 复审新快照） |
