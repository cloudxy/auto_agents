# backend memory · feat-product-complete

> Facts this role learned (**what**). Cap 2200 chars.

## Last

- Date: 2026-09-11
- Hat: sdlc-workflow:backend（T-22 fail-open+查询面收口；此前 T-02…T-42 共 15 票）
- Outputs: `03-impl/T-{02,05,07,08,09,14,22,24,26,27,35,37,38,39,41,42}-evidence.md`

## Facts

- T-22 done：七上报点 fail-open 审查，六点既有合格；**一处缺陷修复**：relay `refresh_tokens_usage` emit 在 commit 后 refresh 前读过期属性 → 生产 `expire_on_commit=True` 抛 MissingGreenlet，**抛点在 emit_product_event 吞异常圈外**（参数求值先于调用）→ 主路径 500+事件必丢。修法=`_usage_snapshot`（commit 前纯值 dict）+`_emit_usage_event(snap)`，get_token/refresh 两调用面同口径。
- 坑（重要盲区）：conftest `db_session` 工厂显式 `expire_on_commit=False`，生产 `platform_core/db.py:158` 为默认 True——凡「commit 后读 ORM 属性」缺陷测试面天然盲区。复现法：`AsyncSession(db_engine)` 不传 kwarg（生产形态）驱动整链。
- 92.7「404 同形」口径=统一异常处理器信封（code HTTP_404/message "Not Found"）；对照 oracle 用另一个 `require_platform_admin_or_404` 面（GET /api/v1/admin/tenants）。**不是** Starlette 裸默认（`{"detail"}`，不经统一处理器）。GET /api/v1/admin/users 不在 404 守卫后（require_admin 放租户 owner 进）。
- 坑：本仓 feature 工作树**全部票未提交**——`git stash push <file>` 会把前序票未提交工作一并回退（曾致 ImportError）；演示红用 Edit 手工回改，禁 stash。
- 基线 **1546/38**（T-22 后，+8 测：七点注入+生产 expire 回归+92.7 同形）。
- 坑：类名 relay=`RelayService`；跨测试文件复用 fixture/helper 直接 `from backend.tests.test_xxx import`（pytest 按模块命名空间解析）。
- 坑：MagicMock(name=...) 是 repr 保留字——属性桩用 SimpleNamespace。registry service import ai_planner 必须函数级局部（顶层撞 import 环）。跨租户越权测试 make_tenant_owner_headers(slug=…) 双租户真 JWT。钉改写先例：守卫/口径随 GWT 变时旧钉同 PR 改。async 测试禁 run_until_complete 嵌套；grep=ugrep 用 --include；权威=arch.sh；R10 辅助函数 `_` 前缀；MYSQL_FIDELITY 本 shell 无 root 口令。

## Open (mine)

- None.

## Do not re-litigate

- Online capture (Q-BILL empty)。Billing/relay schema expand-only；T-01 释放占位键不可回退；`_apply_plan` 骨架不写 Then 不删。出站域禁 import relay/llm_gateway。GWT-51.5/51.9 单支。GWT-60.1 after Q-RELAY。member 释放语义不改。不代选 Q-VOICE/Q-PRICE/Q-MARKET-USER/Q-AGPL/Q-C-REG。sk- 守卫只作用第一环。种子谓词三支口径（T-13）。60.6 写面 403。企业改名冲突域=精确匹配。平台租户种子行缺失=fail loud。专家团无执行引擎。方案名称/类型不可改；定义删除=既有硬删口径。QA-40 无「来源分组」幽灵交付物；空表回填种子语义已废（T-41）。queue_depth 评估口径=规则所属租户 pending 数；Q-QUEUE-DEPTH 已决接通不回下架。T-22 事件名字面量/WACT/PC-3(=已确认) 不可改；七点 fail-open 注入统一打 `_persist_event`。
