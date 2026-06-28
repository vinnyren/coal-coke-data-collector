# 煤焦交易数据采集技能 — 设计文档

- 日期：2026-06-28
- 形态：Claude Code 技能（SKILL.md + Python 脚本）
- 状态：已确认，待实现

## 1. 目标

开发一个可被斜杠命令/自动触发调用的 Claude Code 技能，采集**焦煤、焦炭、动力煤**三个品种的**期货与现货**数据，存入**本地 SQLite 数据库**，支持**历史回补**与**每日增量**两种运行模式。

## 2. 数据范围与来源

### 品种与代码

| 品种 | 期货代码 | 交易所 |
|---|---|---|
| 焦煤 | jm | 大连商品交易所 |
| 焦炭 | j | 大连商品交易所 |
| 动力煤 | zc | 郑州商品交易所 |

### 主通道：AKShare（开源、合法、零成本）

| 数据类别 | AKShare 接口 | 说明 |
|---|---|---|
| 期货历史日线 | `futures_zh_daily_sina` | 各合约 OHLCV + 持仓量 |
| 期货主力连续 | `futures_main_sina` | 主力连续合约历史 |
| 期货实时行情 | `futures_zh_spot` | 当日最新价/买卖价/持仓快照 |
| 现货价与基差 | `futures_spot_price_daily` / `futures_spot_price` | 现货价、最近合约、基差、基差率 |
| 持仓排名 | `futures_dce_position_rank` | 大商所前20会员持买/持卖排名（焦煤、焦炭） |
| 库存 | `futures_inventory_em` | 东财库存数据（动力煤等） |

> 备注：接口可用性以运行时 AKShare 实测为准；`config.py` 集中维护品种↔接口映射，便于版本变化时调整。

### 补充通道：公开网页（可插拔，失败不影响主通道）

- 目标为**免登录**的公开指数页面：CCTD 煤价指数中心、全国煤炭交易中心等的指数价（如环渤海动力煤指数、CCTD 指数）。
- 实现为 `sources/web_*.py`，单独 try/except，失败仅记 WARN。
- 专业现货资讯站（SMM、Mysteel、煤炭资源网）多需登录/付费，**不纳入**硬爬范围（合规与稳定性风险）。

## 3. 目录结构

```
煤炭和焦炭交易数据采集技能/
├── SKILL.md                  # 技能说明 + 触发描述 + 用法
├── requirements.txt          # akshare, pandas, requests, beautifulsoup4
├── config.py                 # 品种、接口映射、表名、数据库路径
├── db/
│   ├── schema.sql            # 建表 DDL
│   └── coal_data.db          # SQLite（运行后生成）
├── collectors/
│   ├── base.py               # 采集器基类（重试、异常隔离、写库去重）
│   ├── futures_daily.py      # 期货历史日线
│   ├── futures_realtime.py   # 期货实时行情
│   ├── spot_basis.py         # 现货价 + 基差
│   ├── position_rank.py      # 持仓排名
│   └── inventory.py          # 库存
├── sources/
│   └── web_cctd.py           # 公开网页补充（可插拔）
├── storage/
│   └── sqlite_store.py       # SQLite 读写封装（upsert 去重）
├── run.py                    # 统一入口
├── scripts/
│   └── cron.example          # crontab / launchd 定时示例
├── logs/                     # 运行日志（运行后生成）
└── README.md
```

## 4. 数据库表设计（SQLite）

所有表使用 `INSERT ... ON CONFLICT ... DO UPDATE`（或 `INSERT OR REPLACE`）实现幂等去重，重复运行不产生脏数据。

| 表 | 关键字段 | 主键/唯一约束 |
|---|---|---|
| `futures_daily` | 日期, 品种, 合约, 开, 高, 低, 收, 结算, 成交量, 持仓量 | (品种, 合约, 日期) |
| `futures_realtime` | 采集时间, 品种, 合约, 最新价, 买价, 卖价, 持仓量, 成交量 | (品种, 合约, 采集时间) |
| `spot_basis` | 日期, 品种, 现货价, 最近合约价, 基差, 基差率 | (品种, 日期) |
| `position_rank` | 日期, 品种, 类型(买/卖), 会员, 数量, 增减, 名次 | (品种, 日期, 类型, 名次) |
| `inventory` | 日期, 品种, 库存, 增减 | (品种, 日期) |
| `index_price` | 日期, 指数名称, 价格, 来源 | (指数名称, 日期) |

## 5. 运行方式

```bash
python run.py --mode backfill --start 2015-01-01      # 首次历史回补
python run.py --mode daily                            # 每日增量
python run.py --mode daily --kind futures             # 只更某类: futures|spot|rank|inventory|index|all
```

- `backfill`：拉取全历史日线 / 现货基差入库；实时类按性质仅在 daily 抓当日快照。
- `daily`：只补最新交易日，自动跳过非交易日与已存在记录。
- 单个采集器失败不中断其它采集器；每次运行写日志至 `logs/`。

## 6. 健壮性

- 网络请求重试 + 指数退避；AKShare 接口异常捕获并记录。
- 空数据/异常返回告警。
- `config.py` 集中管理品种与接口映射，新增品种只改配置。
- 公开网页源失败仅 WARN，不影响期货主数据。

## 7. 定时（可选）

- 提供手动运行能力，附 `scripts/cron.example`（crontab + macOS launchd 示例），由用户自行决定是否启用每日定时。

## 8. 非目标（YAGNI）

- 不做付费/登录站点的硬爬。
- 不做实时推送、不做 Web 前端、不做多用户。
- 不内置强制定时（仅提供示例）。
