from storage.sqlite_store import SqliteStore
import config
from sources import web_ncexc

# 真实接口 getQuotationIndexPrice.json 的 dataRows 结构样本
# ZS=指数值, ZSZLX=指数种类(区域+热值), FBRQ=发布日期, INDEXTYPE=指数类型
SAMPLE_ROWS = [
    {"INDEXTYPE": "直达煤指数", "ZS": "564", "FBRQ": "2026-05-29",
     "ZSZLX": "陕西5500K", "INDEXTYPECODE": "103"},
    {"INDEXTYPE": "直达煤指数", "ZS": "497", "FBRQ": "2026-05-29",
     "ZSZLX": "陕西5000K", "INDEXTYPECODE": "103"},
    {"INDEXTYPE": "直达煤指数", "ZS": "500", "FBRQ": "2026-05-29",
     "ZSZLX": "蒙东3500K", "INDEXTYPECODE": "103"},
    {"INDEXTYPE": "下水煤指数", "ZS": "640", "FBRQ": "2026-05-29",
     "ZSZLX": "5500K", "INDEXTYPECODE": "101"},
    {"INDEXTYPE": "直达煤指数", "ZS": None, "FBRQ": "2026-05-29",
     "ZSZLX": "山西5500K", "INDEXTYPECODE": "103"},  # 空值应跳过
]


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_extracts_regional_thermal_indices():
    rows = web_ncexc.parse_ncexc(SAMPLE_ROWS)
    # 4 行有效（山西因 ZS=None 被跳过），全为动力煤
    assert len(rows) == 4
    assert all(r["variety"] == "动力煤" for r in rows)
    assert all(r["source"] == "ncexc" for r in rows)
    # region 保留完整 ZSZLX，区分同省不同热值
    assert {r["region"] for r in rows} == {"陕西5500K", "陕西5000K", "蒙东3500K", "5500K"}


def test_zhida_is_production_area_and_xiashui_is_port():
    rows = web_ncexc.parse_ncexc(SAMPLE_ROWS)
    sx = next(r for r in rows if r["region"] == "陕西5500K")
    assert sx["region_type"] == "产地"      # 直达煤→产地
    assert sx["price"] == 564.0
    assert sx["trade_date"] == "2026-05-29"
    xs = next(r for r in rows if r["region"] == "5500K")
    assert xs["region_type"] == "港口"      # 下水煤→港口


def test_fetch_with_injected_rows_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_ncexc.NcexcSource(s).fetch(data_rows=SAMPLE_ROWS)
    assert n == 4
    assert len(s.query("SELECT * FROM spot_regional WHERE source='ncexc'")) == 4
