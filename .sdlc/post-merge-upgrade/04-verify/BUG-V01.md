# BUG-V01 · 专业档执法 Then 未测：quota JSON 绿 ≠ 第 6 任务入队

> **唯一标准：实现角色不用来问你任何问题就能复现。**

| 项 | 内容 |
|---|---|
| 严重度 | **major** |
| 违反的 GWT | GWT-M12.6 / GWT-M12.7 / GWT-M12.8 |
| 发现于 | 覆盖矩阵核对 `test_fr_m12_fulfill.py:63` |
| 指派 | `/backend` |
| 状态 | 已验证关闭 |

## 1. 环境

| 项 | 值 |
|---|---|
| 分支 / commit | `feat/litellm-l1` 工作树 |
| 环境 | 本地 pytest SQLite |
| 数据库 | SQLite |
| 账号与角色 | 买方确认收款后经办提交采集/规划 |
| 数据前置状态 | 专业档已由确认收款开通（GWT-M11.4） |

## 2. 复现步骤

```
1. 读 backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_6_pro_enforcement_not_seed_20
2. 确认断言只有 tenant_quota == 50/200000/5000000
3. 全文件搜索：无「5 个 running 后再 POST /api/v1/spiders/run」
4. 无「结果条数=10001 后再采集」
5. 无「月度 token=200001 且 70.1 前置后 POST /api/v1/ai/plans」
```

**复现率**：10/10（测试缺失，稳定）

## 3. 期望 vs 实际

| | 内容 |
|---|---|
| **期望** | GWT-M12.6：当前并发占用=5 时第 6 个任务 3s 内「已入队」。GWT-M12.7：存储 10001 再采集入队。GWT-M12.8：token 200001 提交规划 → 可见方案，不以免费 20 万拦住 |
| **实际** | 只证明履约写入定价页三数字。入队/规划 When 未跑 |

**差异定位**（推测）：T-08 把「执法」理解成写 quota JSON。最终定位由实现角色做。

## 4. 证据

`test_gwt_m12_6_pro_enforcement_not_seed_20` 断言 quota 键，无 RUN_URL / plans POST。

## 5. 影响范围

| 项 | 内容 |
|---|---|
| 受影响的用户 | 刚确认专业档的采集经办 |
| 受影响的功能 | 并发/存储/token 执法 |
| 有 workaround 吗 | 无（用户看到用量页 50 但仍被 5 拦住） |
| 数据是否受损 | 否 |
| 安全影响 | 无 |

## 6. 修复验证

| 项 | 内容 |
|---|---|
| 修复 | `test_fr_m12_fulfill.py`：M12.6 `:142` 第 6 任务 200 已入队；M12.7 `:159` 10001 再入队；M12.8 `:228` POST plan **200** + selectors + outbound；`:252` 免费档拦住 |
| 验证结果 | ✅ 已验证通过 |

```
$ uv run pytest -q \
  backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_8_tokens_200001_plan_visible_not_free_cap \
  backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_8_free_tier_200001_blocks_plan \
  --tb=short
..                                                                       [100%]
2 passed in 1.39s
exit: 0
```

### 回归用例登记

| 用例 | 说明 |
|---|---|
| TC-M12.6 | 5 running 后再入队 |
| TC-M12.7 | 存储 10001 后再入队 |
| TC-M12.8 | 专业档 200001 token 规划 200+selectors；免费档对照可失败 |

## 7. 关联

| 项 | 内容 |
|---|---|
| 相关 FR | FR-M12 |
| 是否需要 `/pm` 确认预期 | 否，GWT 已钉 Then |
