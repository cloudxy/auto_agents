# Compete · .agents 资产能力市场（展示/后台/导入/扫描修复）

> 作者：competitor 帽｜日期：2026-09-15｜泳道：L3｜下游：discover briefing
> 长文模板：`skills/signals/templates/competitor-analysis.md`（本次按快照 + 功能点粒度结论）

## 压缩版（≤5 行，供 manager 进 briefing）

1. 扫描语义对照定案：Claude marketplace 的 refresh 明确非破坏（"refresh a marketplace without losing installed plugins"，E2 文档原句），我们的扫描=root 缺失即软删全部（recon A）——修复验收线=「扫描/同步永不回收非本通道数据」，显式动作才下架。
2. 视觉卡片是差异化不是追赶：marketplace.json 与 SKILL.md 规范均无 icon/图字段（E2，文档 0 命中），我们插件目录自带 icon.png/background.png 本地约定 + 迁移 049 已入库，别人规范层做不了；四类资产同货架也是独有形态。
3. 导入自动分类借鉴 Dify：类型由资产自描述（SKILL.md/插件结构=manifest）判定，不做内容嗅探；目录选择器是 web 后台特有能力（CLI 产品没有）。
4. 排序只做有数据支撑的：「最新」有 content_hash/updated_at 支撑；「综合」=人工精选（Dify Featured 模式）；「最热」需要事件数据，现状无埋点——discover 必须先回答数据从哪来，否则砍掉，假排序比没排序糟。
5. 回避：git/URL 远程源分发体系、公开 installs 计数、AI 生成图（复审条件见结论节）；GPT Store 的 conversation starters（示例 prompt 区）值得借鉴到功能点（E1 未核）。

## 集合

| 类 | 名字 | 来源等级 |
|---|---|---|
| 直接 | Dify Marketplace（docs.dify.ai + marketplace.dify.ai 实站） | 文档 E2（2026-09-15 实测可达） |
| 直接 | Claude Code Plugin Marketplace（code.claude.com/docs） | 文档 E2（2026-09-15 实测可达） |
| 间接 | Anthropic Agent Skills 规范（SKILL.md，code.claude.com/docs/en/skills） | 文档 E2（实测可达） |
| 间接 | Coze 插件/商店（www.coze.com 页面 JS 渲染，无法提取正文） | E1（今日未能核验，仅保留最小主张） |
| 标杆 | OpenAI GPT Store（卡片+详情+示例 prompt 的 UI 参照；help.openai.com 今日 403） | E1（未核，不作为结论依据，仅 UI 参照） |
| 替代行为 | 操作者翻 `.agents/README.md` 当目录 + 群里口口相传 `$name` 用法 | E2（recon/仓库事实） |
| **现状** | 治理 7-tab 表格；货架卡片无 onClick 无详情；official 详情 `<pre>` 纯文本；导入=文件多选或手填服务器路径；扫描按钮=破坏性软删（recon 结论 A/B） | E2（recon.md，file:line 可核） |

场景差（总）：他们面向公开生态（Dify 单插件 17 万 installs 量级，实站 E2），要社交证明/审核/防滥用；我们是单仓内部平台（9 skills + 6 plugins，几十个资产），使用者是内部操作者与租户，量级差 3–4 个数量级。他们的排行榜、公开计数、上架审核对我们是浪费；我们的真痛点是「资产看不见长什么样 + 一个按钮毁库」。

## 本变更一行（五个对照维度）

| 能力 | 他们 | 现状 | 我们若做 | 台面资格 / 差异化 / 浪费 |
|---|---|---|---|---|
| ① 卡片展示 | Claude marketplace：无 icon，仅 displayName/keywords 等文本字段（E2）；Dify：icon+作者+installs 计数（E2 实站）；GPT：icon+分类（E1） | 治理表格为主；货架卡片 WIP 才加 logo/背景，无排版标签体系 | icon+背景图+标签的四类资产卡片 | 差异化：两家规范均无 imagery 字段（E2 0 命中），图是我们插件目录已有本地约定；不抄 installs 计数（见回避） |
| ② 详情页 | SKILL.md 正文即详情是生态惯例（E2）；GPT conversation starters=示例 prompt 区+主 CTA（E1 未核） | admin 卡片无 onClick 无详情；official 详情 `<pre>` 纯文本（E2） | md 渲染详情 + 示例 prompt 区 + CTA | 借鉴：md 即正文对齐生态；starters 借鉴到功能点；渲染依赖是 Q-MD-RENDER（operator） |
| ③ 后台管理·扫描语义 | Claude：`marketplace update`=非破坏 refresh，仅显式 remove 才卸载，renames 显式迁移（E2 原句）；Dify：marketplace 索引与 workspace 安装分层（E1） | 扫描=root 缺失 → `_retract_missing_plugins(set())` 软删全部 source_id IS NULL 存活行；双通道打架（E2 recon A） | 扫描/同步改非破坏 + 通道收敛（Q-SCAN-CHANNEL） | 借鉴 Claude 语义作修复验收线；差异化：我们有双通道冲突（Claude 是单通道 git），收敛通道而非只改 retract 条件 |
| ④ 批量导入 | Dify：Marketplace/GitHub/Local File 三通道，类型由 manifest 声明的 plugin_type 自动归桶（E2）；Claude：local path marketplace（E2） | 文件多选 .md/.zip 或手填服务器路径字符串；无目录选择（E2 recon B） | 选目录导入 + 自动分类 | 借鉴：按资产自描述分类（SKILL.md/插件结构即 manifest），不内容嗅探；目录选择器（Q-DIR-PICKER）是 web 特有；不抄远程源分发（见回避） |
| ⑤ 分类排序 | Dify：Trending（"what builders are installing"）+ Featured 双轨（E2 实站）；Claude：relevance 字段（E2）；GPT：分类榜（E1） | 无分类 tab 无排序，仅 listing | 分类 tab + 综合/最热/最新 | 部分借鉴：综合=Featured 人工精选可行；最新=content_hash/updated_at 已支撑（E2）；最热=无埋点数据，先回答来源再谈 |

