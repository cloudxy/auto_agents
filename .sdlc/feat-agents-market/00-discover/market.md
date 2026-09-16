# Market · feat-agents-market（.agents 资产进能力市场 + 后台管理 + 扫描 bug 修复）

> 作者：researcher 帽｜日期：2026-09-15｜泳道：L3｜下游：discover briefing · pm RICE Reach
> 单位：☑ 租户/买方账号（ToB，消费面）——治理面（平台管理员）是平台自有运营角色，按账号单列，不与租户混计。这是**内部平台表面变更**，不是外部市场进入。

## 可及集合

本变更有两个受益表面，闸前/闸后可及集合不同（闸 = `POWER_MARKET.ENABLED`，默认 **false**，config/default/power_market.yml:3，E2）：

### A. 消费面（租户货架 TenantShelf / official 官网）

| | 数 | 来源 | 等级 |
|---|---|---|---|
| 下界（闸前） | **0** —— 货架与 media 端点同受闸，租户当前完全不可达 | config/default/power_market.yml:3 + public_skills.py 闸门 | E2 |
| 上界（闸后） | 租户数（本地 DB 5 个；生产**未量化**）+ official 公开端点的访客（**未量化**，仓库无埋点/分析证据） | 本地 MySQL `SELECT COUNT(*) FROM tenants`（2026-09-15 快照） | E3（仅本地）/ E1（生产） |
| 未量化 | 是 —— 生产租户数、生产用户数、official 访客量。缺生产 DB / 访问日志 | — | E1 |

### B. 治理面（admin Capabilities：导入 / 扫描 / 上下架 / 治理表格）——不受闸

| | 数 | 来源 | 等级 |
|---|---|---|---|
| 下界 | **1** —— `init_project.sh:127-137` 每次全新安装必建 1 个 admin 账号 | init_project.sh | E2 |
| 上界 | 本地 DB：7 用户（is_admin=1 者 3 人；role=admin 5 / operator 1 / viewer 1）；生产管理员数**未量化** | 本地 MySQL `users` 表分组计数（2026-09-15 快照） | E3（仅本地）/ E1（生产） |
| 未量化 | 是 —— 生产部署的管理员/操作员人数 | — | E1 |

### C. 供给侧（可上架资产，治理与消费两面的「货」）

磁盘盘点（2026-09-15，`find` 计数，E2）：

| 类别 | 数 | 备注 |
|---|---|---|
| 一等 skill（`.agents/skills/`） | 9 | 均无 icon/背景图 |
| 插件（`.agents/plugins/` 符号链接） | 6 | dev-team / drama-skills / mattpocock-skills / oh-story / sdlc-workflow / superpowers；5/6 有 icon+background，**sdlc-workflow 无图** |
| 插件内 bundled skill | 128（40+11+25+13+25+14） | dev-team 与 mattpocock-skills 内容大量重叠（.agents/README.md 明示「已含于 dev-team」），去重后数**未量化** |
| 插件内 bundled command | 5（仅 sdlc-workflow） | |
| 插件内 bundled agent | 18（仅 sdlc-workflow） | |
| 合计资产条目 | 166 | |

本地 DB 快照（2026-09-15，`capability_assets` 计数，E3）：

| | 数 | 说明 |
|---|---|---|
| live 行（deleted_at IS NULL） | **182**（skill 146 / command 18 / agent 18 / **plugin 0**） | 12 条 plugin 行全部软删（deleted_at 置值）——即扫描 bug 的现存足迹：货架当前 **0 张插件卡** |
| 修复后预期 | ≈188（182 + 6 插件行恢复） | 含脏数据：13 条 `oh-story__*` command 行与约 9 条 skill 行在当前 `.agents` 磁盘上无对应源（旧 capability-library/plugins 通道残留，仅 plugin 类型会被 retract，skill/command/agent 永不回收） |

> 结论：供给侧充足（166 条磁盘资产 / 182 条 live 行），消费面闸前可及集合 = 0。本变更的主要即期受益人是治理面（平台管理员）；消费面 Reach 取决于开闸决策，不在本变更内默认发生。

## 渠道偏差

当前证据来自：操作者口述（E1，2026-09-15 需求原话 + 参考图）+ 本地 DB 计数（E3，仅 local 环境）+ 磁盘/代码盘点（E2，file:line 可核）。

听不到谁：生产租户（本地 5 个种子租户不能代表任何真实需求）／official 官网访客（无埋点）／仓库贡献者之外的潜在最终用户／已开闸场景下会沉默浏览不订阅的轻度用户。操作者即平台 owner，其「UI 好用美观」判断不等于租户审美。

本轮补不补：不补。理由：无生产环境访问权、无行为日志可查；DB 计数已给出供给侧硬数，消费面数字留给开闸后的真实行为数据，不以推测填充。

## 现状替代与切换成本

- 治理面现状：Capabilities 页 7-tab 治理表格（CatalogTab / list_assets），能管理但无市场形态；导入向导=多选 .md/.zip 文件或**手输服务器路径字符串**（ImportWizard.tsx:178-216）。
- 消费面现状：货架卡片无 onClick、无详情、（WIP 前）无图；official 有 /skills 列表 + `<pre>` 纯文本详情页（明确禁 HTML）。
- 真正的「现状替代」：**没有市场**——租户侧闸门关闭，能力消费实际不发生；治理侧靠表格 + 手工路径。切换成本低（内部平台，无外部用户迁移/留存风险）；最大切换成本在数据侧：旧通道软删足迹与 22 条左右无源残留行需要清理口径（Q-SCAN-CHANNEL）。

## 频次 / 付费位置

- 治理动作频次：随 `.agents` 资产变更触发（每次改 skill/插件后需重导入/扫描），当前 ctl.py 每次启动已自动同步一次（E2，recon C）；精确频次**未量化**。
- 付费位置：无计费证据。public_skills.py 有 subscribe 端点，但 power_market.yml 仅含 ENABLED 开关，无套餐/价格/配额配置 → 付费位置**未量化/暂不存在**。
- ToC 增长环：不适用（ToB 平台）；official 官网曝光位本轮不扩展（Q-DETAIL-SURFACE 未决）。

## 给 RICE 的 Reach

- 治理面（导入/扫描/上下架/管理）：下界 1（每部署必有管理员）——上界生产未量化（本地 3 名 is_admin 用户）。单位：平台管理员账号，非租户。
- 消费面（市场卡片/详情/订阅）：闸前 **0**；闸后 = 租户数（本地 5，生产未量化）。单位：租户。
- 供给侧影响（bug 修复直接恢复）：插件卡 0 → 6；全货架 live 行 182 → ≈188（清理残留后回落，未量化精确值）。
- 一个客户不是市场：本地 5 个种子租户不构成市场证据；消费面需求强度全部来自操作者 E1，勿在 RICE 中按租户数 × 假设渗透率放大。
