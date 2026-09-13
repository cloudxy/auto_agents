# qa memory · feat-product-complete

> Facts (**what**). How stays in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-12
- Hat: verify
- Outputs: `04-verify/coverage.md`；`backend/tests/test_t42_fidelity_queue_depth.py`（新增真库保真测试，sqlite 态自动 skip）

## Facts

- 矩阵定盘：153 格 = 活跃 152 + 作废 1（105.2）。151 ✅（43 双半拼合）、⚠️1 = **GWT-103.4**：`FileTab.tsx:266` 渲染「未发现爬虫定义」，spec 冻结句「还没有采集方案。」未落且无测。数据半已由 T-41 兑现。微票归管理窗（<0.5h）。
- IMPL-QA-5 已关：真库轮 1 passed exit 0。命中行 INSERT+字段、静默窗二连、user_id FK 负向探针（1452→IntegrityError）真 MySQL 8 直证。
- **真库口令坑**：config/local/.env 的 AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD 带**引号**，须剥引号再用；用户 `auto_agents` 无 CREATE DATABASE（1044），fidelity 须 `MYSQL_FIDELITY_USER=root`（root 同密码可登）。
- check-sdlc MATRIX 规则：spec 里出现的每个 `FR-nn` 字面都必须在 coverage.md 出现（含 v2 对照 FR）。解法=§1.0 FR 索引表（50 行，v2 已兑行写豁免+保持点）。终态仅 6 条 OPENQOPEN 红（六开放问，packet 定为已记录豁免）。
- 豁免三处有据：60.6 写面 403（IMPL-QA-1）、93.6 列表面 200（IMPL-QA-3）、105.2 作废。90.1 写者=平台超管已核落（Settings.tsx:33 canWriteSettings=is_platform_admin）。
- deferred-live 七项：NFR-01 P95（Playwright 计时，≥50 样本）、60.3/92.4 真网关轮、51.10/60.5 真网关面、98.4 真探针引擎、102.1/102.2 真队列环、全量 fidelity 轮、WACT/PC 四周窗。命令模板在 coverage §3/§5.B。
- 后续票账本：T-32 三降级端点（IMPL-QA-4）；IM-02/03/12/13/18/26、C35-QA-05 仍开。

## Open (mine)

- GWT-103.4 微票是否随 review 批次收口——管理窗决定。
- 全量 fidelity 轮未跑（本轮只 T-42 定向）；交付清单已带 root 权限注记。

## Do not re-litigate

- define 期 12 格 ➖ stub 账已过时（T-42/billing 已落）；以 coverage.md §1 为准。
- OPENQOPEN 6 红 = 预期豁免，非 verify 缺口。
