# ADR-0015：平台目录表豁免；安装表禁止豁免；目录写仅平台超管

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：FR-06 FR-20、NFR-05、D10/D14、`contract.md` §7
> 本文件是塑形 v2 **新建**（stale contract 曾引用但不存在于磁盘）。

## 背景

`capability_assets` 有 `tenant_id` 列（恒 NULL，平台级公共资产），**不**继承 `TenantMixin`，**未**进 `TENANT_EXEMPT_TABLES`。`tenant_context` 对含 `tenant_id` 且未豁免的表，Core UPDATE/DELETE 注入 `tenant_id = 当前租户`。平台行全是 NULL → **0 行命中**：扫描/治理「成功」但不落库。SELECT 因非 Mixin 不过滤，租户能读全量目录——读路径「看起来正常」。

`skills` 三表已豁免。CONTEXT 写资产 `tenant_id` 恒 NULL，代码没登。R13 只校验清单自洽，不扫描「有列无 Mixin 未豁免」。

Wave 1 安装表有真实 `tenant_id`，若误进豁免，跨租户安装会泄漏。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 平台目录变更仅超管 | FR-06 / D14 |
| 安装跨租户不可见 | FR-20/21 / NFR-05 |
| 基建不感知业务表名 | B1；豁免只活在 `tenant_isolation.py` |
| 安装表有真实租户 | D10 |

## 决策

1. 平台目录及相关表登记进 `TENANT_EXEMPT_TABLES`：`capability_assets`、`capability_plugins`、`capability_experts`、`capability_commands`、`capability_teams`；Wave 1 增加 `capability_sources`、`capability_components`、`capability_aliases`。
2. **`capability_installs` 禁止豁免**，必须 `TenantMixin`，行级隔离。
3. **不要**给 `CapabilityAsset` 加 Mixin 当租户资产——与「平台级公共资产」相反。
4. 目录写 API（扫描/验证/上架/源/许可放行）使用 `require_platform_admin`，不用 `require_admin`。
5. 补回归：租户 token 扫目录 → 403；豁免后平台态 UPDATE 命中 >0。

## 备选与否决理由

### 备选 A：给 `CapabilityAsset` 加 TenantMixin，每租户一份目录

**否决理由**：与 CONTEXT「平台级公共资产、tenant_id 恒 NULL」相反。公开商店会变成 N 份目录。D10 已把租户态放到安装表。

### 备选 B：安装表也豁免，靠 service 手写 WHERE

**否决理由**：漏一处 = 跨租户可见事故（护栏红线 0）。SELECT 注入只打 Mixin；手写必漏。

### 备选 C：Wave 0 不豁免，等 Wave 1 和市场表一起改

**否决理由**：FR-06 是 Wave 0 永不砍。不豁免则超管在租户态（若误用）或任何注入路径 0 行，治理假成功今天就在。

## 证据

`backend/app/tenant_isolation.py` 清单含 `skills` / `skill_reviews` / `skill_jobs`，不含 `capability_assets`。模型 `platform_core/models/capability.py` 手写 `tenant_id`。`test_saas_isolation.py` 只钉 skills 豁免 vs spider_tasks 注入。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 豁免表变多，R13 仍不发现「有列未登记」 | qa 夹具：租户态 UPDATE assets 在豁免后不再 0 行；平台态才写 |
| 租户仍能 **读** 全量目录（非 Mixin SELECT 不过滤） | 产品允许：平台目录对登录者可见；**写**拒绝。公开面另走闸门 |
| 误把 installs 登记进豁免 | 代码评审 + 测试：租户 A 看不见 B 的安装行 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/dba` | 登记语义见 §7；installs 必须 Mixin |
| `/backend` | T-01 改 `tenant_isolation.py`；T-02 改 Depends |
| `/qa` | 租户 admin 扫描 403 + 目录一行不变 + 审计 |

## 后续复审条件

若产品要把部分资产做成租户私有技能库（定价空头「私有技能库」若 Q-PRICE=履约），必须新 ADR：那是另一张表或另一隔离模式，不能把平台目录改成 Mixin。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 新建 |
