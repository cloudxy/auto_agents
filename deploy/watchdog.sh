#!/bin/bash
# ============================================================================
# watchdog.sh — 后端僵死看门狗（T11）
#
# 背景：2026-08 冻结事故（docs/ops/incident-2026-08-backend-freeze.md）——
# 进程僵死时既不崩溃也不退出，compose 的 restart 策略永不触发（它只覆盖
# "进程退出"型故障）。本脚本轮询深探测健康端点（/api/v1/health/deep，
# MySQL + Redis 任一失败返回 503），连续 N 次失败判定僵死嫌疑：
# 记录告警 + 可选 webhook，并对目标 PID 执行 kill -9（配合
# restart: unless-stopped 由编排器拉起，或按 WATCHDOG_RESTART 显式拉起）。
#
# 安全缺省：只告警不杀进程（WATCHDOG_RESTART=0）。开启自动处置的方式与
# 风险说明见 docs/ops/deploy.md「看门狗」一节。
#
# 配置（全部环境变量外置，无硬编码端口/密钥）：
#   WATCHDOG_URL          必填。健康端点完整 URL
#                         例：http://127.0.0.1:9111/api/v1/health/deep
#   WATCHDOG_INTERVAL     轮询间隔秒，默认 10
#   WATCHDOG_TIMEOUT      单次探测超时秒，默认 5
#   WATCHDOG_FAILURES     连续失败判定阈值，默认 3
#   WATCHDOG_PID          目标进程 PID（第一优先）
#   WATCHDOG_PID_FILE     PID 文件路径，取首行（第二优先）
#   WATCHDOG_PID_PATTERN  pgrep -f 兜底匹配模式，默认 "run_backend.py"
#                         （第三优先；slim 容器镜像无 pgrep，容器内前两者必填其一）
#   WATCHDOG_RESTART      处置开关，默认 0：
#                         0 = 只告警，不 kill 不拉起（安全缺省：深探测失败也可能
#                             是 MySQL/Redis 挂了，此时杀 backend 无益且掩盖问题；
#                             宿主机直跑场景杀了没人拉起 = 把僵死升级成宕机）
#                         1 = kill -9 目标 PID 后执行 WATCHDOG_RESTART_CMD 拉起
#   WATCHDOG_RESTART_CMD  拉起命令（WATCHDOG_RESTART=1 时必填；compose 场景
#                         用幂等命令，如 'docker compose -f <file> up -d backend'，
#                         容器 restart 策略与该命令双保险）
#   WATCHDOG_ALERT_COOLDOWN  同一持续故障的告警冷却秒数，默认 300：
#                         冷却窗口内不重发 webhook / 不重打 ALERT（仅记一行简短
#                         WARN 留痕），防持续失败时告警轰炸；kill/拉起动作不受
#                         冷却影响（kill+restart 模式的核心使命是恢复）
#   WATCHDOG_LOG          事件日志文件；缺省输出 stdout（由 docker/系统日志接管）
#   WATCHDOG_WEBHOOK_URL  可选。告警 webhook（POST application/json，
#                         尽力而为，投递失败不影响主流程）
#                         payload（B4 规范化，字段断言见 docs/ops/deploy.md §4）：
#                           event=watchdog.frozen-suspected / severity=P1 /
#                           timestamp(ISO8601) / host / url / pid /
#                           failures / action(kill+restart|alert-only) /
#                           detail / hint(处理指引)
#   WATCHDOG_DRY_RUN      1 = 单轮探测 + 打印判定与"将执行的动作"，
#                         不 kill / 不重启 / 不发告警（验证语法与逻辑用）
#
# 退出码：0 正常（健康 / 收到退出信号）；1 参数错误；2 dry-run 判定僵死嫌疑
# bash 3.2 兼容：无关联数组 / 无 ${var,,} / 无 mapfile / 无进程替换；
# 且中文语境的变量引用一律 ${VAR} 花括号（裸 $VAR 后跟全角标点的首字节 0xef
# 会被 bash 3.2 并入变量名 → set -u 下 unbound 崩溃，B4 演练实测踩中）
# ============================================================================
set -u

INTERVAL="${WATCHDOG_INTERVAL:-10}"
TIMEOUT="${WATCHDOG_TIMEOUT:-5}"
FAILURES="${WATCHDOG_FAILURES:-3}"
PID_PATTERN="${WATCHDOG_PID_PATTERN:-run_backend.py}"
RESTART="${WATCHDOG_RESTART:-0}"
RESTART_CMD="${WATCHDOG_RESTART_CMD:-}"
ALERT_COOLDOWN="${WATCHDOG_ALERT_COOLDOWN:-300}"
LAST_ALERT_TS=0
LOG_FILE="${WATCHDOG_LOG:-}"
WEBHOOK_URL="${WATCHDOG_WEBHOOK_URL:-}"
DRY_RUN="${WATCHDOG_DRY_RUN:-0}"
URL="${WATCHDOG_URL:-}"

