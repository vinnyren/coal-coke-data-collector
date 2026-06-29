from storage.sqlite_store import SqliteStore
import config
from sources import web_ctctc

# 真实接口 zhIndexDataAll 的 data 结构样本
SAMPLE_ROWS = [
    {"CURRENT_PRICE": 1948, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "sxgljm", "INDEX_NAME": "山西高硫焦精煤", "TYPE": "1"},
    {"CURRENT_PRICE": 1995, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "sxdlsm", "INDEX_NAME": "山西低硫瘦精煤", "TYPE": "1"},
    {"CURRENT_PRICE": 720, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "sxdlm55", "INDEX_NAME": "山西动力煤5500", "TYPE": "1"},
    {"CURRENT_PRICE": 650, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "tyzl45", "INDEX_NAME": "太原中硫4500", "TYPE": "2"},
    {"CURRENT_PRICE": 900, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "sxpcm", "INDEX_NAME": "山西喷吹煤", "TYPE": "1"},
    {"CURRENT_PRICE": 1100, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "jcwykm", "INDEX_NAME": "晋城低硫中块煤", "TYPE": "3"},
    {"CURRENT_PRICE": None, "STAGE_DATE": "2023-03-03",
     "INDEX_CODE": "x", "INDEX_NAME": "山西低硫气精煤", "TYPE": "1"},  # 空价跳过
]


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_maps_jiaomei_and_dongli_skips_others():
    rows = web_ctctc.parse_ctctc(SAMPLE_ROWS)
    # 精煤→焦煤(2)、动力煤/热值→动力煤(2)；喷吹煤/块煤/空价 跳过
    by_variety = {}
    for r in rows:
        by_variety.setdefault(r["variety"], []).append(r["region"])
    assert set(by_variety) == {"焦煤", "动力煤"}
    assert set(by_variety["焦煤"]) == {"山西高硫焦精煤", "山西低硫瘦精煤"}
    assert set(by_variety["动力煤"]) == {"山西动力煤5500", "太原中硫4500"}


def test_parse_record_fields():
    rows = web_ctctc.parse_ctctc(SAMPLE_ROWS)
    coke = next(r for r in rows if r["region"] == "山西高硫焦精煤")
    assert coke["variety"] == "焦煤"
    assert coke["region_type"] == "产地"
    assert coke["price"] == 1948.0
    assert coke["trade_date"] == "2023-03-03"
    assert coke["unit"] == "元/吨"
    assert coke["source"] == "ctctc"


def test_fetch_with_injected_rows_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_ctctc.CtctcSource(s).fetch(data_rows=SAMPLE_ROWS)
    assert n == 4
    assert len(s.query("SELECT * FROM spot_regional WHERE source='ctctc'")) == 4
