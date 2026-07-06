# OpenClaw 一键安装 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 OpenClaw 类智能体在会话里执行一条命令，即完成 clone 公开仓 → 建 venv → 装依赖 → 离线冒烟验证，并打印如何运行；智能体据此可幂等自愈安装后再采集。

**Architecture:** 两个 bash 脚本职责单一：`scripts/install.sh`（仓内幂等安装器，不 clone）与 `scripts/openclaw-bootstrap.sh`（远程入口，clone/pull 后调 install.sh）。两者均留 dry-run 接缝，使决策逻辑可用 pytest+subprocess 自动化测试；真实端到端安装留作手动冒烟。文档让智能体「自知」安装命令。

**Tech Stack:** bash（`set -euo pipefail`）、Python venv/pip、pytest（subprocess 调脚本）。不新增第三方依赖。

## Global Constraints

- 仅 macOS/Linux bash（WSL 可用）；不做 Windows 原生、不自动注册 cron、不做历史回补、不做 PyPI/Docker。
- 脚本**不自动修改仓库可见性**——「仓设为 public」是发布前的手动步骤（见 Task 5）。
- Python 版本下限 3.9。默认安装目录 `~/.openclaw-skills/coal-coke-data-collector`，可用 `COAL_HOME` 覆盖；clone URL 可用 `COAL_REPO_URL` 覆盖（供测试）。
- dry-run 环境变量：`COAL_INSTALL_DRYRUN=1`（install.sh 打印计划后退出，不建 venv/不装依赖）、`COAL_BOOTSTRAP_DRYRUN=1`（bootstrap 打印 clone/pull 决策后退出，不动 git）。版本门在 dry-run 之前，故坏版本 dry-run 仍非零退出。
- 冒烟验证用离线 `pytest`（当前 76 passed，确定性、不依赖网络）。
- 脚本创建后加可执行位 `chmod +x`。

---

### Task 1: `scripts/install.sh` 仓内幂等安装器

**Files:**
- Create: `scripts/install.sh`
- Create: `tests/test_install_scripts.py`

**Interfaces:**
- Consumes: 无。
- Produces: 可执行 `scripts/install.sh`；在仓根运行，退出码 0=装好并 pytest 通过，非 0=某步失败。dry-run 打印 `DRYRUN: python=<PY> version=<X.Y> venv=<path>`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_install_scripts.py
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "scripts" / "install.sh"


def _run(cmd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, env=e, capture_output=True, text=True)


def test_install_sh_exists_and_strict_mode():
    assert INSTALL.exists(), "scripts/install.sh 应存在"
    assert os.access(INSTALL, os.X_OK), "install.sh 应可执行"
    assert "set -euo pipefail" in INSTALL.read_text(encoding="utf-8")


def test_install_dryrun_accepts_current_python():
    r = _run(["bash", str(INSTALL)], env={"COAL_INSTALL_DRYRUN": "1"})
    assert r.returncode == 0, r.stderr
    assert "DRYRUN" in r.stdout and ".venv" in r.stdout


def test_install_rejects_old_python(tmp_path):
    # 伪造 python3 报告 3.8，置于 PATH 最前；install.sh 版本门应在 dry-run 前拦截
    fake = tmp_path / "python3"
    fake.write_text(
        '#!/usr/bin/env bash\n'
        'if [ "$1" = "-c" ]; then echo "3.8"; else exit 0; fi\n',
        encoding="utf-8")
    fake.chmod(0o755)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}",
           "COAL_INSTALL_DRYRUN": "1"}
    r = _run(["bash", str(INSTALL)], env=env)
    assert r.returncode != 0
    assert "3.9" in r.stderr
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_install_scripts.py -v`
Expected: FAIL（`scripts/install.sh` 不存在，`INSTALL.exists()` 断言失败）

- [ ] **Step 3: 写 `scripts/install.sh`**

```bash
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

