# Spec（PRD）· .agents 资产能力市场（展示 + 后台管理 + 目录导入 + 扫描修复）

> 泳道：L3｜appetite：3–5pw 等效（manager 建议，操作者未给定；超 50% 停下重判）｜作者：pm 帽｜日期：2026-09-15｜版本：v1.2（define G-fresh r2 返工，NEW-1..NEW-5 全处置，变更明细见 §8）
> 下游：`architect`（方案与拆票）· `designer`（IA 与 flow）· `qa`（GWT 是用例唯一来源）· `analyst`（§6 是复盘依据）
> 输入：`00-discover/{briefing,recon,market,compete}.md`（frozen）· state.yaml（lane_judge/discover 判定）

## 0. WIP 基底声明（先读，防重复建设）

工作区已有**未提交 WIP** 并已闭环：`.agents → capability_assets` 同步链路（agents_hub collect + upsert）、logo/background 列（迁移 049）+ 媒体端点、货架卡片图渲染、ctl 启动自动同步、单测（recon C）。**本 spec 的全部 FR 是该基底的增量定义**——扫描→入库→图→媒体→货架渲染→自动同步已具备的能力不列为待建；实现帽不得回退 WIP，须先验证其测试可过。缺口（本轮交付）：①治理/货架无详情视图 ②无 md 渲染依赖 ③旧 scan-plugins 入口仍指向软删语义 ④货架无分类 tab/排序 ⑤无图资产无占位 ⑥目录导入无目录选择器。

---

## 1. 背景与问题定义

**谁**：auto_agents 平台管理员（操作者本人；每个部署必有 ≥1 名，本地 DB 3 名 is_admin 用户——market.md E3）。次要受益人：租户与买方（代理推断，闸前 Reach=0，**价值未量化，不进本轮验收**——briefing Falsify A3/K3）。

**现在什么情况**：插件卡 0 张（DB 12 条 plugin 行全部被「扫描插件目录」软删，deleted_at 置值——bug 足迹 E3）+ ~22 条无磁盘源孤儿行（13 条 oh-story__* command + ~9 条 skill）；资产只有 7-tab 治理表格，货架卡片无 onClick、无详情、（WIP 前）无图；导入只能多选 .md/.zip 或**手填服务器路径字符串**（ImportWizard.tsx:178-216）；要看 SKILL.md 正文只能翻仓库文件。一次误点扫描 = 插件全部消失。

**期望什么结果**（用户的话）：管理员点一次同步，插件卡回来且**以后怎么扫都不再丢**；在市场里按 skill/command/agent/plugin 四类 tab 浏览带 icon/背景图的卡片，点开抽屉直接看 md 正文；导入时选一个目录，系统自动分好类，预览确认后入库；上下架、精选、开闸都在同一个后台完成。

**凭什么说改善了**：同步后 plugin 型 live 行 0→6 且重复触发不降；live 行数与磁盘可识别资产数**对账差 = 0**；卡片→md 正文 1 次点击；一个混合目录一次导入得到「分类结果预览→确认入库」。§6 细化。

### 需求来源

| 来源 | 证据 | 频次/影响面 |
|---|---|---|
| 操作者指令（E1，2026-09-15 原话 + 参考图二张） | intent quote：四类资产进市场（icon/背景、md 详情、全后台管理、选目录自动分类、UI 好用美观）+「插件页点扫描插件目录插件全部丢失是 bug」 | 单一 owner（=平台全部治理用户下界）；治理动作随 `.agents` 变更触发 |
| 代码实证（E2，recon file:line） | bug 根因 plugin_service.py:46-88（root 缺失→`_retract_missing_plugins(set())` 软删全部 source_id IS NULL 存活行，:150-174）；导入现状 ImportWizard.tsx:178-216；货架 TenantShelf.tsx:83 无 onClick | 治理面全部插件数据 |
| DB 快照（E3，market.md 2026-09-15） | live 182 行（plugin 0）；12 plugin 行软删；~22 孤儿行；磁盘 166 资产 | 供给侧全量 |
| 竞品语义（E2，compete.md） | Claude marketplace「refresh 不丢已装插件」原句 = 修复验收线；Dify manifest 自动分类；GPT starters 示例区 | 验收线与设计输入 |

无来源的需求不进本文档。

### 分诊结论

| 项 | 结论 |
|---|---|
| 需求类型 | 扫描丢失 = **缺陷修复**（真需求，DB 足迹可复现）；目录导入/详情/四类货架/后台管理 = **真需求**（E1 指令级 + E2 现状 workaround 成本）；消费面价值 = **未量化**（A3 禁 pass，随闸交付不进验收） |
| 原始诉求 | 「做到能力市场（icon+背景图、md 详情、全后台管理、导入选目录自动分类、UI 好用美观）」+「扫描后插件全丢是 bug」 |
| 三连问后的真问题 | 不是「加个市场页面」，是：①一条通道能把治理数据毁掉（信任问题）②资产不可见不可读（翻仓库文件当目录）③导入按文件粒度人肉分类（成本问题） |
| 本轮选择的解法 | S1 收敛单通道非破坏 + 失源行清理；S2 webkitdirectory 目录导入 + 结构判型；S3 admin 抽屉详情（official 不动）；S4 react-markdown+remark-gfm。详见下表 |

### 方案分叉决策记录（Discuss-S 已答，操作者保留否决权 Q-OP-RATIFY）

