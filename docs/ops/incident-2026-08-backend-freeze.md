# 事故复盘：2026-08 后端整进程冻结（stdout 管道阻塞 + 事件循环僵死）

> 状态：补记复盘（事故当时未留档，时线以 git 历史与代码注释为锚点重建，未覆盖处显式标注"未留档"）。
> 撰写：SRE（工单 T11）｜日期：2026-09-05
> 关联改进：`scripts/watchdog.sh`（僵死看门狗）、`/api/v1/health/deep`（深探测）、`docs/ops/deploy.md`

## 1. 摘要

后端进程在运行中整进程冻结：进程存活、端口仍在监听，但所有 HTTP 请求无响应；
不崩溃、不退出、不产生任何日志。compose 的 restart 策略（只覆盖"进程退出"型
故障）对此完全无效，且当时的健康探测是浅探测（恒 200），外部无法发现——
**服务事实不可用，但所有自动化信号都是绿的。**

## 2. 时线（以 git 锚点重建；标注 ※ 的为未留档、依代码注释还原）

| 时间 | 事件 | 证据锚点 |
|---|---|---|
| 2026-08 中下旬 ※ | 冻结发生：后端无响应，进程不退出；触发场景为 stdout 接到无人排水的管道（IDE 终端管道、`| head` 类读端退出） | `run_backend.py` `_bridge_uvicorn_logging` docstring（c1b302a 引入，追述描述） |
| 当时 ※ | 无告警、无深探测：浅探测 `/api/v1/health` 恒 200；`docker` HEALTHCHECK 打的正是该浅端点 | 旧 Dockerfile HEALTHCHECK（本票 T11 修改前） |
| 2026-08-31 03:07 | 修复前置：12+ 处同步 `redis_client()` 直调异步化（含健康探活），消除事件循环内的已知阻塞点（R11） | commit `3e8e1fc` |
| 2026-09-05 14:07 | 根因修复：uvicorn access/error 日志接管改投 loguru（enqueue 后台排水线程 + 文件 sink），`log_config=None` 防止 uvicorn 自带 dictConfig 重挂同步 StreamHandler；同 commit 修复 `--reload` 子进程不继承接管的问题（工厂字符串路径） | commit `c1b302a`（工单 T3）、`platform_core/logger.py` `enqueue=True` |
| 2026-09-05 | 本票（T11）：补复盘 + 深探测 `/api/v1/health/deep`（DB+Redis 任一失败 503）+ compose/镜像健康检查切深探测 + 僵死看门狗 `scripts/watchdog.sh` | 本文件、`docker-compose.yml`、`Dockerfile` |

## 3. 根因分析

### 故障链

```
uvicorn access log（每请求一行）经默认 StreamHandler 同步写 stdout
  → stdout 是无人排水的管道（读端退出：IDE 终端关闭、`| head` 结束）
  → 两种形态：
     a) 读端还开着但不再读：管道缓冲区（~64KB）写满后 write() 永久阻塞
     b) 读端已关闭：write() 触发 EPIPE（BrokenPipeError）
  → 形态 a 的 write() 阻塞发生在事件循环线程内
  → 整个事件循环卡死：不响应任何请求、不执行任何回调（含日志回调）
  → 进程不退出 → restart 策略永不触发 → 永久僵死
```

### 为什么 loguru 的 enqueue 没有兜住

`platform_core/logger.py` 早已 `enqueue=True`（后台排水线程写 sink），但它只
覆盖 **loguru 自己的 sink**。uvicorn 的 access/error 日志走标准 logging，
默认 StreamHandler 直接同步写 stdout——这条旁路在 2026-09-05 之前一直存在。

### 为什么当时发现不了（发现盲区，对事不对人）

1. 浅探测 `/api/v1/health` 不探依赖、恒 200——端口在监听就"健康"；
   事实上僵死进程端口也在监听（accept 队列堆满），浅探测同样恒绿。
   **只有"真正处理一个请求并触达依赖"的深探测 + 状态码语义才能暴露僵死。**
2. 僵死进程不退出 → compose restart 策略无感知。
3. 事件循环卡死 → 连"卡死前最后一刻"的日志都写不出（日志回调也在循环里）。
4. 无运维告警通道（notify.yml 是业务通知，不是运维告警）。

## 4. 已修复部分（截至本票）