# 离线冒烟验证（不依赖网络；当前 76 passed）
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
```

然后加可执行位：`chmod +x scripts/install.sh`

- [ ] **Step 4: 运行测试确认通过**

Run: `chmod +x scripts/install.sh && python -m pytest tests/test_install_scripts.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/install.sh tests/test_install_scripts.py
git commit -m "feat: 仓内幂等安装器 scripts/install.sh（venv+依赖+离线验证）"
```

---

### Task 2: `scripts/openclaw-bootstrap.sh` 远程入口

**Files:**
- Create: `scripts/openclaw-bootstrap.sh`
- Modify: `tests/test_install_scripts.py`

**Interfaces:**
- Consumes: `scripts/install.sh`（Task 1）。
- Produces: 可执行 `scripts/openclaw-bootstrap.sh`；`curl|bash` 抓取执行：clone（不存在）或 pull（已存在）到 `$COAL_HOME` → 调 install.sh。dry-run 打印 `DRYRUN: action=<clone|pull> target=<dir> url=<url>`。

- [ ] **Step 1: 追加失败测试**

在 `tests/test_install_scripts.py` 末尾追加：
```python
BOOTSTRAP = REPO / "scripts" / "openclaw-bootstrap.sh"


def test_bootstrap_sh_exists_and_strict_mode():
    assert BOOTSTRAP.exists(), "scripts/openclaw-bootstrap.sh 应存在"
    assert os.access(BOOTSTRAP, os.X_OK), "bootstrap 应可执行"
    assert "set -euo pipefail" in BOOTSTRAP.read_text(encoding="utf-8")


def test_bootstrap_dryrun_clone_when_missing(tmp_path):
    target = tmp_path / "notyet"
    r = _run(["bash", str(BOOTSTRAP)],
             env={"COAL_BOOTSTRAP_DRYRUN": "1", "COAL_HOME": str(target)})
    assert r.returncode == 0, r.stderr
    assert "action=clone" in r.stdout and f"target={target}" in r.stdout


def test_bootstrap_dryrun_pull_when_exists(tmp_path):
    target = tmp_path / "exists"
    (target / ".git").mkdir(parents=True)
    r = _run(["bash", str(BOOTSTRAP)],
             env={"COAL_BOOTSTRAP_DRYRUN": "1", "COAL_HOME": str(target)})
    assert r.returncode == 0, r.stderr
    assert "action=pull" in r.stdout


def test_bootstrap_dryrun_respects_repo_url_override(tmp_path):
    r = _run(["bash", str(BOOTSTRAP)],
             env={"COAL_BOOTSTRAP_DRYRUN": "1",
                  "COAL_HOME": str(tmp_path / "x"),
                  "COAL_REPO_URL": "https://example.com/foo.git"})
    assert r.returncode == 0, r.stderr
    assert "url=https://example.com/foo.git" in r.stdout
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_install_scripts.py -k bootstrap -v`
Expected: FAIL（`scripts/openclaw-bootstrap.sh` 不存在）

- [ ] **Step 3: 写 `scripts/openclaw-bootstrap.sh`**

```bash
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
```

然后加可执行位：`chmod +x scripts/openclaw-bootstrap.sh`

- [ ] **Step 4: 运行测试确认通过**

Run: `chmod +x scripts/openclaw-bootstrap.sh && python -m pytest tests/test_install_scripts.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 全量回归**

Run: `python -m pytest -q`
Expected: PASS（此前 76 + 新增 7 = 83 passed）

- [ ] **Step 6: Commit**

```bash
git add scripts/openclaw-bootstrap.sh tests/test_install_scripts.py
git commit -m "feat: 远程入口 scripts/openclaw-bootstrap.sh（clone/pull 后装）"
```

---

### Task 3: 真实端到端手动冒烟（验证，非单测）

**Files:** 无（仅验证）。

**Interfaces:**
- Consumes: Task 1/2 产出。
- Produces: 验证证据（install.sh 真装一遍能通过）。

- [ ] **Step 1: 临时目录真跑 install.sh（会真装 akshare 等，耗时数分钟）**

