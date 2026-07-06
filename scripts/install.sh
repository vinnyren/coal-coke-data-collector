#!/usr/bin/env bash
# scripts/install.sh — 仓内幂等安装器：venv → 依赖 → 离线冒烟验证(pytest) → 打印用法。
# 不 clone、不调度、不回补历史（那些是 bootstrap / 使用者的事）。
set -euo pipefail

# 定位仓根（本脚本在 <repo>/scripts/ 下）并进入
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

MIN_PY_MINOR=9  # 需要 Python 3.9+

# 选解释器：优先 python3
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "错误：未找到 python3/python，请先安装 Python 3.9+。" >&2
  exit 1
fi

# 校验版本 ≥ 3.9（在 dry-run 之前，坏版本也会被拦截）
PY_VER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VER%%.*}"
PY_MINOR="${PY_VER##*.}"
if [ "$PY_MAJOR" -ne 3 ] || [ "$PY_MINOR" -lt "$MIN_PY_MINOR" ]; then
  echo "错误：需要 Python 3.${MIN_PY_MINOR}+，当前为 ${PY_VER}（${PY}）。" >&2
  exit 1
fi

VENV_DIR="$REPO_ROOT/.venv"

if [ "${COAL_INSTALL_DRYRUN:-}" = "1" ]; then
  echo "DRYRUN: python=$PY version=$PY_VER venv=$VENV_DIR"
  exit 0
fi

# 建 venv（已存在则复用）；失败回退系统解释器 + pip --user
if [ -x "$VENV_DIR/bin/python" ]; then
  VENV_PY="$VENV_DIR/bin/python"
  USER_FLAG=""
elif "$PY" -m venv "$VENV_DIR" 2>/dev/null; then
  VENV_PY="$VENV_DIR/bin/python"
  USER_FLAG=""
else
  echo "告警：创建 venv 失败（可能缺 python3-venv），回退为 pip install --user。" >&2
  VENV_PY="$PY"
  USER_FLAG="--user"
fi

# 装依赖
"$VENV_PY" -m pip install $USER_FLAG --upgrade pip
"$VENV_PY" -m pip install $USER_FLAG -r requirements.txt

# 离线冒烟验证（不依赖网络，确定性；全绿视为安装通过）
echo "运行离线冒烟验证（pytest）..."
"$VENV_PY" -m pytest -q

cat <<EOF

✅ 安装完成并通过验证。

每日增量：
  $VENV_PY $REPO_ROOT/run.py --mode daily --kind all

首次历史回补：
  $VENV_PY $REPO_ROOT/run.py --mode backfill --start 2015-01-01

退出码：0=全部跑通  3=有采集器异常  2=致命（详见 runs/latest.json）
OpenClaw 调度与用法：docs/OpenClaw一键安装.md、scripts/openclaw-task.example.md
EOF
