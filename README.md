# 煤焦交易数据采集技能

采集**焦煤、焦炭、动力煤**三个品种的**期货与现货**数据，存入本地 **SQLite** 数据库，支持**历史回补**与**每日增量**两种运行模式。以 Claude Code 技能（SKILL.md + Python 脚本）形态交付。

## 数据范围

| 品种 | 期货代码 | 交易所 |
|---|---|---|
| 焦煤 | jm | 大连商品交易所 |
| 焦炭 | j | 大连商品交易所 |
| 动力煤 | zc | 郑州商品交易所 |

数据类别：期货历史日线、主力连续、实时行情、现货价与基差、持仓排名、库存、分地区现货指数与跨地区统计。

## 数据来源

- **主通道 AKShare**（开源、合法、零成本）：聚合新浪/东财/交易所数据。
- **补充通道**：CCTD 煤价指数中心、生意社、全国煤炭交易中心、中国太原煤炭价格指数（ctctc，含历史周度）等免登录公开页/接口（可插拔，失败不影响主通道）。

## 运行方式

```bash
pip install -r requirements.txt
python run.py --mode backfill --start 2015-01-01   # 首次历史回补
python run.py --mode daily                         # 每日增量
python run.py --mode daily --kind regional         # 只更某一类
```

`--kind`：`all | futures | spot | rank | inventory | regional`。

## 无人值守 / 定时

```bash
python run.py --mode daily --kind all      # 默认 --format json
```

- stdout 输出单个 JSON 运行报告；同时原子写 `runs/latest.json`（权威机器输出）与 `runs/run-<UTC时间戳>.json` 归档。
- **退出码契约 `{0,2,3}`**：`0`=全部跑通（含 0 行软失败）；`3`=有采集器异常；`2`=致命（DB/报告写出失败）。
- 路径可用 `COAL_DB_PATH` / `COAL_RUNS_DIR`（支持 `~`）覆盖。

定时与调度示例见 `scripts/cron.example`、`scripts/openclaw-task.example.md`。

## 数据表

`futures_daily` / `futures_realtime` / `spot_basis` / `position_rank` / `inventory` / `index_price` / `spot_regional`（分地区现货/指数）/ `spot_regional_stats`（跨地区统计）；均以业务主键唯一约束，重复运行幂等去重。详见 `db/schema.sql`。

## 文档

- **[安装与使用指南](docs/安装与使用指南.md)** — 安装、参数、定时、报告、排错的完整说明。
- [SKILL.md](SKILL.md) — 技能清单与无人值守约定。
- [CHANGELOG.md](CHANGELOG.md) — 版本变更日志（当前 0.2.0.0）。
- [设计文档](docs/superpowers/specs/2026-06-28-coal-coke-data-collector-design.md) — 架构设计。
