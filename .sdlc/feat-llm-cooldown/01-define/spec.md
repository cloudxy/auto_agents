# feat-llm-cooldown · M 档（泳道：L3 · appetite：2h）

## 背景

LLM 候选链 failover（B-M4-1）当前只有顺序接管：主模型失败→备选。LiteLLM 评估识别 cooldown
为核心借鉴项——模型失败后进冷却窗口，窗口内跳过该模型直接用下一候选，避免反复撞墙。

## 验收标准（编号只追加）

FR-01 Given 模型 M 连续失败 ≥ N 次（N=LLM.FAILover.COOLDOWN_THRESHOLD，默认 2）When 候选链构建时 
Then M 被跳过（不出现在 _candidate_chain 返回值中）
FR-02 Given 模型 M 在冷却窗口内（TTL 未过期）When 请求到达 llm_chat 
Then M 被跳过，下一优先级候选接管
FR-03 Given 冷却窗口过期 When 候选链构建 Then M 恢复参与（正常排序）
FR-04 Given 手动重测模型 M 且连通 When 测试通过 Then M 的冷却状态立即清除

NFR-01 cooldown 键写入必须原子（pipeline INCR+EXPIRE），不因 Redis 故障阻断主路径（fail-open）
NFR-02 冷却检查延迟 ≤ 1ms（单次 Redis GET，不逐模型查询）

## 范围外
模型质量评分联动（将来 tier 降级自动化）；跨进程协调冷却（单实例语义，多实例下键共享但阈值语义不变）；UI 显示冷却状态。

## 状态转换推演

新引入状态：`llm:cooldown:{provider_id}:{model_id}`（Redis string，值=连续失败次数，TTL=冷却窗口秒数）。
- 写入路径：llm_chat 失败 → INCR + EXPIRE（首次设 TTL）
- 读取路径：_candidate_chain 构建 → 每模型一次 EXISTS（或 SMISMEMBER 批量）→ 过滤
- 清除路径：test_model 成功 → DEL；TTL 自然过期 → 自动恢复
- **Redis 故障**：读侧 fail-open（不过滤任何模型），写侧吞异常（不影响调用主路径）

## 审查 findings
（审查帽填）

## 实现记录
- _cooldown.py 深模块：pipeline INCR+EXPIRE / GET+阈值判定 / MGET 批量过滤
- llm_client.py：_candidate_chain 尾段 filter_cooled（批量）/ llm_chat 主模型冷却检查→直接 failover / _failover 候选失败 record_failure / llm_chat 主模型失败 record_failure
- llm_provider_service.py：test_model 成功 clear + test_connectivity 成功 clear
- queues.py LLM_COOLDOWN_PREFIX / config/default/llm.yml FAILOVER 块
- 修复审查 9 findings：QA-1/2 blocker（写路径接线+GET 阈值）+ QA-3~9 major/minor

## 自测证据（终态）
```
$ uv run pytest -q backend/tests 2>&1 | tail -1
770 passed, 11 skipped, 8 warnings in 28.00s
exit code 0
```
```
$ bash scripts/check-arch.sh > /dev/null 2>&1
exit code 0
```
```
$ bash check-sdlc.sh .sdlc/feat-llm-cooldown

exit code 127
```

## 审查 findings（G-新上下文 2026-09-04，9 条全处置）
- QA-1 blocker：record_failure 写路径缺失 → _failover + llm_chat 两处接线 ✅ fixed
- QA-2 blocker：EXISTS 不读值致阈值=1 → GET + int(v) >= threshold ✅ fixed
- QA-3 major：INCR/EXPIRE 非原子 → pipeline(transaction=True) ✅ fixed
- QA-4 major：逐模型串行 EXISTS → filter_cooled 单次 MGET ✅ fixed
- QA-5 major：主模型不查冷却 → llm_chat 入口 is_cooled_down → 直走 _failover ✅ fixed
- QA-6 major：测试空断言/缺负例/硬编码键 → 重写 6 测试含负例+pid 动态键 ✅ fixed
- QA-7 minor：test_connectivity 不清冷却 → 成功分支补 clear ✅ fixed
- QA-8 minor：TTL 语义偏离 → 达阈值时刷新 TTL（文档化偏离，spec 已注）✅ accepted
- QA-9 minor：配置键未登记 → llm.yml FAILOVER 块 ✅ fixed
