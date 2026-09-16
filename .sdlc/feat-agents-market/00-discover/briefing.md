# Briefing · feat-agents-market（.agents 资产进能力市场 + 后台管理 + 扫描 bug 修复）

- 表面：ToB 双面 —— 平台管理员（治理面：导入/扫描/上下架管理）+ 租户与买方（消费面：市场货架浏览与订阅，受闸）。本轮两面都做，消费面在 `POWER_MARKET.ENABLED` 闸后。
- Appetite：操作者未给（manager 建议 3–5pw 等效：四类资产展示 + 详情抽屉 + 导入重构 + 单通道 bug 修复 + UI 重设计）。
- Claim（经 Falsify 缩小后）：平台运营者，在「`.agents` 资产只有后台治理表格、卡片无 icon/背景图、点击无详情、导入只能选文件或手填服务器路径、点『扫描插件目录』把全部插件行软删」的现状里，要一个参考图所示的能力市场（四类资产卡片 + md 详情抽屉 + 目录导入自动分类 + 好用美观的后台管理），并修掉扫描清空 bug。消费面价值未量化，不作为本轮验收依据。
- 泳道：L3（发现带判定见 state.yaml lane_judge：schema/auth/UI/双子项目/新依赖 react-markdown 均是）。

## 操作者给定约束（2026-09-15 原话 + 参考图）

1. skills / commands / agents / plugins 四类资产都要进市场。
2. 参考图一（卡片网格）：顶部分类 tab + 右上排序（综合/最热/最新）+ 三列卡片（拟物 icon + 主/副标题 + 两行描述 + 底部标签）。
3. 参考图二（详情浮层）：大头像 + 能力标签 + 「帮你做」示例区 + 主 CTA。详情必须能看到 xxx.md（SKILL.md / 正文）具体信息。
4. 后台管理要「全」：导入、扫描、上下架、治理。
5. 导入要能**选择目录**并自动区分内容类型。
6. 后台 UI 要好用、美观、符合操作习惯。
7. Bug：插件页点『扫描插件目录』→ 插件全部丢失（根因见 recon.md 结论 A + market.md DB 实证）。

## Discuss-P

**谁 / 现在 / 期望 / 凭什么说改善了**

- 平台管理员（操作者本人）：现在用治理表格管理资产、导入要手填服务器路径、扫描按钮有毒（E2：DB 12 行 plugin 全软删 + ~22 孤儿行）；期望：卡片化市场 + 目录导入 + 安全扫描。改善判据=扫描后插件行不再消失（可计数）。
- 租户/买方（代理推断，无一手访谈）：现在货架闸关（Reach=0）；期望闸开后能浏览四类资产并订阅。**未量化，不做验收依据**。
- 冲突：无（治理面先行不损害消费面；闸默认关由操作者掌握开放节奏）。

## Discuss-S

方案分叉四问已发操作者（2026-09-15 AskUserQuestion），未即时作答，manager 按推荐项继续并记录在案（操作者可在 review 前否决）：

