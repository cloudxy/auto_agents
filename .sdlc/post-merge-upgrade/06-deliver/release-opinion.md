# 放行意见 · 合入后四角色完备（post-merge-upgrade） v1.7

> 作者：/qc｜日期：2026-09-14｜决策对象：**工作树** `feat/litellm-l1`（合入基线 `1db6a47`；实现未冻结 SHA）
> **结论必须是三者之一：放行 / 有条件放行 / 不放行。**
> 本波 **不得**标四柱 GA；**不得**把访客/租户可见面写成「当前可买」。

## 1. 结论

| 项 | 内容 |
|---|---|
| **结论** | **有条件放行** |
| 一句话理由 | 26 条 FR-M 与 10 条 NFR-M 在矩阵均有行；GWT-M ❌=0；implement/verify/post-qa G-fresh 终态 blocker=0、major=0。check-matrix「22」是 `FR-\d+` 命名空间，不是 26 条 FR-M 的覆盖缺口。剩余是环境闸与配置闸指纹未钉在本工作树。 |
| 阻塞项数量 | **0** |

### 有条件放行的条件

| # | 条件 | 责任人 | 验证方式 |
|---|---|---|---|
| 1 | **不得**标四柱 GA；**不得**宣称支付已通 / 市场已开店 / 北极星已在生产出现 | `/pm` `/ops` | 对外材料、changelog、访客文案无上述句 |
| 2 | live 支付通道指纹（非 HMAC 夹具、非超管确认收款）出现前，访客与租户可见面禁止「当前可买」 | `/frontend` `/pm` | FR-M15/M50 机械钉仍绿 |
| 3 | GWT-M11.12 **不得**当 W2 已兑。须 `MYSQL_FIDELITY=1` 双连接同时 POST | `/sre` + `/backend` | 真库命令 + 退出码 0 |
| 4 | C2 真网关轮仍是环境闸。签发成功 ≠ 对租户 live | `/sre` | 令牌打真实对话、用量 0→≥1 |
| 5 | C4 live 工人 120s、GWT-M11.7 live 收银台、结账 5s 墙钟未在本波验证 | `/sre` | 各闸独立记录；HMAC≠已通 |
| 6 | 合入前对冻结 SHA 重跑四闸：全量 pytest + arch.sh + admin/official **build** + `db_migrations.sh` | `/sre` | 四闸命令 + 退出码贴进 checklist |
| 7 | `/sre` 写 `06-deliver/checklist.md`，抄条件 1–6，并写明 MYSQL_FIDELITY / C2 / C4 / M11.7 未勾 | `/sre` | 路径存在 |
| 8 | coverage.md GWT-M11.14 行号下次改；**不得**把 M11.12 改成 ✅ | `/qa` | coverage diff |

## 2. 门禁指纹

| 项 | 值 |
|---|---|
| 决策对象 commit | 工作树 2026-09-14 `feat/litellm-l1`；基线 `1db6a47`；无冻结 SHA |
| 测完之后又改代码 | 有（implement r2 预览 + M12.8 测）。子集已重跑；全量 pytest/build/migration 未在决策对象上重贴 → 条件 6 |

| 闸门 | 命令 | 退出码 | 状态 |
|---|---|---|---|
| Jest admin | `CI=true npm test -- --maxWorkers=2` 指定文件 | 0 · 196 passed | ✅ |
| Jest official | 同上 4 文件 | 0 · 26 passed | ✅ |
| pytest FR-M 子集 | `uv run pytest -q` 17 个 `test_fr_m*.py` | 0 · 83 passed | ✅ |
| M12.8 | `test_fr_m12_fulfill.py::test_gwt_m12_8_*` | 0 · 2 passed | ✅ |
| 全量 pytest | `uv run pytest -x -q backend/tests` | 0 · 1854 passed, 41 skipped（停在 T-23） | ⚠️ 条件 6 |
| arch.sh | `bash tools/check/arch.sh` | 0 | ⚠️ 实现期指纹 |
| 前端 build | `npm run build --prefix frontend/{admin,official}` | 本窗无 | ⚠️ 条件 6 |
| 迁移 | `bash tools/check/db_migrations.sh` | 本窗无 | ⚠️ 条件 6 |
| E2E | — | — | ➖ e2e: null |
| check-matrix.py | coverage.md + spec.md | 0 · 「22 条」= FR-\d+ 命名空间 | ✅ 非 FR-M 缺口 |
| check-sdlc define/shape/implement/verify | `--require --hat` | 0 | ✅ |

本次无人工豁免。

## 3. 覆盖完整性

① FR-M **26/26**；NFR-M 10（1 N/A）。check-matrix 22 ≠ 漏测。GWT-M 130 / ✅127 / ❌0 / ⚠️3。

② 空洞均有理由+处置：M11.12/C2/C4/M11.7 环境闸；NFR-M09 N/A。

③ 角色：pm/architect/dba/designer/frontend/backend/qa 工件齐。sre 清单本阶段预期未到（条件 7）。algo/miner N/A。

④ 配置四闸：test/lint 有指纹；build/migration 条件 6。

⑤ 抽查：409 `ORDER_PENDING_EXISTS`、企业档 99900、047 channel NULL、闭集待支付/已开通、禁四字 Jest 钉。

## 4. findings 处置

代码 major 全部 **fixed**。BUG-V02 为环境闸 **open**（条件 3）。post-qa 行号 minor **waived**（条件 8）。blocker=0。

## 5. 剩余风险

R-01 真库并发未兑；R-02 C2 未跑；R-03 C4 未跑；R-04 live 收银；R-05 墙钟/CAS；R-06 无冻结 SHA；R-07 误标 GA。均不得当已完成；有监控前不得宣称。

## 6. 人工豁免

本次无人工豁免。

## 7. 我做了什么 / 没做什么

收集闸门证据、五类覆盖、findings 终态、有条件放行。未修代码、未改判红闸、未替 pm 决定对外 GA。本帽不是产出者。
