# 煤焦交易数据采集技能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Claude Code 技能，采集焦煤/焦炭/动力煤的期货与现货数据并幂等写入本地 SQLite，支持历史回补与每日增量。

**Architecture:** 分层：`config`（品种↔接口映射）→ `storage`（SQLite 幂等 upsert）→ `collectors`（各数据类别，调用 AKShare，异常隔离）→ `sources`（公开网页补充，可插拔）→ `run.py`（编排入口）。每个采集器独立可测，单个失败不影响其它。

**Tech Stack:** Python 3.9+，akshare，pandas，requests，beautifulsoup4，pytest，标准库 sqlite3。

## Global Constraints

- Python 版本下限：3.9。
- 数据库：仅使用标准库 `sqlite3`，DB 文件 `db/coal_data.db`。
- 所有写库走 `SqliteStore.upsert`，必须幂等（重复运行不产生重复行）。
- 品种固定三个：焦煤(jm,大商所)、焦炭(j,大商所)、动力煤(zc,郑商所)。
- 单个采集器异常必须被捕获并记 WARN 日志，不得中断其它采集器。
- AKShare 返回列名以运行时实测为准；解析代码必须对缺列做防御（缺列跳过该行并 WARN）。
- 时间戳统一用 `datetime.now().isoformat(timespec="seconds")`；交易日日期统一 `YYYY-MM-DD` 字符串。

---

### Task 1: 项目骨架与配置

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `config.VARIETIES`（dict，键为中文品种名，值含 `code/exchange/main_symbol/spot_var/dce_name/inventory_name`）；`config.DB_PATH`（pathlib.Path）；`config.SCHEMA_PATH`、`config.LOG_DIR`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import config

def test_varieties_cover_three_kinds():
    assert set(config.VARIETIES) == {"焦煤", "焦炭", "动力煤"}

def test_each_variety_has_required_fields():
    for name, v in config.VARIETIES.items():
        for field in ("code", "exchange", "main_symbol", "spot_var", "inventory_name"):
            assert field in v, f"{name} 缺少 {field}"

def test_db_path_points_to_sqlite_file():
    assert str(config.DB_PATH).endswith("coal_data.db")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'config'`）

- [ ] **Step 3: Write minimal implementation**

```python
# config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "coal_data.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
LOG_DIR = BASE_DIR / "logs"

# 品种 → 各接口所需标识
# main_symbol: 新浪主力连续代码; spot_var: 现货基差/持仓接口的品种缩写
VARIETIES = {
    "焦煤": {"code": "jm", "exchange": "dce", "main_symbol": "JM0",
             "spot_var": "JM", "dce_name": "焦煤", "inventory_name": "焦煤"},
    "焦炭": {"code": "j", "exchange": "dce", "main_symbol": "J0",
             "spot_var": "J", "dce_name": "焦炭", "inventory_name": "焦炭"},
    "动力煤": {"code": "zc", "exchange": "czce", "main_symbol": "ZC0",
               "spot_var": "ZC", "dce_name": None, "inventory_name": "动力煤"},
}
```

```text
# requirements.txt
akshare>=1.12
pandas>=1.5
requests>=2.28
beautifulsoup4>=4.11
pytest>=7.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config.py tests/test_config.py
git commit -m "feat: 添加项目配置与品种映射"
```

---

### Task 2: SQLite 建表 DDL 与幂等存储层

**Files:**
- Create: `db/schema.sql`
- Create: `storage/__init__.py`
- Create: `storage/sqlite_store.py`
- Create: `tests/test_sqlite_store.py`

**Interfaces:**
- Consumes: 无。
- Produces: `SqliteStore(db_path)`；方法 `init_schema(schema_path)`、`upsert(table, rows, conflict_cols) -> int`（返回写入行数）、`query(sql, params=()) -> list[dict]`、`close()`。`upsert` 对 `rows`（list[dict]）按 `conflict_cols` 做 `INSERT ... ON CONFLICT DO UPDATE`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sqlite_store.py
from storage.sqlite_store import SqliteStore

def make_store(tmp_path):
    db = tmp_path / "t.db"
    store = SqliteStore(str(db))
    store.conn.executescript(
        "CREATE TABLE t (a TEXT, b TEXT, v REAL, UNIQUE(a, b));"
    )
    return store

def test_upsert_inserts_rows(tmp_path):
    s = make_store(tmp_path)
    n = s.upsert("t", [{"a": "x", "b": "1", "v": 10.0}], ["a", "b"])
    assert n == 1
    assert s.query("SELECT v FROM t")[0]["v"] == 10.0

def test_upsert_is_idempotent_and_updates(tmp_path):
    s = make_store(tmp_path)
    s.upsert("t", [{"a": "x", "b": "1", "v": 10.0}], ["a", "b"])
    s.upsert("t", [{"a": "x", "b": "1", "v": 99.0}], ["a", "b"])
    rows = s.query("SELECT v FROM t")
    assert len(rows) == 1           # 不重复
    assert rows[0]["v"] == 99.0     # 覆盖更新

def test_upsert_empty_rows_returns_zero(tmp_path):
    s = make_store(tmp_path)
    assert s.upsert("t", [], ["a", "b"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sqlite_store.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'storage'`）

