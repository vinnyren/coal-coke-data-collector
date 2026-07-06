#!/usr/bin/env bash
# scripts/openclaw-bootstrap.sh — 远程入口（curl|bash 抓取执行）：
# clone（不存在）或 pull（已存在）公开仓到 $COAL_HOME，再调 scripts/install.sh。
set -euo pipefail

REPO_URL="${COAL_REPO_URL:-https://github.com/vinnyren/coal-coke-data-collector.git}"
TARGET="${COAL_HOME:-$HOME/.openclaw-skills/coal-coke-data-collector}"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "错误：需要 $1，请先安装。" >&2; exit 1; }
}
need git

# 决定 clone 还是 pull
if [ -d "$TARGET/.git" ]; then
  ACTION="pull"
else
  ACTION="clone"
fi

if [ "${COAL_BOOTSTRAP_DRYRUN:-}" = "1" ]; then
  echo "DRYRUN: action=$ACTION target=$TARGET url=$REPO_URL"
  exit 0
fi

if [ "$ACTION" = "pull" ]; then
  echo "更新已存在的仓库：$TARGET"
  git -C "$TARGET" pull --ff-only
else
  echo "克隆仓库到：$TARGET"
  mkdir -p "$(dirname "$TARGET")"
  git clone "$REPO_URL" "$TARGET"
fi

cd "$TARGET"
exec bash scripts/install.sh
