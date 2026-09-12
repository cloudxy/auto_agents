# 实现证据 · T-38 平台超管以平台租户身份入队

> 票：contract §7「平台租户入队（FR-102）」+ §11 T-38 行｜FR 锚点：FR-102（GWT-102.1…102.5；GWT-82.4 边界钉住）｜角色：/backend｜日期：2026-09-11

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| actor→tenant 解析（超管→platform 租户） | **API 依赖层单点** | `backend/app/api/deps.py::task_actor_tenant_id` | 契约 §8「解析点单一」；由同步改 async（需查 DB） |
| platform 种子行查询 + fail loud | Service | `backend/services/background_session.py::platform_tenant_id(_or_none)` | 行缺失=配置错误→`BusinessException("平台租户未初始化，无法入队")`，**不**静默回退、**不**临时建租户（契约 §7/§8 钉死） |
| 冒名直打拒绝（102.5） | 同解析单点 | 同上 deps.py | 非超管且挂 platform 租户 → 中文句拒绝，无内部码 |
| 配额执法（102.3） | 既有链零改动 | `spider_task_service._check_enqueue_quota` → `quota_service.check_task_concurrency` | 平台租户照常执法（T-12 句族原样复用） |
| 普通租户解析不变（102.4） | 同解析单点 | deps.py 尾分支 `return user.tenant_id` | require_enqueue_tenant 本体零改动 |
| 路径/方法/状态码 | Router ×4 | `ai.py` / `spiders/tasks.py` / `spiders/templates.py`（×2）/ `spiders/schedules.py` | 仅改 `await task_actor_tenant_id(user, session)`，协议零变化 |

**分层依赖核对**：☑ Router 未 import ORM（deps.py 经 services 查租户，与既有 audit_service/user_service 同模式）☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☐ ORM 与 Schema 互不 import —— 不涉

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/background_session.py` | 修改 | 新增 `PLATFORM_TENANT_SLUG` / `platform_tenant_id_or_none` / `platform_tenant_id`（R10 logger 齐） |
| `backend/app/api/deps.py` | 修改 | `task_actor_tenant_id` 同步→async 三分支改造（见 §6 对照） |
| `backend/app/api/v1/ai.py` | 修改 | create_plan 调用点 await 化 |
| `backend/app/api/v1/spiders/tasks.py` | 修改 | run_spider 调用点 await 化 |
| `backend/app/api/v1/spiders/templates.py` | 修改 | create_template / run_from_template 两处 await 化 |
| `backend/app/api/v1/spiders/schedules.py` | 修改 | create_schedule 调用点 await 化 |
| `backend/tests/test_t38_platform_tenant_enqueue.py` | 新增 | GWT-102.1…102.5 + fail loud，7 例 |
| `backend/tests/test_saas_wiring.py` | 修改 | GWT-09.4 金标同 PR 改写（PIT-2，契约 §5 已裁旧句为 T-38 改造对象） |
| `backend/tests/test_ai_planner.py` | 修改 | ai_client fixture 的 mock session 补可等待 execute（依赖签名变化的机械适配） |

**与票里「会改哪些文件」一致**：☑ 是（deps.py 解析 + 等价函数 + 测试）☐ 有偏差：等价函数落 `background_session.py`（票面建议位）但语义为 **fail loud** 而非 `default_tenant_id` 的兜底建——契约 §7「不临时建租户」优先于票面括号内建议（见 §8 给 /architect）。

**未触碰「不许改的文件」**：☑ 确认（AI 规划器内部流程 `ai_planner/orchestrator.py`、渠道组/安装 relay 域、`require_enqueue_tenant` 本体、WACT 相关零改动；`git status` 干净域核对）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| platform 种子行 SELECT | 否（只读，无写） | 解析点零写路径，不引入事务 |

### 幂等 / 并发控制

☑ N/A：本票零 DDL、零新写路径（纯解析改造）；入队写路径事务边界沿用 `SpiderTaskService.enqueue` 既有形态。

### 外部依赖

☑ N/A：无新外部依赖（Redis/DB 用法均既有门面）。

## 4. ORM 与 DBML 对齐

☑ 零 DDL、零字段变更——「实体：平台租户身份（FR-102，无新表）」按契约 §8 落地：不建表、不加列，slug=platform 种子行（迁移 024 既有）即身份锚。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `task_actor_tenant_id`：`入队企业解析 \| user=<username> platform_admin=<bool>`；`platform_tenant_id` 缺失行 `logger.error`（含迁移 024 提示）；冒名拒绝 `logger.warning` |
| R10 | 三函数入口均有 logger（arch.sh 通过即证） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 仅 username 与布尔

## 6. 自测证据

### deps.py 改造前后对照（票面要求）

改前（L127-131）：

```python
def task_actor_tenant_id(user: CurrentUser) -> int | None:
    """租户任务路径的入队企业：超管无企业空间 → None（enqueue 拒绝，GWT-09.4）。"""
    if user.is_platform_admin:
        return None
    return user.tenant_id
