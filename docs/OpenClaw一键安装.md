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

- 缺 `git`：bootstrap 明确报错退出，先装 git。
- 缺 `curl`：一键命令无法拉取脚本（shell 报 `curl: command not found`，`bash` 收到空输入静默结束），请先装 curl。
- Python < 3.9 或缺失：install.sh 报错退出，先装 Python 3.9+。
- 建 venv 失败（缺 python3-venv）：自动回退 `pip install --user` 并告警。
