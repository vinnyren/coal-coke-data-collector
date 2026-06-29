import config
from storage.sqlite_store import SqliteStore


def make_store(tmp_path):
    db = tmp_path / "t.db"
    store = SqliteStore(str(db))
    store.init_schema(config.SCHEMA_PATH)
    return store


def test_init_schema_creates_tables(tmp_path):
    """Test that init_schema creates all required tables and close() works."""
    store = SqliteStore(str(tmp_path / "test.db"))
    store.init_schema(config.SCHEMA_PATH)

    tables = store.query("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = {r["name"] for r in tables}

    expected_tables = {
        "futures_daily",
        "futures_realtime",
        "spot_basis",
        "position_rank",
        "inventory",
        "index_price",
    }
    assert expected_tables <= table_names

    store.close()


def test_upsert_inserts_rows(tmp_path):
    s = make_store(tmp_path)
    n = s.upsert(
        "spot_basis",
        [{"variety": "jm", "trade_date": "2024-01-01", "spot_price": 10.0}],
        ["variety", "trade_date"],
    )
    assert n == 1
    rows = s.query("SELECT spot_price FROM spot_basis")
    assert rows[0]["spot_price"] == 10.0
    s.close()


def test_upsert_is_idempotent_and_updates(tmp_path):
    s = make_store(tmp_path)
    s.upsert(
        "spot_basis",
        [{"variety": "jm", "trade_date": "2024-01-01", "spot_price": 10.0}],
        ["variety", "trade_date"],
    )
    s.upsert(
        "spot_basis",
        [{"variety": "jm", "trade_date": "2024-01-01", "spot_price": 99.0}],
        ["variety", "trade_date"],
    )
    rows = s.query("SELECT spot_price FROM spot_basis")
    assert len(rows) == 1  # 不重复
    assert rows[0]["spot_price"] == 99.0  # 覆盖更新
    s.close()


def test_upsert_empty_rows_returns_zero(tmp_path):
    s = make_store(tmp_path)
    assert s.upsert("index_price", [], ["index_name", "trade_date"]) == 0
    s.close()
