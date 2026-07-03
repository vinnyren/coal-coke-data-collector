# 变更日志

本项目变更日志，格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号采用四段式 `MAJOR.MINOR.PATCH.MICRO`。

## [0.2.0.0] - 2026-07-03

无人值守 / 定时任务重构：把执行与回报层改造成可被 OpenClaw 类智能体定时无人值守运行。

### 新增

- **结构化运行结果**：`BaseCollector.run()` 返回 `RunResult`（`name/status/rows/error/duration_ms`），异常在 `run()` 内隔离并标 `status=error`；`status ∈ {ok, empty, error}`。
- **机器可读运行报告**（新模块 `report.py`）：汇总各源为含 `totals` 与 `exit_code` 的报告；写 `runs/latest.json` + `runs/run-<UTC时间戳>.json`（同秒冲突自动追加 `-N`，原子写不覆盖）。
- **退出码契约** `{0,2,3}`：`0`=全部跑通（含 0 行软失败）；`3`=有采集器异常；`2`=致命（DB 初始化 / 报告写出失败 / 任何逃逸异常）。
- **stdout 输出**：`--format json`（默认，单个可解析 JSON）/ `--format text`（人类可读摘要）。
- **环境变量配置**：`COAL_DB_PATH`、`COAL_RUNS_DIR`（支持 `~` 展开）。
- **调度文档**：`SKILL.md` 无人值守段、`scripts/openclaw-task.example.md`（派生会话指令、频率、flock 防重叠、保留清理、健康判断）。

### 加固

- cron/systemd 无 locale 时启动即重配 stdout 为 UTF-8，避免中文报告崩为 exit 1。
- `main()` 兜底捕获任何逃逸异常归为 exit 2，维持退出码契约；`store.close()` 静默不掩盖结果。
- 致命失败（含 DB 初始化）也写出 `latest.json`，避免旧的成功报告掩盖失败。
- 顶层 `duration_ms` 钳位为 0（NTP 回拨不产生负值）；采集异常摘要限长。
- 提取 `STATUS_*/EXIT_*/BACKFILL_START` 常量，消除跨模块字符串耦合与退出码魔法数。

### 测试

- 76 个单元测试（pytest）：RunResult 状态、报告构建/退出码/原子写/防撞、`run_once`/`main` 编排与 JSON/text 输出、两条致命路径与兜底、环境路径解析。
- `--kind regional` / `inventory` 端到端实测通过（exit 0）；DB 初始化失败端到端得 exit 2 + latest.json。

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
