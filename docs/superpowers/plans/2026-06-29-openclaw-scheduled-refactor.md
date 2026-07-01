# OpenClaw 无人值守定时任务重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把采集技能的执行/回报层重构为可被 OpenClaw 类智能体无人值守定时运行：采集器返回结构化结果、run.py 产出机器可读 JSON 运行报告 + 退出码、SKILL.md 重写无人值守用法。

**Architecture:** `BaseCollector.run()` 由返回裸 int 改为返回 `RunResult`（name/status/rows/error/duration_ms），异常在 run() 内捕获并标 status=error。`run.py` 把各 RunResult 汇总为 RunReport（含 totals + exit_code），打印到 stdout（JSON 或 text）并写 `runs/latest.json` + 时间戳文件，按规则返回退出码。环境变量 `COAL_DB_PATH`/`COAL_RUNS_DIR` 可覆盖路径。

**Tech Stack:** Python 3.9+，标准库（sqlite3/json/argparse/datetime/os/time），pytest。不新增第三方依赖。

## Global Constraints

- Python 版本下限：3.9；不新增第三方依赖（仅标准库）。
- `RunResult` 字段固定：`name:str, status:str, rows:int, error:str|None, duration_ms:int`；`status ∈ {ok, empty, error}`（ok=跑通且 rows>0；empty=跑通且 rows==0；error=fetch 抛异常）。
- 退出码：`0`=无 error（全 ok/empty）；`3`=存在 status=error；`2`=致命（DB 初始化失败/无可运行采集器/报告写出失败）。
- 报告文件：`runs/latest.json` + `runs/run-<UTC时间戳>.json`；时间戳格式 `YYYYMMDDTHHMMSSZ`（UTC，无冒号，文件名安全）。
- stdout：`--format json`（默认）打印单个可解析 JSON 对象；`--format text` 打印人类可读摘要。
- 不改采集逻辑、数据源、数据表结构；`fetch()` 仍返回写入行数 int。
- 时间戳：ISO8601 用 `datetime.now(timezone.utc).isoformat()`；不使用裸 `datetime.now()`。
- 向后兼容：`python run.py` 仍可人手运行。

---

### Task 1: 环境可配的路径解析

**Files:**
- Modify: `config.py`
- Create: `tests/test_config_paths.py`

**Interfaces:**
- Consumes: 无。
- Produces: `config.resolve_db_path() -> pathlib.Path`（读环境变量 `COAL_DB_PATH`，回退 `DB_PATH`）；`config.resolve_runs_dir() -> pathlib.Path`（读 `COAL_RUNS_DIR`，回退 `BASE_DIR/"runs"`）。

- [x] **Step 1: Write the failing test**

```python
# tests/test_config_paths.py
import importlib
import config


def test_resolve_db_path_default():
    importlib.reload(config)
    assert str(config.resolve_db_path()).endswith("coal_data.db")


def test_resolve_db_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("COAL_DB_PATH", str(target))
    assert config.resolve_db_path() == target


def test_resolve_runs_dir_default():
    assert config.resolve_runs_dir().name == "runs"


def test_resolve_runs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("COAL_RUNS_DIR", str(tmp_path / "r"))
    assert config.resolve_runs_dir() == tmp_path / "r"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_paths.py -v`
Expected: FAIL（`AttributeError: module 'config' has no attribute 'resolve_db_path'`）

- [x] **Step 3: Write minimal implementation**

在 `config.py` 末尾追加（保留既有内容；顶部已 `from pathlib import Path`，需补 `import os`）：
```python
import os


def resolve_db_path():
    """DB 路径：环境变量 COAL_DB_PATH 优先，回退 DB_PATH。"""
    env = os.environ.get("COAL_DB_PATH")
    return Path(env) if env else DB_PATH


def resolve_runs_dir():
    """运行报告目录：环境变量 COAL_RUNS_DIR 优先，回退 <项目>/runs。"""
    env = os.environ.get("COAL_RUNS_DIR")
    return Path(env) if env else BASE_DIR / "runs"
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_paths.py -v`
Expected: PASS（4 passed）

