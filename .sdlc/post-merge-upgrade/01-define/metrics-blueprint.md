# 度量蓝图 · 合入后四角色完备（post-merge-upgrade）

> 泳道：L3｜作者：pm 帽｜日期：2026-09-13｜对应 `spec.md` v1.7（§6 不另给表）
> **本文件是 analyst 复盘的唯一口径。** spec §6 只保留指针。北极星/驱动/护栏以本文为准。冲突以本文为准。
> 前合同：upgrade 蓝图的非夹具合格出数 **仍是** 出数口径来源（FR-U03）。**本特征北极星**按 briefing 赌注保持该口径，**不是**把支付成功、订阅成功或「四角色都点过」升成北极星。
> 约束：ops **0 工单**、无生产 n、Reach **未量化**。禁止写转化率提升百分比。禁止标 falsify 通过。禁止标四柱 GA。本轮成功 = 能判定。
> 数仓分层 / 离线模型：**实现面 N/A**。四周数字从产品事实查询面出。

---

## 1. 判定纪律

| 项 | 规则 |
|---|---|
| 判定周期 | 所在波对用户可用之后 **4 个上海自然周**；中途不下成败 |
| 基线 | 无。第一轮目标就是建立基线 |
| 时区 | **Asia/Shanghai 业务日**；指标用 **事件发生时间**（不是入库记录时间） |
| 分流 | 无 A/B。市场总开关与 LLM/规划开关是发布控制。分流单位若将来做实验 = **企业** |
| 排除 | 市场候选不得计入北极星。内部测试企业 `is_internal_fixture=true` 不得计入北极星。平台租户（产品名）事件不计入北极星与 D1 |
| 验收 | 以事件可查为准。不得用官网 Hero 数字、后台任务总数、pytest 条数、本机 4 行租户冒充北极星 |
| 禁止当 OEC | Hero 静态数字、全历史成功率、listed 资产数、扫描成功次数、HMAC 夹具支付、超管确认收款当 live 指纹 |
| Q-VOICE | **已答采集**。禁止双北极星。支付/结账只进驱动 |

Hero 示意大数 **禁止当基线**。

---

## 2. 北极星（唯一）

| 字段 | 内容 |
|---|---|
| 名称 | 非夹具租户合格出数（企业去重） |
| 口径 | 一个判定窗内，至少发生 1 次核心动作的 **非夹具企业** 去重数 |
| 核心动作 | `task_completed` 且 `result_count>0` 且 `is_marketplace_candidate=false` 且 `is_internal_fixture=false` |
| 来源 | 事件 `task_completed`（FR-U03：`tenant_id`、`result_count`、两布尔）。本特征不改该口径 |
| 时间窗 | 上海周一 00:00 至周日 24:00，事件发生时间；四周复盘把四周每周都报出 |
| 目标值 | 建立基线。四周结束必须能报「这四周每周该数=？」；报不出 = FR-U03 失败。不设提升百分比 |

选这个：briefing 赌注 + Q-VOICE=采集。经办价值是本企业表里有条。结账走到已开通是套餐出口，离第一次交差更远，只进驱动。

混淆：该数=0 可能是没人来 / 没登录 / **工人未运行** / 配额拦住 / **规划未开放却只走规划叶**。用 D3 + `llm_planning_blocked` 拆开，不得把工人空洞或规划关闭解释成「没人要采集」。

upgrade / v2 WACT **不是** 本蓝图北极星。不要并列两个北极星。

---

## 3. 驱动指标（4 个）

结账故事在本层。**不抢北极星。** live 沙箱成功 **不是** 本特征北极星，也不是 W2 放行条件。

### D1 单一结账走到待支付或已开通（企业去重）

| 字段 | 内容 |
|---|---|
| 口径 | 分子：一周内至少一次 `order_status_reached` 且 `status` 为 `pending` 或 `fulfilled` 的非夹具企业去重。分母：无（报去重企业数，不报转化率——Reach 未量化） |
| 来源 | FR-M14；`order_status_reached` 字段 `tenant_id`、`product`（`plan_pro` / `plan_enterprise` / `relay`）、`status`=`pending`\|`fulfilled`（与 spec §0.4.1 同一枚举；本波不上报 `fulfilling` / `unpaid`） |
| 时间窗 | 上海自然周，事件发生时间 |
| 目标 | W2 对用户可用后建基线。W2 放行看「能否判定」，不看 live 通道是否弹出 |
| 诊断 | 北极星>0 且 D1=0 → 采集赌注可活、结账未发生（允许）。D1>0 且北极星=0 → 买方下了单但经办未交差。`status=pending` 有、`fulfilled` 无 → 超管尚未确认收款（W2 合法开通路径） |