- **S1 扫描通道 = 收敛单通道**：「扫描插件目录」改走 agents_hub 同步（幂等 upsert、非破坏）；旧 scan-plugins 退役；~22 条无磁盘源孤儿行按「.agents 是唯一真相源」一次性清理。验收线对齐 Claude marketplace 非破坏性语义（compete.md E2 引文）。
- **S2 目录导入 = webkitdirectory**：浏览器原生目录选择，整树带相对路径上传，后端按结构自动分类（SKILL.md→skill、plugin.json→plugin、agents/*.md→agent、commands/*→command），复用 agents_hub collect 分类逻辑；手填服务器路径保留为高级选项。
- **S3 详情面 = admin 抽屉式**：货架卡片点击开详情抽屉（对齐参考图二：icon+背景、能力标签、示例区、md 正文富渲染、订阅 CTA）；official 本轮不重做。
- **S4 md 渲染 = react-markdown + remark-gfm**（新依赖，Q5=yes；默认禁 raw HTML）。

Manager 附加裁定（低风险设计项）：
- 「最热」排序不得造假：用真实订阅/安装计数（capability_installs），无数据则降级综合序。
- 无图资产（9 个一等 skill + sdlc-workflow）：确定性优雅占位（渐变+首字母），不做 AI 生成图。
- `POWER_MARKET.ENABLED` 默认仍 false，开放由操作者经现有 PowerMarketSwitch 决定（release checklist 项）。

## Compete

压缩：现状（必填行）= 我们自己的破坏性扫描 + 文件级导入（E2，recon A/B）；Claude marketplace 更新明确非破坏（E2 引文）= 修复验收线；icon/背景图是规范级差异化（marketplace.json/SKILL.md 零图像字段，我们已有 bundled 图 + 049 迁移）；借鉴 manifest 驱动自动分类（Dify 式）+ 示例 prompt 区 + Featured 式「综合」；回避远程源分发 / 公开安装计数 / AI 生成图；「最新」可用 updated_at/content_hash 支撑，「最热」无事件数据。
长文：`00-discover/compete.md`。

## Market

压缩：可及集合分两层——治理面（不受闸）：管理员本地 3、下界 1、生产未量化；消费面：闸前 Reach=0（POWER_MARKET.ENABLED=false，E2），闸后=租户数（本地 5 个种子租户，E3 快照，不可放大；生产未量化）。供给侧：磁盘 166 资产（9 skill + 6 插件内含 128 bundled skill/5 command/18 agent；5/6 插件有图）；DB live 182 行、12 plugin 行全被 bug 软删（修复后 ≈188）、~22 孤儿行。pm 做 RICE 时消费面 Reach 必须按「闸后=租户数」参数化。
长文：`00-discover/market.md`。

## Falsify

| ID | 假设（可证伪的一句） | 若假则 | 最便宜检验 | 证据级 | 结果 |
|---|---|---|---|---|---|
| A1 | agents_hub 同步能把插件行恢复并保持在架（非破坏收敛成立） | K1 触发：回退原地修复旧通道 | 对本地 DB 跑一次 sync_agents_hub 数 plugin 行（预期 0→12） | E3（DB 足迹：12 行已删）+ E2（WIP 单测） | 存活（实现帽开头实证） |
| A2 | 166 条磁盘资产可直接上架为卡片（含无图资产占位可看） | 无图/重复资产降展示优先级，卡片占位方案升级为硬性 FR | 数资产 + 检查无图子集（9 skill + sdlc） | E2（market.md 计数） | 存活（缩小：占位设计为 FR） |
| A3 | 租户会在闸开后浏览/订阅市场 | 消费面验收不作数，货架仅交付闸后 | 无（未量化；不 fake door） | 未量化 | 未量化 → 本行禁止 pass |
| A4 | webkitdirectory 整树上传统计可控（admin 场景 ≤ 数百文件） | 大目录改走服务器路径高级选项 | 实现帽实测一个真实插件目录 | E2（Chrome/Safari/Firefox 支持面）+ E1 | 存活 |

杀死条件（预先写死）：
- K1：本地 DB 跑 sync 后 plugin 行未恢复 → 单通道前提死，回退旧通道原地修复（feature 不死）。
- K2：react-markdown 破坏 admin 构建/ESLint/体积红线 → 降级自写轻量渲染（feature 不死）。
- K3：任何消费面指标在无计数数据下被写进验收 → 视为范围欺诈，砍掉。

本轮裁决：**缩小后存活（narrow）**——治理面 + 供应链修复 + bug 修复按操作者指令推进（E1 指令 + E2 实证）；消费面货架随闸交付但价值未量化，不进验收；无赌注行（无 ≤50% 信心的核心假设留待 A/B，A/B 归 retro/analyst）。

## Glossary

- 能力市场 / 货架（TenantShelf / list_public）：面向租户的公开展示面，受 `POWER_MARKET.ENABLED`（默认 false）闸。
- 治理目录（Capabilities 页 / list_assets）：面向平台管理员的资产治理面。
- agents_hub 同步：WIP 新增的 `.agents → capability_assets` 增量 upsert 通道（本 feature 的基底）。
- scan-plugins：旧通道，扫 `capability-library/plugins`（目录已删）——bug 源头，本轮退役。
- 孤儿行：无磁盘来源的 capability_assets 残留（13 oh-story__* command + ~9 skill）。

## Fog / 范围外

- official 官网详情页重做（本轮不动；S3 已定）。
- 远程源（git/URL）分发导入（compete 明确回避）。
- 公开安装计数/排行榜（单租户规模造假风险）。
- AI 生成图标。
- 生产租户规模量化（无数据源）。

## Q-*

| id | 问题 | 阻塞 | 谁答 | 状态 |
|---|---|---|---|---|
| Q-SCAN-CHANNEL | 旧扫描退役 vs 原地修复 | define 方案 | operator | 已按推荐答（S1 收敛单通道），待操作者追认 |
| Q-DIR-PICKER | webkitdirectory vs 服务器端 | define 方案 | operator | 已按推荐答（S2 webkitdirectory），待操作者追认 |
| Q-DETAIL-SURFACE | admin 抽屉 vs 独立页 vs 官网同改 | shape UI 范围 | operator | 已按推荐答（S3 admin 抽屉），待操作者追认 |
| Q-MD-RENDER | react-markdown vs 自写 | Q5 依赖闸 | operator | 已按推荐答（S4 引入），待操作者追认 |
| Q-HOT-SORT | 「最热」数据源 | define FR | manager 裁定 | 已答：真实订阅/安装计数，无数据降级综合 |
