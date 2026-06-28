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
