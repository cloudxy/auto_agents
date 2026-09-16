# designer 记忆 · feat-agents-market

- 交付：`02-shape/edge-states.md` **v1.1**（QA-10 增补；check-sdlc --hat designer exit=0）。修订记录在 §14——后续返工先加行再动正文。
- §7.7 失源清理弹窗（T-15）：打开即 dry_run 取 {n}（QA-9 口径）；确认句「将下线 {n} 个无磁盘来源的资产」是 contract T-15 组件测试断言句（逐字，勿改）；成功 toast 对账三元组 下线{n}/存活{live_total}/磁盘{disk_total}；失败可重试不自动重试；F-7 超行拆 PruneConfirmModal ≤150。
- 钉句索引在 §10，GWT 逐字句：暂无该类资产 / 未识别到可导入资产 / 单次最多导入500个文件… / 暂无正文 / 市场暂未开放，开放后可订阅。改句必须回 spec 走变更，不通知 qa 会挂 GWT。
- 裁定（我 owns）：①卡片订阅按钮移除，CTA 收敛抽屉——T-08 别照抄旧 ShelfCard；②「最热」降级=静默（断言走 sort_applied）；③占位 8 组渐变最浅端白字 ≥3:1（gold/lime 剔除）；④「已订阅 N 次」n≥1 才显示。组件预算 §1.2 最大 380 行（AssetDetailDrawer）。
- OQ-D1：contract v1.1 AD-5c 已裁定豁免 listed 过滤——edge-states §5.4/§12 仍写「默认期望」，下次修订顺手同步（本次限 QA-10 最小增补未动）。OQ-D4 tokens 未独立文件——归 manager。
- 坑：TenantShelf 现状切 tab 会整屏变骨架（React Query 无 keepPreviousData）——§4.1 已钉「保旧卡+进度条」为实现契约。
