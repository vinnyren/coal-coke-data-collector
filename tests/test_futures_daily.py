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
