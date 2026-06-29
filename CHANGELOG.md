# 变更日志

本项目变更日志，格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号采用四段式 `MAJOR.MINOR.PATCH.MICRO`。

## [0.1.0.0] - 2026-06-29

首个版本：煤焦交易数据采集技能（焦煤/焦炭/动力煤，期货+现货，写入本地 SQLite）。

### 新增

- **期货采集**：基于 AKShare 的历史日线/主力连续（`futures_daily`）、实时行情（`futures_realtime`）、持仓排名（`position_rank`）、库存（`inventory`）。
- **现货与基差**：AKShare 全国现货价与基差（`spot_basis`）。
- **现货多源 + 多地结构化**：地区分类器 `classify()`（品种 × 地区类型 × 地区），三个公开免登录源写入 `spot_regional`：
  - `web_cctd`：CCTD 公开指数页，双写 `index_price`（原始）与 `spot_regional`（可分类）。
  - `web_100ppi`：生意社现货表全国价，过 `HW_CHECK` JS 反爬挑战，当日价取数据行倒数第二列。
  - `web_ncexc`：全国煤炭交易中心 JSON 接口（直达煤=产地、下水煤=港口）。
- **跨地区统计**：`SpotStatsCollector` 按品种 × 地区类型 × 日期计算均价/极差/最低最高地，并产出 `ALL` 跨类型汇总（`spot_regional_stats`）。
- **存储层**：标准库 `sqlite3` 幂等 upsert（`INSERT ... ON CONFLICT`）+ 表名白名单。
- **统一入口** `run.py`：`--mode backfill|daily`、`--kind all|futures|spot|rank|inventory|regional`；单采集器失败隔离，不中断其它。
- **技能交付**：`SKILL.md`、`requirements.txt`、cron/launchd 定时示例。

### 测试

- 49 个单元测试（pytest）：存储幂等、重试/异常隔离、各采集器与解析器、地区分类、跨地区统计、入口编排。
- `--kind regional` 端到端实测：100ppi 3 行 + CCTD 46 行 + ncexc 17 行 + 跨地区统计 54 行。
