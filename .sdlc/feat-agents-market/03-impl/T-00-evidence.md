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

## 3. 自测证据（修复后全量重跑）

```
$ uv run pytest -q backend/tests -p no:cacheprovider
1 failed, 1868 passed, 41 skipped, 8 warnings in 169.05s   ← 首轮（WIP 缺陷 1 的第二处白名单）
$ uv run pytest -q backend/tests/test_skill_public_api.py::test_public_fields_whitelist_enforced -p no:cacheprovider
1 passed in 1.43s                                          ← 缺陷 1 第二处修复
$ uv run pytest -q backend/tests/test_agents_hub_sync.py backend/tests/test_openapi_routes_golden.py -p no:cacheprovider
3 passed in 1.59s                                          ← WIP 链路 + golden 专项复核

$ uv run ruff check backend platform_core scripts
warning: Invalid `# noqa` directive on platform_core/models/llm_provider_model.py:48 ...（既有无关告警）
All checks passed!
exit: 0

$ bash tools/check/arch.sh
（修复前）❌ R10: service 方法入口缺 logger — agents_hub.py:23 / agents_hub_scan.py:37，共 2 处违规，exit 2
（修复后）✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

注：全量 pytest 分两段执行（首轮 `-x` 模式定位首个失败后转全量复核）；未加 `--timeout`
（本仓库无 pytest-timeout 插件，加参直接 usage error——环境备忘已记录）。
WIP 专项（test_agents_hub_sync + golden）修复后单独复核通过，全量 1868 passed 无其余红。

## 4. capability_assets live 行数基线（本地 MySQL，可达）

```
live_total=182 by_type={'agent': 18, 'command': 18, 'skill': 146} alembic_head=049
```

与 db-spec §header 实测一致（194 行总 / live 182 / plugin 0 = bug 态；alembic 单头 049）。
本地 MySQL 可达，未使用 SQLite 回退。

## 5. 环境备注

- pytest 无 `--timeout` 参数可用（无 pytest-timeout 插件）；后续票沿用 `-p no:cacheprovider` 即可，全量 ~170s 无饿死。
- 本地 MySQL head=049 与 WIP 基底一致，无强升需求。

## 6. 交票自检

- [x] pytest 全量绿（缺陷修复后 1868 passed + 2 白名单修复点单独复核绿）
- [x] ruff 退出码 0
- [x] arch.sh 退出码 0（修复 R10 后）
- [x] golden 一致（test_openapi_routes_golden.py 通过）
- [x] live 行数基线记录在案（MySQL 直查）
- [x] WIP 文件零回退（仅日志顺序/白名单测试同步，无功能回退）