Run:
```bash
TMP="$(mktemp -d)"
git clone "$(git -C . rev-parse --show-toplevel)" "$TMP/repo"
cd "$TMP/repo" && bash scripts/install.sh; echo "exit=$?"
```
Expected: 末尾打印「✅ 安装完成并通过验证」，`exit=0`，`$TMP/repo/.venv` 存在，pytest 全绿。

- [ ] **Step 2: 幂等复跑**

Run: `cd "$TMP/repo" && bash scripts/install.sh; echo "exit=$?"`
Expected: 复用已有 `.venv`，仍 `exit=0`（不重建 venv）。

- [ ] **Step 3: 清理临时目录**

Run: `rm -rf "$TMP"`

（注：bootstrap 真跑需仓已 public，见 Task 5；本任务只验证 install.sh 的本地端到端。）

---

### Task 4: 文档——让智能体「自知」一键安装

**Files:**
- Create: `docs/OpenClaw一键安装.md`
- Modify: `README.md`
- Modify: `scripts/openclaw-task.example.md`
- Modify: `docs/安装与使用指南.md`

**Interfaces:**
- Consumes: Task 1/2 的命令与路径。
- Produces: 一键安装说明与智能体幂等自愈调度指令。

- [ ] **Step 1: 新建 `docs/OpenClaw一键安装.md`**

```markdown
# OpenClaw 一键安装

让 OpenClaw 类智能体在派生会话里**一条命令**装好本采集技能。

## 一键安装命令

```bash
curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash
```

它会：clone（或 pull）公开仓到 `~/.openclaw-skills/coal-coke-data-collector` → 建 `.venv` → 装依赖 → 跑离线 `pytest` 冒烟验证 → 打印运行命令。

## 目标目录与覆盖

- 默认装到 `~/.openclaw-skills/coal-coke-data-collector`。
- 用 `COAL_HOME=/your/path` 覆盖安装位置。

## 装好后如何运行

安装末尾会打印确切命令（含 venv 路径），形如：

```bash
~/.openclaw-skills/coal-coke-data-collector/.venv/bin/python \
  ~/.openclaw-skills/coal-coke-data-collector/run.py --mode daily --kind all
```

## 更新

重跑一键安装命令即可（已存在则 `git pull` 后重装验证，幂等）。

## 健康判断（退出码）

- `0`：全部跑通（含当日 0 行软失败）。
- `3`：有采集器异常，看 `runs/latest.json` 的 `results[].error`。
- `2`：致命（DB/报告写出/安装失败），看 `error` 字段。

## 常见失败

- 缺 `git`/`curl`：bootstrap 会明确报错，先装这两个。
- Python < 3.9 或缺失：install.sh 报错退出，先装 Python 3.9+。
- 建 venv 失败（缺 python3-venv）：自动回退 `pip install --user` 并告警。
```

- [ ] **Step 2: README 顶部加一键安装块**

在 `README.md` 的首段之后、`## 数据范围` 之前插入：
```markdown
## OpenClaw 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash
```

clone 公开仓 → 建 venv → 装依赖 → 离线冒烟验证 → 打印运行命令。详见 [docs/OpenClaw一键安装.md](docs/OpenClaw一键安装.md)。
```

- [ ] **Step 3: `scripts/openclaw-task.example.md` 改为幂等自愈式**

在该文件「## 调度内容（派生会话的指令）」的引用块前，插入新段：
```markdown
## 自助安装（首次或环境缺失时）

若目标环境未安装本技能（无 `~/.openclaw-skills/coal-coke-data-collector/.venv`），
先跑一键安装（幂等，已装则自动更新）：

```bash
curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash
```

装好后用打印出的 venv Python 运行采集（见下）。
```

并把原「## 调度内容」引用块中的运行命令由 `python run.py ...` 改为：
```markdown
> 先确保已安装（未装则跑上面的一键安装命令）；然后在
> `~/.openclaw-skills/coal-coke-data-collector` 运行
> `.venv/bin/python run.py --mode daily --kind all`，读取 `runs/latest.json`，
> 用中文总结各源 status/行数、totals 与退出码。若退出码非 0 或存在 status=error，
> 明确标注"采集告警"并列出失败源与 error 摘要。不要交互式提问，自动完成并回报。
```

- [ ] **Step 4: `docs/安装与使用指南.md` 安装章节加小节**

在「## 3. 安装」小节末尾追加：
```markdown
### OpenClaw 一键安装