## 结论

### 借鉴（到功能点）

- **扫描非破坏语义**（Claude，E2）：refresh 只更新索引、永不回收已装数据；回收必须显式动作（remove/下架）。「重扫=root 没了就清库」在对照集里不存在对应物。落地粒度：`_retract_missing_plugins` 的回收范围收窄到「本通道、本 source 识别得出来的行」，或旧通道退役收敛进 agents_hub 单通道（Q-SCAN-CHANNEL，operator 决定方向，我不替选）。
- **manifest 自描述分类**（Dify，E2）：目录导入的自动分类按资产自身结构判定——见 SKILL.md 即 skill、见插件目录结构即展开 bundled 资产，不做文件内容嗅探。这正是 agents_hub collect 已实现的判定方式（E2 recon），方向一致。
- **示例 prompt 区**（GPT Store conversation starters，E1 未核）：详情页给「帮你做」的成句示例而非抽象描述，降低租户侧理解成本。粒度=详情页一个区块，不抄它的对话式交互。
- **Featured 式人工精选**（Dify，E2）：「综合」排序用人工置顶/运营精选实现，不需要算法。粒度=一个 is_featured 位或排序权重字段。

### 回避（替代方案 + 复审条件）

- **远程源分发体系**（Claude git/npm source、Dify GitHub URL 安装，E2）：内部单仓平台没有多仓分发问题。替代：目录/本地导入即可。复审条件：出现外部供应商仓或多仓供给时重评。
- **公开 installs 计数与排行榜**（Dify 实站 174,209 installs，E2；GPT 分类榜，E1）：单租户内部量级太小，数字既不可信也不构成社交证明。替代：参考图二的「使用量」改用内部真实事件（订阅/调用），且数据没接入前不展示。复审条件：POWER_MARKET 对外开放多租户后重评。
- **AI 生成 icon/自动作图**（GPT，E1）：存量 5 个插件已有人工图，真实缺口只有 sdlc-workflow 一个（E2 recon）。替代：补一张人工图或用首字母占位。复审条件：无图资产数上几十再评自动化。

### 差异化（为什么我们能、他们不能）

- **视觉资产进市场**：marketplace.json 与 SKILL.md 规范都没有 imagery 字段（E2，文档 0 命中）——他们改规范要过生态兼容，我们只管自己的仓库；且 icon.png/background.png 本地约定与迁移 049 的 logo/background 列已就位（E2 recon），边际成本低。
- **四类资产同货架**：Claude marketplace 只有 plugin；Dify 按 plugin_type 分站点；GPT 只有 GPT。我们把 skill/command/agent/plugin 放进一个市场维度（capability_assets.asset_type）是他们都没有的形态（E2 对照 + E2 recon）。
- **治理面与货架同后台**：Claude 连 admin UI 都没有（纯 CLI，E2 文档全是命令）；GPT/Dify 商店与构建器分离。我们的 admin 同时承载治理（上下架/扫描/导入）与消费（货架），内部平台天然成立——但这也意味着「扫描毁库」直接打到消费面，非破坏语义比他们更刚性。

## 我们已有、他们没有

| 项 | 说明 | 是否强化 |
|---|---|---|
| content_hash 增量 upsert（md+图 sha256，E2 recon） | Claude 走 git 全量拉取，无资产级 hash 增量 | 是——「最新」排序与幂等重扫的地基 |
| 启动自动同步（ctl.py cmd_start，失败不阻断，E2 recon） | 内部平台特有便利，外部市场无此入口 | 是——修扫描 bug 后它成为唯一写入通道的候选 |
| 媒体端点带路径校验与闸门（get_media_path + POWER_MARKET.ENABLED，E2 recon） | CLI 产品不需要，web 平台必须有 | 是——上线前保持默认关闸的策略由 operator 定 |
| 7-tab 治理表格（E2 recon） | Claude 无任何 admin UI | 是——保留表格治理，叠加卡片/详情消费面，不二选一 |

## 观察到的他们的问题

| 问题 | 来源 | 我们的机会 |
|---|---|---|
| Claude 纯 CLI，无浏览界面（文档全是命令） | E2 文档 | 我们的 web 市场本身就是补这个位——内部操作者不是 CLI 熟手 |
| Dify 无「最新」排序（实站仅 Trending/Featured，E2） | E2 实站 | 我们要的「最新」有 content_hash/updated_at 支撑，是可超的车 |
| （E1 观察）GPT Store 上架审核与拒审摩擦 | E1 未核，不作为依据 | 内部市场上下架即时、无审核流——先天优势，别自己加审核 |

## 来源与核验记录（2026-09-15）

- E2 已核：code.claude.com/docs/en/plugin-marketplaces（icon 0 命中；"To refresh a marketplace without losing installed plugins, use claude plugin marketplace update"；renames/remove 语义；category/tags/relevance 字段）；code.claude.com/docs/en/skills（frontmatter 字段；icon|image 0 命中）；docs.dify.ai/plugins/marketplace（Marketplace/GitHub Repository/Local File；plugin type 决策指南）；marketplace.dify.ai（Trending/Featured/installs 计数实文）。
- E1 未核：help.openai.com 403（GPT Store）；coze.com 页面 JS 渲染无法提取（Coze）——两者不作为结论依据，仅 GPT 作 UI 参照。
- 现状 E2：recon.md 结论 A（扫描清空机制）/B（导入现状）/C（WIP 完成度），file:line 可核。
