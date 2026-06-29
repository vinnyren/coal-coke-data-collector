from storage.sqlite_store import SqliteStore
import config
from sources import web_cctd

SAMPLE_HTML = """
<table id="indexTable">
  <tr><td>CCTD秦皇岛动力煤(Q5500)</td><td>2023-01-03</td><td>880</td></tr>
  <tr><td>环渤海动力煤指数</td><td>2023-01-03</td><td>732</td></tr>
</table>
"""


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_index_extracts_rows():
    out = web_cctd.parse_index(SAMPLE_HTML)
    assert {"index_name", "trade_date", "price"} <= set(out[0])
    names = {r["index_name"] for r in out}
    assert "环渤海动力煤指数" in names


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_cctd.CctdIndexSource(s).fetch(html=SAMPLE_HTML)
    # 2 index_price + 2 classifiable spot_regional = 4
    assert n == 4
    rows = s.query("SELECT * FROM index_price")
    assert rows[0]["source"] == "cctd"


def test_fetch_also_writes_spot_regional(tmp_path):
    s = make_store(tmp_path)
    html = """
    <table><tr><td>CCTD秦皇岛动力煤(Q5500)</td><td>2023-01-03</td><td>880</td></tr>
    <tr><td>螺纹钢华东</td><td>2023-01-03</td><td>4000</td></tr></table>
    """
    web_cctd.CctdIndexSource(s).fetch(html=html)
    # index_price 收两行（含不可分类的螺纹钢）
    assert len(s.query("SELECT * FROM index_price")) == 2
    # spot_regional 只收可分类的动力煤一行
    reg = s.query("SELECT * FROM spot_regional")
    assert len(reg) == 1
    assert reg[0]["variety"] == "动力煤"
    assert reg[0]["region_type"] == "港口"
    assert reg[0]["region"] == "秦皇岛"
    assert reg[0]["source"] == "cctd"
