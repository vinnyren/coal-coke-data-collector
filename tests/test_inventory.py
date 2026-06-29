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
