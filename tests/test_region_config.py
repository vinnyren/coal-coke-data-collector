import config
from storage.sqlite_store import SqliteStore, VALID_TABLES


def test_keyword_tables_present():
    assert set(config.VARIETY_KEYWORDS) == {"焦煤", "焦炭", "动力煤"}
    assert "炼焦煤" in config.VARIETY_KEYWORDS["焦煤"]
    assert "秦皇岛" in config.PORT_NAMES
    assert "山西" in config.PRODUCTION_AREAS
    assert any("蒙煤" == k or "蒙煤" in k for k in config.IMPORT_KEYWORDS)
    assert "唐山" in config.CONSUMPTION_AREAS


def test_valid_tables_include_regional():
    assert {"spot_regional", "spot_regional_stats"} <= VALID_TABLES


def test_schema_creates_regional_tables(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    names = {r["name"] for r in s.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "spot_regional" in names and "spot_regional_stats" in names
    s.close()