- [x] **Step 5: Commit**

```bash
git add config.py tests/test_config_paths.py
git commit -m "feat: 环境变量可配的 DB 与 runs 路径解析"
```

---

### Task 2: BaseCollector.run() 返回结构化 RunResult

**Files:**
- Modify: `collectors/base.py`
- Modify: `tests/test_base_collector.py`

**Interfaces:**
- Consumes: 无（`fetch` 契约不变，返回 int 行数）。
- Produces: `BaseCollector.run(**kwargs) -> dict`，返回 `{"name","status","rows","error","duration_ms"}`；`status` 由 rows/异常决定。计时用 `time.monotonic()`。

- [x] **Step 1: Write the failing test**

替换 `tests/test_base_collector.py` 中关于 `run()` 的两个测试（`test_run_isolates_exception_and_returns_zero`、`test_run_returns_fetch_count`），保留 `with_retry` 两个测试不动。新增：
```python
def test_run_ok_status_with_rows():
    class Good(BaseCollector):
        name = "good"
        def fetch(self, **kwargs):
            return 7
    r = Good(store=None).run()
    assert r["name"] == "good" and r["status"] == "ok" and r["rows"] == 7
    assert r["error"] is None and isinstance(r["duration_ms"], int)


def test_run_empty_status_when_zero_rows():
    class Empty(BaseCollector):
        name = "empty"
        def fetch(self, **kwargs):
            return 0
    r = Empty(store=None).run()
    assert r["status"] == "empty" and r["rows"] == 0 and r["error"] is None


def test_run_error_status_on_exception():
    class Boom(BaseCollector):
        name = "boom"
        def fetch(self, **kwargs):
            raise RuntimeError("explode")
    r = Boom(store=None).run()
    assert r["status"] == "error" and r["rows"] == 0
    assert "explode" in r["error"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base_collector.py -v`
Expected: FAIL（`run()` 返回 int，`r["name"]` 抛 TypeError）

- [x] **Step 3: Write minimal implementation**

在 `collectors/base.py` 顶部确保 `import time`（已有）。把 `BaseCollector.run` 改为：
```python
    def run(self, **kwargs):
        start = time.monotonic()
        try:
            rows = self.fetch(**kwargs)
            rows = int(rows or 0)
            status = "ok" if rows > 0 else "empty"
            error = None
            self.log.info("%s 写入 %s 行", self.name, rows)
        except Exception as e:  # noqa: BLE001
            rows, status, error = 0, "error", f"{type(e).__name__}: {e}"
            self.log.warning("%s 采集失败: %s", self.name, e)
        return {
            "name": self.name, "status": status, "rows": rows,
            "error": error,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_base_collector.py -v`
Expected: PASS（with_retry 2 + run 3 = 5 passed）

- [x] **Step 5: Commit**

```bash
git add collectors/base.py tests/test_base_collector.py
git commit -m "feat: BaseCollector.run 返回结构化 RunResult"
```

---

### Task 3: run_pipeline 返回 RunResult 列表

**Files:**
- Modify: `run.py`
- Modify: `tests/test_run.py`

**Interfaces:**
- Consumes: `BaseCollector.run() -> dict`（Task 2）。
- Produces: `run_pipeline(store, mode, kind="all", start="2015-01-01") -> list[dict]`（按采集器顺序返回各 RunResult；`futures_daily` 传 start）。

- [x] **Step 1: Write the failing test**

