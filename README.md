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
- **补充通道**：CCTD 煤价指数中心、全国煤炭交易中心等免登录公开页面（可插拔，失败不影响主通道）。

## 运行方式

```bash
pip install -r requirements.txt
python run.py --mode backfill --start 2015-01-01   # 首次历史回补
python run.py --mode daily                         # 每日增量
```

## 状态

设计已确认，开发中。详见 [设计文档](docs/superpowers/specs/2026-06-28-coal-coke-data-collector-design.md)。
