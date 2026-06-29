from storage.sqlite_store import SqliteStore
import config
from collectors.spot_stats import SpotStatsCollector


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def seed(s, rows):
    s.upsert("spot_regional", rows,
             ["variety", "region_type", "region", "trade_date", "source"])


def test_stats_per_region_type(tmp_path):
    s = make_store(tmp_path)
    seed(s, [
        {"variety": "动力煤", "region_type": "港口", "region": "秦皇岛",
         "trade_date": "2023-01-03", "price": 900, "unit": None, "source": "cctd"},
        {"variety": "动力煤", "region_type": "港口", "region": "日照",
         "trade_date": "2023-01-03", "price": 800, "unit": None, "source": "cctd"},
    ])
    SpotStatsCollector(s).fetch(date="2023-01-03")
    row = s.query(
        "SELECT * FROM spot_regional_stats "
        "WHERE variety='动力煤' AND region_type='港口'")[0]
    assert row["sample_count"] == 2
    assert row["avg_price"] == 850.0
    assert row["min_price"] == 800.0 and row["max_price"] == 900.0
    assert row["spread"] == 100.0
    assert row["min_region"] == "日照" and row["max_region"] == "秦皇岛"


def test_all_rollup_across_region_types(tmp_path):
    s = make_store(tmp_path)
    seed(s, [
        {"variety": "动力煤", "region_type": "港口", "region": "秦皇岛",
         "trade_date": "2023-01-03", "price": 900, "unit": None, "source": "cctd"},
        {"variety": "动力煤", "region_type": "产地", "region": "山西",
         "trade_date": "2023-01-03", "price": 600, "unit": None, "source": "ncexc"},
    ])
    SpotStatsCollector(s).fetch(date="2023-01-03")
    allrow = s.query(
        "SELECT * FROM spot_regional_stats "
        "WHERE variety='动力煤' AND region_type='ALL'")[0]
    assert allrow["sample_count"] == 2
    assert allrow["min_region"] == "山西" and allrow["max_region"] == "秦皇岛"
    assert allrow["spread"] == 300.0


def test_idempotent_and_skips_null_price(tmp_path):
    s = make_store(tmp_path)
    seed(s, [
        {"variety": "焦炭", "region_type": "全国", "region": "全国",
         "trade_date": "2023-01-03", "price": None, "unit": None, "source": "100ppi"},
        {"variety": "焦炭", "region_type": "全国", "region": "全国",
         "trade_date": "2023-01-03", "price": 1955, "unit": None, "source": "cctd"},
    ])
    SpotStatsCollector(s).fetch(date="2023-01-03")
    SpotStatsCollector(s).fetch(date="2023-01-03")
    rows = s.query("SELECT * FROM spot_regional_stats WHERE variety='焦炭' AND region_type='全国'")
    assert len(rows) == 1                 # 幂等不翻倍
    assert rows[0]["sample_count"] == 1   # None 价被跳过