替换 `tests/test_run.py` 的 `test_run_pipeline_aggregates_counts`（其 FakeCollector 返回 int），改为返回 RunResult：
```python
def test_run_pipeline_returns_runresults(tmp_path, monkeypatch):
    import config
    from storage.sqlite_store import SqliteStore
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)

    class FakeCollector:
        def __init__(self, name, rows):
            self.name = name
            self._rows = rows
        def run(self, **kwargs):
            return {"name": self.name, "status": "ok", "rows": self._rows,
                    "error": None, "duration_ms": 1}

    monkeypatch.setattr(run, "_collectors_for_kind",
                        lambda store, kind: [FakeCollector("a", 3),
                                             FakeCollector("b", 5)])
    results = run.run_pipeline(s, mode="daily", kind="all")
    assert [r["name"] for r in results] == ["a", "b"]
    assert sum(r["rows"] for r in results) == 8
```
（保留 `test_build_store_creates_tables`、`test_regional_kind_order_and_membership`、`test_all_includes_regional_not_index` 不变。）

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py::test_run_pipeline_returns_runresults -v`
Expected: FAIL（现 `run_pipeline` 返回 dict 而非 list）

- [x] **Step 3: Write minimal implementation**

把 `run.py` 的 `run_pipeline` 改为返回列表：
```python
def run_pipeline(store, mode, kind="all", start="2015-01-01"):
    results = []
    for c in _collectors_for_kind(store, kind):
        if c.name == "futures_daily":
            results.append(c.run(start=start))
        else:
            results.append(c.run())
    return results
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run.py -v`
Expected: PASS（4 passed）

- [x] **Step 5: Commit**

```bash
git add run.py tests/test_run.py
git commit -m "refactor: run_pipeline 返回 RunResult 列表"
```

---

### Task 4: 运行报告构建与退出码（纯函数）

**Files:**
- Create: `report.py`
- Create: `tests/test_run_report.py`

**Interfaces:**
- Consumes: RunResult 列表。
- Produces: `report.build_report(results, mode, kind, started_at, finished_at) -> dict`（含 totals 与 exit_code）；`report.compute_exit_code(results) -> int`；`report.write_report(report_dict, runs_dir) -> pathlib.Path`（写 latest.json + 时间戳文件，返回时间戳文件路径）；`report.format_text(report_dict) -> str`。

- [x] **Step 1: Write the failing test**

```python
# tests/test_run_report.py
import json
import report


def _rr(name, status, rows):
    return {"name": name, "status": status, "rows": rows,
            "error": None if status != "error" else "X: boom",
            "duration_ms": 1}


def test_exit_code_zero_when_no_error():
    rs = [_rr("a", "ok", 3), _rr("b", "empty", 0)]
    assert report.compute_exit_code(rs) == 0


def test_exit_code_three_when_any_error():
    rs = [_rr("a", "ok", 3), _rr("b", "error", 0)]
    assert report.compute_exit_code(rs) == 3


def test_exit_code_two_when_no_collectors():
    assert report.compute_exit_code([]) == 2


def test_build_report_totals_and_exit():
    rs = [_rr("a", "ok", 3), _rr("b", "empty", 0), _rr("c", "error", 0)]
    rep = report.build_report(rs, "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:05+00:00")
    assert rep["totals"] == {"rows": 3, "ok": 1, "empty": 1, "error": 1}
    assert rep["exit_code"] == 3
    assert rep["mode"] == "daily" and rep["kind"] == "all"
    assert rep["duration_ms"] == 5000


def test_write_report_creates_latest_and_timestamped(tmp_path):
    rs = [_rr("a", "ok", 3)]
    rep = report.build_report(rs, "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:01+00:00")
    rep["timestamp_slug"] = "20260629T000001Z"
    path = report.write_report(rep, tmp_path)
    assert (tmp_path / "latest.json").exists()
    assert path.exists() and path.name == "run-20260629T000001Z.json"
    loaded = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert loaded["totals"]["rows"] == 3


def test_format_text_has_summary():
    rs = [_rr("a", "ok", 3), _rr("b", "error", 0)]
    rep = report.build_report(rs, "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:01+00:00")
    txt = report.format_text(rep)
    assert "a" in txt and "error" in txt and "exit_code" in txt
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_report.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'report'`）

- [x] **Step 3: Write minimal implementation**

```python
# report.py
import json
from pathlib import Path


