from storage.sqlite_store import SqliteStore
import config
from sources import web_100ppi

SAMPLE = """
<table>
 <tr><td>焦炭</td><td>等级:准一级冶金焦</td><td>1950</td><td>1955</td><td>0%</td></tr>
 <tr><td>动力煤</td><td>发热量:5500</td><td>860</td><td>865</td><td>0%</td></tr>
 <tr><td>炼焦煤</td><td>类别:焦煤</td><td>1900</td><td>1911</td><td>0%</td></tr>
 <tr><td>螺纹钢</td><td>HRB400</td><td>4000</td><td>4010</td><td>0%</td></tr>
</table>
"""


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_keeps_only_coal_varieties():
    rows = web_100ppi.parse_spot_table(SAMPLE, "2023-01-03")
    varieties = {r["variety"] for r in rows}
    assert varieties == {"焦炭", "动力煤", "焦煤"}     # 炼焦煤→焦煤；排除螺纹钢
    for r in rows:
        assert r["region_type"] == "全国" and r["region"] == "全国"
        assert r["source"] == "100ppi"


def test_parse_uses_current_price_column():
    rows = web_100ppi.parse_spot_table(SAMPLE, "2023-01-03")
    coke = next(r for r in rows if r["variety"] == "焦炭")
    assert coke["price"] == 1955.0          # 取"当日价"列（第4列）


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_100ppi.Ppi100Source(s).fetch(html=SAMPLE, trade_date="2023-01-03")
    assert n == 3
    assert len(s.query("SELECT * FROM spot_regional WHERE source='100ppi'")) == 3
