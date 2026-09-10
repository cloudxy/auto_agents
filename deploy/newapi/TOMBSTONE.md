# TOMBSTONE · deploy/newapi

> T-20 / ADR-0014 / FR-72。本目录 **不是运行时**。
> 本文件不含任何上游 Key / AccessToken / DSN / 口令。

## 状态

new-api **已退出运行时**（进程停止）。平台 LLM 数据面默认 `LLM.DATA_PLANE=litellm`（LiteLLM Proxy，`deploy/litellm/`）。

禁止：

- 把本目录服务写回根 `docker-compose.yml`
- 把 `NEWAPI.ENABLED=true` 当完成态或运行时开关（该键恒 false，读路径已删）
- 把 `LLM.DATA_PLANE=providers` 当完成态（仅 expand 回滚窗）
- 把渠道组 / 中转令牌写成当前可买（Q-RELAY / Q-AGPL 未关，本墓碑不代选）

## 不要启动

```bash
# 退役夹具：若仍有容器，停掉并确认无名 newapi 容器、3000 无监听
docker compose -f deploy/newapi/docker-compose.yml down --remove-orphans
docker compose -f deploy/newapi/docker-compose.sqlite.yml down --remove-orphans
docker ps -a --filter name=newapi
```

本目录 compose 文件仅作历史编排/回滚窗文物。Wave L 完成后 **不得**再 `up` 当作平台路径出口。

## 运行时替代

| 原 new-api 职责 | 现在 |
|---|---|
| 平台路径 chat | LiteLLM `POST /v1/chat/completions`（`LITELLM.BASE_URL`） |
| 值班列表 / 空态 / 降级 | `/api/v1/newapi/*` 一周期保留；列表来自网关模型（FR-71） |
| 窗口 / 探针产品规则 | `RELAY.*`（`config/default/relay.yml`） |
| 规划无自有行 outbound | 网关 URL，不是 `https://pub`，不是 new-api |

## 回滚（已演练口径，不是完成态）

1. 数据面回滚：`LLM.DATA_PLANE=providers`（yml 或 `AUTO_AGENTS_LLM__DATA_PLANE`）。这 **不是** T-20 完成态。
2. **不要**把 new-api 请回运行时当常规回滚。SALT/网关密钥仍只活在 LiteLLM 密钥面。

值班页继续走 FR-71 网关列表或 71.2/71.3，不依赖本目录管理面。
