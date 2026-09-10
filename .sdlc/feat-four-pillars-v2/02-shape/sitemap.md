# 站点图 · 四柱程序 v2

> 泳道：L4
> 上游：`design-brief.md` · spec FR-01…20 / 70…75 / 30…45 · contract v1.8 · ADR-0017 / ADR-0018
> 作者：/designer｜日期：2026-09-08
> 下游：`flows/*.md` · `/frontend` 路由与菜单可见性
> **冻结：** 后台五组不重排；无聊天页；无租户渠道组；无四柱并列 Hero。

## 0. 纪律

- 路由：名词复数 + ID；筛选进查询参数。
- 公开 `type` ∈ `skill|plugin|command|agent|team`（全部 = 不传或 `type` 空）。禁止对外 `expert`。
- `/skills` → `/capabilities?type=skill`（替换，不是第二套店）。
- 旧「专家」地址一周期映射 `/capabilities?type=agent` 或与 404 同形，禁止第三套店。
- 官网无会话。订/卸在后台。
- 平台专属地址：租户导航隐藏；直打 = 该端**后台 404 同形**（无渠道、无密钥、无「抱歉您没有权限」）。
- 商店未上架/黑名单 **GET 详情** = 官网真 404 字节级同形。

## 1. 官网（:9113）品牌前线

```
SiteLayout NAV（唯一能力入口）
├── 首页            /                         FR-01/02/70.4
├── 能力市场        /capabilities             FR-30/31/33/44
├── 定价            /pricing                  FR-01/05
└── （页脚/次）登录管理后台 → {ADMIN_URL}/login
    免费注册         /register                 FR-04

深链 / 兼容
├── /capabilities/:type/:slug                 FR-32/40/45  详情
├── /skills                                   → /capabilities?type=skill
├── 旧 expert 地址                            → type=agent 或 404 同形
└── *                                         404「页面不存在，可能已被移除或地址有误」+「返回首页」
```

**不出现：** `/chat` · 技能广场并列 · 能力广场并列 · 「我的渠道组」 · 「直连平台网关」 · 「我的中转令牌」 · Hero 统计三列。

**定价付费档** 不新开销售站：`/pricing` 页内说明「预告不可购买」+ mailto。

## 2. 后台（:9112）antd 五组（组 key 冻结）

组结构与现网 `menuConfig` **同五组**：概览 / 数据工厂 / 能力资产 / 运营管理 / 系统管理。本程序只改**叶可见性、叶名、组内加叶**，不调组顺序、不合并组、不新增第六组。

```
概览 /overview
├── 仪表盘              /dashboard              全登录角色
└── 用量看板            /usage                  tenantOnly

数据工厂 /factory
├── 采集任务            /spiders/tasks
├── 运行日志            /spiders/logs
├── 节点监控            /spiders/nodes
├── AI 采集规划         /ai                     规划/试采/评分的产品面（不是聊天）
└── 数据中心            /data                   不含市场候选

能力资产 /assets          ← 组名不改
├── 能力市场            /capabilities           叶名由「资产目录」改为「能力市场」
│                         超管：顶栏七叶 源|目录|插件|技能|命令|智能体|专家团
│                         租户：无源登记/上架写；不把治理当租户货架
└── 我的安装            /capabilities/installs  tenantOnly；FR-35
                                              超管无企业空间：权限态「需要企业空间才能订阅」

运营管理 /ops
├── 成员管理            /members                tenantOnly
├── 平台运营台          /platform-ops           仅 is_platform_admin；含产品事实查询
└── 日志中心            /logs

系统管理 /system
├── LLM 配置            /llm                    **经办可进**（menu:llm；无 ProtectedRoute requireAdmin）
├── 中转站管控          /newapi                 仅超管（menu:newapi）；值班 FR-71；URL 一周期保留
├── 用户管理            /users                  仅超管
└── 系统设置            /settings               平台写仅超管；租户若历史书签仍进：密钥仅掩码、无本机路径
```

**公开/半公开后台**

| 路由 | 谁 | 说明 |
|---|---|---|
| `/login` | 匿名 | 到期句 FR-08；页脚「没有账号？企业注册」→ 官网 `/register` |
| `/unauthorized` | 已登录但非本程序平台页 | **不得**用于 `/newapi` `/platform-ops` `/users` 源/上架写直打 |
| 布局内 `*` | 任何人直打不存在或平台专属 | 后台 404：「页面不存在或已被移除」+「返回工作台」 |

**不做：** 菜单或站点图出现 `/enterprise` `/rbac`（幽灵不修、不进导航）。直打维持现网拦截，**不**在本程序当产品入口设计。

