# Recon · 代码事实底座（manager 侦察，2026-09-15，供 market/compete/disucss 引用）

来源：Explore 全量扫描（file:line 可核）。

## .agents 现状

- 顶层仅 `README.md` + `skills/`（9 个一等 skill：check-arch/cicd/db-design/deploy/new-model/new-spider/new-svc/pua/verify，各= SKILL.md + 可选 references/）+ `plugins/`（README + 6 个符号链接 → `~/.zcode/local-plugins/{dev-team,drama-skills,mattpocock-skills,oh-story,sdlc-workflow,superpowers}`）。
- **没有顶层 commands/ 与 agents/ 目录**；commands/agents 是插件内部 bundled 资产（仅 sdlc-workflow 有 agents/ + commands/）。用户所说四类 = capability_assets.asset_type 维度，不是四个物理顶层目录。
- 图资产：dev-team/drama-skills/mattpocock-skills/oh-story/superpowers 五个插件有 `icon.png` + `background.png`；**sdlc-workflow 无**；skills/ 无任何图。
- `capability-library/plugins`（scan-plugins 的扫描根）**已不存在**：5d2e600 真目录 → b8b5f85 符号链接 → 48fabd4(2026-09-10) 删除，未重建。

## 后端现状（含未提交 WIP）

- 端点：`/api/v1/capabilities/*`（capabilities.py：scan-plugins:128、import:253 multipart files 或 directory、installs、listing、export 等）；`/api/v1/public/capabilities*`（public_skills.py：货架:101、**media/{kind}:143 本次新增**、subscribe:163、详情:181）。
- WIP 新链路：`power_market/agents_hub_scan.py`（collect：skills/*/SKILL.md + plugins/ 子目录展开 plugin/bundled skills/commands/agents，读 icon.png/background.png，content_hash=md+图 sha256）→ `agents_hub.py`（按 asset_type+name 增量 upsert，dev-team 强制 unlisted）→ `capability_assets.logo/background`（模型:86-87 + 迁移 049）→ 货架 `_project` 注入 media href（service.py:463-473，经 `get_media_path`:253 校验）。
- `scripts/sync_agents_hub.py` CLI + `ctl.py cmd_start` 每次启动自动同步（失败不阻断）+ `backend/tests/test_agents_hub_sync.py` 单测。
- 货架闸门：`POWER_MARKET.ENABLED` 默认 **false**（config/default/power_market.yml:3）→ 市场当前对租户关闭，media 端点同受闸。

## 前端现状

- admin：`/capabilities` → Capabilities.tsx（非超管→TenantShelf 货架；超管→PowerMarketSwitch+导入按钮+7 tab）。货架卡片（TenantShelf.tsx:83）**无 onClick 无详情**；WIP 已加 logo/背景图渲染。
- PluginTab.tsx:83「扫描插件目录」→ scanPlugins() → 重新 listAssets('plugin')；前端逻辑干净。
- ImportWizard.tsx:178-186 隐藏 `<input type="file" multiple accept=".md,.zip">`；:209-216 手填服务器目录路径 Input（二选一）。无 webkitdirectory、无拖拽。
- official 官网有 /skills 与 /capabilities 列表 + CapabilityDetail 详情页（:137-147 用 `<pre>` 纯文本渲染 md，明确禁 HTML）。
- **全仓库无 react-markdown/marked/remark/dompurify 依赖**。

## 关键结论

**A. 扫描清空 bug 根因（后端）**：`plugin_service.scan_plugins`（plugin_service.py:46-88）扫 `SKILLS.LIBRARY_ROOT=/capability-library`+`/plugins`（skills.yml:4）→ 目录不存在 → `_retract_missing_plugins(set())`（:150-174）把**所有 source_id IS NULL 的存活 plugin 行软删**（deleted_at 置值 + sync_state=gone）→ 治理目录与货架查询过滤 deleted_at IS NULL → 列表空。agents_hub 同步入库的插件行 source_id 同为 NULL → 两通道打架，点一次旧扫描=把新通道成果全部软收。次要：scan-experts 扫 capability-library/experts 同不存在（未验证 retract 行为）。

**B. 导入现状**：向导完整但文件侧=多选 .md/.zip；目录侧=手输服务器路径字符串。无文件夹选择器。

**C. WIP 完成度**：扫描→入库→logo/background→媒体端点→货架渲染→自动同步→单测 已闭环（未提交、未跑过端到端?）；缺口=①admin 卡片无详情视图 ②无 md 渲染依赖 ③旧 scan-plugins 按钮指坑 ④POWER_MARKET.ENABLED 默认关 ⑤sdlc-workflow 插件无图。
