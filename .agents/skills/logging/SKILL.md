---
name: logging
description: >-
  日志规范 - 分级、格式、轮转、脱敏。当用户添加日志记录、排查日志输出、
  或配置日志存储与轮转策略时触发。
  适用于新增业务日志点、实现敏感信息脱敏、按模块分类存储日志，
  以及配置日志轮转周期和爬虫请求日志等场景。
trigger: >-
  添加或修改日志、日志分级调整、脱敏规则配置、日志轮转设置、
  日志目录结构变更
---

# 日志规范

事实源：`config/default/log.yml` + `platform_core/logger.py`。sink 由 `init_log()` 按 `LOGGERS` 挂载。

```python
from platform_core.logger import get_logger
logger = get_logger("api")          # 或 service.{module} / spider / tenant
```

## 分级

| 级别 | 用途 |
|------|------|
| DEBUG | 开发调试，生产不输出 |
| INFO | 业务关键节点（请求进入、写入、用户操作） |
| WARNING | 可恢复异常（缺失、降级、重试） |
| ERROR | 需人工介入 |

## 必须 / 禁止

必须：请求进出、业务关键节点、写入成败、异常带堆栈、爬虫每次请求的 URL+状态码。

禁止：生产 DEBUG、密码/密钥/Token、完整身份证/银行卡。

R10：`backend/services/*.py` 的 public 方法第一行必须是 `logger.info` / `logger.debug` 等（`scripts/check-arch.sh` 启发式：def 下一行匹配 `logger.`）。

## 脱敏

```
手机号：13812345678 → 138****5678
身份证：310101199001011234 → 310**************1234
密码 / API Key：不记录；URL 要剥 query 里的 key（见 openweather.strip_appid）
```

## 存储（与 log.yml 一致）

```
logs/
├── global/app.log
├── api/api.log
├── admin/admin.log
├── official/official.log
├── error/error.log      # level ERROR，retention 90
└── spider/spider.log    # 与 run_spider.py / 后端任务日志偏移同一文件
```

轮转、大小、保留天数只改 `config/default/log.yml`（及 env 覆盖）的 `max_size` / `retention` / `rotate_hour`，不要在业务代码里另挂 sink。

格式：`LOG_FORMAT`（含 `{extra[request_id]}`，中间件 `contextualize`）。

## 爬虫

每次请求：URL、HTTP 状态码。结束统计走现有 extension / 任务回调，不要新建第二套日志根目录。
