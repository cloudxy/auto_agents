# Findings · define G-fresh r1（2026-09-15）

## Snapshot

| 文件 | sha256 |
|---|---|
| 01-define/spec.md | 7fc841ca6fa4aa8a1087df0adbe5aab5e682135b9673f7ef6e4449d8b03a48ae |
| 00-discover/briefing.md | 62e6e05b43c32c54691b7ca6167a1812a77c966d85c3da2938da6faf285dee81 |

（哈希由 manager 补算；reviewer 工具集无 shell。）

## Verdict: **FAIL**（2 条未豁免 major）

## QA-1 [major] 货架卡片计数 oracle 与白名单规则矛盾
- spec.md:106（GWT-01.1 "plugin 型 live 行 = 6 …货架数据中"）、spec.md:132（GWT-03.2 "仅显示 6 张 plugin 卡"）vs spec.md:210（dev-team 系强制 unlisted）+ agents_hub.py:58（MERGED_PLUGIN_NAME="dev-team" 强制 unlisted）+ service.py:113（list_public 只取 listed/coming_soon）→ 货架 plugin 卡最多 5 张，两条 Then 不可同时成立。
- 修复：GWT-03.2 按「货架可见集」定义预期数（当前 5，dev-team unlisted 显式排除）；GWT-01.1 的 Then 收敛为治理目录（list_assets）。
- 附带产品口径（manager 裁定方向，pm 落实）：保持 WIP 既有规则 dev-team=unlisted，不改产品语义；spec 显式定义可见集与排除项。

## QA-2 [major] 上下架（listed⇄unlisted）零 GWT
- briefing 约束 4 含「上下架」；spec 状态流转/权限矩阵都覆盖，但 FR-01..08 无一条上下架效果 GWT，unlisted 资产不得经公开详情/货架泄露的关键授权语义无 oracle；上下架端点非管理员 403 也缺。
- 修复：增 GWT-03.x（listed→下架→货架 tab 与公开详情消失、治理目录仍可见）+ 公开详情对 unlisted 资产 404/不可见行 + 非管理员上下架 403 行。

## QA-3 [minor] 「闸后」标注不对称
- GWT-04.1 标闸后而 04.2-04.4、03.3 未标；未标注即本轮验收主体但货架默认闸关，只能走超管预览入口构造。修复：统一标注或在 FR-03 声明排序/空态 GWT 经超管预览入口验收。

## QA-4 [minor] 导入扩展名白名单无 GWT
- spec.md:229 NFR-05 说了白名单+跳过清单，FR-07 八条 GWT 无覆盖。修复：增 GWT-07.x（树含 .exe → 预览跳过清单列出、确认后不入库、其余正常）。

## QA-5 [minor] 并发无 oracle
- 幂等只测串行。修复：增并发 GWT（两次并发同步不产生重复行、不软删）或 §5 显式声明单管理员串行假设。

## QA-6 [minor] 中间角色（普通管理员）禁做项无越权用例
- 全部越权 GWT Given 都是租户角色。修复：增一条普通管理员调导入/清理 403 行，或权限矩阵注明沿用现状权限码本轮不新增端点故不新增用例。

## QA-7 [minor] 措辞/一致性
- GWT-07.2 "与同步前一致"→"与上传/取消前一致"；spec.md:203 "listd" 拼写；「四要素」实列 5 项与 NFR-U1 合并口径 4 不一致（以 NFR-U1 口径为准并在 FR-03 复述）。

## 维度结论

合规✅ / 质量⚠️ / 证据✅（file:line 全部复核属实，数字自洽）/ 安全⚠️ / 性能✅ / 契约⚠️ / 项目规范✅ / 边界⚠️。调用方六项：①覆盖缺「上下架」oracle（QA-2）②QA-1 矛盾 oracle ③④✅ ⑤✅ ⑥✅。

## 处置

pm 返工 r1：修 QA-1（按 manager 口径 dev-team 保持 unlisted）+ QA-2（增 2-3 条 GWT）+ 顺手清 QA-3..QA-7。修复后新快照复审。
