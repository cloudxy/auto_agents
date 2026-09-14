# ADR-0009: 时间字段时区契约——全库 DATETIME naive + 单一时钟源（DB 时钟）

- 状态：已采纳（2026-09-05，工单 B3——dba P2 池 F-10 处置）
- 背景：体检 F-10 指出模型层 `timezone=True` 声明约半数表缺失，时区语义
  混用（TIMESTAMP vs DATETIME 语义之争），契约未成文。
- 关联：ADR-0008（同批 B3 处置）；迁移 026/027；dba 方法论第 2 步
  「时区：统一约定写进 db-spec」。
- 决策类型：契约成文 + 存量声明 waived-with-reason + 应用层混写移交独立票。

## 真库证据（2026-09-05 本机 MySQL 8.0.42）

```
SELECT @@global.time_zone, @@session.time_zone, NOW(), UTC_TIMESTAMP();
→ ('SYSTEM', 'SYSTEM', 2026-09-05 19:30:05, 2026-09-05 11:30:05)
  （DB 时钟 = 系统时区 UTC+8，非 UTC）

information_schema.columns：
  DATA_TYPE='timestamp' → 0 列
  DATA_TYPE='datetime'  → 91 列
  （timezone=True 在 MySQL 方言下不产生任何 DDL 差异——F-10 判断实证）
```

## 盘点清单

**带 `timezone=True` 声明（13 文件）**：alert_rule / archive / attachment /
mixins(SoftDeleteMixin.deleted_at) / notification / resource_version /
spider_result / spider_schedule / spider_task / system_cache / tag /
task_template / workflow。

**无 tz 声明（17 业务模型）**：ai_plan / capability / channel_event /
channel_probe_result / department / llm_provider / llm_provider_model /
llm_token_usage / menu / operation_log / permission / role / skill /
spider_definition / system_config / tenant / user。

**存量列型**：全库 0 TIMESTAMP、91 DATETIME——「TIMESTAMP vs DATETIME 混用」
在 DDL 层不存在，混用发生在**时钟源**（见风险清单）。

## 决策

1. **列型契约**：全库统一 `DATETIME`（naive，无时区标记）。MySQL TIMESTAMP
   的 2038 上限与隐式 UTC 转换不采用；新表一律 `sa.DateTime()`，
   **禁止新增 `timezone=True`**（它在本方言无 DDL 效果，徒增「以为有时区
   语义」的误导）。
2. **时钟源契约（单一事实源）**：落库时间一律取 **DB 时钟**
   （`func.now()` / `CURRENT_TIMESTAMP` 的 server_default 或 UPDATE 语句）。
   Python 侧 `datetime.now()` / `_utcnow()` 仅允许用于纯内存运算
   （TTL 计算、调度比对入参），**禁止直接赋值落库**——与 019 步骤 5 修复
   system_configs 的口径一致。
3. **DB 服务器时区**：部署清单显式声明（当前单区域部署 = UTC+8 系统时区）。
   展示层（前端）按浏览器时区转换，DB 层不做换算。
4. **存量 `timezone=True` 声明：waived**。理由：MySQL 方言下 DDL 与驱动
   返回行为均无差异（91 列全 DATETIME、pymysql 返回 naive）；批量改 13 个
   模型文件是纯声明清理，回归面（ORM 属性比较语义、测试快照）大于收益。
   保留声明不违反契约第 1 条的实质（列型已是 DATETIME）。

## 风险清单（本票不动 services，移交独立票）

存量存在**三种时钟混写**，同库时间最多偏差 8 小时：

| 时钟源 | 写入点 | 语义 |
|---|---|---|
| DB 时钟（UTC+8） | server_default=func.now() / CURRENT_TIMESTAMP（主流） | 本地时间 |
| naive-UTC（Python） | plugin_service._utcnow / tenant_expiry_service._utcnow 落库 | UTC |
| naive-本地（Python） | alert_service:112 / channel_scheduler_service:101,319 / schedule_service:227 落库 | UTC+8 |

**实害样例**：tenant_expiry_service 用 naive-UTC 与 `tenants.expires_at`
比较——若 expires_at 由 DB 时钟（+8）写入，到期判断偏差 8 小时。

**建议处置（独立票）**：混写点全部改为 DB 时钟赋值（`update(...).values(
x=func.now())` 模式）或统一 naive 口径；历史数据偏差需一次性订正脚本
（比对两类写入点的列，±8h 平移）。

## 触发重评条件

1. 多区域/跨时区部署（单一 DB 时区假设失效）→ 升级为 UTC 存储 +
   展示层全量转换（存量数据迁移，破坏性）。
2. 迁移到时区感知数据库（如 PostgreSQL timestamptz）→ 列型与驱动行为
   全面重审。
3. 外部系统对接要求 RFC3339 带时区时间戳 → 在 API 序列化层转换，
   DB 契约不变。
