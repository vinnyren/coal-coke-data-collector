# OpenClaw 一键安装 设计文档

**日期：** 2026-07-05
**版本目标：** 0.3.0.0（MINOR，新增用户可见的安装能力）
**状态：** 已确认，待写实现计划

## 目标

把本采集技能迭代为「OpenClaw 类智能体可自助一键安装」：OpenClaw 在派生会话里执行**一条命令**，即完成 clone 公开仓 → 建 venv → 装依赖 → 离线冒烟验证，并打印如何运行与调度。智能体据此可无脑自愈安装后再采集。

## 范围决策（brainstorm 确认）

| 决策点 | 选定 | 说明 |
|---|---|---|
| OpenClaw 安装模型 | 跑 bootstrap 脚本/命令 | 技能 = 公开仓 + 自安装脚本 |
| 代码来源 | bootstrap 自己 clone | 远程一条命令拉仓再装 |
| 私有仓鉴权 | **改为公开仓** | 无密钥公开数据工具，公开不泄密；免鉴权一键 |
| 安装终点 | clone + 依赖 + 冒烟验证 | 调度交给 OpenClaw 自己（它即调度器） |
| 入口形态 | 方案 A：`curl\|bash` | 内部拆出可复用的仓内 `install.sh`，顺带支持仓内直跑 |
| 冒烟验证 | 离线 `pytest` | 确定性、不依赖网络；真实源留给装后首次 `run.py` |
| 默认安装目录 | `~/.openclaw-skills/coal-coke-data-collector` | 可用 `COAL_HOME` 覆盖 |

## 架构

三个交付物，职责单一、可独立测试：

```
远程一条命令
  curl -fsSL <raw>/scripts/openclaw-bootstrap.sh | bash
        │
        ▼
scripts/openclaw-bootstrap.sh   ── 远程入口：定位/clone 仓 → 调 install.sh
        │  (git clone 或已存在则 git pull)
        ▼
scripts/install.sh              ── 仓内幂等安装器：venv → 依赖 → 离线验证 → 打印用法
        │
        ▼
<repo>/.venv/bin/python run.py  ── 装好后的运行入口（OpenClaw 会话直接调）
```

### 组件 1：`scripts/install.sh`（仓内幂等安装器）

- **输入：** 在仓库根目录运行（`cd` 到脚本所在仓根）。无参数。
- **输出：** 退出码 0=装好并验证通过；非 0=某步失败（打印失败原因）。
- **行为（按序）：**
  1. 定位仓根（脚本自身路径推导），`cd` 过去。
  2. 选 Python：优先 `python3`，回退 `python`；校验版本 ≥ 3.9，否则报错退出。
  3. 建 venv `<repo>/.venv`（已存在则复用）。若 `python3 -m venv` 失败（如缺 python3-venv），**回退**：直接用系统解释器 `pip install --user` 并打印告警。
  4. 升级 pip 后 `pip install -r requirements.txt`。
  5. **离线冒烟验证：`python -m pytest -q`**，须全绿（当前 76 passed）。失败即 exit 非 0。
  6. 打印「装好」摘要：确切运行命令（含 venv 路径）、`--kind` 取值、退出码契约 `{0,2,3}`、OpenClaw 调度指令、指向 `docs/OpenClaw一键安装.md`。
- **幂等：** 可反复运行；venv/依赖已在则复用，不重复重建。
- **不做：** 不 clone（那是 bootstrap 的事）、不调度、不回补历史。

### 组件 2：`scripts/openclaw-bootstrap.sh`（远程入口）

- **触发：** `curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash`
- **行为：**
  1. 目标目录 = `${COAL_HOME:-$HOME/.openclaw-skills/coal-coke-data-collector}`。
  2. 目录不存在 → `git clone https://github.com/vinnyren/coal-coke-data-collector.git "$TARGET"`；已存在且是 git 仓 → `git pull --ff-only`（更新到最新）。
  3. `cd "$TARGET"` → 执行 `bash scripts/install.sh`（透传其退出码）。
- **前置检查：** `git`、`curl` 可用；否则打印清晰的缺失提示并退出。
- **幂等：** 重复跑 = 拉最新 + 重装验证。

### 组件 3：文档与「智能体自知安装」

- **README 顶部**：新增「OpenClaw 一键安装」块，突出那一条命令。
- **新增 `docs/OpenClaw一键安装.md`**：安装命令、目标目录与 `COAL_HOME`、装后如何运行、健康判断、常见失败排错、如何更新（重跑 bootstrap）。
- **更新 `scripts/openclaw-task.example.md`**：调度指令改为**幂等自愈式**——「先确保已安装（未装则跑一键安装命令），再运行 `<repo>/.venv/bin/python run.py --mode daily --kind all`，读取 `runs/latest.json` 回报」。
- **更新 `docs/安装与使用指南.md`**：在安装章节加「OpenClaw 一键安装」小节，指向新文档。

## 前置动作（用户侧）

把 GitHub 仓 `vinnyren/coal-coke-data-collector` 设为 **public**（`gh repo edit --visibility public --accept-visibility-change-consequences`，或网页操作）。否则 `curl|bash` 与 `git clone` 拉不到。实现计划会把这一步作为「发布前手动步骤」标注，不在脚本内自动改可见性。

## 错误处理

- Python 缺失/版本过低 → 明确报错 + 建议，退出码非 0。
- venv 建失败 → 回退 `--user` 安装 + 告警，继续。
- `pip install` 失败 → 打印 pip 输出，退出码非 0。
- `pytest` 失败 → 退出码非 0（安装视为未通过）。
- bootstrap 缺 git/curl → 清晰提示，退出码非 0。
- 所有脚本 `set -euo pipefail`，失败即停并回报。

## 测试策略

脚本层用轻量 bash 测试（不引入新框架）：
- `install.sh` 幂等性：连跑两次均 exit 0、venv 只建一次（可在临时目录 mock）。
- `install.sh` Python 版本门：伪造低版本解释器 → 报错退出。
- `openclaw-bootstrap.sh` 目标目录逻辑：已存在仓走 pull 分支、不存在走 clone 分支（用本地 file:// 仓或 mock `git` 验证参数拼装）。
- 现有 `pytest`（76）不受影响（脚本不改 Python 逻辑）。

具体测试形态（bash 脚本 vs pytest 调 subprocess）在实现计划里定；倾向放 `tests/` 下用 pytest + `subprocess` 调脚本，复用现有测试入口。

## 版本与交付

- 版本：`0.3.0.0`（MINOR）。
- CHANGELOG「新增」：一键安装 bootstrap/installer + OpenClaw 自助安装文档。

## 不在范围（YAGNI）

- 不做 Windows 原生支持（仅 macOS/Linux bash；WSL 可用）。
- 不自动注册 cron/launchd（调度交给 OpenClaw）。
- 不在安装内做历史回补。
- 不做 pip 包/PyPI 发布、不做 Docker 镜像（未来可另立范围）。
- 脚本不自动修改仓库可见性（安全边界，留给用户手动）。