### D2 第二套结账故事次数

| 字段 | 内容 |
|---|---|
| 口径 | 一周内 `second_checkout_story_submitted` 次数（成功产生第二套单据才计） |
| 来源 | FR-M14 |
| 时间窗 | 上海自然周，事件发生时间 |
| 目标 | **0**。非 0 = FR-M10 失败，不是「用户喜欢两个入口」 |
| 诊断 | 旧用量页订购入口仍可提交 |

### D3 空租户首次提交拦住率

| 字段 | 内容 |
|---|---|
| 口径 | 分子：非夹具企业 **第一次**提交采集被工人不在线或配额已尽拦住的企业数。分母：非夹具企业第一次提交采集的企业数 |
| 来源 | FR-U03 GWT-U03.4 / U03.5；提交侧 `task_run_submitted`。规划未开放另计 `llm_planning_blocked`（FR-M06），**不得**并进本分子（那不是采集提交拦住） |
| 时间窗 | 每企从首次提交起算；周报按事件发生时间归周 |
| 目标 | 建基线 |
| 诊断 | 分母有、北极星=0、D3 高 → 工人/配额。`llm_planning_blocked` 高、采集提交分母=0 → 经办只撞了规划叶（FR-M01 / FR-M03 是否被看见） |

### D4 订一行企业数

| 字段 | 内容 |
|---|---|
| 口径 | 一周内至少一次 `market_subscribe_succeeded` 的非夹具企业去重 |
| 来源 | FR-U14（事件名沿用 v2 `market_subscribe_succeeded`） |
| 时间窗 | 上海自然周，事件发生时间 |
| 目标 | 市场总开关打开后建基线。开关关闭时该数必须为 0，**不得**解释成「没人要订」 |
| 诊断 | 列表浏览有、订阅 0：查开关、预告占比、只读角色、许可闸、是否走进了治理七叶（FR-M40） |

upgrade 蓝图 D1「非夹具成功支付企业数」本特征 **降为诊断、不进本 4 驱动**：W2 不要求 live 沙箱；live `payment_succeeded`（FR-U38 验真）在指纹出现之前不得当增长指标。出现后可在复盘附录报，仍不得升北极星。

---

## 4. 护栏指标

| 指标 | 口径 | 红线 | 来源 | 超线 |
|---|---|---|---|---|
| 跨租户可见事故 | 经复现：企业 A 读到 B 的任务/结果/安装/令牌/支付单据/成员 | **0** | 越权审计 + 手工复现 | 停发布 |
| 商户/上游密钥泄漏 | git 跟踪文件、默认配置、租户浏览器响应出现密钥全文 | **0** | FR-U31；NFR-M04 | 停发布；轮换密钥 |
| 「当前可买」文案 | **所有访客可见面与所有租户可见面**出现这四字 | **0**（直至 live 支付通道指纹） | FR-M50 / FR-M15 | 撤回文案；不得宣称可买 |
| 第二套结账故事 | D2 > 0 | **0** | FR-M14 | 视为 W2 未完成 |
| 非超管平台写成功 | 上架 / 扫描 / 平台渠道 / 商户凭据 / 平台 RBAC / 总开关 / 值班联系 被非超管做成 | **0** | 审计 | 视为本波未完成 |
| 配额文案泄漏内部码 | 用户可见含 `QUOTA_EXCEEDED` 或裸 `429` | 抽检 **0** | FR-U02 / FR-87 / FR-M01 | 不作为增长手段上线 |
| 404 同形被道歉 403 替换 | 租户直打值班或平台 RBAC/运营台/用户管理出现渠道列表、密钥或「抱歉您没有权限」 | **0** | FR-M30 / M31 / M32 / FR-U15 | 停发布 |
| 出站错平面拉到行 | 渠道组令牌或未在出站入口签发的凭证拉到 `result_count>0` | **0** | FR-M20 / FR-M26 | 停发布 |
| 值班入口数（用户可见） | 超管导航值班类叶子 | **=1** | FR-M30 | 未完成 W4 |
| 规划未开放却产生方案 | `llm_planning_blocked` 应发生的窗口内出现由该次规划入队的任务 | **0** | FR-M01 / FR-M06 | 未完成 W1 |

探针「伪装」次数不是北极星，无红线（不自动关渠道）。

---

## 5. 埋点契约

字段最低集：`occurred_at`、已登录则 `tenant_id`/`user_id`/`role`。切日：存 UTC、报表日 Asia/Shanghai。失败上报不挡主路径。查询面 **仅平台超管**。租户无查询面（GWT-U03.3 同一句）。