**不做：** `/chat` · `/relay` · `/tokens` · 租户「我的渠道组」。

## 3. 可见性矩阵（租户壳 vs 平台壳）

用登录投影 `is_platform_admin`（缺字段当 false），**不用** `role==='admin'` 开平台叶。

| 叶 | 经办 | 租户 admin | 只读 | 超管（有企业） | 超管（无企业） |
|---|---|---|---|---|---|
| 仪表盘 / 数据工厂 | 显示 | 显示 | 显示（只读） | 显示 | 显示 |
| 用量 / 成员 / 我的安装 | 显示 | 显示 | 显示（只读） | 显示 | **隐藏**或进页权限态「用量/成员/安装属于企业空间」 |
| 能力市场 `/capabilities` | 显示但无上架写 | 同左 | 同左 | **七叶治理** | 七叶治理 |
| 平台运营 / 中转 / 用户管理 | **隐藏**；直打 404 同形 | 同左 | 同左 | 显示 | 显示 |
| `/llm` | **显示**；本企业行可保存/测试连接 | 同左 | 显示；写控件禁用 | 显示；平台行可写 | 显示 |
| 源登记 / 上架开关 | 导航不出现；控件隐藏或直打 404 | 同左 | 同左 | 显示 | 显示 |

权限缓存未就绪：壳显示「权限加载中」或保留**读叶**；**不得**露出中转 / 平台 LLM 写（平台行）/ 用户管理 / 平台运营；**不得**整站空白。

## 4. 同形 404 两套（禁止混用）

| 场景 | 模板 | 文案 | 主按钮 |
|---|---|---|---|
| 官网任意不存在 URL；商店未上架/黑名单 **打开详情** | 官网 `NotFound` | 「页面不存在，可能已被移除或地址有误」 | 「返回首页」 |
| 后台不存在 URL；租户直打 `/newapi` `/platform-ops` `/users` / 源与上架写地址 | 后台 `NotFound` | 「页面不存在或已被移除」 | 「返回工作台」 |

禁止：「已下架」「抱歉您没有权限」出现在上述两套。unlist vs 黑名单的**差别**只画在已登录「我的安装」。

订阅提交失败（从不存在/未上架/黑名单短名）**不是**这套 HTML 404：弹窗内联，无「已下架」，无新行。

## 5. 页面标题（`pageTitleFor`）

| path | h1 / Header 标题 |
|---|---|
| `/dashboard` | 仪表盘 |
| `/usage` | 用量看板 |
| `/spiders/tasks` | 采集任务 |
| `/ai` | AI 采集规划 |
| `/data` | 数据中心 |
| `/capabilities` | 能力市场 |
| `/capabilities/installs` | 我的安装 |
| `/llm` | LLM 配置 |
| `/newapi` | 中转站管控（页内标题可改口「LLM 网关值班」，Q-VOICE 未关前**不**当对外 Hero） |
| `/members` | 成员管理 |
| `/platform-ops` | 平台运营台 |
| `/login` | 登录 |

每页一个 h1 = 上表。不跳级。

## 6. FR → 路由核对

| FR | 主路由 |
|---|---|
| 01 02 05 70.4 文案 | `/` `/pricing` |
| 04 08 | `/register` `{ADMIN}/login` |
| 03 11 18 19 | `/spiders/tasks` `/data` `/spiders/nodes` |
| 06 07 17 73.4 | `/llm` `/newapi` 壳 |
| 12 16 | `/usage` |
| 15 43 | `/platform-ops`（超管）；租户直打 404 |
| 71 72 75 | `/newapi` |
| 70 73 74 产品失败句 | `/ai` 计划详情（及技能评分入口，**无** `/chat`） |
| 30–33 44 45 | `/capabilities` 官网 |
| 34 35 | 详情订阅弹窗 + `/capabilities/installs` |
| 36–42 20 | 后台 `/capabilities` 七叶 |
| 13 14 51 | 无新路由 |
| 50 60 stub | 无新路由；定价/用量 CTA 约束 |

## 7. 深链与返回

- 市场筛选：`/capabilities?type=&q=&host=&category=&page=`
- 详情：`/capabilities/:type/:slug`（目录短名或 alias）
- 登录回跳：`/login?from=<path>`；注册成功：`{ADMIN_URL}/login?from=/dashboard`
- 未登录订阅：`{ADMIN_URL}/login?from=/capabilities/installs` 或带回详情 path；回后**尚未订**
- 从详情回列表：恢复 q/type/page/滚动
