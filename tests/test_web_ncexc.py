from storage.sqlite_store import SqliteStore
import config
from sources import web_ncexc

SAMPLE = """
<table>
 <tr><th>指数名称</th><th>数值</th></tr>
 <tr><td>陕西动力煤价格指数</td><td>720</td></tr>
 <tr><td>大同动力煤价格指数</td><td>700</td></tr>
 <tr><td>沪深300</td><td>3500</td></tr>
</table>
"""


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_classifies_and_filters():
    rows = web_ncexc.parse_ncexc(SAMPLE, "2023-01-03")
    # 陕西→产地, 大同→产地；沪深300 无品种被过滤
    assert len(rows) == 2
    regions = {r["region"] for r in rows}
    assert regions == {"陕西", "大同"}
    for r in rows:
        assert r["variety"] == "动力煤"
        assert r["region_type"] == "产地"
        assert r["source"] == "ncexc"


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_ncexc.NcexcSource(s).fetch(html=SAMPLE, trade_date="2023-01-03")
    assert n == 2
    assert len(s.query("SELECT * FROM spot_regional WHERE source='ncexc'")) == 2
