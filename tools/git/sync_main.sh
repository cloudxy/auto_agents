#!/usr/bin/env bash
# 分支切换后自动同步 main：fetch origin/main 并合并进当前分支
#
# 触发：git post-checkout（经 pre-commit 安装，hook id: sync-main）
# 安装：uv run pre-commit install --hook-type post-checkout
# 临时跳过一次：SKIP=sync-main git checkout <branch>
# 手动执行：bash tools/git/sync_main.sh
#
# 设计：fail-open —— checkout 已经发生，任何异常只告警不阻断（exit 0）
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TAG="[sync-main]"
MAIN_BRANCH="${AUTO_SYNC_MAIN_BRANCH:-main}"

say() { echo "$TAG $*"; }
skip() { say "跳过：$*"; exit 0; }

# --- 触发条件过滤 ---
# PRE_COMMIT_CHECKOUT_TYPE：1=分支切换，0=单文件检出；手动执行时视为分支切换
CHECKOUT_TYPE="${PRE_COMMIT_CHECKOUT_TYPE:-1}"
[ "$CHECKOUT_TYPE" = "1" ] || skip "非分支切换（checkout_type=${CHECKOUT_TYPE}）"

# merge / rebase / cherry-pick 进行中不掺和
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null || true)"
[ -n "$GIT_DIR" ] || exit 0
for state in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD; do
    [ -e "$GIT_DIR/$state" ] && skip "仓库处于 $state 进行中"
done

CURRENT="$(git branch --show-current 2>/dev/null || true)"
[ -n "$CURRENT" ] || skip "detached HEAD"
[ "$CURRENT" != "$MAIN_BRANCH" ] || skip "当前就是 ${MAIN_BRANCH}，无需自合并"

# 工作区有未提交改动时不自动合并（避免混入），提示手动处理
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    skip "工作区有未提交改动，请手动执行 git merge origin/$MAIN_BRANCH"
fi

# --- 拉取远端 main ---
if ! git fetch origin "$MAIN_BRANCH" --quiet 2>/dev/null; then
    skip "git fetch origin ${MAIN_BRANCH} 失败（离线？），请手动同步"
fi

TARGET_REF="origin/$MAIN_BRANCH"
TARGET="$(git rev-parse --verify -q "$TARGET_REF" || true)"
[ -n "$TARGET" ] || skip "没有 ${TARGET_REF}"

# 当前分支已包含 main 全部提交则无事可做（静默退出）
if git merge-base --is-ancestor "$TARGET" HEAD 2>/dev/null; then
    exit 0
fi

# --- 合并（可 fast-forward），冲突则回滚交还用户 ---
say "合并 ${TARGET_REF}（$(git rev-parse --short "$TARGET")）→ ${CURRENT}"
if git merge --no-edit "$TARGET_REF" >/dev/null 2>&1; then
    say "完成：$CURRENT 已同步 $MAIN_BRANCH"
else
    git merge --abort >/dev/null 2>&1
    say "存在冲突，已自动回滚。请手动处理：git merge $TARGET_REF"
fi
exit 0
