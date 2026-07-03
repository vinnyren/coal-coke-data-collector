---
name: 煤焦交易数据采集
description: 采集焦煤、焦炭、动力煤的期货与现货数据（行情/基差/持仓/库存/指数）并写入本地 SQLite。当用户提到采集煤炭/焦煤/焦炭价格、煤焦期货现货数据入库、煤焦行情回补或每日更新时使用本技能。
---

# 煤焦交易数据采集技能

采集焦煤(jm)、焦炭(j)、动力煤(zc)的期货与现货数据并幂等写入本地 SQLite。

## 依赖

```bash
pip install -r requirements.txt
```

## 用法

```bash
# 首次历史回补（拉全历史日线/基差等）
python run.py --mode backfill --start 2015-01-01

# 每日增量（只补最新交易日）
python run.py --mode daily

# 只更某一类: all | futures | spot | rank | inventory | regional
python run.py --mode daily --kind futures

# 只更现货多地与统计（生意社/CCTD/全国煤炭交易中心/中国太原煤炭价格指数 + 跨地区统计）
python run.py --mode daily --kind regional

# 人类可读摘要（默认 --format json）
python run.py --mode daily --kind inventory --format text
```

> 安装、参数、定时、报告字段与排错的完整说明见 **[docs/安装与使用指南.md](docs/安装与使用指南.md)**。

## 无人值守 / 定时任务（OpenClaw 类智能体）

机器层：
- 命令：`python run.py --mode daily --kind all`（默认 `--format json`）。
- **退出码是最可靠的健康信号**：`0`=全部跑通（含当日 0 行的软失败）；`3`=有采集器异常（报告内 status=error 标明）；`2`=致命（DB 初始化/报告写出失败或任何逃逸异常）。契约恒为 `{0,2,3}`。
- **`runs/latest.json` 为权威机器输出**：每次运行原子覆盖（含致命失败也写出），优先据此判读。
- stdout 首选打印同一份 JSON 报告（启动时已把 stdout 重配为 UTF-8）；但采集库偶发打印可能干扰 stdout，故解析以 `latest.json` 为准。
- 另写 `runs/run-<UTC时间戳>.json` 归档（同秒冲突自动追加 `-N`，不覆盖）。
- 路径可用环境变量覆盖：`COAL_DB_PATH`、`COAL_RUNS_DIR`（均支持 `~`）。

报告字段：`started_at/finished_at/duration_ms/mode/kind/results[{name,status,rows,error,duration_ms}]/totals{rows,ok,empty,error}/exit_code`。

智能体层（派生会话内执行，不要交互式提问）：
1. 运行 `python run.py --mode daily --kind all`。
2. 读取 `runs/latest.json`。
3. 产出中文完成回报：各源 `name/status/rows`、`totals`、退出码。
4. 若退出码非 0 或任一 `status=error`：在回报中明确"采集告警"并列出失败源与 error 摘要。

调度示例见 `scripts/cron.example` 与 `scripts/openclaw-task.example.md`。

## 数据表

futures_daily / futures_realtime / spot_basis / position_rank / inventory / index_price /
spot_regional（分地区现货/指数价）/ spot_regional_stats（跨地区统计），
均以业务主键唯一约束，重复运行幂等去重。详见 db/schema.sql。

## 数据来源

- 主通道：AKShare（聚合新浪/东财/交易所，合法零成本）。
- 补充（sources/，可插拔，失败不影响主数据）：CCTD 指数页、生意社全国价、全国煤炭交易中心 JSON 接口、中国太原煤炭价格指数 JSON 接口（ctctc，含 2023 至今周度历史）。

## 定时

参见 scripts/cron.example（crontab 与 macOS launchd 示例）。
