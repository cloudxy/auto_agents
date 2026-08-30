# New API 多租户中转站 · 部署与租户管控指南（auto_agents 定制版）

> 基于 [new-api](https://github.com/QuantumNous/new-api)（One API 增强分支，**AGPLv3**），
> 镜像 `calciumion/new-api:v0.10.7`（**锁定版本**，勿用 `:latest`）。
> 能力：多用户分组 / 令牌限额 / 渠道负载均衡 + 故障转移 / 倍率计费 / 用量审计 /
> OpenAI + Claude + Gemini 多协议互转。
>
> **本目录定位**：new-api 作为**独立隔离部署**的中转站引入本项目——独立目录
> `deploy/newapi/`、独立网络 `newapi-net`，不并入根 `docker-compose.yml`、
> 不进 uv workspace。**渠道调度器与渠道真伪探针不由本目录承载**，由本项目
> backend 内置服务实现（见 §5），配置见 `config/default/newapi.yml`（默认关闭）。

---

## 一、简介与架构

### 1.1 架构图（文本版）

```
 租户客户端（OpenAI / Claude SDK，base_url 指向中转站）
        │  租户令牌（new-api「令牌层」签发：额度上限 / 模型白名单 / 过期时间 / 速率限制）
        ▼
 ┌────────────────────────────────────────────────────────┐
 │  new-api  calciumion/new-api:v0.10.7  （对外仅 3000）    │
 │  · 租户 / 分组 / 倍率计费 / 用量与操作审计 —— 内建         │
 │  · 会话与令牌缓存  ← Redis 7.4-alpine（newapi-redis）    │
 │  · 业务数据        ← MySQL 8.0（newapi-mysql）；         │
 │                      SQLite 快速版则落在 ./data          │
 └───────────────────────────┬────────────────────────────┘
                             │ 渠道层：真实上游 Key 只存服务端，
                             │ 权重 / 优先级 / 故障转移
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
      上游 A（官方）      上游 B（中转）      上游 C（中转）
                             ▲
                             │ 管理 API 启停渠道 / 行为指纹探针
 ┌───────────────────────────┴────────────────────────────┐
 │ auto_agents backend 内置服务（非外部脚本）                │
 │  · 渠道调度器：用量巡检 → 超限下线 → 冷却到期 → 自动上线    │
 │  · 渠道真伪探针：知识截止 / reasoning_tokens / 延迟等体检   │
 │  · 配置：config/default/newapi.yml（ENABLED 默认 false）  │
 └────────────────────────────────────────────────────────┘
```

### 1.2 职责边界（重要）

| 关注点 | 承载方 | 说明 |
| --- | --- | --- |
| 租户/令牌/渠道/计费/审计 | new-api 内建 | 本目录部署运维 |
| 渠道用量调度（超限下线→冷却→恢复） | **本项目 backend 内置服务** | 不使用参考材料中的外部 `channel-scheduler.py` 脚本 |
| 渠道真伪检测（降智/套壳识别） | **本项目 backend 内置服务** | 周期探针，配置 `config/default/newapi.yml` |
| AI 采集调用中转站 | admin「LLM 配置」页 | 见 §5.1 |

> 调度/探针内置化的原因：参考脚本存在已知缺陷（DSN 127.0.0.1 误连本机库、
> `created_at` 字符串与 unix 时间戳比较失效、状态 JSON 非原子写、单渠道异常
> 中断整轮），由 backend 服务统一规避并复用项目配置/日志/告警体系。

---

## 二、部署步骤

### 2.1 快速开始（SQLite 版，3 步）

```bash
cd deploy/newapi

# ① 准备环境变量（试跑可只改 SESSION_SECRET）
cp .env.example .env
openssl rand -hex 32          # 生成结果填入 .env 的 SESSION_SECRET
#    注意：纯 HTTP 直连试跑，请把 .env 中 SESSION_COOKIE_SECURE 改为 false，
#    否则浏览器不回传会话 Cookie，表现为无法登录

# ② 启动
docker compose -f docker-compose.sqlite.yml up -d

# ③ 初始化
#    浏览器打开 http://<host>:3000 → root / 123456 登录 → 立即改密码
#    数据保存在 ./data（SQLite），迁移生产前务必备份
```

### 2.2 生产部署（MySQL 版）

```bash
cd deploy/newapi

# ① 准备环境变量（全部密钥/密码必改）
cp .env.example .env
openssl rand -hex 32          # ×2：分别填 SESSION_SECRET / CRYPTO_SECRET
vim .env                      # 修改 MYSQL_* / REDIS_PASSWORD 等全部占位值

# ② 启动（MySQL/Redis 就绪后 new-api 才启动，healthcheck 把关）
docker compose up -d

# ③ 初始化（同 SQLite 版第 ③ 步）
#    浏览器打开 http://<host>:3000 → root / 123456 登录 → 立即改密码

# ④ 部署前验证（务必执行，见 §6）
```

### 2.3 运维速查

| 操作 | 命令/方式 |
| --- | --- |
| 看日志 | `docker compose logs -f new-api` |
| 升级版本 | 先备份数据库 → 改 compose 中镜像 tag → `docker compose pull && docker compose up -d` |
| 备份 | 生产版：`mysqldump` 或备份 `./mysql-data/`；SQLite 版：备份 `./data/` |
| 3000 连不上 | 查 `docker compose ps`（healthcheck）与防火墙；确认 `NEWAPI_BIND` |
| 401 调用失败 | 检查租户令牌是否过期 / 被限模型 / 组权限不足 |

---

## 三、租户管控四层操作手册（核心）

### ① 渠道层（上游接入）—— 先配这里

后台 **渠道 → 添加渠道**：

- **类型**：OpenAI / Anthropic Claude / Azure / Gemini / DeepSeek / 各国内厂商……
- **真实 Key 只存服务端**：上游 API Key 填在渠道里，租户永远看不到；
  `CRYPTO_SECRET` 负责加密存储，泄露等于全部上游 Key 暴露，务必妥善保管。
- **权重 / 优先级**：同一模型配多个渠道，按比例分流；某渠道报错自动
  **故障转移**到下一渠道。
- **模型倍率**：按渠道设置（如 gpt-4o 收 1 倍、claude 收 2 倍）。
- **自动禁用**：渠道页可设连续失败阈值自动下线（覆盖"渠道挂了"）；
  "自定义用量上限 + 定时恢复"由本项目调度器承担（§5.2），两者互补。

### ② 用户层（租户账号）—— 管控谁能用

后台 **用户** 页面 + **运营设置**：

- **关闭开放注册改邀请码**：运营设置里关闭开放注册，改为邀请码注册，
  防止陌生人涌入。
- **分组**：默认 `default` 组；可建 `vip` / `trial` 等组，不同组不同权限与
  倍率折扣（如 vip 组 0.8 倍）。
- **额度管理**：按租户分配/调整额度余额（充值或赠送），余额用尽自动停。
- **封禁/解封**：异常租户一键禁用，名下令牌即刻失效。

### ③ 令牌层（调用凭证）—— 管控调用方式

租户登录后在 **令牌** 页创建自己的 API Key，管理员可全局控制：

- **额度上限**：单个 Key 最多消耗多少，防单租户刷爆成本。
- **模型白名单**：该 Key 只能调用指定模型。
- **过期时间**：临时令牌到期自动失效。
- **速率限制**：结合 Redis 做 RPM/TPM 限流（SQLite 版无 Redis，此能力缺席）。
- **指定渠道/分组**：令牌可锁定走某渠道或某用户组。

### ④ 审计 —— 管控与追溯

- **请求日志**：后台可查全部请求日志（调用方、模型、token 消耗、耗时、状态码）；
  租户可见自己的用量，管理员可审计全站。
- **操作记录**：管理员对用户/令牌/渠道的增删改均有记录。
- **密钥轮换**：`CRYPTO_SECRET` / `SESSION_SECRET` 建议定期评估；注意
  更换 `CRYPTO_SECRET` 前先导出渠道信息（见 `.env.example` 注释）。

---

## 四、安全加固清单（生产必做）

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | **改默认管理员口令** | 初始 `root / 123456`，首次登录立即改强密码 |
| 2 | **HTTPS 反代** | 见下方 Caddy / Nginx 示例；**SSE/流式输出需保留 Upgrade 头**并关闭缓冲 |
| 3 | **SESSION_COOKIE_SECURE=true** | HTTPS 就绪后保持 `.env` 中的 `true`；纯 HTTP 试跑才允许 `false` |
| 4 | **3000 不暴露公网** | 建议 `.env` 设 `NEWAPI_BIND=127.0.0.1`，外部统一走反代；云安全组只放行 80/443 |
| 5 | 密钥管理 | `SESSION_SECRET` / `CRYPTO_SECRET` / `.env` 严禁提交 git（本目录 `.gitignore` 已忽略） |
| 6 | MySQL/Redis 不出网 | 两个容器均**未发布宿主端口**，仅 `newapi-net` 内部互通；勿额外加 `ports` |
| 7 | 数据库口令 | `.env` 中全部占位密码必改；数据目录初始化后改密需 `ALTER USER` |
| 8 | 备份 | 定期 `mysqldump`（或备份 `./mysql-data/`）+ `.env` 离线保存 |

**Caddy 示例**（自动签发证书，最省事）——Caddy 容器需加入 `newapi-net` 网络
（`docker network connect newapi-net caddy` 或在 Caddy 的 compose 里声明外部网络）：

```caddyfile
api.example.com {
    reverse_proxy new-api:3000
}
```

**Nginx 示例**（SSE/流式必需项已标注）：

```nginx
server {
    server_name api.example.com;
    listen 443 ssl;
    # ssl_certificate / ssl_certificate_key ...

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # SSE/流式必需
        proxy_set_header Connection "upgrade";       # SSE/流式必需
        proxy_buffering off;                         # 流式输出防缓冲
        proxy_read_timeout 300s;                     # 长流式响应
    }
}
```

> 反代就绪后确认 `.env` 中 `SESSION_COOKIE_SECURE=true` 并 `docker compose up -d`
> 重建生效；同时建议设置 `SESSION_COOKIE_TRUSTED_URL=https://api.example.com`。

---

## 五、与本项目（auto_agents）集成

### 5.1 AI 采集接入路径

1. 在 new-api 后台按 §3①③ 配好渠道与租户令牌；
2. 本项目 admin 后台打开 **「LLM 配置」** 页：
   - `base_url` 填 `http://<host>:3000/v1`（同机为 `http://127.0.0.1:3000/v1`；
     走 HTTPS 反代后为 `https://api.example.com/v1`）；
   - API Key 填**租户令牌**（§3③ 创建，带模型白名单与额度上限）；
   - 保存并**激活**后，AI 采集（`config/default/llm.yml` 的 LLM 服务）即可走中转站。
3. **双层熔断**（成本双保险）：
   - 第一层：本项目 token 预算熔断 —— `config/default/llm.yml` 的
     `MAX_TOKENS_BUDGET`（累计用量超阈值即拒绝调用）；
   - 第二层：new-api 令牌限额 —— §3③ 的令牌额度上限/过期时间/速率限制。
   两层任一触发即停，互为兜底。

### 5.2 渠道调度器与真伪探针（本项目 backend 内置服务）

- **不在本目录部署任何调度脚本**。参考材料的 `channel-scheduler.py` 仅作设计
  参考，其功能由 backend 服务重写实现，并规避其四项已知缺陷：
  DSN 误连本机库（改走统一配置）、`created_at` 类型比较失效（按 §6 先确认
  列类型再做归一化）、状态写非原子（改原子落库）、单渠道异常中断整轮
  （单渠道隔离异常）。
- **配置**：`config/default/newapi.yml`（Dynaconf，`NEWAPI__` 前缀风格），
  `ENABLED` / `SCHEDULER_ENABLED` / `PROBE_ENABLED` **默认全部 false**；
  敏感项 `ACCESS_TOKEN`（new-api 管理员 AccessToken）、`DB_DSN` 走
  `config/<env>/.env` 或环境变量覆盖（`AUTO_AGENTS_NEWAPI__*`），不落 yml。
- **网络**：backend 与 new-api 若同机，`BASE_URL=http://127.0.0.1:3000`；
  若 backend 也容器化，加入 `newapi-net` 后用服务名 `http://new-api:3000`。

---

## 六、部署前验证清单

1. **Compose 语法校验**（不启动）：

   ```bash
   docker compose -f deploy/newapi/docker-compose.yml config -q
   docker compose -f deploy/newapi/docker-compose.sqlite.yml config -q
   ```

2. **确认 new-api `logs` 表 `created_at` 列类型**（调度器直连库聚合用量时
   依赖该字段；不同版本/迁移路径下类型可能不同）：

   ```bash
   docker exec newapi-mysql mysql -uroot -p -e "DESC logs;" newapi
   ```

   - `created_at` 为 **BIGINT（unix 时间戳）** 或 **datetime** 均可能存在：
     内置调度器**两者都兼容**，但实现按列类型做条件归一化，需在部署后
     记录实际类型（SQLite 版可用 `sqlite3 ./data/one-api.db ".schema logs"` 查看）。
3. **健康检查**：`docker compose ps` 三服务 `healthy`；`curl http://127.0.0.1:3000/api/status` 返回正常 JSON。
4. **首次登录改密**（§2 步骤 ③/④）完成后再对外放行端口。
5. **调度/探针默认关闭确认**：`config/default/newapi.yml` 中
   `ENABLED/SCHEDULER_ENABLED/PROBE_ENABLED` 均为 `false`，未经评审不开启。

---

## 七、合规与风险提醒

- **AGPLv3 边界**：new-api 采用 **AGPLv3**。
  - **仅容器化使用、不修改其源码**：无开源衍生义务，内部自用/团队使用无问题；
  - **对外商用（SaaS/收费分发）**：若修改了 new-api 源码或形成衍生作品，
    需按 AGPLv3 开源衍生代码（或向上游购买商业授权/遵守其附加条款）；
    本项目当前仅容器化集成，**未修改上游源码**，无衍生义务。
- **上游授权**：只聚合调用**自己合法持有**的上游 API（官方账号或已授权渠道）；
  不要接入来路不明的"低价 Key"——随时跑路且可能窃取请求数据。
- **不做"套壳倒卖"**：若对外收费，确认合规边界，做好实名、审计与投诉通道。
- **保密**：`SESSION_SECRET` / `CRYPTO_SECRET` / `.env` 不提交 git、不贴公网。

---

## 八、渠道真伪检测 · 日常自查清单（降智预警）

内置探针（§5.2）即按下列行为指纹体检；人工快速自查同样适用：

| # | 检查点 | 判读 |
| --- | --- | --- |
| 1 | **usage 字段命名** | OpenAI 端点却返回 Anthropic 命名字段（`input_tokens`/`claude_cache_*`）→ 协议转换中转，警惕 |
| 2 | **知识截止** | 问"你的知识截止到什么时候"，旗舰模型日期对不上 → 被换模型了 |
| 3 | **reasoning_tokens** | 非 o 系列模型却每次返回该字段 → o 系列冒充 |
| 4 | **延迟异常低** | 号称 gpt-4o 却 200ms 出结果（正常 1s+）→ 嫌疑 |
| 5 | **价格异常便宜** | 号称 Opus 却按 $0.5/M 收费 → 掺水高概率 |
| 6 | **同题逐字同答** | 相同问题重复提问返回完全一致答案 → 命中缓存/固定模板 |

处置建议：疑似降智渠道先降低用量上限、缩短冷却（等价于降权），确认掺水立即移除；
新渠道上架前必须先过一轮探针体检。

---

## 九、文件说明

| 文件 | 用途 |
| --- | --- |
| `docker-compose.yml` | 生产版：new-api + MySQL 8 + Redis 7.4（独立网络 `newapi-net`） |
| `docker-compose.sqlite.yml` | 快速版：new-api + SQLite（试跑用） |
| `.env.example` | 环境变量模板（密钥、数据库密码、Cookie/端口，含醒目提示） |
| `.gitignore` | 忽略 `.env` 与数据目录，防密钥/数据入库 |
| `../../config/default/newapi.yml` | 本项目 backend 调度/探针对接配置（默认关闭） |

### 版本锁定一览

| 镜像 | 锁定 tag | 依据 |
| --- | --- | --- |
| `calciumion/new-api` | `v0.10.7` | 2026-02 发布，v0.x 正式稳定线最新；v1.0.0 尚在 RC（rc.27），不用于生产 |
| `mysql` | `8.0` | 任务约定 8.0.x 线（可再固定补丁版；8.0 EOL 2026-10，后续评估 8.4 LTS） |
| `redis` | `7.4-alpine` | 锁定 7.x 线内 7.4 |
