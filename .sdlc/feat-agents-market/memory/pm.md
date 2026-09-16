# pm 记忆 · feat-agents-market

## 决策（我所有）
- spec v1.2（define r2 返工过，NEW-1..NEW-5 全处置）：FR 骨架 8 条不变——01 非破坏单通道｜02 **失源行清理**（改名：首清存量 ~22 条，入口可复用；北极星归零口径=FR-02 显式清理，GWT-01.3 保证同步不软删）｜03 四类卡+tab｜04 排序三档｜05 抽屉+md（XSS P-03）｜06 确定性占位｜07 目录导入｜08 治理埋点。
- **越权 GWT 统一口径（r2 教训，硬约束）**：治理写面非平台管理员一律 **404**（require_platform_admin_or_404 存在性隐藏门面），不走 403 信封；Given 措辞「非平台管理员（租户角色或普通登录用户）」；权限模型 = is_platform_admin 布尔，无运营中间角色，NFR-06 不扩不缩。矩阵只有 平台管理员/非平台管理员/未登录 三行。
- 货架可见集 = listed/coming_soon ∩ 闸与白名单；dev-team 强制 unlisted（manager 裁定）→ 货架 plugin 卡 5、治理目录 6，GWT-01.1 只数治理目录。上下架 oracle 定居 03.6/03.7/03.8；03.6 公开详情子句注明与 03.7 同批（闸开）验收。§3.1 注 coming_soon 既有第三态。低风险默认（Q-OP-RATIFY 可否决）：d 示例区 0–N 空则隐藏；e CTA 闸关=禁用态文案。
- 北极星=资产对账一致率；消费面指标开闸后建基线不进验收（K3）。闸语义单 oracle 在 GWT-03.4。

## 输出路径
- 01-define/spec.md（单文件交付，user-story/metrics 内嵌）。

## 坑（验证过的）
- **写鉴权类 GWT 断言前必读仓库门面现状**（deps.py require_platform_admin_or_404 等）：r1/r2 的 NEW-1 major 就是拿通用 403 直觉套本仓 404 同形门面，按字面必红。权限类断言以 deps.py/capabilities.py 现挂守卫为准。
- check-sdlc OPENQ 陷阱：spec 含「待确认」行会提取 Q-* 要求 state.yaml 记账——用「开放·不阻塞」措辞；Q-OP-RATIFY 已记账可自由引用。
- 无「验收标准」标题则 VAGUE 不触发，仍自 grep 不可测词（v1.2 后 0 命中）。
- check-sdlc --require --hat define 对 v1.2 通过（EXIT=0），返工后无需改 state.yaml。
- 概念改名（如 一次性清理→失源行清理）要全文档扫残留，含 S1 决策表，否则两名字并存。

## 仍开放（我这边）
- Q-OP-RATIFY（S1–S4+a–e）待操作者追认；Q-SCAN-EXPERTS 下一轮无 FR 依赖。
- RICE Effort 占位粗估，architect 拆票复核。
- 后续失源行清理的 GWT（qa/architect 可补，编号 append-only）。
