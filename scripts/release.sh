#!/usr/bin/env bash
# scripts/release.sh — 幂等发版：读 VERSION，提取 CHANGELOG 对应条目为发布说明，
# 打 tag 并创建 GitHub Release。判级、写 CHANGELOG、提交与推送是发版前置，
# 完整流程见 docs/发布流程.md。
set -euo pipefail

# 定位仓根（本脚本在 <repo>/scripts/ 下）并进入
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# 版本号：四段式 MAJOR.MINOR.PATCH.MICRO
VERSION="$(tr -d '[:space:]' < VERSION)"
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "错误：VERSION 格式非法（需四段式 MAJOR.MINOR.PATCH.MICRO）：'$VERSION'" >&2
  exit 1
fi
TAG="v$VERSION"

# 发布说明 = CHANGELOG 中 '## [<version>]' 标题行之后、下一个 '## [' 之前的内容
NOTES="$(awk -v ver="$VERSION" '
  BEGIN { pfx = "## [" ver "]" }
  substr($0, 1, length(pfx)) == pfx { hit = 1; next }
  hit && /^## \[/ { exit }
  hit { print }
' CHANGELOG.md)"
if [ -z "${NOTES//[[:space:]]/}" ]; then
  echo "错误：CHANGELOG.md 中找不到 '## [$VERSION]' 条目，请先补写变更日志。" >&2
  exit 1
fi

# 标题：条目首个非空行为摘要；有全角冒号取冒号前，否则整行；去句尾句号
SUMMARY="$(printf '%s\n' "$NOTES" | awk 'NF { print; exit }')"
SHORT="${SUMMARY%%：*}"
SHORT="${SHORT%。}"
TITLE="$TAG — $SHORT"

if [ "${COAL_RELEASE_DRYRUN:-}" = "1" ]; then
  echo "DRYRUN: tag=$TAG title=$TITLE"
  echo "NOTES_BEGIN"
  printf '%s\n' "$NOTES"
  echo "NOTES_END"
  exit 0
fi

command -v gh >/dev/null 2>&1 || {
  echo "错误：需要 GitHub CLI（gh），请先安装并执行 gh auth login。" >&2
  exit 1
}

# 发版必须基于已推送的状态：本地 HEAD 与 origin/main 一致才继续
git fetch origin main --quiet
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "错误：本地 HEAD 与 origin/main 不一致，请先完成提交与推送再发版。" >&2
  exit 1
fi

# 幂等：同名 Release 已存在则直接返回其 URL
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "Release $TAG 已存在，跳过创建（幂等）。"
  gh release view "$TAG" --json url -q .url
  exit 0
fi

NOTES_FILE="$(mktemp)"
trap 'rm -f "$NOTES_FILE"' EXIT
printf '%s\n' "$NOTES" > "$NOTES_FILE"
gh release create "$TAG" --target main --title "$TITLE" --notes-file "$NOTES_FILE"
echo "✅ Release $TAG 已发布。"
