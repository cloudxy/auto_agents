# data-collector memory · feat-four-pillars-v2

> Facts (**what**). Cap 2200 chars. Frozen snapshot.

## Last

- Date: 2026-09-08
- Hat: define / diagnosis
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/data-collector.md`

## Facts

- 09-08 复核：裂缝与 09-07 旧诊断代码面一致。B2 仍成立。
- 真出数=否。本机另开 Worker 对 httpbin/`example` 能刮 Item。回流 `tenant_id=msg.get(...)` 恒 None；`_flush_batch` 已 load task 却不用 `task.tenant_id`。MySQL 017 NOT NULL 拒写；SQLite NULL 对租户不可见。
- 门面 enqueue 不转发 tenant。调度/模板/AI 试采丢租户。仅 `POST /spiders/run` 任务行有租户。
- IdleAutoClose 默认 0；有产出才收尾。0 条永不 finished（6h stale）。compose/`run.py all` 无 Worker。入队不读心跳。
- harvester：GitHub 目录名，`source=marketplace`，content 空。`item.extra` 被 consumer 再包一层，候选 Tab kind/repo 空。测试种子扁平。
- generic/flow 不继承基类 → 无站点 delay。prod delay 0.5。robots 关。无 0-item×3 告警。
- 旧 T-05/T-07 清单无 `consumer.py`。ADR-0013 v2：结果行禁止 NULL；占位租户 + source 过滤；不改 harvester 出口。
- WACT=completed∧result_count>0。旧方案 Wave 4 stub FR-70…72 与此互斥。最小出数环必须实现波。

## Open (mine)

源=站点目录还是 URL 袋？harvester 白名单？Worker 常驻 vs idle-close？GitHub token 配置位？热搜 site 废/待建？0-item×3 窗口？crawl 插件包应走 C？无 Worker 硬拒还是排队？出数环与 Wave 0 同波还是薄波？占位租户 slug=dba。

## Do not re-litigate

Scrapy 租户盲；Item 不加 tenant_id。不改 harvester 出口、不直写主库。不放宽 017。C 路径不是爬虫。不新建候选表。登录墙/验证码/代理网/模板店不当 Wave 0 卖点。
