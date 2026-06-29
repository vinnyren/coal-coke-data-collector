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