```

改后：

```python
async def task_actor_tenant_id(user: CurrentUser, session: AsyncSession) -> int | None:
    """租户任务路径的入队企业（FR-102 / T-38 改造；解析点单一——契约 §8）

    - 平台超管 → 平台租户（slug=platform 种子行；行缺失 = 配置错误、入队失败
      可见：fail loud，不静默回退 None、不临时建租户）
    - 非超管但挂平台租户 → 拒绝（GWT-102.5 冒名直打；中文可见句，无内部码）
    - 其余普通用户 → user.tenant_id（GWT-102.4 解析不变，零回退）
    """
    logger.info(f"入队企业解析 | user={user.username} platform_admin={user.is_platform_admin}")
    if user.is_platform_admin:
        return await platform_tenant_id(session)
    platform_tid = await platform_tenant_id_or_none(session)
    if platform_tid is not None and user.tenant_id == platform_tid:
        logger.warning(f"非超管以平台租户身份入队被拒绝 | user={user.username}")
        raise BusinessException(
            "当前账号不能以平台租户身份提交采集任务，请联系平台管理员"
        )
    return user.tenant_id
```

消费方 4 处（ai create_plan / spiders run / templates create+run / schedules create）统一 `await task_actor_tenant_id(user, session)`；`require_enqueue_tenant`（spider_common L43）本体零改动——GWT-09.4 服务层 None 拒绝守卫保留。

### TDD 红（先写测试，实现前）

```
$ uv run pytest -q backend/tests/test_t38_platform_tenant_enqueue.py
FAILED .../test_gwt_102_1_platform_admin_enqueue_belongs_to_platform_tenant
FAILED .../test_gwt_102_1_plan_and_test_capture_share_platform_identity
FAILED .../test_gwt_102_2_online_enqueue_same_platform_identity
FAILED .../test_gwt_102_3_platform_tenant_quota_not_bypassed
FAILED .../test_gwt_102_5_non_admin_impersonation_rejected
FAILED .../test_platform_tenant_missing_fails_loud
6 failed, 1 passed in 2.57s
```

（红因即现状：`task_actor_tenant_id` 超管返回 None → 400「没有企业身份，无法入队」；
102.4 钉住例实现前即绿——该行本就断言现状语义不回归。）

### 绿 + 回归

```
$ uv run pytest -q backend/tests/test_t38_platform_tenant_enqueue.py
7 passed in 2.22s

$ uv run pytest -q backend/tests/test_saas_wiring.py backend/tests/test_fr87_enqueue_envelope.py \
    backend/tests/test_ai_planner.py backend/tests/test_spider_task_flow.py \
    backend/tests/test_t38_platform_tenant_enqueue.py
135 passed in 4.89s

$ uv run pytest -q backend/tests
1467 passed, 37 skipped, 7 warnings in 153.27s (0:02:33)
exit: 0

$ uv run pytest -q backend/tests          # 共享工作树稳定性复核（连跑第二次）
1467 passed, 37 skipped, 7 warnings in 135.62s (0:02:15)
exit: 0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

