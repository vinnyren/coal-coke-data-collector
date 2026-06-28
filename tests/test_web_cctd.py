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
    assert n == 2
    rows = s.query("SELECT * FROM index_price")
    assert rows[0]["source"] == "cctd"
