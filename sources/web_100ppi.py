import re
from datetime import date as _date
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector, with_retry
from sources.region_classify import _match_variety

PPI_URL = "https://www.100ppi.com/xhb/"
SOURCE = "100ppi"
_UA = "Mozilla/5.0"
# 反爬挑战页把校验值写在 var _0x2 = "..." 中，需带 HW_CHECK cookie 重放
_CHALLENGE_RE = re.compile(r'var\s+_0x2\s*=\s*"([0-9a-f]+)"')


def _extract_challenge_token(html: str):
    """从反爬挑战页提取 HW_CHECK 校验值；非挑战页返回 None。"""
    if "安全检查" not in html and "HW_CHECK" not in html:
        return None
    m = _CHALLENGE_RE.search(html)
    return m.group(1) if m else None


def parse_spot_table(html: str, trade_date: str) -> list:
    """解析生意社现货表，保留煤焦三品种的当日价，全国维度。

    真实页面数据行含品名重复/图标列（7 个单元格），列尾固定为
    [昨日价, 当日价, 涨跌]，故当日价取倒数第二列 tds[-2]；品名取 tds[0]。
    该取法对 5 列与 7 列两种结构均成立。
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        variety = _match_variety(tds[0])
        if variety is None or variety in seen:
            continue
        try:
            price = float(tds[-2].replace(",", ""))   # 倒数第二列=当日价
        except ValueError:
            continue
        seen.add(variety)
        out.append({
            "variety": variety, "region_type": "全国", "region": "全国",
            "trade_date": trade_date, "price": price, "unit": "元/吨",
            "source": SOURCE,
        })
    return out


def _fetch_html(session: requests.Session) -> str:
    """抓取现货表页，自动通过 HW_CHECK 反爬挑战（拿到校验值后重放）。"""
    resp = session.get(PPI_URL, timeout=15, headers={"User-Agent": _UA})
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    token = _extract_challenge_token(resp.text)
    if token:
        session.cookies.set("HW_CHECK", token, path="/")
        resp = session.get(PPI_URL, timeout=15, headers={"User-Agent": _UA})
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
    return resp.text


class Ppi100Source(BaseCollector):
    name = "web_100ppi"

    def fetch(self, html=None, trade_date=None):
        trade_date = trade_date or _date.today().isoformat()
        if html is None:
            try:
                session = requests.Session()
                html = with_retry(lambda: _fetch_html(session))
            except Exception as e:  # noqa: BLE001
                self.log.warning("100ppi 页面抓取失败: %s", e)
                return 0
        rows = parse_spot_table(html, trade_date)
        if not rows:
            self.log.warning("100ppi 未解析到煤焦现货行（页面结构可能已变）")
            return 0
        return self.store.upsert(
            "spot_regional", rows,
            ["variety", "region_type", "region", "trade_date", "source"])
