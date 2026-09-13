# 未完成事项清单 · feat-product-complete 关账后（2026-09-12）

> 已完成部分见 git 三提交（5f768be/2506797/743b96b）与 42 份 evidence；本文件只列**还没做的**。
> 详细命令与口径：[checklist.md](checklist.md)（sre）· [coverage.md](../04-verify/coverage.md) §5（qa）· [release-opinion.md](release-opinion.md) §5/§9。

## 一、上线前必跑（环境闸，代码已就绪）——责任 sre+qa

| # | 事项 | 时机 | 关键口径 |
|---|---|---|---|
| C2 | **真网关轮（硬闸）**：LLM.ENABLED+上游 key 机外配置 → 渠道组令牌按 T-09 口径打真实 chat（用量 0→≥1、恰 1 条事件）→ 出站钥匙打 Base URL 验拒绝+用量基线不变；顺跑探针 B-4 一枪 | **向租户开放渠道组/令牌之前** | 失败=环境未过，不上线 |
| C3 | staging/生产克隆迁移 apply（041→044，up→down→up 复证）+ 本机 alembic 039/040 漂移对齐 + B-6 真库轮（需 root，auto_agents 用户无 CREATE） | 部署时 | 迁移门禁脚本 0 |
| C4 | worker 队列冒烟：Redis+worker 起链 → AI 方案→试采→轮询 completed | 部署时 | 任务终态 completed |
| C5 | P95 抽测：当日 curl 冒烟（≥50 样本）；3 日内 Playwright 全量；P95≥2s 告警 | 上线当日/后 3 日 | coverage §5.B-1 双口径 |

## 二、后续开发票（账本，已脱离本特征发布面）

| # | 事项 | 出处 |
|---|---|---|
| L1 | T-32 三处数据补齐端点：per-channel 24h 事件聚合 / 窗口用量读 API（暴露 Redis last_usage）/ channels·probe 响应直带 channel_id | IMPL-QA-4 |
| L2 | 测试债：IM-02/03/12/13/18/26、C35-QA-05（conftest `expire_on_commit=False` 与生产相反的盲区，T-22 已立 precedent） | spec §5 / T-22 evidence §8 |
| L3 | 环境对齐：本机 DB 迁移头升级到 044；分支合并主干排期 | checklist |
| L4 | `services/menus.ts`+menuConfig MENU_ICON_MAP 已无消费方——下特征评估随 menus 表删除 | T-15 evidence §8 |
| L5 | spider_registry_service.py 516 行超 500（存量）——拆分 refactor 票 | T-41 evidence |

## 三、等操作者拍板（六开放问，全程未代选）

| 问 | 一句话 | 影响面 |
|---|---|---|
| Q-VOICE | 对外第一句：采集、四柱平台，还是能力市场？ | 官网首屏/北极星 |
| Q-PRICE | 专业档定价策略（撤文案/履约/预告）+确认收款后是否履约三数字+是否撤 ¥299+渠道组是否企业档专属 | 官网定价/收款流程 |
| Q-MARKET-USER | 能力市场主用户与获客；租户侧栏「能力市场」落点（货架 vs 我的安装） | FR-91（本特征未施工） |
| Q-AGPL | 中转作独立 SKU 的商用口径 | 官网渠道组对外句 |
| Q-OPS-COLLECT | 真实值班/收集通道（当前 mailto 是占位） | 联系页 |
| Q-C-REG | **C 端个人注册是否开放**（现在注册强制建企业；归属规则已就绪挂平台租户） | 注册流程 |

## 四、随手事项

- `feature/pm` 领先 origin/main（提交未推送）——推送时机由操作者定。
- 上线后四周窗（B-7）：WACT/PC-1…PC-4 自上线日起算，中途不下成败。
- 上线后红线四抽检：/skills 零种子；官网零「当前可买」；租户直打 /platform-ops /newapi 404 同形；平台租户改名/停用被拒。
- 不可逆面须知（收款单向门/明文只显一次/基座守卫勿绕）见 release-opinion §8，随上线交 ops。
