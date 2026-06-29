# tests/test_run.py
import run
import config
from storage.sqlite_store import SqliteStore


def test_run_pipeline_returns_runresults(tmp_path, monkeypatch):
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


def test_build_store_creates_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "x.db")
    s = run.build_store()
    names = {r["name"] for r in s.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "futures_daily" in names and "spot_basis" in names


def test_regional_kind_order_and_membership(tmp_path):
    import config
    from storage.sqlite_store import SqliteStore
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    names = [c.name for c in run._collectors_for_kind(s, "regional")]
    assert names == ["web_100ppi", "web_cctd", "web_ncexc", "web_ctctc",
                     "spot_stats"]


def test_all_includes_regional_not_index(tmp_path):
    import config
    from storage.sqlite_store import SqliteStore
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    names = [c.name for c in run._collectors_for_kind(s, "all")]
    assert "spot_stats" in names and "web_100ppi" in names
    # index kind 已移除
    assert run._collectors_for_kind(s, "index") == []
