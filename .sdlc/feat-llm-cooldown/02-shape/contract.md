# feat-llm-cooldown · 契约

## Redis 键设计

键：`llm:cooldown:{provider_id}:{model_id}`（string，值=连续失败次数 int）
TTL：`LLM.FAILOVER.COOLDOWN_SECONDS`（默认 300 = 5 分钟）
阈值：`LLM.FAILOVER.COOLDOWN_THRESHOLD`（默认 2 次）

## 模块边界

```
platform_core/queues.py          ← 新增 LLM_COOLDOWN_PREFIX（契约登记）
backend/services/ai_planner/_cooldown.py  ← 深模块：record_failure / is_cooled_down / clear
backend/services/ai_planner/llm_client.py ← 消费：_candidate_chain 过滤 + 失败时 record_failure
backend/services/llm_probe_engine.py      ← 消费：test_model 成功时 clear
```

依赖方向：_cooldown.py → platform_core（redis_async/queues）；llm_client → _cooldown（单向）；probe_engine → _cooldown（单向）。

## rabbit holes
- 不做滑动窗口精细计数（INCR+固定 TTL 足够，LiteLLM 也是这个粒度）
- 不做冷却原因记录（错误分类是另一个 feature）

## 红线自检
- ✅ 键前缀入 queues.py 契约
- ✅ Redis 故障 fail-open（读侧不过滤、写侧吞异常）
- ✅ 不动 ORM（纯 Redis 层）