RUNBOOK="处理指引：先看后端日志尾部与 MySQL/Redis 状态（docs/ops/deploy.md 看门狗一节）；复盘背景 docs/ops/incident-2026-08-backend-freeze.md"

log() {
    # log <级别> <内容> —— 统一 ISO8601 时间戳；输出到 WATCHDOG_LOG 或 stdout
    local line
    line="$(date '+%Y-%m-%dT%H:%M:%S%z') [$1] $2"
    if [ -n "$LOG_FILE" ]; then
        echo "$line" >> "$LOG_FILE" || echo "$line"
    else
        echo "$line"
    fi
}

probe() {
    # 探测 $URL：HTTP 2xx 视为健康（深探测端点在依赖故障时返回 503 → 不健康）。
    # 优先 curl（宿主机/绝大多数镜像可用）；slim 镜像无 curl 时回落 python。
    if command -v curl > /dev/null 2>&1; then
        curl -fsS -m "$TIMEOUT" -o /dev/null "$URL" 2> /dev/null
        return $?
    fi
    local py=""
    if command -v python3 > /dev/null 2>&1; then
        py=python3
    elif command -v python > /dev/null 2>&1; then
        py=python
    else
        log ERROR "无可用探测工具（curl 与 python 均缺失），本次按失败计"
        return 1
    fi
    "$py" - "$URL" "$TIMEOUT" <<'PYEOF'
import sys
import urllib.request

url, timeout = sys.argv[1], float(sys.argv[2])
try:
    urllib.request.urlopen(url, timeout=timeout).read()
    sys.exit(0)
except Exception:
    sys.exit(1)
PYEOF
    return $?
}

resolve_pid() {
    # 依次：显式 PID → PID 文件 → pgrep 兜底；均未命中输出空串
    if [ -n "${WATCHDOG_PID:-}" ]; then
        echo "$WATCHDOG_PID"
        return 0
    fi
    if [ -n "${WATCHDOG_PID_FILE:-}" ] && [ -f "$WATCHDOG_PID_FILE" ]; then
        local pid_from_file
        pid_from_file="$(head -n 1 "$WATCHDOG_PID_FILE" 2> /dev/null | tr -d '[:space:]')"
        if [ -n "$pid_from_file" ]; then
            echo "$pid_from_file"
            return 0
        fi
    fi
    if command -v pgrep > /dev/null 2>&1; then
        pgrep -f "$PID_PATTERN" | head -n 1
        return 0
    fi
    echo ""
}

json_escape() {
    # JSON 字符串值转义（bash 3.2 兼容：仅处理反斜杠与双引号；配置值不含控制字符）
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "$s"
}

send_webhook() {
    # 告警动作（SRE 纪律：告警必须带处理指引，否则等于噪音）
    # 入参 $1 = 判定时解析到的目标 PID（可能为空 → JSON null）
    # payload 字段规范（B4）：severity/timestamp/host/url/pid/hint 为必带，
    # 接收端断言见 docs/ops/deploy.md §4「告警 payload 契约」
    [ -z "$WEBHOOK_URL" ] && return 0
    command -v curl > /dev/null 2>&1 || return 0
    local pid="${1:-}"
    local host
    host="${HOSTNAME:-$(hostname 2> /dev/null || echo unknown)}"
    local pid_json="null"
    [ -n "$pid" ] && pid_json="\"$pid\""
    local payload
    payload='{"event":"watchdog.frozen-suspected","severity":"P1","timestamp":"'"$(date '+%Y-%m-%dT%H:%M:%S%z')"'","host":"'"$(json_escape "$host")"'","url":"'"$(json_escape "$URL")"'","pid":'"$pid_json"',"failures":"'"$FAILURES"'","action":"'"$([ "$RESTART" = "1" ] && echo 'kill+restart' || echo 'alert-only')"'","detail":"deep probe failed '"$FAILURES"' times in a row","hint":"'"$(json_escape "$RUNBOOK")"'"}'
    curl -fsS -m 5 -X POST -H 'Content-Type: application/json' \
        -d "$payload" "$WEBHOOK_URL" > /dev/null 2>&1 \
        || log WARN "webhook 投递失败（${WEBHOOK_URL}）"
}

