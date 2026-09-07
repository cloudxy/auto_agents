# ADR-0010：四柱留在同一 FastAPI 单体，市场以 `power_market` 子包演进

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：PRD FR-01…FR-32、`contract.md` §2–3
> 本文件 **整份替换** stale `02-shape/adr-0010-four-pillar-topology.md`（同一决策，补 FR-32 与 B4 强制手段）。不是对旧正文打补丁。

## 背景

四柱（采集 / SaaS / 中转站 / 能力市场）已经长在同一 `create_app()` 进程里。Power Market 设计选择「升级 P6 能力中心、不另起 `/market` 服务」。需要把「单体 vs 拆服务 vs 按 Controller 切」写成不可逆拓扑，否则 Wave 1 会一边加包一边拆仓。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 无独立伸缩/独立发布节奏/多团队墙 | 现有部署：official/admin/API/scrapy；市场流量与采集同级且更小（~300 行资产） |
| 宪法「独立部署优于耦合」= 先画清边界 | `project_rule.md`；拆服务信号见 boundary-derivation |
| B1–B3 挡不住 services 内柱间 import | `scripts/check-arch.sh` 无域级规则 |
| appetite 按波，禁止四柱巨票 | spec §0 |

## 决策

保持 **单一 FastAPI 可部署单元**。在单体内按能力切单向依赖：SaaS / 采集 / 中转站 / Power Market / LLM 叶子。市场代码新建 `backend/services/power_market/`，不平行再做一个产品。

配套强制：`scripts/check-arch.sh` 增加 **B4**：`backend/services/power_market/` 禁止 import `spider_*` / `newapi_*` / `ai_planner` / `channel_*`。R10 日志扫描范围扩到 `backend/services/**/*.py`。B4 挂 `sdlc.config.yaml` 的 lint 闸门。

不把 40+ 平铺 service 一次性搬到 `backend/domains/`。

## 备选与否决理由

### 备选 A：市场独立 workspace member / 微服务

**否决理由**：无独立伸缩（公开目录 ~300 行）、无独立发布节奏、共享 MySQL 仍把数据边界留在库里。拆服务代价（分布式事务、本地开发劣化）相对 Wave 1 11 人周是净亏损。设计 Alternatives「产品形态」已 recorded no。

### 备选 B：按 Controller / Service / Repository 切「市场模块」

**否决理由**：一个上架变更会同时改 MarketController、MarketService、MarketRepository，等于没有边界。FR 聚类要求按能力切。

### 备选 C：本期就把 `backend/services` 搬成 `domains/{saas,collect,relay,market,llm}`

**否决理由**：移动 40+ 文件会使 R12 门面与测试 patch 路径全碎，超出单波 50% 重判线。作为目标态记下，不在本特征搬完。

## 证据

```
spike：单体内能放下市场
问题：是否已有四类资产目录 + 公开 /public/capabilities + Admin Capabilities.tsx
环境：仓库 head（2026-09-07）
结果：三者都在；全库 POWER_MARKET / listing_state / capability_installs = 0 命中
结论：缺的是 Source / listing / installs 缝，不是进程。升级枢纽，不新起容器
```

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| `backend/services` 继续膨胀 | B4 挡住市场包向采集/中转伸手 |
| 柱间存量耦合不消失 | Wave 0 只修鉴权/配额缝；不假装已域化 |
| B4 不扫旧代码 | 只约束新包；SkillService 直查结果表由 ADR-0013 冻结 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 新代码进 `power_market/`；API 仍挂 `/api/v1`；T-15 落地 B4 |
| `/dba` | 新实体仍在同一 MySQL |
| `/sre` | 无新进程监控 |
| `/qa` | 回归仍是单 API 基址 |

## 后续复审条件

出现以下任一信号：市场 QPS 与采集差一个量级且互相拖死；市场需要每日发版而采集月发；独立团队维护市场。届时新 ADR supersede，不原地改本文。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 采纳（替换 stale 稿） |
