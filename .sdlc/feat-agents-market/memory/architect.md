# architect 记忆 · feat-agents-market

- 交付：02-shape/contract.md **v1.2**（shape r2 返工）。check-sdlc --require --hat shape exit 0。r1 七项 + r2 三项（QA-7R/QA-9/QA-11）全处置；QA-6 归 dba、QA-10 归 designer 并行。
- r2 教训（QA-7R）：**排除谓词必须与入库通道交互推演**——agents_hub.py:148-157 对每个同步 agent 行都建 capability_experts 侧行 →「有侧行」≠遗留判别；hub 行 file_path 恒 `.agents/` 前缀（agents_hub_scan.py:46-54 `_repo_rel` 两路径同前缀；`_agent_item` :226-235 落库），legacy 行落 LIBRARY_ROOT 非 .agents/ 前缀。最终谓词：`asset_type='agent' AND EXISTS(侧行) AND file_path NOT LIKE '.agents/%'`（AD-3；OQ-2 回退同款判别式）。T-03 夹具：legacy 形态行仍 live（负向）+ hub 孤儿被 prune（正向）。
- QA-9：prune 端点 `dry_run=true` 同构预览不落库；T-15 弹窗先 dry_run 取 {n} 再确认执行；取消断言=不发执行（非 dry_run）请求。
- effort 口径：spec.md:3 = 3–5pw（上界 5pw，超 50%=7.5pw 停下重判）；合计 5.75pw 超 0.75pw；回收项 T-11 缩减 / T-09 并入各 ~0.25pw，双落地 5.25pw 仍余 0.25pw 溢出归 manager 批复。**勿再引 5.5pw 基数（无出处，QA-11）**。
- v1.1 存续裁定：预览旁路双豁免（闸 service.py:237 + listed :241，只豁 listing_state 分量，黑名单/seed/license/deleted 仍拦）；hot=COALESCE(cnt,0) DESC；GWT-03.7/03.8→T-04、03.6→T-08；事件锚 product_event_service.py:74；AD-4a 路径清洗（../绝对路径/反斜杠→skipped）；AD-5a _read_skill_md 分流、AD-5b persona_md 投影。
- bug 根因事实：plugin_service.py:75,:150-174（retract 传空集软删全部 source_id IS NULL plugin 行）。
- 行数临界：capabilities.py 458/500、power_market/service.py 495/500 → 新路由进 capabilities_gov.py（挂 api/v1/__init__.py:36 之前）+ 抽 projection.py/sorting.py。
- 开放：OQ-1 .agents 顶层 agents/commands 目录（默认接受）；OQ-2 legacy 切根（默认执行）；OQ-3 team tab（默认保留）。
- 下游注意：golden（openapi_routes_golden.txt）随路由增删同步；**AD 与票表不重复维护断言清单**（r1 谓词漂移源：AD-3 与 T-03 各写一份易失同步）。
