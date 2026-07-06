# OpenClaw 无人值守定时任务示例

让 OpenClaw 调度器按周期派生会话，运行煤焦数据采集并回报。

## 自助安装（首次或环境缺失时）

若目标环境未安装本技能（无 `~/.openclaw-skills/coal-coke-data-collector/.venv`），
先跑一键安装（幂等，已装则自动更新）：

```bash
curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash
```

装好后用打印出的 venv Python 运行采集（见下）。

## 调度内容（派生会话的指令）

> 先确保已安装（未装则跑上面的一键安装命令）；然后在
> `~/.openclaw-skills/coal-coke-data-collector` 运行
> `.venv/bin/python run.py --mode daily --kind all`，读取 `runs/latest.json`，
> 用中文总结各源 status/行数、totals 与退出码。若退出码非 0 或存在 status=error，
> 明确标注"采集告警"并列出失败源与 error 摘要。不要交互式提问，自动完成并回报。

## 频率建议

- 每个交易日 17:30（收盘后）跑一次 `daily all`。推荐 17:30（CST）而非凌晨：`daily`
  以 UTC 当日为起点，凌晨（00:00–08:00 CST）会落到 UTC 前一日（幂等 upsert 下仅多回补一天，无正确性问题）。

## 环境变量（可选）

- `COAL_DB_PATH`：指定 SQLite 库位置（支持 `~`）。
- `COAL_RUNS_DIR`：指定运行报告目录（支持 `~`）。
- 建议在无 locale 的 cron/systemd 环境显式设 `LANG=C.UTF-8`（程序已在启动时把
  stdout 重配为 UTF-8 兜底，此项为双保险）。

## 防止重叠运行（建议）

慢跑与下一次触发重叠会导致 SQLite `database is locked`（被误报为 exit 3）。用 `flock` 串行化（`REPO` 为一键安装目录，默认 `~/.openclaw-skills/coal-coke-data-collector`）：

```bash
REPO=~/.openclaw-skills/coal-coke-data-collector
flock -n /tmp/coal-collect.lock "$REPO/.venv/bin/python" "$REPO/run.py" --mode daily --kind all || echo "上一轮仍在跑，跳过"
```

## 报告目录保留（建议）

每次运行写一个 `run-<UTC时间戳>.json` 归档，长期累积。可定期清理，例如保留 30 天：

```bash
find "$COAL_RUNS_DIR" -name 'run-*.json' -mtime +30 -delete
```

## 健康判断（调度器/智能体）

优先以**退出码**为准（最可靠的机器信号）；`runs/latest.json` 为权威机器输出，
每次运行原子覆盖（含致命失败也会写出，不会被旧的成功报告掩盖）：

- exit 0：健康（含当日无数据的软失败）。
- exit 3：部分失败，看 runs/latest.json 的 results[].error。
- exit 2：致命，需人工介入（DB 初始化 / 报告写出失败等，详见 latest.json 的 error）。
