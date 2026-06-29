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
```

## 数据表

futures_daily / futures_realtime / spot_basis / position_rank / inventory / index_price /
spot_regional（分地区现货/指数价）/ spot_regional_stats（跨地区统计），
均以业务主键唯一约束，重复运行幂等去重。详见 db/schema.sql。

## 数据来源

- 主通道：AKShare（聚合新浪/东财/交易所，合法零成本）。
- 补充（sources/，可插拔，失败不影响主数据）：CCTD 指数页、生意社全国价、全国煤炭交易中心 JSON 接口、中国太原煤炭价格指数 JSON 接口（ctctc，含 2023 至今周度历史）。

## 定时

参见 scripts/cron.example（crontab 与 macOS launchd 示例）。
