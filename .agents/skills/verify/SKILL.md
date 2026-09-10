---
name: verify
description: >-
  Runs the repo build/test/curl commands for the changed paths and pastes
  output. Use when 声称已完成, 交付自检, 提交前, PR, or 跑测试.
---

# 交付自检

命令矩阵：[references/verify-commands.md](references/verify-commands.md)。

## Route

| 观察到 | 先做 |
|--------|------|
| 只要扫架构红线 | `check-arch` |
| 声称「已完成 / 测过了 / 可以提交」 | 本 skill（含 arch.sh） |

## Quick start

Copy and check off:

```
Verify:
- [ ] git status --short 与 git diff --stat HEAD
- [ ] 按矩阵跑对应命令（可并行）
- [ ] 贴 stdout/stderr 最后 20–50 行
- [ ] 任一条非 0：修完再跑同一条
- [ ] bash tools/check/arch.sh 退出码 0
- [ ] 改了 frontend UI/路由/状态：按真实路径点一遍（不只截一张图）
```

启停：`uv run python run.py start <服务>`（已运行会跳过）。生成类 skill 再核产出物（见矩阵）。输出不能支撑声称时，不要写「已完成」。

无浏览器工具时：用测试 / curl / 构建日志代替，并写明哪条用户路径没点到。

## 完成时回复

```
=== git status --short ===
...

=== <矩阵命令> ===
<末段 20–50 行，含退出码含义>

=== bash tools/check/arch.sh ===
✓ 架构合规检查通过（13 红线 + 3 边界，全部通过）
```

## Examples

**Input:** 改了 `backend/services/user_service.py`，准备说测试过了。

**Output:**

```
=== uv run pytest -x -q backend/tests ===
========= 42 passed in 3.1s =========

=== bash tools/check/arch.sh ===
✓ 架构合规检查通过（13 红线 + 3 边界，全部通过）
```
