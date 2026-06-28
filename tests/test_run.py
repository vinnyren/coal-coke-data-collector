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