- [ ] **Step 3: Write minimal implementation**

```python
# storage/__init__.py
```

```python
# storage/sqlite_store.py
import sqlite3
from pathlib import Path


class SqliteStore:
    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self, schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    def upsert(self, table, rows, conflict_cols):
        if not rows:
            return 0
        cols = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        update_cols = [c for c in cols if c not in conflict_cols]
        set_clause = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        conflict = ", ".join(conflict_cols)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {set_clause}"
            if update_cols else
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO NOTHING"
        )
        data = [tuple(r.get(c) for c in cols) for r in rows]
        self.conn.executemany(sql, data)
        self.conn.commit()
        return len(rows)

    def query(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()
```

```sql
-- db/schema.sql
CREATE TABLE IF NOT EXISTS futures_daily (
    variety TEXT NOT NULL,
    contract TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, settle REAL,
    volume REAL, open_interest REAL,
    UNIQUE(variety, contract, trade_date)
);

CREATE TABLE IF NOT EXISTS futures_realtime (
    variety TEXT NOT NULL,
    contract TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    last_price REAL, bid REAL, ask REAL,
    volume REAL, open_interest REAL,
    UNIQUE(variety, contract, captured_at)
);

CREATE TABLE IF NOT EXISTS spot_basis (
    variety TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    spot_price REAL, dominant_price REAL, near_price REAL,
    basis REAL, basis_rate REAL,
    UNIQUE(variety, trade_date)
);

CREATE TABLE IF NOT EXISTS position_rank (
    variety TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    side TEXT NOT NULL,          -- 'long' / 'short'
    rank_no INTEGER NOT NULL,
    member TEXT,
    volume REAL, change REAL,
    UNIQUE(variety, trade_date, side, rank_no)
);

CREATE TABLE IF NOT EXISTS inventory (
    variety TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    inventory REAL, change REAL,
    UNIQUE(variety, trade_date)
);

CREATE TABLE IF NOT EXISTS index_price (
    index_name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL, source TEXT,
    UNIQUE(index_name, trade_date)
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sqlite_store.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add db/schema.sql storage/ tests/test_sqlite_store.py
git commit -m "feat: 添加 SQLite 建表 DDL 与幂等存储层"
```

---

### Task 3: 采集器基类（重试 + 异常隔离 + 日志）

**Files:**
- Create: `collectors/__init__.py`
- Create: `collectors/base.py`
- Create: `tests/test_base_collector.py`

**Interfaces:**
- Consumes: `SqliteStore`。
- Produces: `with_retry(fn, retries=3, backoff=2)`（成功返回 fn 结果，全部失败抛最后异常）；`BaseCollector(store)`，子类实现 `fetch(self, **kwargs) -> int`（返回写入行数），`name` 类属性；`run(self, **kwargs) -> int` 捕获异常返回 0 并记 WARN。`get_logger(name)` 返回写入 `logs/` 的 logger。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_base_collector.py
import pytest
from collectors.base import BaseCollector, with_retry


def test_with_retry_succeeds_after_failures(monkeypatch):
    import collectors.base as base
    monkeypatch.setattr(base.time, "sleep", lambda *_: None)
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"
    assert with_retry(flaky, retries=3, backoff=0) == "ok"
    assert calls["n"] == 3


def test_with_retry_raises_after_exhaustion(monkeypatch):
    import collectors.base as base
    monkeypatch.setattr(base.time, "sleep", lambda *_: None)
    def always_fail():
        raise ValueError("nope")
    with pytest.raises(ValueError):
        with_retry(always_fail, retries=2, backoff=0)


def test_run_isolates_exception_and_returns_zero():
    class Boom(BaseCollector):
        name = "boom"
        def fetch(self, **kwargs):
            raise RuntimeError("explode")
    assert Boom(store=None).run() == 0


def test_run_returns_fetch_count():
    class Good(BaseCollector):
        name = "good"
        def fetch(self, **kwargs):
            return 7
    assert Good(store=None).run() == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base_collector.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'collectors'`）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/__init__.py
```