继续用的事件：`task_run_submitted`、`task_completed`（含 `is_internal_fixture`）、`quota_exceeded`（内部事件名可留；**用户可见文案**仍禁该码）、`market_subscribe_succeeded`、`market_subscribe_rejected`、`payment_succeeded` / `payment_failed`（FR-U37；live 另波）、`outbound_key_issued`、`offline_order_confirmed`（若超管确认仍用该名，必须能关联到 **同一** 结账单据，不得表示第二套故事）。

本特征必须可查的增量：

| 事件 | 何时 | 关键字段 | 对应 FR | 查询面 GWT |
|---|---|---|---|---|
| `llm_planning_blocked` | 智能规划未开放时提交规划被拦住 | `tenant_id`、`reason=disabled` | FR-M06 | GWT-M06.1 |
| `data_export_completed` | 数据中心导出 CSV/JSON 成功 | `tenant_id`、`file_format`=`csv`\|`json`、`row_count` | FR-M06 | GWT-M06.2 |
| `checkout_story_started` | 买方进入结账页 | `tenant_id`、`product`、`surface` **钉死** `checkout`；来源页 `referrer_surface`=`pricing`\|`usage`\|`nav` | FR-M14 | GWT-M14.1 |
| `order_status_reached` | 租户可见变为待支付或已开通 | `tenant_id`、`product`、`status`=`pending`\|`fulfilled`（W2 不上报 `unpaid` / `fulfilling`） | FR-M14 | GWT-M14.1 / M14.2 |
| `second_checkout_story_submitted` | 旧用量页订购入口成功产生第二套单据 | `tenant_id` | FR-M14 | GWT-M14.3（目标 0 次） |
| `outbound_wrong_plane_rejected` | 错平面凭证拉数被拒 | `tenant_id`；**不含明文** | FR-M26 | GWT-M26.1 |
| `duty_entry_opened` | 超管打开唯一值班入口 | `user_id`；不含密钥 | FR-M35 | GWT-M35.1 |

通知类型字符串 **禁止**当本蓝图事件。HMAC / `signed_body` 夹具 **禁止**计入 live `payment_succeeded` 指纹。

---

## 6. 缺口盘点

| 指标 | 需要 | 现有 | 状态 | 处理 |
|---|---|---|---|---|
| 北极星 | `task_completed` + 两布尔 + `result_count` | upgrade FR-U03 | ✅ 有合同 | 对照验收，不重开口径 |
| D3 拦住 | 拦住 vs 完成可区分 | FR-U03.4 / .5 | ✅ 有合同 | 规划拦住另事件，不并进 D3 |
| D1 结账故事 | `checkout_story_started` / `order_status_reached` | 无（双轨两套状态词） | ❌ 缺 | **写进 FR-M14** |
| D2 第二套故事 | `second_checkout_story_submitted` | 无 | ❌ 缺 | **写进 FR-M14**；目标 0 |
| 规划未开放 | `llm_planning_blocked` | 无 | ❌ 缺 | **写进 FR-M06** |
| 数据中心导出 | `data_export_completed` | 无 | ❌ 缺 | **写进 FR-M06** |
| 错平面拉数 | `outbound_wrong_plane_rejected` | 无 | ❌ 缺 | **写进 FR-M26** |
| 值班入口 | `duty_entry_opened` | 无 | ❌ 缺 | **写进 FR-M35** |
| D4 订一行 | `market_subscribe_succeeded` | FR-U14 | ✅ 有合同 | 开关关闭时该数必须为 0 |
| live 支付指纹 | 非夹具、非 HMAC 的 `payment_succeeded` | FR-U37/U38 | ⚠️ 另波 | 指纹前不得当增长；不得印四字 |
| Reach / UV / 工单 | 生产 n | **没有** | ⚠️ 不可测 | 不打 RICE 分；不标市场 pass；不补问卷（briefing） |

---

## 7. 判定周期与基线

**判定周期**：所在波对用户可用之后 4 个上海自然周；中途不下结论。  
**基线**：无。本轮目标=建立基线。报不出周数 = 对应埋点 FR 失败。  
**W2 放行 ≠ 复盘成功**：W2 代码放行看 FR-M10 + GWT-M11.1…M11.6 + GWT-M11.8 + GWT-M11.12 + GWT-M11.14…M11.17 + FR-M12（含 GWT-M12.6 / M12.8 执法）+ FR-M13 + FR-M14 + FR-M15；四周复盘才报 D1。live 收银台不在 W2 放行，也不在北极星。租户可见状态闭集本波仅「待支付」「已开通」。同一商品再提交租户句只「已有待支付」。
