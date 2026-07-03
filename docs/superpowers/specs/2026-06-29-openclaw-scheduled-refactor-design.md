# 适配 OpenClaw 无人值守定时任务 — 重构设计

- 日期：2026-06-29
- 基线：在已落主干的 v0.1.0.0 之上重构"执行/回报/契约"层
- 状态：已确认，待实现

## 1. 目标

让本采集技能能被 **OpenClaw 类智能体编排器**以**无人值守定时任务**方式运行：非交互执行、输出机器可读结果、失败可被调度器/智能体感知。不改采集逻辑与数据表，只改执行与回报层。

OpenClaw 派生会话特征（来自运行环境约定）：无人值守、不可用交互式提问、自动决策、以结构化结果回报。

## 2. 核心改动：采集器返回结构化结果

现状：`BaseCollector.run()` 返回裸 `int`（行数），异常被吞为 `0`，无法区分"跑通但 0 行"与"报错"。

改为返回 `RunResult`（dict）：
```python
{
  "name": str,            # 采集器名
  "status": str,          # ok | empty | error
  "rows": int,            # 写入行数
  "error": str | None,    # 异常摘要（status=error 时）
  "duration_ms": int,
}
```
- `ok`：`fetch` 正常且 `rows > 0`
- `empty`：`fetch` 正常但 `rows == 0`（软失败，如 web 源当日无数据 / 非交易日）
- `error`：`fetch` 抛异常（被捕获，记 WARN，写入 `error` 摘要）

`fetch(**kwargs)` 契约不变（仍返回写入行数 int）；包装逻辑集中在 `run()`。

## 3. 运行报告（机器可读）

`run.py` 把各 `RunResult` 汇总为 `RunReport`：
```python
{
  "started_at": ISO8601, "finished_at": ISO8601, "duration_ms": int,
  "mode": "daily|backfill", "kind": str,
  "results": [RunResult, ...],
  "totals": {"rows": int, "ok": int, "empty": int, "error": int},
  "exit_code": int,
}
```
输出去向：
- **stdout**：默认打印单个 JSON 对象（机器优先）；`--format text` 时打印人类可读摘要。
- **文件**：写 `runs/latest.json`（智能体固定读取）+ `runs/run-<UTC时间戳>.json`（历史留档）。`runs/` 加入 `.gitignore`。

## 4. 退出码语义

| 码 | 含义 |
|---|---|
| `0` | 全部跑通（含 `empty` 软失败；web 源当日 0 行不算故障，避免非交易日误报） |
| `3` | 有采集器 `status=error`（部分失败，报告中标明） |
| `2` | 致命错误（DB 初始化失败 / 无可运行采集器 / 报告无法写出） |

调度器/智能体依据退出码即可判断是否需要告警；细节在 `runs/latest.json`。

## 5. 环境可配

- DB 路径：环境变量 `COAL_DB_PATH` 优先，回退 `config.DB_PATH`。
- 报告目录：环境变量 `COAL_RUNS_DIR` 优先，回退 `<项目>/runs`。
- 集中在 `config.py` 读取（`resolve_db_path()` / `resolve_runs_dir()`），便于测试注入与调度环境覆盖。

## 6. SKILL.md 重写（双层）

- **机器层**：命令 `python run.py --mode daily --kind all`；说明 stdout 为 JSON、退出码语义、`runs/latest.json` 路径与字段。
- **智能体层（OpenClaw 无人值守）**：派生会话内**不提问、自动执行**；流程：跑采集 → 读 `runs/latest.json` → 产出中文完成回报（各源行数/状态、总计、是否有 error）→ 非零退出或存在 `error` 时在回报中明确告警。附调度示例：crontab、macOS launchd、以及 OpenClaw scheduled-task 说明（派生会话运行该命令并回报）。

## 7. 目录与文件变更

```
config.py                 # + resolve_db_path()/resolve_runs_dir()（读环境变量）
collectors/base.py        # run() 返回 RunResult（ok/empty/error + 计时 + error 摘要）
run.py                    # 汇总 RunReport、写 runs/、stdout JSON/text、退出码
.gitignore                # + runs/
SKILL.md / README.md      # 重写无人值守用法与调度说明
tests/
  test_base_collector.py  # 改：断言 RunResult 结构与 status 分类
  test_run.py             # 改：run_pipeline 返回结构、报告构建、退出码、stdout
  test_run_report.py      # 新：RunReport 汇总/totals/exit_code/文件写出
```

## 8. 测试

- `run()`：成功有数据→`ok`；成功 0 行→`empty`；抛异常→`error` 且含 error 摘要、不向上抛。
- `run_pipeline`：返回 `RunResult` 列表；多采集器聚合。
- `build_report`：totals 计数正确；存在 error→exit_code=3；全 ok/empty→0；无采集器/DB 失败→2。
- 报告文件：`runs/latest.json` 与时间戳文件均写出且为合法 JSON。
- stdout：`--format json` 为可解析 JSON 对象；`--format text` 为人类可读摘要。
- 退出码：`main()`（或纯函数 `compute_exit_code(report)`）按 §4 返回。

## 9. 非目标（YAGNI）

- 不引入告警渠道（webhook/邮件）——失败感知交给退出码 + 报告。
- 不改采集逻辑、数据源、数据表结构。
- 不内置进程级守护/重试编排（重试仍是 `with_retry` 网络层；调度由外部 cron/OpenClaw 负责）。
- 不做多租户/分布式。

## 10. 向后兼容

- `python run.py` 仍可人手运行；唯一可见变化是 stdout 默认变 JSON（`--format text` 恢复人类可读）。
- `fetch()` 签名与数据表不变；现有采集器无需改动。
