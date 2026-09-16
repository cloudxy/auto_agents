# 实现证据 · T-07 目录导入（两段式 + 落盘统一 .agents）

> 票：contract §7 T-07｜FR 锚点：FR-07 GWT-07.1–07.10 + GWT-08.1/08.2｜lane：api｜日期：2026-09-15

## 1. 交付面

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/hub_import.py` | 新增 287 行 | 清洗/限额/铺形状/判型/落盘/upsert |
| `backend/services/power_market/agents_hub.py` | 改 | 抽出 `_apply_upsert`，新增 `_upsert_item_listing`（导入通道 upsert） |
| `backend/services/power_market/agents_hub_scan.py` | 改 | AD-4g：顶层 `agents/*.md`、`commands/*.md` 扫描 |
| `backend/app/api/v1/capabilities_gov.py` | +2 端点 | `POST /import/tree/preview`、`/confirm` |
| `backend/services/asset_import_service.py` | 改 | AD-4c/OQ-2：legacy 落盘根 capability-library → `.agents`，`file_path` 带前缀 |
| `AGENTS.md` | +1 段 | OQ-1：顶层游离资产位说明 |
| `backend/tests/test_tree_import.py` | 新增 | 13 用例 |
| `backend/tests/test_t35_asset_import.py` | 改 | 夹具改钉 `SKILLS.AGENTS_ROOT`，落盘断言随根切换 |

## 2. 关键实现裁定

- **判型禁止两份实现（AD-4b）**：不另写一套规则，而是把清洗后的 raw 树**铺成 `.agents`
  形状的暂存根**，再交给 `collect_agents_hub` 判型——与同步通道共用同一份实现。
  暂存根就命名为 `.agents`，于是 `_repo_rel` 算出的 `file_path/origin_ref/logo/background`
  天然等于落盘后的真实相对路径，confirm 不需要二次改写路径。
- **相对路径清洗前置（QA-8）**：`..` 分量 / 前导 `/` / 盘符 / 任何反斜杠分量 → 入
  `skipped[{path, reason:"非法路径"}]`，**在判型与落盘之前**拦掉。`webkitRelativePath`
  是前端可控输入，服务端不信任。
- **无状态两段式（AD-4d）**：服务端不存暂存态；preview 与 confirm 各自上传同一棵树，
  判型确定性保证结果一致；取消 = 不发 confirm（GWT-07.2 天然成立，用例另断言预览零落盘）。
- **upsert 保留既有上架态（AD-4e 补强）**：新建行 `unlisted`；**已存在行沿用它当前的
  `listing_state`**——否则重导一个已上架资产会把它悄悄打回未上架。这条在 contract 里
  只写了「新建行 unlisted」，实现按不回退原则补齐并加用例
  `test_reimport_keeps_existing_listing_state`。
- **单项失败不整批回滚（GWT-07.5）**：逐项 try，失败入 `failed[{name, reason}]` 继续下一项。
- **legacy 落盘根切换（AD-4c / OQ-2「执行统一」）**：`_land` 与 `_contained_write` 的收容
  断言都改走新增的 `_landing_root()`（= `agents_root()`）；`_file_path` 同步带 `.agents/`
  前缀——详情正文分流（AD-5a）与 prune 判别式（AD-3/QA-7R）都以该前缀识别 hub 来源行，
  不带前缀会让导入行被误判为 legacy。沙箱与限额逻辑一行未动（GWT-07.8 能力不回退）。

## 3. GWT × 用例对照

| GWT | 用例 |
|---|---|
| 07.1 正常 | `test_gwt_07_1_preview_then_confirm_matches`（2 skill + 1 plugin + 3 bundled；预览零写入；落盘可验） |
| 07.2 取消 | `test_gwt_07_2_cancel_writes_nothing`（live 行数不变 + 磁盘零 SKILL.md） |
| 07.3 upsert | `test_gwt_07_3_second_import_updates_not_duplicates` |
| 07.4 空态 | `test_gwt_07_4_no_recognizable_asset_422` |
| 07.5 部分失败 | `test_gwt_07_5_single_failure_listed_not_whole_batch` |
| 07.6 超限 | `test_gwt_07_6_over_500_files_rejected`（文案逐字） |
| 07.7 / 07.10 越权 | `test_gwt_07_7_tenant_admin_404_zero_write` / `test_gwt_07_10_normal_user_404_zero_write` |
| 07.9 白名单 | `test_gwt_07_9_non_whitelisted_extension_skipped` |
| QA-8 清洗 | `test_qa8_malicious_relative_paths_skipped` |
| AD-4e | `test_imported_rows_are_unlisted`、`test_reimport_keeps_existing_listing_state` |
| AD-4g | `test_ad4g_loose_agent_and_command_land_and_collect`（落盘后同步通道必须认得，否则 prune 会把它们当失源剪掉） |

夹具铁律：**所有 confirm 用例先把 `SKILLS.AGENTS_ROOT` 钉到 `tmp_path`**，否则会写进仓库真 `.agents`。

## 4. 自测证据

```
$ python -m pytest -q backend/tests/test_tree_import.py -p no:cacheprovider
13 passed in 8.47s

$ python -m pytest -q backend/tests/test_t35_asset_import.py -p no:cacheprovider
13 passed in 7.51s           ← legacy 落盘根切换后的回归

$ ruff check backend platform_core scripts   → All checks passed!
$ bash tools/check/arch.sh                   → exit 0
```

## 5. 未尽项（交给下一票/评审）

- 前端 T-12 的 GWT-07.x **UI 用例仍缺**（组件 `ImportTreePicker.tsx` 已在，旧向导 9 用例绿）。
  本票只交后端面；T-12 的前端断言未补。