def compute_exit_code(results):
    if not results:
        return 2
    if any(r.get("status") == "error" for r in results):
        return 3
    return 0


def _iso_to_ms(start_iso, end_iso):
    from datetime import datetime
    a = datetime.fromisoformat(start_iso)
    b = datetime.fromisoformat(end_iso)
    return int((b - a).total_seconds() * 1000)


def build_report(results, mode, kind, started_at, finished_at):
    totals = {
        "rows": sum(int(r.get("rows") or 0) for r in results),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "empty": sum(1 for r in results if r.get("status") == "empty"),
        "error": sum(1 for r in results if r.get("status") == "error"),
    }
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": _iso_to_ms(started_at, finished_at),
        "mode": mode,
        "kind": kind,
        "results": results,
        "totals": totals,
        "exit_code": compute_exit_code(results),
    }


def write_report(report_dict, runs_dir):
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    slug = report_dict.get("timestamp_slug", "run")
    payload = json.dumps(report_dict, ensure_ascii=False, indent=2)
    (runs_dir / "latest.json").write_text(payload, encoding="utf-8")
    ts_path = runs_dir / f"run-{slug}.json"
    ts_path.write_text(payload, encoding="utf-8")
    return ts_path


def format_text(report_dict):
    lines = [
        f"采集完成 mode={report_dict['mode']} kind={report_dict['kind']} "
        f"exit_code={report_dict['exit_code']}",
        f"totals: {report_dict['totals']}",
    ]
    for r in report_dict["results"]:
        line = f"  {r['name']}: {r['status']} rows={r['rows']}"
        if r.get("error"):
            line += f" error={r['error']}"
        lines.append(line)
    return "\n".join(lines)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_report.py -v`
Expected: PASS（6 passed）

- [x] **Step 5: Commit**

```bash
git add report.py tests/test_run_report.py
git commit -m "feat: 运行报告构建/退出码/写出/文本格式化"
```

---

### Task 5: main() 接线报告、stdout、退出码、环境路径

**Files:**
- Modify: `run.py`
- Modify: `tests/test_run.py`

**Interfaces:**
- Consumes: `run_pipeline`（Task 3）、`report.*`（Task 4）、`config.resolve_db_path/resolve_runs_dir`（Task 1）。
- Produces: `build_store()` 用 `config.resolve_db_path()`；`run_once(mode, kind, start, fmt="json") -> dict`（执行一轮、写报告、返回 report dict）；`main()` 解析参数、调用 `run_once`、按 `report["exit_code"]` `sys.exit`。

- [x] **Step 1: Write the failing test**

在 `tests/test_run.py` 追加：
```python
def test_run_once_writes_report_and_sets_exit(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv("COAL_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("COAL_RUNS_DIR", str(tmp_path / "runs"))

    class FakeCollector:
        def __init__(self, name, status):
            self.name = name
            self._status = status
        def run(self, **kwargs):
            rows = 5 if self._status == "ok" else 0
            err = None if self._status != "error" else "X: boom"
            return {"name": self.name, "status": self._status, "rows": rows,
                    "error": err, "duration_ms": 1}

    monkeypatch.setattr(run, "_collectors_for_kind",
                        lambda store, kind: [FakeCollector("a", "ok"),
                                             FakeCollector("b", "error")])
    rep = run.run_once(mode="daily", kind="all", start="2015-01-01")
    assert rep["exit_code"] == 3
    assert (tmp_path / "runs" / "latest.json").exists()
    assert rep["totals"]["error"] == 1


def test_build_store_uses_env_db_path(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv("COAL_DB_PATH", str(tmp_path / "x.db"))
    s = run.build_store()
    assert (tmp_path / "x.db").exists()
    s.close()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py::test_run_once_writes_report_and_sets_exit -v`
Expected: FAIL（`run.run_once` 不存在）

- [x] **Step 3: Write minimal implementation**

修改 `run.py`：顶部增加 `import sys` 与 `from datetime import datetime, timezone`、`import report`；`build_store` 改用环境路径；新增 `run_once`；改 `main`：
```python
def build_store():
    store = SqliteStore(str(config.resolve_db_path()))
    store.init_schema(config.SCHEMA_PATH)
    return store


def _utcnow():
    return datetime.now(timezone.utc)


def run_once(mode, kind="all", start="2015-01-01"):
    started = _utcnow()
    store = build_store()
    results = run_pipeline(store, mode, kind, start)
    store.close()
    finished = _utcnow()
    rep = report.build_report(results, mode, kind,
                              started.isoformat(), finished.isoformat())
    rep["timestamp_slug"] = finished.strftime("%Y%m%dT%H%M%SZ")
    report.write_report(rep, config.resolve_runs_dir())
    return rep


def main():
    p = argparse.ArgumentParser(description="煤焦交易数据采集")
    p.add_argument("--mode", choices=["backfill", "daily"], default="daily")
    p.add_argument("--kind",
                   choices=["all", "futures", "spot", "rank",
                            "inventory", "regional"],
                   default="all")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--format", choices=["json", "text"], default="json")
    args = p.parse_args()
    start = args.start if args.mode == "backfill" else \
        datetime.now(timezone.utc).date().isoformat()
    rep = run_once(args.mode, args.kind, start)
    if args.format == "text":
        print(report.format_text(rep))
    else:
        print(json.dumps(rep, ensure_ascii=False))
    sys.exit(rep["exit_code"])
```
并在顶部补 `import json`。删除旧 `main` 中对 `result` dict 的打印逻辑。

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run.py -v`
Expected: PASS（6 passed）

- [x] **Step 5: 烟测 stdout/退出码**

Run: `python run.py --mode daily --kind regional --format json; echo "exit=$?"`
Expected: 打印一行 JSON（含 results/totals/exit_code），`exit=0` 或 `exit=3`（取决于当日各源）；`runs/latest.json` 生成。

Run: `python run.py --mode daily --kind regional --format text; echo "exit=$?"`
Expected: 打印人类可读摘要。

- [x] **Step 6: Commit**

```bash
git add run.py tests/test_run.py
git commit -m "feat: run_once 报告+stdout(JSON/text)+退出码+环境路径"
```

---

### Task 6: .gitignore 忽略 runs/ + SKILL.md/README 重写无人值守用法

**Files:**
- Modify: `.gitignore`
- Modify: `SKILL.md`
- Modify: `README.md`
- Create: `scripts/openclaw-task.example.md`

**Interfaces:**
- Consumes: 全部前序产出。
- Produces: 无人值守运行说明与调度示例。

- [x] **Step 1: 忽略 runs/**

在 `.gitignore` 的"数据库与日志"段后追加：
```
# 运行报告（无人值守产物）
runs/
```

- [x] **Step 2: 重写 SKILL.md 无人值守段**

在 `SKILL.md` 的"## 用法"之后插入新段（机器层 + 智能体层）：
```markdown
## 无人值守 / 定时任务（OpenClaw 类智能体）

机器层：
- 命令：`python run.py --mode daily --kind all`（默认 `--format json`）。
- stdout 为单个 JSON 运行报告；同时写 `runs/latest.json` 与 `runs/run-<UTC时间戳>.json`。
- 退出码：`0`=全部跑通（含当日 0 行的软失败）；`3`=有采集器异常（报告内 status=error 标明）；`2`=致命（DB/报告写出失败）。
- 路径可用环境变量覆盖：`COAL_DB_PATH`、`COAL_RUNS_DIR`。

报告字段：`started_at/finished_at/duration_ms/mode/kind/results[{name,status,rows,error,duration_ms}]/totals{rows,ok,empty,error}/exit_code`。

智能体层（派生会话内执行，不要交互式提问）：
1. 运行 `python run.py --mode daily --kind all`。
2. 读取 `runs/latest.json`。
3. 产出中文完成回报：各源 `name/status/rows`、`totals`、退出码。
4. 若退出码非 0 或任一 `status=error`：在回报中明确"采集告警"并列出失败源与 error 摘要。

调度示例见 `scripts/cron.example` 与 `scripts/openclaw-task.example.md`。
```
并把"## 数据表"前的旧 `--kind` 示例保留不动。

- [x] **Step 3: README 补一行**

在 `README.md` 的"## 运行方式"末尾追加：
```markdown
无人值守/定时：`python run.py --mode daily --kind all`（stdout 输出 JSON 报告 + 退出码；详见 SKILL.md 与 scripts/openclaw-task.example.md）。
```

- [x] **Step 4: 写 OpenClaw 任务示例**

```markdown
# scripts/openclaw-task.example.md

# OpenClaw 无人值守定时任务示例

让 OpenClaw 调度器按周期派生会话，运行煤焦数据采集并回报。

## 调度内容（派生会话的指令）

> 在项目目录运行 `python run.py --mode daily --kind all`，然后读取 `runs/latest.json`，
> 用中文总结各数据源的 status 与行数、totals 与退出码。若退出码非 0 或存在 status=error，
> 明确标注"采集告警"并列出失败的源与 error 摘要。不要交互式提问，自动完成并回报。

## 频率建议

- 每个交易日 17:30（收盘后）跑一次 `daily all`。

## 环境变量（可选）

- `COAL_DB_PATH`：指定 SQLite 库位置。
- `COAL_RUNS_DIR`：指定运行报告目录。

## 健康判断（调度器/智能体）

- exit 0：健康（含当日无数据的软失败）。
- exit 3：部分失败，看 runs/latest.json 的 results[].error。
- exit 2：致命，需人工介入（DB/报告写出失败）。
```

- [x] **Step 5: 全量回归 + 烟测**

Run: `python -m pytest -v`
Expected: PASS（全部通过）

Run: `python run.py --mode daily --kind regional --format text; echo "exit=$?"`
Expected: 人类可读摘要 + 退出码；`runs/latest.json` 存在；`git status` 不显示 `runs/`（已忽略）。

- [x] **Step 6: Commit**

```bash
git add .gitignore SKILL.md README.md scripts/openclaw-task.example.md
git commit -m "docs: 无人值守/定时任务用法与 OpenClaw 调度示例"
```

---

## Self-Review

- **Spec coverage:** 环境可配→Task1；RunResult 结构化 run()→Task2；run_pipeline 列表→Task3；RunReport/退出码/写出/text→Task4；main 接线 stdout/退出码/环境路径→Task5；runs/ 忽略 + SKILL/README/OpenClaw 示例→Task6。spec §2-§10 均覆盖。
- **Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码与命令。
- **Type consistency:** RunResult 键 `name/status/rows/error/duration_ms` 在 Task2/3/4/5 一致；`status ∈ {ok,empty,error}` 一致；`build_report(results,mode,kind,started_at,finished_at)`、`compute_exit_code(results)`、`write_report(report_dict,runs_dir)`、`format_text(report_dict)` 在 Task4/5 调用一致；退出码 0/3/2 在 spec §4 与 Task4 一致；`config.resolve_db_path/resolve_runs_dir` 在 Task1/5 一致；`run_once(mode,kind,start)`、`run_pipeline(...)->list` 一致。
- **风险提示:** Task2/3/5 改变 run()/run_pipeline 返回类型，需同步更新既有测试（已在对应任务列出替换项）；既有 `test_run.py` 的 `test_run_pipeline_aggregates_counts` 被 Task3 替换，避免遗留断言冲突。
