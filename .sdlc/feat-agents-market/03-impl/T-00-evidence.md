# 实现证据 · T-00 WIP 基底验证

> 票：contract §0 / 票表 T-00｜FR 锚点：WIP 基底（无 FR）｜角色：/backend｜日期：2026-09-15

## 1. 验证目标

WIP 未提交基底（agents_hub 链路 + 049 迁移 + 媒体端点 + 货架渲染 + ctl 同步）必须全绿才算
feature 基底成立；后续任何票不得使这些用例转红。

## 2. 发现并修复的 WIP 缺陷（并入本帽职责）

首轮全量验证发现 2 类 WIP 缺陷（测试红 + 架构红线违规），按票指令「WIP 缺陷修复之」处置：

| # | 缺陷 | 症状 | 修复 |
|---|---|---|---|
| 1 | WIP 给公开投影 `_project` 加了 `logo`/`background` 媒体 href，但两处公开字段白名单测试未同步 | `test_b1c_capabilities_coverage.py::test_public_capabilities_fields_whitelist` 与 `test_skill_public_api.py::test_public_fields_whitelist_enforced` 红（`白名单外字段外泄: {'logo','background'}`） | 两处测试白名单补 `logo`/`background`（均为相对媒体 href，无本机绝对路径泄漏；与 WIP 媒体端点设计一致） |
| 2 | R10：`agents_hub.sync_agents_hub` 与 `agents_hub_scan.collect_agents_hub` 公开函数入口第一条语句非 logger（sync 的 logger 在局部 import 之后；scan 模块无 logger） | `bash tools/check/arch.sh` 退出码 2（R10 两处违规） | sync 的 logger.info 提到函数首句；scan 模块补 `logger = get_logger("service.power_market")` 且 collect 入口首句记 root |

改动文件：

- `backend/tests/test_b1c_capabilities_coverage.py`（白名单 +2 字段）
- `backend/tests/test_skill_public_api.py`（白名单 +2 字段）
- `backend/services/power_market/agents_hub.py`（logger 入口顺序）
- `backend/services/power_market/agents_hub_scan.py`（模块 logger + collect 入口日志）

## 3. 自测证据（QA-16 终态替换：此前贴的是中间态，违反 `_lessons.md` ESC-8）

> 2026-09-16 补：本节原贴 `1 failed, 1868 passed`（首轮中间态），全文再无一次
> 「0 failed」全量输出，但 §6 自检却勾了"pytest 全量绿"——这正是 `_lessons.md`
> ESC-8 描述的问题（证据须为终态，中间态输出禁入）。以下替换为 QA-1～QA-16
> 全部修复后、本轮最后一次全量重跑的终态输出（含本文件所有历史缺陷修复 +
> feat-agents-market 评审 16 条 finding 的全部后续修复，非本票单独产出）。

```
$ uv run pytest -q backend/tests
1954 passed, 41 skipped, 8 warnings in 295.72s (0:04:55)
exit: 0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run pytest -q backend/tests/test_openapi_routes_golden.py
1 passed in 1.75s
exit: 0
```

原始缺陷修复记录（下表，历史保留）：WIP 首轮全量验证发现的 2 类缺陷（公开投影
白名单遗漏 logo/background、R10 两处入口缺 logger）已在当轮修复并被后续全量
重跑覆盖，不再单独复核。

## 4. capability_assets live 行数基线（本地 MySQL，可达）

```
live_total=182 by_type={'agent': 18, 'command': 18, 'skill': 146} alembic_head=049
```

与 db-spec §header 实测一致（194 行总 / live 182 / plugin 0 = bug 态；alembic 单头 049）。
本地 MySQL 可达，未使用 SQLite 回退。

## 5. 环境备注

- pytest 无 `--timeout` 参数可用（无 pytest-timeout 插件）；后续票沿用 `-p no:cacheprovider` 即可，全量 ~170s 无饿死。
- 本地 MySQL head=049 与 WIP 基底一致，无强升需求。

## 6. 交票自检（QA-16 终态更新，见 §3）

- [x] pytest 全量绿（终态：1954 passed / 41 skipped / 0 failed，见 §3）
- [x] ruff 退出码 0
- [x] arch.sh 退出码 0
- [x] golden 一致（test_openapi_routes_golden.py 通过）
- [x] live 行数基线记录在案（MySQL 直查，见 §4）
- [x] WIP 文件零回退（仅日志顺序/白名单测试同步，无功能回退）
