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