（全量基线 1460 → 1467：+7 为本票新文件；wiring 金标 -1 +1 重写，净持衡。）

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| 102.1 试采入队成功/无旧拒句/列表可见/归属平台租户 | `test_gwt_102_1_platform_admin_enqueue_belongs_to_platform_tenant` + `test_gwt_102_1_plan_and_test_capture_share_platform_identity`（方案归属 + orchestrator._execute_test 同链服务层复演） | ✅ |
| 102.2 上线入队同一身份语义 | `test_gwt_102_2_online_enqueue_same_platform_identity`（AI 注册定义经 run 端点） | ✅ |
| 102.3 配额不绕（X-QUOTA 句族无内码） | `test_gwt_102_3_platform_tenant_quota_not_bypassed`（复用 T-12 `已达配额上限，请联系企业管理员。` 句式断言） | ✅ |
| 102.4 企业 A 归属不变/平台与企业 B 队列不变 | `test_gwt_102_4_regular_tenant_attribution_unchanged`（+ 全量 1467 零回退） | ✅ |
| 102.5 非超管冒名直打拒绝/无平台租户任务/句无内码 | `test_gwt_102_5_non_admin_impersonation_rejected` | ✅ |
| 契约 §7 种子行缺失 fail loud（不回退/不临时建） | `test_platform_tenant_missing_fails_loud`（断言未建 platform 行、零任务行） | ✅ |
| GWT-09.4 无无主任务不变量（新金标） | `test_saas_wiring.py::test_platform_admin_run_enqueues_as_platform_tenant_no_ownerless` | ✅ |
| GWT-82.4 边界（不开渠道组/安装） | 后端零动作：relay/出站域文件零改动，`test_relay_token_usage` / `test_billing_relay` 等全量绿即回归网 | ✅（回归口径） |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（零新写路径；解析点纯只读 SELECT） |
| 幂等 | ➖ N/A（无新增可重试操作） |
| 并发写 | ➖ N/A（无新并发面；配额计数沿用既有 `_cached_count`） |
| 外部依赖失败 | ➖ N/A（无新外部依赖；Redis 故障回源口径沿用 quota_service 既有行为） |

## 7. NFR 验证

票面无 T-38 专属 NFR。每入队请求新增 1 次平台租户 id SELECT（slug 唯一索引，单行）——入队为人工低频动作，量级可忽略；未加缓存（防漂移：种子行 id 稳定，如后续有热点再议）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| /architect | 票面括号「不存在兜底建/取（default_tenant_id 同构）」与契约 §7「**不**临时建租户、行缺失=fail loud」冲突——已按契约实现（fail loud）；如需改口径请回契约变更，勿在实现侧漂移。 |
| /qa | ①「归属显示平台租户」(102.1) 后端可测面=任务行 `tenant_id`=platform 种子行 + 列表可见（SpiderTaskResponse 无 tenant 字段，归属名呈现走前端既有租户名解析，**未扩响应字段**——契约无此项，expand-only 原则不动）。② WACT/PC 排除（蓝图 §1/契约 §7 末行）：后端**无 WACT/PC 计算代码**（grep 零命中），product-events 查询面（T-02）保持全保真（超管抽检需要）；「平台租户不计入」是事件**消费侧**（复盘/analyst 手工名单）口径，不在写入点过滤、不改 WACT 本体——与契约「事件消费侧口径，不在入队点过滤」一致。③ 102.5 冒名向量=非超管但挂 platform 租户（tenant_id 不可由请求注入，服务端派生）。 |
| /frontend | 无行为差异需适配：超管试采/上线不再吃「没有企业身份」；新失败句（低概率配置错）：「平台租户未初始化，无法入队」；冒名句：「当前账号不能以平台租户身份提交采集任务，请联系平台管理员」。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（红绿双输出 + 命令原样）
- [x] 自测全绿（全量 1467/37skip ×2 连跑；ruff 0；arch 0）
- [x] 契约落位表已核对，分层无违规（Router 零 ORM import）
- [x] ORM 与 DBML 一致，未自行加字段（零 DDL）
- [x] 无硬编码连接串/密钥/端口/阈值（slug 字面量与既有三处同口径）
- [x] async 上下文无同步阻塞调用（SELECT 走注入的 AsyncSession）
- [x] 无 `except: pass`
- [x] 日志已脱敏（仅 username/布尔）
- [x] 事务里无外部调用（无新事务）
- [x] 幂等未用「先查后插」（N/A）
- [x] 条件更新 rows==0 已处理（N/A）
- [x] 外部依赖四件套（N/A，无新依赖）
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报（票面×契约冲突 → §8 /architect）
- [x] 票状态：done（T-38）