act() {
    # 判定僵死嫌疑后的动作：告警（带冷却）→ RESTART=1 时 kill -9 + 拉起
    # B4 演练修正：kill 只发生在 WATCHDOG_RESTART=1（此前 RESTART=0 也照杀，
    # 与"安全缺省只告警"的文档承诺相悖——宿主机直跑场景杀了没人拉起，
    # 把僵死升级成宕机）
    local pid
    pid="$(resolve_pid)"

    if [ "$DRY_RUN" = "1" ]; then
        echo "[dry-run] 判定：僵死嫌疑（连续 ${FAILURES} 次深探测失败）"
        if [ "$RESTART" = "1" ]; then
            if [ -n "$pid" ] && kill -0 "$pid" 2> /dev/null; then
                echo "[dry-run] 将执行：告警 + kill -9 ${pid} + 拉起"
            else
                echo "[dry-run] 将执行：告警 + 拉起（目标 PID 未解析或已消失，跳过 kill）"
            fi
            echo "[dry-run] 拉起命令：${RESTART_CMD:-<未配置 WATCHDOG_RESTART_CMD>}"
        else
            echo "[dry-run] 将执行：仅告警（WATCHDOG_RESTART=0 安全缺省，不 kill 不拉起）"
        fi
        return 0
    fi

    # 告警冷却：窗口内不重发 webhook / 不重打 ALERT，仅留一行简短 WARN
    # （B4 演练实测：无冷却时持续失败每阈值轮轰炸一次，7 秒 3 轮）
    local now
    now=$(date +%s)
    if [ $((now - LAST_ALERT_TS)) -lt "$ALERT_COOLDOWN" ]; then
        log WARN "冷却窗口（${ALERT_COOLDOWN}s）内再次触发，不重发告警；动作继续"
    else
        # 注：中文语境变量一律 ${VAR} 花括号——bash 3.2 在 UTF-8 下会把紧跟变量的
        # 多字节字符首字节（如全角括号 0xef）并入变量名，set -u 判 unbound 直接崩
        # （B4 演练实测踩中：act() 首次真实执行即死于本行，dry-run 路径不经过此处）
        log ALERT "僵死嫌疑：连续 ${FAILURES} 次深探测失败（${URL}）。${RUNBOOK}"
        send_webhook "$pid"
        LAST_ALERT_TS=$now
    fi

    if [ "$RESTART" != "1" ]; then
        log INFO "仅告警模式（WATCHDOG_RESTART=0）：未 kill 未拉起（安全缺省）"
        return 0
    fi

    if [ -n "$pid" ] && kill -0 "$pid" 2> /dev/null; then
        if kill -9 "$pid" 2> /dev/null; then
            log INFO "已 kill -9 pid=${pid}（拉起由 WATCHDOG_RESTART_CMD / 编排器负责）"
        else
            log WARN "kill -9 pid=${pid} 失败（权限不足或进程刚消失）"
        fi
    else
        log WARN "目标 PID 未解析（WATCHDOG_PID / WATCHDOG_PID_FILE / pgrep 均未命中），跳过 kill 仅拉起"
    fi

    if [ -z "$RESTART_CMD" ]; then
        log ERROR "WATCHDOG_RESTART=1 但未配置 WATCHDOG_RESTART_CMD，无法拉起"
    else
        sh -c "$RESTART_CMD" > /dev/null 2>&1 &
        log INFO "已触发拉起命令：$RESTART_CMD"
    fi
}

main() {
    if [ -z "$URL" ]; then
        echo "用法错误：必须设置 WATCHDOG_URL（健康端点完整 URL，含端口）" >&2
        echo "示例：WATCHDOG_URL=http://127.0.0.1:9111/api/v1/health/deep WATCHDOG_DRY_RUN=1 bash scripts/watchdog.sh" >&2
        exit 1
    fi

    log INFO "看门狗启动：url=$URL interval=${INTERVAL}s timeout=${TIMEOUT}s 阈值=${FAILURES}次 restart=${RESTART} dry_run=${DRY_RUN}"

    # dry-run：单轮探测 + 打印判定与动作计划，验证语法与逻辑（不进入循环）
    if [ "$DRY_RUN" = "1" ]; then
        if probe; then
            echo "[dry-run] 探测成功：$URL → 健康，不触发任何动作"
            exit 0
        fi
        log WARN "深探测失败（dry-run 单轮）：$URL"
        act
        exit 2
    fi

    trap 'log INFO "收到退出信号，看门狗停止"; exit 0' TERM INT

    count=0
    acted=0
    while :; do
        if probe; then
            if [ "$acted" = "1" ]; then
                # 处置→恢复 闭环完成的自证（B4 演练依赖此行确认闭环）
                log INFO "深探测恢复（此前已触发处置动作，事件闭环）"
                acted=0
            elif [ "$count" -gt 0 ]; then
                log INFO "探测恢复（此前连续失败 ${count} 次，未达阈值 ${FAILURES}，未触发动作）"
            fi
            count=0
        else
            count=$((count + 1))
            log WARN "深探测失败（连续第 ${count}/${FAILURES} 次）：$URL"
            if [ "$count" -ge "$FAILURES" ]; then
                act
                # 动作后清零重新计数：同一僵死事件只告警一轮，避免轰炸
                count=0
                acted=1
            fi
        fi
        sleep "$INTERVAL"
    done
}

main