```python
# collectors/base.py
import time
import logging
from pathlib import Path
import config


def get_logger(name):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(config.LOG_DIR / "collector.log", encoding="utf-8")
        sh = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        fh.setFormatter(fmt); sh.setFormatter(fmt)
        logger.addHandler(fh); logger.addHandler(sh)
    return logger


def with_retry(fn, retries=3, backoff=2):
    last = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last


class BaseCollector:
    name = "base"

    def __init__(self, store):
        self.store = store
        self.log = get_logger(f"collector.{self.name}")

    def fetch(self, **kwargs):
        raise NotImplementedError

    def run(self, **kwargs):
        try:
            n = self.fetch(**kwargs)
            self.log.info("%s 写入 %s 行", self.name, n)
            return n
        except Exception as e:  # noqa: BLE001
            self.log.warning("%s 采集失败: %s", self.name, e)
            return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_base_collector.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/__init__.py collectors/base.py tests/test_base_collector.py
git commit -m "feat: 添加采集器基类（重试/异常隔离/日志）"
```

---

### Task 4: 期货历史日线采集器

**Files:**
- Create: `collectors/futures_daily.py`
- Create: `tests/test_futures_daily.py`

**Interfaces:**
- Consumes: `BaseCollector`、`SqliteStore`、`config.VARIETIES`。
- Produces: `FuturesDailyCollector(store)`，`fetch(self, start="2015-01-01", end=None) -> int`。内部用 `ak.futures_main_sina(symbol, start_date, end_date)` 取主力连续日线，写 `futures_daily`，`contract` 固定为 `<main_symbol>`（主力连续）。AKShare 函数通过模块属性 `ak` 引用，便于测试 patch。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_futures_daily.py
import pandas as pd
from storage.sqlite_store import SqliteStore
import config
from collectors import futures_daily


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_fetch_writes_daily_rows(tmp_path, monkeypatch):
    df = pd.DataFrame({
        "date": ["2023-01-03", "2023-01-04"],
        "open": [1800, 1810], "high": [1850, 1820],
        "low": [1790, 1800], "close": [1840, 1805],
        "volume": [1000, 1100], "hold": [5000, 5100],
    })
    monkeypatch.setattr(futures_daily.ak, "futures_main_sina",
                        lambda **kw: df)
    s = make_store(tmp_path)
    c = futures_daily.FuturesDailyCollector(s)
    n = c.fetch(start="2023-01-01", end="2023-01-31")
    assert n == len(config.VARIETIES) * 2     # 3 品种 × 2 行
    rows = s.query("SELECT * FROM futures_daily WHERE variety='焦煤'")
    assert len(rows) == 2
    assert rows[0]["close"] in (1840.0, 1805.0)


def test_fetch_idempotent(tmp_path, monkeypatch):
    df = pd.DataFrame({
        "date": ["2023-01-03"], "open": [1800], "high": [1850],
        "low": [1790], "close": [1840], "volume": [1000], "hold": [5000],
    })
    monkeypatch.setattr(futures_daily.ak, "futures_main_sina", lambda **kw: df)
    s = make_store(tmp_path)
    futures_daily.FuturesDailyCollector(s).fetch(start="2023-01-01")
    futures_daily.FuturesDailyCollector(s).fetch(start="2023-01-01")
    rows = s.query("SELECT * FROM futures_daily")
    assert len(rows) == len(config.VARIETIES)   # 不翻倍
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_futures_daily.py -v`
Expected: FAIL（`AttributeError`/`ModuleNotFoundError`：`collectors.futures_daily` 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/futures_daily.py
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

# 列名兼容映射：AKShare 不同版本列名可能不同
_COL = {
    "date": ["date", "日期"],
    "open": ["open", "开盘价"],
    "high": ["high", "最高价"],
    "low": ["low", "最低价"],
    "close": ["close", "收盘价"],
    "volume": ["volume", "成交量"],
    "hold": ["hold", "持仓量"],
}


def _pick(row, keys):
    for k in keys:
        if k in row and row[k] == row[k]:   # 非 NaN
            return row[k]
    return None


class FuturesDailyCollector(BaseCollector):
    name = "futures_daily"

    def fetch(self, start="2015-01-01", end=None):
        from datetime import date
        end = end or date.today().isoformat()
        total = 0
        for vname, v in config.VARIETIES.items():
            df = with_retry(lambda: ak.futures_main_sina(
                symbol=v["main_symbol"],
                start_date=start.replace("-", ""),
                end_date=end.replace("-", "")))
            if df is None or df.empty:
                self.log.warning("%s 无日线数据", vname)
                continue
            rows = []
            for _, r in df.iterrows():
                d = r.to_dict()
                trade_date = str(_pick(d, _COL["date"]))[:10]
                rows.append({
                    "variety": vname, "contract": v["main_symbol"],
                    "trade_date": trade_date,
                    "open": _pick(d, _COL["open"]), "high": _pick(d, _COL["high"]),
                    "low": _pick(d, _COL["low"]), "close": _pick(d, _COL["close"]),
                    "settle": None,
                    "volume": _pick(d, _COL["volume"]),
                    "open_interest": _pick(d, _COL["hold"]),
                })
            total += self.store.upsert(
                "futures_daily", rows, ["variety", "contract", "trade_date"])
        return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_futures_daily.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/futures_daily.py tests/test_futures_daily.py
git commit -m "feat: 添加期货历史日线采集器"
```

