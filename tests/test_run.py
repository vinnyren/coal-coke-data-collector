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


def test_run_once_writes_report_and_sets_exit(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv("COAL_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("COAL_RUNS_DIR", str(tmp_path / "runs"))

    class FakeCollector:
        def __init__(self, name, status):
            self.name = name
            self._status = status
        def run(self, **kwargs):
            rows = 5 if self._status == "ok" else 0
            err = None if self._status != "error" else "X: boom"
            return {"name": self.name, "status": self._status, "rows": rows,
                    "error": err, "duration_ms": 1}

    monkeypatch.setattr(run, "_collectors_for_kind",
                        lambda store, kind: [FakeCollector("a", "ok"),
                                             FakeCollector("b", "error")])
    rep = run.run_once(mode="daily", kind="all", start="2015-01-01")
    assert rep["exit_code"] == 3
    assert (tmp_path / "runs" / "latest.json").exists()
    assert rep["totals"]["error"] == 1


def test_build_store_uses_env_db_path(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv("COAL_DB_PATH", str(tmp_path / "x.db"))
    s = run.build_store()
    assert (tmp_path / "x.db").exists()
    s.close()
