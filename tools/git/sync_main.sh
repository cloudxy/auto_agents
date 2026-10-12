#!/usr/bin/env bash
# 分支切换后自动同步 main：fetch origin/main 并合并进当前分支
#
# 触发：git post-checkout（经 pre-commit 安装，hook id: sync-main）
# 安装：uv run pre-commit install --hook-type post-checkout
# 临时跳过一次：SKIP=sync-main git checkout <branch>
# 手动执行：bash tools/git/sync_main.sh
#
# 设计：fail-open —— checkout 已经发生，任何异常只告警不阻断（exit 0）
#
# 只自动合并「自己的工作分支」，以下情形只提示、不合并（避免切过去看一眼就静默多出一个
# merge commit，下次 push 带上去）：
# - 分支名命中 AUTO_SYNC_MAIN_SKIP（空格分隔的 glob，缺省 "release/* hotfix/* dependabot/* renovate/*"）；
# - 分支最新提交的作者邮箱不是本机 git user.email（别人的分支，例如拉下来 review 的 PR 分支）。
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

# 发布 / 机器人分支：只提示
SKIP_PATTERNS="${AUTO_SYNC_MAIN_SKIP:-release/* hotfix/* dependabot/* renovate/*}"
set -f  # 模式按字面交给 case，不做文件名展开
for pattern in $SKIP_PATTERNS; do
    # shellcheck disable=SC2254
    case "$CURRENT" in
        $pattern) set +f; skip "${CURRENT} 命中 AUTO_SYNC_MAIN_SKIP（${pattern}），需要时手动 git merge origin/${MAIN_BRANCH}" ;;
    esac
done
set +f

# 别人的分支：只提示（本机没配 user.email 时不做这层判断）
ME="$(git config user.email 2>/dev/null || true)"
TIP_AUTHOR="$(git log -1 --format=%ae HEAD 2>/dev/null || true)"
if [ -n "$ME" ] && [ -n "$TIP_AUTHOR" ] && [ "$ME" != "$TIP_AUTHOR" ]; then
    skip "${CURRENT} 最新提交作者是 ${TIP_AUTHOR}（不是你），不自动合并；需要时手动 git merge origin/${MAIN_BRANCH}"
fi

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
