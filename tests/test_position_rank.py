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