| id | 决策 | 依据 |
|---|---|---|
| S1 | 扫描通道收敛为 agents_hub 单通道（幂等 upsert、非破坏）；旧 scan-plugins 退役；孤儿行按「.agents 是唯一真相源」失源行清理（首次清存量，入口保留复用，FR-02） | 竞品验收线（Claude 非破坏语义 E2）；两通道打架根因（recon A） |
| S2 | 目录导入用 webkitdirectory 整树上传（带相对路径），后端按结构自动分类（见 SKILL.md→skill、plugin.json→plugin 并展开 bundled、agents/*.md→agent、commands/*→command），manifest 判型不做内容嗅探；手填服务器路径保留为高级选项 | Dify manifest 分类（E2）；A4 存活（admin ≤ 数百文件可控） |
| S3 | 详情面 = admin 抽屉式（icon/背景、能力标签、「帮你做」示例区、md 富渲染、订阅 CTA）；official 本轮不动 | 操作者参考图二；官网重构超 appetite |
| S4 | md 渲染 = react-markdown + remark-gfm（新依赖，Q5=yes 已裁）；默认禁 raw HTML | E2；XSS 防线见 FR-05 |
| 附加 a | 「最热」排序只用真实订阅/安装计数（capability_installs），无数据降级为综合序，不显示假数字 | compete 回避公开计数造假风险 |
| 附加 b | 无图资产（9 一等 skill + sdlc-workflow）用确定性占位（渐变+资产名首字母），不做 AI 生成图 | manager 裁定；A2 缩小 |
| 附加 c | POWER_MARKET.ENABLED 默认仍 false，开放由操作者经现有 PowerMarketSwitch 决定（release checklist 项） | 开闸节奏归操作者 |
| 附加 d（define 帽新增，低风险默认） | 详情「帮你做」示例区内容 = 治理面**人工维护**的 0–N 条示例（每资产）；未维护时该区块隐藏 | SKILL.md 规范无示例字段（compete E2）；空态隐藏可验收 |
| 附加 e（define 帽新增，低风险默认） | 抽屉订阅 CTA 跟随闸状态：闸关 = 禁用态 + 文案「市场暂未开放，开放后可订阅」（不暴露配置名——P-06）；闸开 = 可点订阅 | 治理面不受闸但消费动作受闸 |

### RICE（排序用，不做唯一裁决；消费面 Reach 按「闸后 = 租户数」参数化，本地 5 不可放大）

| 需求块 | Reach | Impact | Conf | Effort(pw) | RICE | 备注 |
|---|---|---|---|---|---|---|
| FR-01/02 修复+单通道+清理 | 1（管理员/部署，下界） | 3（数据全丢，完全做不到） | 100%（E2+E3 足迹） | 0.5 | **600** | 缺陷修复必做 |
| FR-07 目录导入 | 1 | 2（有 workaround=手填路径，成本高） | 80% | 1.5 | 107 | |
| FR-05 详情+md 渲染 | 1 | 2（workaround=翻仓库文件） | 80% | 1.5 | 107 | |
| FR-08 治理埋点 | 1 | 0.5（评估基建，缺它无法复盘） | 100%（无事件源 E2） | 0.5 | 100 | enabler |
| FR-03/04/06 货架形态（tab/排序/占位） | 1（治理面）；消费面 = T_gate（未量化，不入分） | 1（治理侧展示改善） | 50% | 1.5 | 33 | 随闸交付不进验收 |

Effort 为 pm 帽在 manager appetite 内的占位粗估（WIP 基底已在），**architect 拆票时复核修正**。实施顺序建议：FR-01/02 → FR-05 → FR-07 → FR-03/04/06/08（可并行）；安全/权限/数据一致性不参与切分。

---

## 2. 用户故事

### US-1 平台管理员（治理面，本轮验收主体）

作为管理 `.agents` 资产的平台管理员，我想要一个不会毁数据的同步通道、能看正文的详情和选目录即分类的导入，以便我不必在治理表格、仓库文件和服务器路径之间来回人肉对账。

| 3C | 内容 |
|---|---|
| **Card** | 一次同步让全部四类资产安全可见；点卡片 1 次看 md 详情；选目录 3 步完成导入 |
| **Context** | 触发：`.agents` 新增/修改 skill 或插件后，或上架运营时。之前：手填服务器路径导入 + 翻仓库看正文 + 不敢点扫描。之后：上下架/精选/开闸同后台完成。不做会怎样：插件卡持续为 0、孤儿行持续误导对账、误点扫描再次清空 |
| **Confirmation** | FR-01、FR-02、FR-05、FR-06、FR-07、FR-08（GWT 见 §3） |

### US-2 租户用户（消费面，随闸交付，**本轮不进验收**——A3/K3）

作为已登录的租户用户，我想要在市场货架按类型浏览带图标的能力卡并点开看它能帮我做什么，以便我判断是否订阅该能力。（闸前 Reach=0；闸后 = 租户数 T_gate，本地 5、生产未量化——market.md）

| 3C | 内容 |
|---|---|
| **Card** | 闸开后：分类 tab 浏览卡片 → 点开抽屉看「帮你做」示例与 md 正文 → 一键订阅 |
| **Context** | 闸开后按需浏览；现状：货架不可达（POWER_MARKET.ENABLED=false）。价值未量化，开闸后先建基线（§6） |
| **Confirmation** | FR-03、FR-04、FR-05（标「闸后」的 GWT 行） |

---

## 3. 功能需求（FR）

> 编号纪律：只追加不重排。改判用 `[superseded by FR-nn]`，废弃用 `[dropped: 理由]`。
> 标注「闸后」的 GWT 随闸交付（默认闸关不可达）；其余为本轮验收主体。

### FR-01 同步收敛为非破坏单通道（扫描清空 bug 修复 + 旧通道退役）

管理员触发任何「扫描/同步」入口后，`.agents` 磁盘资产被幂等 upsert 入 `capability_assets`，且**任何扫描/同步动作都不软删行**（回收只能来自显式下架或 FR-02 的失源行清理）——对齐 Claude marketplace 非破坏语义（compete E2 引文）。旧 scan-plugins 破坏性语义退役（入口去留/改指由 architect 定，验收只认「不存在能造成软删的扫描入口」）。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-01.1 | 正常 | **Given** DB 处于 bug 后状态（plugin 型 live 行 = 0，12 行带 deleted_at），磁盘 `.agents/plugins/` 有 6 个插件 **When** 管理员触发一次同步 **Then** plugin 型 live 行 = 6，治理目录（list_assets）重新显示 6 张插件卡，其他类型 live 行数不减少（货架可见性以 GWT-03.2「货架可见集」口径为准，另见 FR-03 术语定义） |
| GWT-01.2 | 幂等 | **Given** 同步已完成一次（live 行数 = N） **When** 连续再触发同步 2 次 **Then** 各 asset_type 的 live 行数仍 = N（无新增重复行，asset_type+name 唯一），无行被软删 |
| GWT-01.3 | 非破坏（验收线） | **Given** 任意 live 状态（含磁盘资产已改名/移除的情况） **When** 管理员把所有扫描/同步类入口各触发一遍 **Then** 本轮触发新增的 deleted_at 行数 = 0（数据回收仅出现在显式下架动作） |
| GWT-01.4 | 边界 | **Given** `.agents/plugins/` 下 1 个符号链接失效（目标目录不存在） **When** 同步 **Then** 同步完成不报错，该插件已有 live 行不被软删，跳过原因写入日志 |
| GWT-01.5 | 越权 | **Given** 非平台管理员（租户角色或普通登录用户）已登录 **When** 调用扫描/同步端点 **Then** 返回 404（require_platform_admin_or_404 存在性隐藏门面，与现状一致），DB 行数与状态无任何变化 |
| GWT-01.6 | 退役 | **Given** 管理员打开插件治理页 **When** 使用页面上的扫描类操作 **Then** 操作完成后 plugin 型 live 行数不小于操作前（不存在使其下降的入口） |
| GWT-01.7 | 并发 | **Given** 同步已完成一次（live 行数 = N） **When** 两个同步请求并发触发（执行时间重叠） **Then** 全部完成后各 asset_type 的 live 行数仍 = N（asset_type+name 唯一，不产生重复行），无行被软删 |

### FR-02 失源行清理（首次执行针对存量 ~22 条，入口可重复用于后续失源行）

存量 ~22 条孤儿行（13 条 oh-story__* command + ~9 条 skill，来源已删除的旧 capability-library/plugins 通道）通过**首次显式执行失源行清理**退出 live 集合，使「live 行数 = 磁盘可识别资产数」可对账归零；该清理入口**可重复用于后续失源行**（磁盘改名/移除事件产生的无源 live 行，归零口径见 §6 北极星注）。清理始终是显式治理动作，不是同步通道的常规行为（同步不软删，GWT-01.3）。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-02.1 | 正常 | **Given** DB 有 13 条 oh-story__* command 与 ~9 条 skill 的 live 行在当前 `.agents` 磁盘无对应源 **When** 管理员执行失源行清理（首次，针对存量） **Then** 上述行不再出现在治理目录与货架查询（对管理员不可见），其余 live 行数不变 |
| GWT-02.2 | 对账 | **Given** 清理与一次同步均已完成 **When** 对账（live 行数 vs 同步通道从磁盘识别的去重资产数） **Then** 差值 = 0 |
| GWT-02.3 | 范围保护 | **Given** skill X 在磁盘 `.agents/skills/` 存在 **When** 清理执行 **Then** X 的行仍为 live（清理不得触及有磁盘源的行） |
| GWT-02.4 | 幂等 | **Given** 清理已执行一次 **When** 再次执行 **Then** live 行数无变化 |
| GWT-02.5 | 越权 | **Given** 非平台管理员（租户角色或普通登录用户）已登录 **When** 调用失源行清理入口 **Then** 返回 404（require_platform_admin_or_404 存在性隐藏门面，与现状一致），DB 无变化 |
| GWT-02.6 | 越权（普通登录用户） | **Given** 非平台管理员（普通登录用户）已登录 **When** 调用失源行清理入口 **Then** 返回 404（同 GWT-02.5 门面），DB 无变化 |

### FR-03 市场货架：四类资产卡片 + 分类 tab

市场货架页（Capabilities 非超管视图 + 超管预览入口）按参考图一呈现卡片网格：顶部分类 tab（全部/skill/command/agent/plugin），卡片四要素（与 NFR-U1 同口径）——icon（真图或 FR-06 占位）、主副标题（主标题 = 资产展示名，副标题 = 所属插件或类型）、≤2 行描述、底部标签。治理面 7-tab 表格保留不替换。

**货架可见集**（本文档统一口径，凡数货架卡片的 GWT 均按此口径）：某类型的货架可见卡片 = 该类型 live 行中状态为 listed 或 coming_soon 的资产 ∩ 既有闸与白名单规则后的存活集。**显式排除项**：dev-team 合并超集插件——其内容已包含 superpowers / mattpocock-skills 子集（AGENTS.md 农场契约：`.agents/plugins/` 仅放符号链接，宿主目录做适配器），单独上架会与被包含插件重复露出，故 WIP 同步通道既有产品语义将其强制 unlisted，本轮不改（manager 裁定）。据此当前磁盘 6 个 plugin 对应货架可见 plugin 卡 = 5（治理目录仍 6 行）。上下架对货架可见性的效果 oracle 见 GWT-03.6–03.8。

**验收路径声明**：未标「闸后」的货架 UI 类 GWT（本 FR 的空态行、FR-04 的排序各档）在默认闸关下经**超管预览入口**验收（预览入口与货架共用同一数据与口径）；此声明只指定验收通道，不改变这些 GWT 属本轮验收主体的交付批次。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-03.1 | 正常（闸后） | **Given** 同步+清理完成（skill/command/agent/plugin 四类均有 live 行） **When** 打开市场货架「全部」tab **Then** 四类卡片混合展示，抽检每类 1 张卡均含四要素，卡片图为真图或确定性占位 |
| GWT-03.2 | 筛选（闸后） | **Given** plugin 型 live 行 = 6（其中 dev-team 为 unlisted，见上方货架可见集定义） **When** 切换到「plugin」tab **Then** 显示 5 张 plugin 卡（= plugin 型货架可见集）；其余 tab 同口径各自过滤 |
| GWT-03.3 | 空态 | **Given** 某类型 live 行 = 0 **When** 打开该类型 tab **Then** 显示空态文案「暂无该类资产」，页面不报错 |
| GWT-03.4 | 闸语义（一个 oracle） | **Given** POWER_MARKET.ENABLED = false **When** 租户请求货架/媒体/公开详情端点 **Then** 与现状闸行为一致（货架不可达，P-02 双公开闸金标不改动） |
| GWT-03.5 | 越权 | **Given** 未登录请求者 **When** 请求公开货架端点 **Then** 按现有公开端点鉴权语义拒绝（与现状一致） |
| GWT-03.6 | 下架 | **Given** 资产 A 为 listed 且货架可见（在货架可见集中） **When** 管理员执行下架（listed→unlisted） **Then** A 从货架 tab 与公开详情均不可见（公开详情在闸开时返回 404；该公开详情子句与 GWT-03.7 同批（闸开环境）验收），治理目录（list_assets）仍可见 A |
| GWT-03.7 | unlisted 防泄露（闸后） | **Given** 闸开、资产 A 为 unlisted **When** 已登录租户请求 A 的公开详情端点 **Then** 返回 404，md 正文与媒体均不返回 |
| GWT-03.8 | 越权 | **Given** 非平台管理员（租户角色或普通登录用户）已登录 **When** 调用上架/下架端点 **Then** 返回 404（require_platform_admin_or_404 存在性隐藏门面；该端点现状即挂此门面，capabilities.py:341-346），目标资产 listed 状态无变化 |

### FR-04 货架排序三档（综合/最热/最新）+ 管理员精选

货架右上提供三档排序：**综合** = 管理员精选置顶（精选内部按更新时间倒序）+ 未精选按更新时间倒序；**最新** = updated_at 倒序；**最热** = 真实订阅计数（capability_installs）倒序，无数据时降级为综合序且不显示任何计数（不造假）。管理员可在治理面对任意资产设置/取消精选。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-04.1 | 综合（闸后） | **Given** 管理员已将 A、B 设为精选，A 的 updated_at 早于 B **When** 选择「综合」 **Then** 置顶顺序为 B、A，其后为未精选资产按 updated_at 倒序 |
| GWT-04.2 | 最新 | **Given** 资产 A 的 updated_at 晚于 B **When** 选择「最新」 **Then** A 排在 B 前 |
| GWT-04.3 | 最热-有数据 | **Given** A 订阅 5 次、B 订阅 2 次 **When** 选择「最热」 **Then** A 排在 B 前；计数并列时按 updated_at 倒序 |
| GWT-04.4 | 最热-降级 | **Given** 全部资产订阅计数 = 0 **When** 选择「最热」 **Then** 列表顺序与「综合」一致，页面上不出现任何订阅/安装计数数字 |
| GWT-04.5 | 精选治理 | **Given** 管理员在治理面对资产 A 点击「精选」 **When** 操作完成 **Then** A 出现在综合序置顶区；取消精选后回到未精选区 |
| GWT-04.6 | 越权 | **Given** 非平台管理员（租户角色或普通登录用户）已登录 **When** 调用设置/取消精选入口 **Then** 返回 404（require_platform_admin_or_404 存在性隐藏门面，与现状一致），精选状态无变化 |

### FR-05 资产详情：md 正文 + admin 抽屉（示例区、订阅 CTA）

货架卡片或治理表格行点击 1 次打开详情抽屉（对齐参考图二）：大 icon + 背景图、能力标签、「帮你做」示例区（人工维护 0–N 条，未维护时隐藏——附加 d）、md 正文富渲染（GFM 表格/代码块；默认禁 raw HTML）、订阅 CTA（附加 e：闸关=禁用态+文案「市场暂未开放，开放后可订阅」；闸开=可点）。公开详情数据含资产 md 正文，供抽屉与（现有）official 详情页共用。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-05.1 | 正常 | **Given** 管理员在货架/治理表格查看资产 A（SKILL.md 含 GFM 表格与代码块） **When** 点击 A 的卡片/行 **Then** 抽屉打开（无页面跳转），展示 icon（或占位）、背景、标签、md 正文（表格与代码块呈结构化样式，非纯文本堆叠）、示例区（有维护时）、订阅 CTA |
| GWT-05.2 | XSS（P-03 金标） | **Given** 资产 md 正文含 `<script>alert(1)</script>` 与 `<img onerror=...>` 载荷 **When** 打开抽屉 **Then** 脚本不执行、无 HTML 注入（raw HTML 默认禁用），载荷字符作为文本可见 |
| GWT-05.3 | 空态 | **Given** 资产无示例维护、md 正文为空 **When** 打开抽屉 **Then** 示例区隐藏，正文区显示「暂无正文」，其余区块正常展示 |
| GWT-05.4 | CTA-闸关 | **Given** POWER_MARKET.ENABLED = false **When** 管理员打开抽屉 **Then** 订阅 CTA 呈禁用态并显示「市场暂未开放，开放后可订阅」，点击无动作 |
| GWT-05.5 | CTA-闸开（闸后） | **Given** 闸开、租户已登录、资产 A 订阅计数 = n **When** 在抽屉点击订阅 CTA **Then** 提示订阅成功，A 的订阅计数变为 n+1（capability_installs 可查） |
| GWT-05.6 | 越权 | **Given** 闸关且租户请求公开详情端点 **When** 请求 **Then** 与 GWT-03.4 同语义（闸行为一致，不新增第二个 oracle） |

### FR-06 无图资产确定性占位

无 logo/background 的资产（9 个一等 skill + sdlc-workflow 插件）在卡片与抽屉显示**确定性占位**：同一资产每次渲染视觉一致（基于 asset_type+name 生成的渐变+首字母），不做 AI 生成图。图片不可读时回落占位。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-06.1 | 正常 | **Given** skill 资产无 logo/background **When** 渲染其卡片与抽屉 **Then** 显示占位（渐变 + 资产展示名首字母），同一资产两次渲染结果一致 |
| GWT-06.2 | 对照 | **Given** 插件有 icon.png/background.png（如 dev-team） **When** 渲染 **Then** 显示真实图，不出现占位 |
| GWT-06.3 | 边界 | **Given** 资产图字段有值但文件损坏/不可读 **When** 渲染 **Then** 回落显示占位，页面不报错 |

### FR-07 目录导入：选目录 → 自动分类 → 预览确认

导入向导新增「选择目录」入口（浏览器原生目录选择，整树带相对路径上传）；后端按结构自动判型：含 SKILL.md → skill；含 plugin.json → plugin 并展开其 bundled skills/commands/agents；agents/*.md → agent；commands/* → command（manifest 判型，不做内容嗅探）。上传后先呈现**分类预览**（各类型数量、新建/更新标注、跳过清单），管理员确认后才入库；同名同类型 upsert 不建重复行。手填服务器路径保留为高级选项（现状能力不回退）。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-07.1 | 正常 | **Given** 所选目录树含 2 个带 SKILL.md 的子目录 + 1 个带 plugin.json 的插件目录（内含 3 个 bundled skill） **When** 上传并查看预览 **Then** 预览列出 2 skill + 1 plugin + 3 bundled skill（含新建/更新标注）；确认后治理目录出现对应行，入库数量与预览一致 |
| GWT-07.2 | 取消 | **Given** 预览页已显示分类结果 **When** 管理员点击「取消」 **Then** 无任何行写入（live 行数与上传/取消前一致） |
| GWT-07.3 | upsert | **Given** 库中已存在同 asset_type+name 的资产且内容有变更 **When** 导入确认 **Then** 该行被更新（updated_at/content_hash 变化），live 行数不增加 |
| GWT-07.4 | 空态 | **Given** 所选目录中无任何可判型资产 **When** 上传 **Then** 提示「未识别到可导入资产」，无写入 |
| GWT-07.5 | 部分失败 | **Given** 目录树含 3 个资产，其中 1 个 SKILL.md 无法解析出标题 **When** 导入确认 **Then** 2 个入库；失败 1 项连同原因列入结果清单展示，不入库 |
| GWT-07.6 | 超限 | **Given** 所选目录树文件数 > 500 **When** 上传 **Then** 提示「单次最多导入 500 个文件，请改用服务器路径导入」，无写入 |
| GWT-07.7 | 越权 | **Given** 非平台管理员（租户角色或普通登录用户）已登录 **When** 调用目录导入端点 **Then** 返回 404（require_platform_admin_or_404 存在性隐藏门面，与现状一致），无写入 |
| GWT-07.8 | 高级选项 | **Given** 管理员打开导入向导 **When** 查看导入方式 **Then** 手填服务器路径入口仍存在且可用（现状能力不回退） |
| GWT-07.9 | 白名单 | **Given** 所选目录树含可判型资产与 1 个非白名单扩展名文件（如 .exe） **When** 上传并查看预览 **Then** 预览的跳过清单列出该文件并标注非白名单扩展名；确认后其余资产入库数量与预览一致，该文件不在库中 |
| GWT-07.10 | 越权（普通登录用户） | **Given** 非平台管理员（普通登录用户）已登录 **When** 调用目录导入端点 **Then** 返回 404（同 GWT-07.7 门面），无写入 |

### FR-08 埋点：治理动作与详情打开事件上报

治理面的关键动作产生结构化事件（结构化日志可检索即可，不要求独立事件后台），作为 §6 度量蓝图的数据源。字段统一含 who（角色）/what（动作与关键参数）/result（成功失败）。

| GWT | 类型 | 内容 |
|---|---|---|
| GWT-08.1 | 导入完成 | **Given** 管理员完成一次目录导入确认 **When** 导入落库 **Then** 上报 `import_completed`，字段：actor_role、source（directory/server_path）、files、assets_created、assets_updated、assets_skipped；结构化日志中可检索到该事件 |
| GWT-08.2 | 导入失败 | **Given** 导入过程失败 **When** 失败发生 **Then** 上报 `import_failed`，含 error_type |
| GWT-08.3 | 同步完成 | **Given** 同步执行 **When** 同步结束 **Then** 上报 `sync_completed`，字段：actor（manual/startup）、added、updated、unchanged；失败时上报 `sync_failed` 含 error_type |
| GWT-08.4 | 详情打开 | **Given** 管理员/租户打开资产详情抽屉 **When** 抽屉渲染完成 **Then** 上报 `detail_opened`，字段：actor_role、asset_type、asset_name |

## 3.1 状态流转（资产行，沿用既有状态维度，本轮不改机器）

```
（磁盘新资产）──同步 upsert──> live[unlisted/listed 按白名单策略]
live[listed⇄unlisted]──显式上下架（人工治理动作）──> listed/unlisted
live ──失源行清理（FR-02，显式治理动作，入口可重复）──> deleted
终态：deleted（仅显式动作可达）
```

> 注：coming_soon 为既有第三态（capabilities.py「上架三态」端点，:341-350），本轮无新增流转。

| 流转 | 触发条件 | 谁能触发 | 副作用 |
|---|---|---|---|
| 新建 → live | 同步发现磁盘新资产 | 同步通道（自动/手动） | 计入 added；白名单策略决定初始 listed（dev-team 系强制 unlisted，既有规则） |
| listed ⇄ unlisted | 治理面上下架 | 管理员 | 货架可见性变化；订阅计数保留 |
| live → deleted | 失源行清理（FR-02，首次针对存量，可重复用于后续失源行） | 管理员显式执行 | 行退出一切查询；可重新由同步重建 |

**非法流转**（qa 负向用例来源）：

| 非法流转 | 期望行为 |
|---|---|
| live → deleted 由同步/扫描隐式触发 | **禁止**（本轮修复点）：任何同步路径不写 deleted_at；状态不变、无副作用 |
| deleted → live 由同步隐式恢复 | 仅当磁盘源真实存在时经 upsert 重建并计入 added；磁盘无源不得复活 |

## 4. 非功能需求（NFR）

| 类别 | 编号 | 要求 | N/A 理由 |
|---|---|---|---|
| 性能 | NFR-01 | 货架 list_public 与治理 list_assets 接口 P95 < 800ms（含 logo/background 字段注入后） | |
| 性能 | NFR-02 | 详情抽屉数据请求 P95 < 800ms；单文档 ≤ 5000 行的 md 渲染完成 < 3s，渲染期间显示加载态不白屏 | |
| 容量 | NFR-03 | 单次目录导入 ≤ 500 文件、单文件 ≤ 5MB（md/json/图片混合树）；SKILL.md 单文件 ≤ 1MB；超出按 FR-07.6/07.5 提示不写入 | |
| 可用性 | NFR-04 | 同步失败不阻断服务启动（既有行为保持）；md 渲染异常时降级显示纯文本（K2 降级路径）；图不可读回落占位（FR-06.3） | |
| 安全 | NFR-05 | md 渲染默认禁 raw HTML（S4）；目录导入仅白名单扩展名入库，非白名单文件入跳过清单不入库；媒体端点路径校验（get_media_path）与闸门保持；日志不落密钥/token（既有红线） | |
| 权限 | NFR-06 | 见下方权限矩阵；扫描/导入/清理/精选/上下架/开闸 = 管理员；本轮不扩不缩既有权限码映射（映射细节由下游对齐现状） | |
| 合规 | NFR-07 | N/A——资产内容为仓库自有（无 PII）；订阅记录含租户标识，按既有数据规范处理 | |
| 兼容 | NFR-08 | 目录选择兼容 Chrome/Edge/Safari/Firefox 现代版（webkitdirectory，E2）；不支持的浏览器自动只显示服务器路径高级选项，能力不缺失；react-markdown+remark-gfm 经根 package.json workspaces 安装（Q5 已裁） | |
| 可观测 | NFR-09 | FR-08 四类事件 + 同步日志（logger 名对齐 LOGGERS）；同步失败可从 error 日志定位原因 | |
| 国际化 | NFR-10 | N/A——本轮内部平台中文界面，无多语言场景 | |
| 可维护 | NFR-11 | 新增列走迁移（049 基底上增量）；POWER_MARKET.ENABLED 保持配置闸不硬编码（R1）；前端业务 .tsx ≤ 400 行（F-7）、ESLint 0 error | |
| 体验（项目附加类，落「UI 好用美观」） | NFR-U1 | 卡片四要素齐全（icon/主副标题/≤2 行描述/标签），信息结构对齐参考图一（tab 顶部、排序右上、三列网格） | |
| | NFR-U2 | 关键路径点击深度：导入 3 步内（选目录→预览→确认）；卡片到详情 1 次点击；下架从列表 2 步内 | |
| | NFR-U3 | 每个新视图（tab 空态、预览、抽屉、结果清单）均有明确空态文案与加载态 | |

### 权限矩阵

| 角色 | 能做什么 | 不能做什么 |
|---|---|---|
| 平台管理员（is_platform_admin=true） | 同步/扫描、目录导入、失源行清理、上下架、精选、PowerMarketSwitch 开闸、查看治理表格与货架预览 | — |
| 非平台管理员（租户角色或普通登录用户） | 闸开后：浏览货架/详情、订阅 | 一切治理写面动作一律 404（现状 is_platform_admin 布尔模型，本轮不引入中间角色，NFR-06 维持不变；越权行 FR-01.5/02.5/02.6/03.8/04.6/07.7/07.10） |
| 未登录 | official 公开端点现状语义 | admin 内一切页面与 API |

## 5. 范围外

| 内容 | 处置 | 理由 |
|---|---|---|
| official 官网详情页重做（`<pre>`→富渲染） | 下一轮 | S3 已定 admin 抽屉；官网重构超 appetite |
| 远程源（git/URL）分发导入 | 不做 | compete 回避；内部单仓无多仓分发。复审条件：出现外部供应商仓 |
| 公开安装计数/排行榜 | 不做 | 单租户量级数字不可信（compete）。复审条件：多租户对外开放后 |
| AI 生成 icon/自动作图 | 不做 | 真实缺口仅 sdlc-workflow 1 个（E2）。复审条件：无图资产上几十 |
| 生产租户规模量化 | 不做 | 无数据源（market.md E1） |
| 消费面（租户）价值指标进验收 | 本轮禁止（K3） | A3 未量化；开闸后先建基线 |
| scan-experts 通道同类体检 | 下一轮 | recon 次要项，行为未复现；见开放问题 Q-SCAN-EXPERTS，无 FR 依赖 |
| 拖拽导入、批量 zip 解包增强 | 下一轮 | webkitdirectory 已覆盖主场景；避免「顺手做了」 |

**未被砍的底线**：安全（NFR-05/XSS）、权限（NFR-06/越权行）、数据一致性（FR-01 非破坏 + FR-02 对账）——三类不参与范围切分。

## 6. 度量蓝图

### 北极星（唯一）

| 指标 | 口径 | 来源 | 时间窗 | 目标值 |
|---|---|---|---|---|
| 资产对账一致率 | 每周对账：`capability_assets` live 行数（含 unlisted）vs 同步通道从 `.agents` 磁盘识别的去重资产数；一致率 = 对账差为 0 的检查次数 ÷ 总检查次数 | DB 计数 + agents_hub collect（WIP 已有，E2） | 自然周，按对账执行时刻 | 上线后连续 4 周 = 100%（差 = 0） |

> 北极星选治理面而非消费面：消费面闸前 Reach=0 且价值未量化（A3/K3），消费面指标开闸后建基线、不进本轮验收。
> 对账差归零口径：磁盘改名/移除事件产生的失源 live 行，由管理员显式执行失源行清理（FR-02，入口可重复使用）退出 live 集合——对账差的归零动作 = FR-02 显式清理；同步通道永不隐式软删（GWT-01.3）。

### 驱动指标（2–4 个）

| 指标 | 口径 | 来源 | 时间窗 | 目标值 |
|---|---|---|---|---|
| 目录导入一次成功率 | 分子 = import_completed 且 assets_skipped 全为白名单跳过的事件数；分母 = import_completed + import_failed | FR-08 事件 | 自然周 | 四周内 ≥ 90%（无基线，首轮建基线） |
| 隐式软删数 | 每周新增 deleted_at 且非显式动作（下架/清理）归属的行数 | DB diff + FR-08 sync 事件 | 自然周 | 恒 = 0 |
| 详情抽屉周打开次数 | detail_opened 事件计数（按 actor_role 分组） | FR-08 事件 | 自然周 | 无基线，本轮建基线（不设目标值） |
| 精选位使用数 | 处于精选态的资产数 | 治理数据 | 自然周 | 无基线，建基线 |

### 护栏指标（≥2 个，有红线）

| 指标 | 红线 | 来源 | 超线怎么办 |
|---|---|---|---|
| list_public / list_assets P95 | > 800ms | 后端接口测试计时 + 人工抽测（前端无 RUM，标 ⚠️ 部分可测） | 回滚拖慢变更（字段注入/排序查询） |
| arch.sh 合规 | 退出码 ≠ 0（新增违规） | tools/check/arch.sh | 修完再合（CI 已挡） |
| 启动自动同步连续失败 | ≥ 2 次 | sync_failed 事件/error 日志 | 修同步再继续运营动作；货架数据冻结待修 |
| 单测回归 | backend/tests 任一失败 | uv run pytest -x -q backend/tests | 停止合入 |

### 埋点缺口盘点

| 指标 | 需要的数据 | 现有来源 | 状态 | 处理 |
|---|---|---|---|---|
| 导入一次成功率 | import_completed/import_failed | 无 | ❌ 缺 | 写进 FR-08（GWT-08.1/08.2） |
| 隐式软删数 | sync_completed(added/updated/unchanged) + DB diff | 日志有、结构化事件无 | ❌ 缺 | 写进 FR-08（GWT-08.3） |
| 详情打开次数 | detail_opened | 无 | ❌ 缺 | 写进 FR-08（GWT-08.4） |
| 最热排序数据 | 订阅/安装计数 | capability_installs 表 | ✅ 有 | FR-04 直用 |
| 对账一致率 | live 行数 vs 磁盘识别数 | DB + collect（WIP） | ✅ 有 | 北极星直用 |
| 消费面浏览/订阅漏斗 | 租侧行为事件 | 闸关 Reach=0 | ⚠️ 本轮不可测 | 开闸后建基线，不进验收（K3）；用运营观察替代 |

**判定周期**：上线 4 周后判定，中途不下结论。
**基线**：北极星基线 = 当前（bug 态）plugin live 0 / 孤儿 ~22 / 对账差 ≈ 22+6；驱动指标除订阅计数外均无基线，首轮目标即建基线。

## 7. 宪法自检

| 红线 | 是否触碰 | 说明 |
|---|---|---|
| R1 硬编码连接串/密钥/端口 | 否 | 闸与配置走 config（POWER_MARKET.ENABLED 保持） |
| R2/R3 爬虫边界、反爬 | 否 | 不涉 scrapy |
| API 层禁 import ORM / ORM 禁 import schema | 否 | 端点契约由下游遵守；responses.ok/created 用于新端点 |
| R10 服务公开方法入口日志 | 否 | 治理动作入口 logger（与 NFR-09 同句） |
| R11 async redis / R13 租户收口 | 否 | 公开端点走闸（一个 oracle：GWT-03.4）；治理端点管理员级；不新增租户数据面 |
| B1/B2/B3 边界 | 否 | 不涉 platform_core 依赖扩张 / backend import scrapy / config 依赖业务模块 |
| Q5 新依赖 | 已裁 yes | react-markdown+remark-gfm 走根 workspaces（NFR-08） |

机械清单以 `tools/check/arch.sh` 输出为准（护栏红线之一）。

## 8. 版本与变更

| 版本 | 日期 | 变更 | 影响的下游 |
|---|---|---|---|
| v1 | 2026-09-15 | 初版（FR-01–FR-08 + NFR + 度量蓝图内嵌；user-story 与 metrics 并入本文档，因本轮交付物收口为单文件 spec.md） | — |
| v1.1 | 2026-09-15 | define G-fresh r1 返工（7 findings 全处置，无新增 FR/方案）：QA-1 GWT-01.1 Then 收敛治理目录、GWT-03.2 改「货架可见集」口径并在 FR-03 定义术语（dev-team 显式排除，manager 裁定保持 unlisted）；QA-2 增 GWT-03.6/03.7/03.8（下架效果、unlisted 公开详情 404、上下架越权）；QA-3 FR-03 增验收路径声明（排序/空态 GWT 经超管预览入口验收）；QA-4 增 GWT-07.9（非白名单扩展名跳过清单）；QA-5 增 GWT-01.7 并发同步（选并发 GWT 而非串行假设：数据一致性是底线不参与切分，双请求用例成本低）；QA-6 增 GWT-02.6/07.10（普通管理员越权）；QA-7 措辞统一（GWT-07.2 改「与上传/取消前一致」、listed 拼写、四要素按 NFR-U1 口径在 FR-03 复述） | qa（复审新快照）；architect 及以下游无方案变化 |
| v1.2 | 2026-09-15 | define G-fresh r2 返工（NEW-1..NEW-5，无新增 FR/GWT 编号）。修订依据（现状代码口径）：deps.py:50-60 `CurrentUser.is_platform_admin` 布尔、无中间角色；deps.py:176-192 `require_platform_admin_or_404` 非超管 404 同形存在性隐藏（docstring「不走 403 信封」）；capabilities.py:341-346 上下架端点现状即挂该门面。NEW-1 七条越权 GWT（01.5/02.5/02.6/03.8/04.6/07.7/07.10）Then 统一改「返回 404（require_platform_admin_or_404 存在性隐藏门面）」、Given 统一「非平台管理员（租户角色或普通登录用户）」并删除权限码引用，权限矩阵删除运营中间角色行（不引入 403 信封、不扩权限映射）；NEW-2 矩阵越权行引用补全七条；NEW-3 FR-02 改「失源行清理（首次存量 + 入口可复用）」＋北极星补对账差归零口径；NEW-4 GWT-03.6 注明公开详情子句与 GWT-03.7 同批（闸开环境）验收；NEW-5 §3.1 注 coming_soon 为既有第三态、无新增流转 | qa（复审新快照）；architect 无方案变化 |

## 9. 开放问题

| 问题 | 阻塞什么 | 需要谁定 | 状态 |
|---|---|---|---|
| Q-OP-RATIFY：S1–S4 + 附加 a–c（manager 定）+ 附加 d–e（pm 定）待操作者追认 | 全部 FR 的方案方向（review 前任意时点可否决） | operator | 在案（state.yaml open_questions；operator_directive_continue 已裁定继续不阻塞） |
| Q-SCAN-EXPERTS：scan-experts 通道扫已不存在的 capability-library/experts，是否同批退役 | 无（已列范围外下一轮，无 FR 依赖） | operator + architect | 开放·不阻塞 |

**开放问题未关闭前，相关 FR 不进入 `/architect`。** 当前两问均不阻塞任一 FR（Q-OP-RATIFY 有继续指令在案；Q-SCAN-EXPERTS 无 FR 依赖）。