面向 OpenClaw 类智能体的自助安装（clone 公开仓 → venv → 依赖 → 冒烟验证）：

```bash
curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash
```

详见 [OpenClaw 一键安装](OpenClaw一键安装.md)。
```

- [ ] **Step 5: Commit**

```bash
git add "docs/OpenClaw一键安装.md" README.md scripts/openclaw-task.example.md "docs/安装与使用指南.md"
git commit -m "docs: OpenClaw 一键安装说明与幂等自愈调度指令"
```

---

### Task 5: 版本、CHANGELOG 与发布前手动步骤

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: 全部前序产出。
- Produces: 版本 0.3.0.0 + 变更日志；标注「仓设为 public」手动步骤。

- [ ] **Step 1: bump VERSION**

把 `VERSION` 内容改为：
```
0.3.0.0
```

- [ ] **Step 2: CHANGELOG 新增条目**

在 `CHANGELOG.md` 顶部（intro 段之后、`## [0.2.1.0]` 之前）插入：
```markdown
## [0.3.0.0] - 2026-07-05

OpenClaw 一键安装：智能体一条命令即可自助安装本技能。

### 新增

- `scripts/openclaw-bootstrap.sh`：远程入口（`curl|bash`），clone/pull 公开仓到
  `~/.openclaw-skills/coal-coke-data-collector`（`COAL_HOME` 可覆盖）后调 install.sh。
- `scripts/install.sh`：仓内幂等安装器——选 Python≥3.9 → 建 `.venv`（失败回退
  `pip install --user`）→ 装依赖 → 离线 `pytest` 冒烟验证 → 打印运行命令与退出码契约。
- `docs/OpenClaw一键安装.md`：一键安装说明；README/安装指南加一键安装块；
  `scripts/openclaw-task.example.md` 改为幂等自愈式（未装先装再跑）。

### 测试

- 新增 7 个脚本测试（pytest + subprocess，用 dry-run 接缝与伪造 python3 断言版本门、
  clone/pull 决策、URL 覆盖），全量 83 passed。
```

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: PASS（83 passed）

- [ ] **Step 4: Commit**

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: bump version and changelog (v0.3.0.0)"
```

- [ ] **Step 5: 发布前手动步骤（记录，不在脚本内自动做）**

一键安装依赖仓库公开。发布/合并前，由维护者手动把仓设为 public：
```bash
gh repo edit vinnyren/coal-coke-data-collector --visibility public --accept-visibility-change-consequences
```
（或 GitHub 网页 Settings → General → Danger Zone → Change visibility。）
安全性：本项目无密钥（AKShare 无 key、SQLite、仓内无凭据），公开不泄密。
公开后可真跑一键命令做端到端验证。

---

## Self-Review

- **Spec coverage:** install.sh→Task1；bootstrap→Task2；端到端冒烟→Task3；文档与智能体自知→Task4；版本/CHANGELOG/公开仓手动步骤→Task5。spec 各决策点均覆盖。
- **Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整脚本/命令与预期。
- **Type/接口一致性:** dry-run 变量名 `COAL_INSTALL_DRYRUN`/`COAL_BOOTSTRAP_DRYRUN`、覆盖变量 `COAL_HOME`/`COAL_REPO_URL`、目标目录 `~/.openclaw-skills/coal-coke-data-collector`、venv 路径 `<repo>/.venv`、退出码 `{0,2,3}` 在 Task1/2/4/5 与 spec 一致；bootstrap 调 `scripts/install.sh`、install.sh 冒烟用 `pytest` 一致。
- **风险提示:** Task3 手动冒烟会真装 akshare（数分钟、需网络）；bootstrap 真跑需仓已 public（Task5 手动步骤）。自动化测试全部用 dry-run，不触发真实 pip/网络。
