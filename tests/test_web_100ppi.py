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
        assert r["unit"] == "元/吨"


def test_parse_uses_current_price_column():
    rows = web_100ppi.parse_spot_table(SAMPLE, "2023-01-03")
    coke = next(r for r in rows if r["variety"] == "焦炭")
    assert coke["price"] == 1955.0          # 取"当日价"列（第4列）


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_100ppi.Ppi100Source(s).fetch(html=SAMPLE, trade_date="2023-01-03")
    assert n == 3
    assert len(s.query("SELECT * FROM spot_regional WHERE source='100ppi'")) == 3


# 真实页面 table[2] 的行结构：品名重复 + 图标列，共 7 个单元格，
# 当日价位于倒数第二列（昨日价/当日价/涨跌）。
SAMPLE_REAL = """
<table>
 <tr><td>商品</td><td>属性与规格</td><td>昨日价</td><td>当日价</td><td>涨跌</td></tr>
 <tr><td>焦炭</td><td></td><td>焦炭</td><td>等级:准一级冶金焦</td><td>1950.00</td><td>1955.00</td><td>0%</td></tr>
 <tr><td>动力煤</td><td></td><td>动力煤</td><td>发热量:5500Kcal/kg</td><td>860.00</td><td>865.00</td><td>0%</td></tr>
 <tr><td>炼焦煤</td><td></td><td>炼焦煤</td><td>类别:焦煤</td><td>1900.00</td><td>1911.25</td><td>0%</td></tr>
</table>
"""


def test_parse_handles_real_seven_column_rows():
    rows = web_100ppi.parse_spot_table(SAMPLE_REAL, "2026-06-29")
    assert {r["variety"] for r in rows} == {"焦炭", "动力煤", "焦煤"}
    coke = next(r for r in rows if r["variety"] == "焦炭")
    assert coke["price"] == 1955.0          # 倒数第二列=当日价，非"属性与规格"文本
    dl = next(r for r in rows if r["variety"] == "动力煤")
    assert dl["price"] == 865.0


CHALLENGE_HTML = (
    '<html><head></head><body><script>(function(_0x1){'
    'var _0x2 = "e68f926caa1be45e9329b8a891f07ecd";'
    '})("v_x");</script><p>正在进行安全检查，请稍候...</p></body></html>'
)


def test_extract_challenge_token():
    assert web_100ppi._extract_challenge_token(CHALLENGE_HTML) == \
        "e68f926caa1be45e9329b8a891f07ecd"
    assert web_100ppi._extract_challenge_token("<html>正常页面</html>") is None