---

### Task 5: 现货价与基差采集器

**Files:**
- Create: `collectors/spot_basis.py`
- Create: `tests/test_spot_basis.py`

**Interfaces:**
- Consumes: `BaseCollector`、`config.VARIETIES`。
- Produces: `SpotBasisCollector(store)`，`fetch(self, date=None) -> int`。用 `ak.futures_spot_price(date_str)` 取某日全品种现货/基差，筛选 `spot_var` 命中的行写 `spot_basis`。模块属性 `ak` 可 patch。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spot_basis.py
import pandas as pd
from storage.sqlite_store import SqliteStore
import config
from collectors import spot_basis


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_fetch_filters_coal_varieties(tmp_path, monkeypatch):
    df = pd.DataFrame({
        "symbol": ["JM", "J", "ZC", "RB"],
        "spot_price": [1800, 2400, 700, 4000],
        "dominant_contract_price": [1820, 2420, 710, 4010],
        "near_contract_price": [1810, 2410, 705, 4005],
        "dom_basis": [-20, -20, -10, -10],
        "dom_basis_rate": [-1.1, -0.8, -1.4, -0.25],
    })
    monkeypatch.setattr(spot_basis.ak, "futures_spot_price", lambda d: df)
    s = make_store(tmp_path)
    n = spot_basis.SpotBasisCollector(s).fetch(date="2023-01-03")
    assert n == 3                       # 只写焦煤/焦炭/动力煤，排除 RB
    rows = s.query("SELECT variety FROM spot_basis ORDER BY variety")
    assert {r["variety"] for r in rows} == {"焦煤", "焦炭", "动力煤"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_spot_basis.py -v`
Expected: FAIL（`collectors.spot_basis` 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/spot_basis.py
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

_VAR_BY_SPOT = {v["spot_var"]: name for name, v in config.VARIETIES.items()}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class SpotBasisCollector(BaseCollector):
    name = "spot_basis"

    def fetch(self, date=None):
        from datetime import date as _date
        d = (date or _date.today().isoformat()).replace("-", "")
        df = with_retry(lambda: ak.futures_spot_price(d))
        if df is None or df.empty:
            self.log.warning("%s 无现货基差数据", d)
            return 0
        trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        rows = []
        for _, r in df.iterrows():
            row = r.to_dict()
            sym = _g(row, "symbol", "var")
            if sym not in _VAR_BY_SPOT:
                continue
            rows.append({
                "variety": _VAR_BY_SPOT[sym],
                "trade_date": trade_date,
                "spot_price": _g(row, "spot_price"),
                "dominant_price": _g(row, "dominant_contract_price"),
                "near_price": _g(row, "near_contract_price"),
                "basis": _g(row, "dom_basis", "near_basis"),
                "basis_rate": _g(row, "dom_basis_rate", "near_basis_rate"),
            })
        return self.store.upsert("spot_basis", rows, ["variety", "trade_date"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_spot_basis.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/spot_basis.py tests/test_spot_basis.py
git commit -m "feat: 添加现货价与基差采集器"
```

---

### Task 6: 持仓排名采集器

**Files:**
- Create: `collectors/position_rank.py`
- Create: `tests/test_position_rank.py`

**Interfaces:**
- Consumes: `BaseCollector`、`config.VARIETIES`（仅 `exchange == "dce"` 的品种：焦煤、焦炭）。
- Produces: `PositionRankCollector(store)`，`fetch(self, date=None) -> int`。用 `ak.futures_dce_position_rank(date)`（返回 `{品种: DataFrame}`）写 `position_rank`，long/short 两侧。模块属性 `ak` 可 patch。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_position_rank.py
import pandas as pd
from storage.sqlite_store import SqliteStore
import config
from collectors import position_rank


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_fetch_writes_long_and_short(tmp_path, monkeypatch):
    jm = pd.DataFrame({
        "long_party_name": ["永安", "中信"],
        "long_open_interest": [1200, 1100],
        "long_open_interest_chg": [10, -5],
        "short_party_name": ["国泰", "海通"],
        "short_open_interest": [1300, 1000],
        "short_open_interest_chg": [20, -8],
        "rank": [1, 2],
    })
    monkeypatch.setattr(position_rank.ak, "futures_dce_position_rank",
                        lambda date: {"焦煤": jm})
    s = make_store(tmp_path)
    n = position_rank.PositionRankCollector(s).fetch(date="2023-01-03")
    assert n == 4                       # 2 long + 2 short
    longs = s.query("SELECT * FROM position_rank WHERE side='long'")
    assert len(longs) == 2
    assert longs[0]["member"] in ("永安", "中信")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_position_rank.py -v`
Expected: FAIL（`collectors.position_rank` 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/position_rank.py
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

_DCE_VARIETIES = {v["dce_name"]: name
                  for name, v in config.VARIETIES.items()
                  if v["exchange"] == "dce" and v["dce_name"]}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class PositionRankCollector(BaseCollector):
    name = "position_rank"

    def fetch(self, date=None):
        from datetime import date as _date
        d = (date or _date.today().isoformat()).replace("-", "")
        data = with_retry(lambda: ak.futures_dce_position_rank(date=d))
        if not data:
            self.log.warning("%s 无持仓排名数据", d)
            return 0
        trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        total = 0
        for dce_name, vname in _DCE_VARIETIES.items():
            df = data.get(dce_name)
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.iterrows():
                row = r.to_dict()
                rank_no = int(_g(row, "rank") or 0)
                rows.append({
                    "variety": vname, "trade_date": trade_date, "side": "long",
                    "rank_no": rank_no, "member": _g(row, "long_party_name"),
                    "volume": _g(row, "long_open_interest"),
                    "change": _g(row, "long_open_interest_chg"),
                })
                rows.append({
                    "variety": vname, "trade_date": trade_date, "side": "short",
                    "rank_no": rank_no, "member": _g(row, "short_party_name"),
                    "volume": _g(row, "short_open_interest"),
                    "change": _g(row, "short_open_interest_chg"),
                })
            total += self.store.upsert(
                "position_rank", rows,
                ["variety", "trade_date", "side", "rank_no"])
        return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_position_rank.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/position_rank.py tests/test_position_rank.py
git commit -m "feat: 添加持仓排名采集器"
```

---

### Task 7: 库存采集器

**Files:**
- Create: `collectors/inventory.py`
- Create: `tests/test_inventory.py`

**Interfaces:**
- Consumes: `BaseCollector`、`config.VARIETIES`。
- Produces: `InventoryCollector(store)`，`fetch(self) -> int`。用 `ak.futures_inventory_em(symbol=inventory_name)` 写 `inventory`。某品种接口不支持时记 WARN 跳过。模块属性 `ak` 可 patch。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory.py
import pandas as pd
from storage.sqlite_store import SqliteStore
import config
from collectors import inventory


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_fetch_writes_inventory(tmp_path, monkeypatch):
    df = pd.DataFrame({
        "日期": ["2023-01-03", "2023-01-04"],
        "库存": [100, 120],
        "增减": [0, 20],
    })
    monkeypatch.setattr(inventory.ak, "futures_inventory_em",
                        lambda symbol: df)
    s = make_store(tmp_path)
    n = inventory.InventoryCollector(s).fetch()
    assert n == len(config.VARIETIES) * 2
    rows = s.query("SELECT * FROM inventory WHERE variety='动力煤'")
    assert len(rows) == 2


def test_fetch_skips_failing_variety(tmp_path, monkeypatch):
    def maybe(symbol):
        if symbol == "动力煤":
            raise ValueError("不支持")
        return pd.DataFrame({"日期": ["2023-01-03"], "库存": [100], "增减": [0]})
    monkeypatch.setattr(inventory.ak, "futures_inventory_em", maybe)
    monkeypatch.setattr(inventory, "with_retry", lambda fn, **kw: fn())
    s = make_store(tmp_path)
    n = inventory.InventoryCollector(s).fetch()
    assert n == 2                        # 焦煤+焦炭各 1 行，动力煤被跳过
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_inventory.py -v`
Expected: FAIL（`collectors.inventory` 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/inventory.py
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class InventoryCollector(BaseCollector):
    name = "inventory"

    def fetch(self):
        total = 0
        for vname, v in config.VARIETIES.items():
            try:
                df = with_retry(
                    lambda: ak.futures_inventory_em(symbol=v["inventory_name"]))
            except Exception as e:  # noqa: BLE001
                self.log.warning("%s 库存接口失败: %s", vname, e)
                continue
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.iterrows():
                row = r.to_dict()
                td = str(_g(row, "日期", "date"))[:10]
                rows.append({
                    "variety": vname, "trade_date": td,
                    "inventory": _g(row, "库存", "inventory"),
                    "change": _g(row, "增减", "change"),
                })
            total += self.store.upsert("inventory", rows, ["variety", "trade_date"])
        return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_inventory.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/inventory.py tests/test_inventory.py
git commit -m "feat: 添加库存采集器"
```

---

### Task 8: 期货实时行情采集器

**Files:**
- Create: `collectors/futures_realtime.py`
- Create: `tests/test_futures_realtime.py`

**Interfaces:**
- Consumes: `BaseCollector`、`config.VARIETIES`。
- Produces: `FuturesRealtimeCollector(store)`，`fetch(self, now=None) -> int`。用 `ak.futures_zh_spot(symbol=..., market="CF")` 取实时快照写 `futures_realtime`，`captured_at` 用 `now` 或当前时间。模块属性 `ak` 可 patch。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_futures_realtime.py
import pandas as pd
from storage.sqlite_store import SqliteStore
import config
from collectors import futures_realtime


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_fetch_writes_snapshot(tmp_path, monkeypatch):
    df = pd.DataFrame({
        "symbol": ["JM0", "J0", "ZC0"],
        "current_price": [1840, 2400, 700],
        "bid_price": [1839, 2399, 699],
        "ask_price": [1841, 2401, 701],
        "volume": [1000, 2000, 300],
        "hold": [5000, 6000, 1500],
    })
    monkeypatch.setattr(futures_realtime.ak, "futures_zh_spot", lambda **kw: df)
    s = make_store(tmp_path)
    n = futures_realtime.FuturesRealtimeCollector(s).fetch(now="2023-01-03T15:00:00")
    assert n == 3
    rows = s.query("SELECT * FROM futures_realtime WHERE variety='焦炭'")
    assert rows[0]["last_price"] == 2400.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_futures_realtime.py -v`
Expected: FAIL（`collectors.futures_realtime` 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/futures_realtime.py
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

_VAR_BY_MAIN = {v["main_symbol"]: name for name, v in config.VARIETIES.items()}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class FuturesRealtimeCollector(BaseCollector):
    name = "futures_realtime"

    def fetch(self, now=None):
        from datetime import datetime
        captured = now or datetime.now().isoformat(timespec="seconds")
        symbols = ",".join(v["main_symbol"] for v in config.VARIETIES.values())
        df = with_retry(lambda: ak.futures_zh_spot(symbol=symbols, market="CF"))
        if df is None or df.empty:
            self.log.warning("无实时行情数据")
            return 0
        rows = []
        for _, r in df.iterrows():
            row = r.to_dict()
            sym = _g(row, "symbol")
            vname = _VAR_BY_MAIN.get(sym)
            if not vname:
                continue
            rows.append({
                "variety": vname, "contract": sym, "captured_at": captured,
                "last_price": _g(row, "current_price", "现价"),
                "bid": _g(row, "bid_price", "买价"),
                "ask": _g(row, "ask_price", "卖价"),
                "volume": _g(row, "volume", "成交量"),
                "open_interest": _g(row, "hold", "持仓量"),
            })
        return self.store.upsert(
            "futures_realtime", rows, ["variety", "contract", "captured_at"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_futures_realtime.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/futures_realtime.py tests/test_futures_realtime.py
git commit -m "feat: 添加期货实时行情采集器"
```

---

### Task 9: 公开网页指数补充源（可插拔）

**Files:**
- Create: `sources/__init__.py`
- Create: `sources/web_cctd.py`
- Create: `tests/test_web_cctd.py`

**Interfaces:**
- Consumes: `BaseCollector`。
- Produces: `CctdIndexSource(store)`，`fetch(self, html=None) -> int`。`parse_index(html) -> list[dict]`（纯函数，解析指数名/价格/日期），`fetch` 默认用 requests 抓页面后调用 `parse_index` 写 `index_price`，网络失败仅 WARN 返回 0。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_cctd.py
from storage.sqlite_store import SqliteStore
import config
from sources import web_cctd

SAMPLE_HTML = """
<table id="indexTable">
  <tr><td>CCTD秦皇岛动力煤(Q5500)</td><td>2023-01-03</td><td>880</td></tr>
  <tr><td>环渤海动力煤指数</td><td>2023-01-03</td><td>732</td></tr>
</table>
"""


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_index_extracts_rows():
    out = web_cctd.parse_index(SAMPLE_HTML)
    assert {"index_name", "trade_date", "price"} <= set(out[0])
    names = {r["index_name"] for r in out}
    assert "环渤海动力煤指数" in names


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_cctd.CctdIndexSource(s).fetch(html=SAMPLE_HTML)
    assert n == 2
    rows = s.query("SELECT * FROM index_price")
    assert rows[0]["source"] == "cctd"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_cctd.py -v`
Expected: FAIL（`sources.web_cctd` 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# sources/__init__.py
```

```python
# sources/web_cctd.py
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector, with_retry

CCTD_URL = "https://www.cctd.com.cn/index.php?m=content&c=index&a=lists&catid=520"
SOURCE = "cctd"


def parse_index(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        name, date_str, price_str = tds[0], tds[1], tds[2]
        try:
            price = float(price_str.replace(",", ""))
        except ValueError:
            continue
        out.append({"index_name": name, "trade_date": date_str,
                    "price": price, "source": SOURCE})
    return out


class CctdIndexSource(BaseCollector):
    name = "web_cctd"

    def fetch(self, html=None):
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(CCTD_URL, timeout=15))
                resp.encoding = resp.apparent_encoding
                html = resp.text
            except Exception as e:  # noqa: BLE001
                self.log.warning("CCTD 页面抓取失败: %s", e)
                return 0
        rows = parse_index(html)
        if not rows:
            self.log.warning("CCTD 未解析到指数行（页面结构可能已变）")
            return 0
        return self.store.upsert("index_price", rows, ["index_name", "trade_date"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_cctd.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add sources/ tests/test_web_cctd.py
git commit -m "feat: 添加 CCTD 公开网页指数补充源"
```

---

### Task 10: 统一入口 run.py（编排 backfill/daily）

**Files:**
- Create: `run.py`
- Create: `tests/test_run.py`

**Interfaces:**
- Consumes: 所有 collector/source、`SqliteStore`、`config`。
- Produces: `build_store() -> SqliteStore`（建库+建表）；`run_pipeline(store, mode, kind="all", start="2015-01-01") -> dict`（返回各采集器写入行数 dict）；`main()` 解析 argparse 参数。`KIND_MAP` 映射 kind→采集器集合。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run.py
import run
import config
from storage.sqlite_store import SqliteStore


class FakeCollector:
    def __init__(self, store, n):
        self.store = store; self.n = n; self.name = "fake"
    def run(self, **kwargs):
        return self.n


def test_run_pipeline_aggregates_counts(tmp_path, monkeypatch):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    monkeypatch.setattr(run, "_collectors_for_kind",
                        lambda store, kind: [FakeCollector(store, 3),
                                             FakeCollector(store, 5)])
    result = run.run_pipeline(s, mode="daily", kind="all")
    assert sum(result.values()) == 8


def test_build_store_creates_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "x.db")
    s = run.build_store()
    names = {r["name"] for r in s.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "futures_daily" in names and "spot_basis" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL（`No module named 'run'`）

- [ ] **Step 3: Write minimal implementation**

```python
# run.py
import argparse
import config
from storage.sqlite_store import SqliteStore
from collectors.futures_daily import FuturesDailyCollector
from collectors.futures_realtime import FuturesRealtimeCollector
from collectors.spot_basis import SpotBasisCollector
from collectors.position_rank import PositionRankCollector
from collectors.inventory import InventoryCollector
from sources.web_cctd import CctdIndexSource


def build_store():
    store = SqliteStore(str(config.DB_PATH))
    store.init_schema(config.SCHEMA_PATH)
    return store


def _collectors_for_kind(store, kind):
    groups = {
        "futures": [FuturesDailyCollector(store), FuturesRealtimeCollector(store)],
        "spot": [SpotBasisCollector(store)],
        "rank": [PositionRankCollector(store)],
        "inventory": [InventoryCollector(store)],
        "index": [CctdIndexSource(store)],
    }
    if kind == "all":
        out = []
        for v in groups.values():
            out.extend(v)
        return out
    return groups.get(kind, [])


def run_pipeline(store, mode, kind="all", start="2015-01-01"):
    result = {}
    for c in _collectors_for_kind(store, kind):
        if c.name == "futures_daily":
            result[c.name] = c.run(start=start)
        else:
            result[c.name] = c.run()
    return result


def main():
    p = argparse.ArgumentParser(description="煤焦交易数据采集")
    p.add_argument("--mode", choices=["backfill", "daily"], default="daily")
    p.add_argument("--kind",
                   choices=["all", "futures", "spot", "rank", "inventory", "index"],
                   default="all")
    p.add_argument("--start", default="2015-01-01")
    args = p.parse_args()
    store = build_store()
    start = args.start if args.mode == "backfill" else \
        __import__("datetime").date.today().isoformat()
    result = run_pipeline(store, args.mode, args.kind, start)
    store.close()
    print("采集完成:", result)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add run.py tests/test_run.py
git commit -m "feat: 添加统一入口 run.py 编排采集流程"
```

---

### Task 11: SKILL.md、定时示例与全量测试通过

**Files:**
- Create: `SKILL.md`
- Create: `scripts/cron.example`
- Modify: `README.md`（补运行说明，已存在则追加“技能用法”段）

**Interfaces:**
- Consumes: 全部。
- Produces: 技能触发描述与用法文档；可被斜杠命令/自动触发引用。

- [ ] **Step 1: 编写 SKILL.md**

```markdown
---
name: 煤焦交易数据采集
description: 采集焦煤、焦炭、动力煤的期货与现货数据（行情/基差/持仓/库存/指数）并写入本地 SQLite。当用户提到采集煤炭/焦煤/焦炭价格、煤焦期货现货数据入库、煤焦行情回补或每日更新时使用本技能。
---

# 煤焦交易数据采集技能

采集焦煤(jm)、焦炭(j)、动力煤(zc)的期货与现货数据并幂等写入本地 SQLite。

## 依赖

\`\`\`bash
pip install -r requirements.txt
\`\`\`

## 用法

\`\`\`bash
# 首次历史回补（拉全历史日线/基差等）
python run.py --mode backfill --start 2015-01-01

# 每日增量（只补最新交易日）
python run.py --mode daily

# 只更某一类: futures | spot | rank | inventory | index | all
python run.py --mode daily --kind futures
\`\`\`

## 数据表

futures_daily / futures_realtime / spot_basis / position_rank / inventory / index_price，
均以业务主键唯一约束，重复运行幂等去重。详见 db/schema.sql。

## 数据来源

- 主通道：AKShare（聚合新浪/东财/交易所，合法零成本）。
- 补充：CCTD 等公开免登录指数页面（sources/，失败不影响主数据）。

## 定时

参见 scripts/cron.example（crontab 与 macOS launchd 示例）。
\`\`\`
```

- [ ] **Step 2: 编写 scripts/cron.example**

```text
# scripts/cron.example
# ── crontab：每个交易日 17:30 增量采集（周一至周五）──
# 编辑: crontab -e ，把 PROJECT 改成本技能绝对路径
# 30 17 * * 1-5 cd /PATH/TO/煤炭和焦炭交易数据采集技能 && /usr/bin/python3 run.py --mode daily >> logs/cron.log 2>&1

# ── macOS launchd：~/Library/LaunchAgents/com.coal.collector.plist ──
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0"><dict>
#   <key>Label</key><string>com.coal.collector</string>
#   <key>ProgramArguments</key>
#     <array><string>/usr/bin/python3</string><string>run.py</string>
#            <string>--mode</string><string>daily</string></array>
#   <key>WorkingDirectory</key><string>/PATH/TO/煤炭和焦炭交易数据采集技能</string>
#   <key>StartCalendarInterval</key>
#     <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
# </dict></plist>
# 加载: launchctl load ~/Library/LaunchAgents/com.coal.collector.plist
```

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest -v`
Expected: PASS（全部通过，约 18 个用例）

- [ ] **Step 4: 烟测入口可启动**

Run: `python run.py --mode daily --kind index`
Expected: 无异常退出，打印“采集完成: {...}”（网络不可用时 index 计数为 0 但不报错）

- [ ] **Step 5: Commit**

```bash
git add SKILL.md scripts/cron.example README.md
git commit -m "docs: 添加 SKILL.md、定时示例与运行说明"
```

---

## Self-Review

- **Spec coverage:** 品种(焦煤/焦炭/动力煤)→Task1 config；期货日线→Task4；实时→Task8；现货基差→Task5；持仓→Task6；库存→Task7；公开网页指数→Task9；SQLite 幂等→Task2；backfill/daily→Task10；SKILL+定时→Task11。设计各节均有对应任务。
- **Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码。
- **Type consistency:** `SqliteStore.upsert(table, rows, conflict_cols)` 在所有 collector 中签名一致；`config.VARIETIES` 字段（code/exchange/main_symbol/spot_var/dce_name/inventory_name）在 Task4-8 引用一致；`BaseCollector.run()/fetch()` 契约统一。
- **风险提示:** AKShare 实际列名/接口签名可能与示例不同，已用 `_g/_pick` 列名兼容 + 防御性跳过缓解；执行时若接口报错，按 systematic-debugging 用实测返回值修正列名映射。