| 修复 | 内容 | 锚点 |
|---|---|---|
| 排水线程 | loguru `enqueue=True`（后台线程排水写文件 sink） | `platform_core/logger.py:79`（早已有，覆盖面修正见下） |
| 日志接管 | uvicorn access/error 清空自有 handler，经 propagate 上浮到挂单一 handler 的 "uvicorn" 父 logger → 转投 loguru；`uvicorn.run(log_config=None)` 防止 dictConfig 重挂 StreamHandler；幂等（父进程与 reload 子进程各挂一次） | `run_backend.py` `_bridge_uvicorn_logging()` |
| reload 修复 | `--reload` 必须传工厂字符串（`run_backend:create_app_for_reload`），子进程内重做 init + 日志接管（此前子进程日志退化为裸 stderr 且 access log 整批丢失） | `run_backend.py` `create_app_for_reload()`（c1b302a，T3） |
| 事件循环阻塞点清理 | 12+ 处同步 `redis_client()` 直调改异步门面（R11），含健康探活 | `3e8e1fc` |
| 本票：深探测 | `/api/v1/health/deep`：MySQL SELECT 1 + Redis PING，任一失败 **503**（旧端点失败仍 200，body 才写 unhealthy，编排器按状态码判定等于恒绿）；compose/Dockerfile HEALTHCHECK 切换至深探测 | `backend/app/api/v1/health.py`、`docker-compose.yml`、`Dockerfile` |
| 本票：看门狗 | `scripts/watchdog.sh`：轮询深探测，连续 N 次失败 → 告警（日志 + 可选 webhook，带处理指引）+ `kill -9` + 按环境变量决定是否拉起（默认只告警）。兜住"僵死不退出"这一 restart 策略覆盖不到的形态 | `scripts/watchdog.sh` |

## 5. 残留风险（诚实清单）

1. **事件循环内同步阻塞调用可能复发**：新增代码若在 async 路径里做同步 IO/
   无超时网络调用/重 CPU 计算，会复现同类僵死。R11 红线 + check-arch.sh 只
   覆盖 redis 直调这一已知模式，不能覆盖所有阻塞形态。
2. **stdout 旁路未彻底消灭**：接管覆盖 uvicorn 三类日志；任何第三方库直接
   `print` / 拿 `sys.stdout` 写大量数据，在管道无人排水的场景仍可能阻塞
   （在事件循环线程内触发时同样僵死）。容器内 stdout 由 docker 接管排水，
   风险主要存在于宿主机直跑场景。
3. **深探测只探 MySQL + Redis**：存储（/storage）与下游 LLM 未纳入 deep 判定
   （它们故障时是否重启后端是另一道权衡，暂不进 503 判定，避免误杀）。
4. **看门狗 kill 路径未在生产演练**：dry-run 验证了探测与判定逻辑，但
   "kill -9 后编排器确实拉起、服务恢复"的完整闭环需在演练环境实测
   （见 `docs/ops/deploy.md` 回滚与演练一节）。
5. **告警通道仍是可选 webhook + 本地日志**：无值班/升级链路（完整监控栈
   不在 T11 范围，遗留项见 §6）。

## 6. 改进项（有责任口径，避免复盘等于没做）

| # | 改进项 | 状态/责任 |
|---|---|---|
| 1 | 深探测端点 + 编排健康检查切换 | 本票完成（T11） |
| 2 | 僵死看门狗脚本 | 本票完成（T11），生产开启方式见 deploy.md |
| 3 | 看门狗 kill→拉起→恢复 闭环演练 | 待办：下次发布前在演练环境执行（deploy.md 演练清单） |
| 4 | 监控四件套（可用性/延迟/饱和度/业务指标）+ 告警分级与值班 | 待办：独立工单（T11 只留告警动作接口：WATCHDOG_WEBHOOK_URL） |
| 5 | 深探测纳入存储探活（或独立的 readiness 细分） | 待办：与容量评估一并做 |

## 7. 经验教训（对流程的追问，不对人）

- **"端口在监听"不等于"服务活着"**：健康检查必须真实处理一个请求并触达
  关键依赖，且失败必须有状态码语义（503），否则编排器视角恒绿。
- **restart 策略只覆盖退出型故障**：僵死型故障需要外部主动探测 + 强杀，
  两者缺一不可。
- **日志基础设施的故障模式要纳入设计**：日志是可观测性的根，根的排水
  （sink/管道）本身就是单点。
- **事故当时就要留档时线**：本复盘一半内容靠 git 考古重建（※ 标注），
  细节（首次发现时间、影响时长、恢复手段）已不可考。
