---
name: coal-coke-data-collector
description: 采集焦煤(jm)、焦炭(j)、动力煤(zc)期货与现货数据并幂等写入本地 SQLite 的采集管道。当用户提到以下任意情形时使用本技能：更新/采集煤焦数据、煤炭价格、焦煤/焦炭/动力煤行情、煤价指数、煤焦期现货数据入库、回补煤价历史、每日增量采集、煤焦库存/基差/持仓排名/分地区现货价格，或要查询、检查、汇报本地煤焦数据库（coal_data.db）的数据与采集状态。即使用户只是笼统地说"更新一下煤炭数据"、"今天煤价拉了吗"、"焦炭库存入了没"也应使用本技能。
---

# 煤焦交易数据采集技能

采集焦煤(jm)、焦炭(j)、动力煤(zc)的期货与现货数据并幂等写入本地 SQLite。
本技能目录**即项目仓库本体**（含 `run.py`），下文以 `$SKILL_DIR` 指代本技能的 base 目录，所有命令均可在任意工作目录下用绝对路径执行。

## 0. 解释器与安装（先决条件）

优先使用仓内虚拟环境解释器：

```bash
PY="$SKILL_DIR/.venv/bin/python"
```

若 `$PY` 不存在或 import 失败，先执行幂等安装（建 venv → 装依赖 → 离线冒烟 pytest）：

```bash
bash "$SKILL_DIR/scripts/install.sh"
```

若本机连技能目录都不存在（全新机器），用远程一键安装：
`curl -fsSL https://raw.githubusercontent.com/vinnyren/coal-coke-data-collector/main/scripts/openclaw-bootstrap.sh | bash`

## 1. 运行采集

```bash
# 日常：每日增量（只补最新交易日，快）
"$PY" "$SKILL_DIR/run.py" --mode daily --kind all

# 首次/断档：历史回补（拉全历史，耗时较长，建议分 kind 跑）
"$PY" "$SKILL_DIR/run.py" --mode backfill --start 2015-01-01

# 只更某一类
"$PY" "$SKILL_DIR/run.py" --mode daily --kind regional

# 人类可读摘要（默认 --format json）
"$PY" "$SKILL_DIR/run.py" --mode daily --kind inventory --format text
```

`--kind`：`all`＝全部；`futures`＝日线+实时行情；`spot`＝现货价与基差；`rank`＝持仓排名；`inventory`＝交易所库存；`regional`＝生意社/CCTD/全国煤炭交易中心/太原煤价指数+跨地区统计。

参数、环境变量（`COAL_DB_PATH`/`COAL_RUNS_DIR`）、定时调度与排错的完整说明见 **`docs/安装与使用指南.md`**（排错查 §10）。

## 2. 判读结果（机器契约）

- **退出码是最可靠的健康信号**，契约恒为 `{0,2,3}`：`0`=全部跑通（含当日 0 行的软失败）；`3`=有采集器异常（报告内 `status=error` 标明）；`2`=致命（DB 初始化/报告写出失败或任何逃逸异常）。
- **`$SKILL_DIR/runs/latest.json` 为权威机器输出**：每次运行原子覆盖（含致命失败也写出），判读以它为准，不要解析 stdout（采集库偶发打印可能污染 stdout）。
- 另写 `runs/run-<UTC时间戳>.json` 归档（同秒冲突自动追加 `-N`，不覆盖）。
- 报告字段：`started_at/finished_at/duration_ms/mode/kind/results[{name,status,rows,error,duration_ms}]/totals{rows,ok,empty,error}/exit_code`；`status` 取值 `ok`/`empty`（0 行软失败）/`error`。完整堆栈在 `logs/collector.log`。

## 3. 完成回报（对用户）

运行后读取 `runs/latest.json`，产出中文回报：

1. 各源 `name / status / rows`；
2. `totals` 与退出码；
3. 若退出码非 0 或任一 `status=error`：明确标注**"采集告警"**并列出失败源与 `error` 摘要（`empty` 属软失败，非交易日/当日无新数据通常正常，连续多日为空才需排查）。

无人值守/派生会话内执行时不要交互式提问，自动完成并回报。调度示例见 `scripts/cron.example` 与 `scripts/openclaw-task.example.md`。

## 4. 查询本地数据

数据库默认在 `$SKILL_DIR/db/coal_data.db`（可被 `COAL_DB_PATH` 覆盖），直接用 sqlite3 查询：

```bash
sqlite3 "$SKILL_DIR/db/coal_data.db" \
  "SELECT date, symbol, close FROM futures_daily ORDER BY date DESC LIMIT 10;"
```

数据表：`futures_daily`（历史日线/主力连续）/ `futures_realtime`（实时快照）/ `spot_basis`（现货价与基差）/ `position_rank`（持仓排名）/ `inventory`（交易所库存）/ `index_price`（原始指数价）/ `spot_regional`（分地区现货/指数，品种×地区类型×地区）/ `spot_regional_stats`（跨地区统计，含 `ALL` 汇总）。列定义见 `db/schema.sql`。均以业务主键唯一约束，重复运行幂等去重。

## 5. 数据来源

- 主通道：AKShare（聚合新浪/东财/交易所，合法零成本）。
- 补充（`sources/`，可插拔，单源失败不影响主数据）：CCTD 指数页、生意社全国价、全国煤炭交易中心 JSON 接口、中国太原煤炭价格指数 JSON 接口（ctctc，含 2023 至今周度历史）。
