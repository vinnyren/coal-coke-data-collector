# OpenClaw 无人值守定时任务示例

让 OpenClaw 调度器按周期派生会话，运行煤焦数据采集并回报。

## 调度内容（派生会话的指令）

> 在项目目录运行 `python run.py --mode daily --kind all`，然后读取 `runs/latest.json`，
> 用中文总结各数据源的 status 与行数、totals 与退出码。若退出码非 0 或存在 status=error，
> 明确标注"采集告警"并列出失败的源与 error 摘要。不要交互式提问，自动完成并回报。

## 频率建议

- 每个交易日 17:30（收盘后）跑一次 `daily all`。

## 环境变量（可选）

- `COAL_DB_PATH`：指定 SQLite 库位置。
- `COAL_RUNS_DIR`：指定运行报告目录。

## 健康判断（调度器/智能体）

- exit 0：健康（含当日无数据的软失败）。
- exit 3：部分失败，看 runs/latest.json 的 results[].error。
- exit 2：致命，需人工介入（DB/报告写出失败）。
