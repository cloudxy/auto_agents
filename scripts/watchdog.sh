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
#   WATCHDOG_RESTART      1 = kill 后执行 WATCHDOG_RESTART_CMD 自动拉起；
#                         默认 0 只告警（安全缺省）
#   WATCHDOG_RESTART_CMD  拉起命令（WATCHDOG_RESTART=1 时必填）
#   WATCHDOG_LOG          事件日志文件；缺省输出 stdout（由 docker/系统日志接管）
#   WATCHDOG_WEBHOOK_URL  可选。告警 webhook（POST application/json，
#                         尽力而为，投递失败不影响主流程）
#   WATCHDOG_DRY_RUN      1 = 单轮探测 + 打印判定与"将执行的动作"，
#                         不 kill / 不重启 / 不发告警（验证语法与逻辑用）
#
# 退出码：0 正常（健康 / 收到退出信号）；1 参数错误；2 dry-run 判定僵死嫌疑
# bash 3.2 兼容：无关联数组 / 无 ${var,,} / 无 mapfile / 无进程替换
# ============================================================================
set -u

INTERVAL="${WATCHDOG_INTERVAL:-10}"
TIMEOUT="${WATCHDOG_TIMEOUT:-5}"
FAILURES="${WATCHDOG_FAILURES:-3}"
PID_PATTERN="${WATCHDOG_PID_PATTERN:-run_backend.py}"
RESTART="${WATCHDOG_RESTART:-0}"
RESTART_CMD="${WATCHDOG_RESTART_CMD:-}"
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

send_webhook() {
    # 告警动作（SRE 纪律：告警必须带处理指引，否则等于噪音）
    [ -z "$WEBHOOK_URL" ] && return 0
    command -v curl > /dev/null 2>&1 || return 0
    local payload
    payload='{"source":"watchdog.sh","severity":"P1","target":"'"$URL"'","verdict":"frozen-suspected","detail":"deep probe failed '"$FAILURES"' times in a row","hint":"'"$RUNBOOK"'"}'
    curl -fsS -m 5 -X POST -H 'Content-Type: application/json' \
        -d "$payload" "$WEBHOOK_URL" > /dev/null 2>&1 \
        || log WARN "webhook 投递失败（$WEBHOOK_URL）"
}

act() {
    # 判定僵死嫌疑后的动作：告警 → kill -9 → 按策略拉起
    local pid
    pid="$(resolve_pid)"

    if [ "$DRY_RUN" = "1" ]; then
        echo "[dry-run] 判定：僵死嫌疑（连续 ${FAILURES} 次深探测失败）"
        if [ -n "$pid" ] && kill -0 "$pid" 2> /dev/null; then
            echo "[dry-run] 将执行：kill -9 ${pid}"
        else
            echo "[dry-run] 将执行：kill 阶段只告警（目标 PID 未解析或已消失）"
        fi
        if [ "$RESTART" = "1" ]; then
            echo "[dry-run] 将执行拉起：${RESTART_CMD:-<未配置 WATCHDOG_RESTART_CMD>}"
        else
            echo "[dry-run] 拉起策略：仅告警不重启（WATCHDOG_RESTART=0 安全缺省）"
        fi
        return 0
    fi

    log ALERT "僵死嫌疑：连续 ${FAILURES} 次深探测失败（$URL）。$RUNBOOK"
    send_webhook

    if [ -n "$pid" ] && kill -0 "$pid" 2> /dev/null; then
        if kill -9 "$pid" 2> /dev/null; then
            log INFO "已 kill -9 pid=$pid（restart 策略/编排器负责拉起）"
        else
            log WARN "kill -9 pid=$pid 失败（权限不足或进程刚消失）"
        fi
    else
        log WARN "目标 PID 未解析（WATCHDOG_PID / WATCHDOG_PID_FILE / pgrep 均未命中），仅告警未 kill"
    fi

    if [ "$RESTART" = "1" ]; then
        if [ -z "$RESTART_CMD" ]; then
            log ERROR "WATCHDOG_RESTART=1 但未配置 WATCHDOG_RESTART_CMD，无法拉起"
        else
            sh -c "$RESTART_CMD" > /dev/null 2>&1 &
            log INFO "已触发拉起命令：$RESTART_CMD"
        fi
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
    while :; do
        if probe; then
            if [ "$count" -gt 0 ]; then
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
            fi
        fi
        sleep "$INTERVAL"
    done
}

main
