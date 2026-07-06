# 变更日志

本项目变更日志，格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号采用四段式 `MAJOR.MINOR.PATCH.MICRO`。

## [0.5.0.0] - 2026-07-06

绕过大商所瑞数动态安全 WAF：position_rank 改用可选无头浏览器通道，并新增 skipped 降级语义。

### 背景（根因）

大商所（DCE）全站升级瑞数动态安全 WAF，对非浏览器请求返回 HTTP 412 + 动态混淆 JS 挑战页（`$_ts`/动态 cookie/外链混淆 JS/`_$mp()`），放行 token 由 JS 在真实浏览器 VM 里动态生成。实测：补齐浏览器 headers、只换 UA、换 akshare 其它 DCE 接口（全站同一 WAF）均仍 412。akshare 的裸 `requests.post` 因此拿到 HTML 抛 `BadZipFile`。这不是代码 bug，是外部持续性访问限制。

### 新增

- `sources/dce_browser.py`：DCE 持仓排名浏览器抓取通道（可选 Playwright 插件）。无头浏览器过瑞数挑战拿放行 cookie → 下载持仓排名 zip → 复用 akshare 解析（`_ReqProxy` 仅替换其内部请求、不改解析）。开关 `COAL_POSITION_RANK_BROWSER`（默认开）。
- `STATUS_SKIPPED` 状态：因已知外部限制主动跳过（如反爬 WAF 需浏览器），**不计入 error、不触发 exit 3**，退出码契约 `{0,2,3}` 不变；报告 `totals` 新增 `skipped` 计数。`base.UpstreamBlocked` 异常触发该降级。
- `scripts/verify_dce_browser.py`：本机端到端实测脚本（抓取→解析→打印行数，只读不写主库），用于确认浏览器通道在目标机器可用。

### 变更

- `position_rank` 不再走注定被 412 拦截的 akshare 裸请求：改为经浏览器通道拿 zip 再复用 akshare 解析；未装插件时降级为 `status=skipped` 并说明启用方式，不再每日误报 `BadZipFile`/exit 3。
- `run.py --mode daily --kind all` 在无浏览器插件的默认环境下退出码由 3 回归 0（position_rank=skipped，其它源不受影响）。

### 测试

- 新增/改造 15 个测试（skipped 退出码与 totals、UpstreamBlocked→skipped 降级、浏览器通道开关与缺依赖降级、`_ReqProxy` 注入机制、position_rank 编排与降级传播），全量 104 passed。
- 浏览器真实过 WAF + 真解析无法在离线/CI 覆盖，已隔离为可注入函数并提供 `verify_dce_browser.py` 供本机实测；文档明确标注需 `playwright install chromium` 后实测。

## [0.4.1.0] - 2026-07-06

发布流程固化：流程文档 + 幂等发版脚本，发版从手工操作变成一条命令。

### 新增

- `scripts/release.sh`：幂等发版脚本——校验 VERSION 四段式与 CHANGELOG 条目存在、
  校验本地 HEAD 与 origin/main 一致，提取 CHANGELOG 条目为发布说明（摘要冒号前为
  Release 标题），打 tag 并创建 GitHub Release；同名 Release 已存在则跳过。
  `COAL_RELEASE_DRYRUN=1` 预演不做远程操作。
- `docs/发布流程.md`：完整发布流程（测试→判级→CHANGELOG→分块提交→push→release.sh）
  与常见错误表；CLAUDE.md 新增"发布"节固化路由（本仓直接提交 main，/ship 分支前置不适用）。

### 测试

- 新增 7 个 release.sh 脚本测试（dry-run 接缝：tag/标题提取、条目边界、坏版本号、
  缺 CHANGELOG 条目、真实仓库 VERSION↔CHANGELOG 一致性约束），全量 90 passed。

## [0.4.0.0] - 2026-07-06

Claude Code 技能化：仓库本体可直接安装为个人技能，任意会话提到煤焦数据即自动触发。

### 新增

- `SKILL.md` 重构为可安装技能：`name` 规范为 `coal-coke-data-collector`；触发描述覆盖
  "更新煤焦数据 / 查煤价 / 库存·基差·持仓·分地区现货 / 查询本地煤焦库"等口语说法；
  正文面向"从任意目录被调用"重写——以技能 base 目录定位仓库、优先用 `.venv/bin/python`、
  以 `runs/latest.json` 判读结果，并新增本地 SQLite 查询指引（§4）。
- README 与 `docs/安装与使用指南.md` §12：新增"通过 GitHub 安装为 Claude Code 技能"教程，
  三种方式（clone 到 `~/.claude/skills/`、`curl` 一键复用 bootstrap 并以 `COAL_HOME` 指定
  安装位置、开发者软链），含验证触发、更新（`git pull`）与卸载（注意备份 `db/`）说明。

### 验证

- 有/无技能对照评测（3 个真实用例）：with-skill 断言通过率 100%（10/10），无技能基线 22.2%，
  且技能路径平均快 126 秒；报告数字逐项与库中核验一致。
- 远程 raw bootstrap 与本地脚本 diff 一致；`COAL_HOME` 环境变量传递经 dry-run 验证
  （目标已存在时自动走 `git pull`，幂等）。离线冒烟 83 passed。

## [0.3.0.0] - 2026-07-05

OpenClaw 一键安装：智能体一条命令即可自助安装本技能。

### 新增

- `scripts/openclaw-bootstrap.sh`：远程入口（`curl|bash`），clone/pull 公开仓到
  `~/.openclaw-skills/coal-coke-data-collector`（`COAL_HOME` 可覆盖，`COAL_REPO_URL` 可覆盖源）后调 install.sh。
- `scripts/install.sh`：仓内幂等安装器——选 Python≥3.9 → 建 `.venv`（失败回退
  `pip install --user`）→ 装依赖 → 离线 `pytest` 冒烟验证 → 打印运行命令与退出码契约。
- `docs/OpenClaw一键安装.md`：一键安装说明；README/安装指南加一键安装块；
  `scripts/openclaw-task.example.md` 改为幂等自愈式（未装先装再跑）。

### 测试

- 新增 7 个脚本测试（pytest + subprocess，用 dry-run 接缝与伪造 python3 断言版本门、
  clone/pull 决策、URL 覆盖），全量 83 passed。端到端手动冒烟：真装 + 幂等复跑均 exit 0。

## [0.2.1.0] - 2026-07-03

文档与注释完善（代码零改动）。

### 文档

- 新增 **`docs/安装与使用指南.md`**：环境要求、安装、命令行参数、数据表、无人值守/定时（cron/launchd/OpenClaw）、运行报告字段、环境变量、数据来源与容错、排错、测试的完整说明。
- `README.md`：更新为 0.2.0.0 后状态，补 `--kind`/无人值守退出码/数据表小节，指向新指南。
- `SKILL.md`：补 `--format` 示例并指向新指南。

### 注释

- 为全部 14 个源码模块（`collectors/*`、`sources/*`、`storage/sqlite_store.py`、`config.py`、`report.py`、`run.py`）补充中文**模块级 docstring**，并为缺失的关键类/公开函数补一行说明；表名与数据源均按实际代码填写。纯增量（128 行新增，0 删除），逻辑零改动。

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
