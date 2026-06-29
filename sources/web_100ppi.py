from datetime import date as _date
import requests
from bs4 import BeautifulSoup
import config
from collectors.base import BaseCollector, with_retry
from sources.region_classify import _match_variety

PPI_URL = "https://www.100ppi.com/xhb/"
SOURCE = "100ppi"


def parse_spot_table(html, trade_date):
    """解析生意社现货表，保留煤焦三品种的当日价，全国维度。

    【选择器现状说明】
    以下解析逻辑基于"假设的页面表格结构"（<table><tr><td>），实测对当前真实页面
    返回 0 行（页面结构与假设不同，实际页面可能为 JS 渲染或不同 HTML 结构）。
    属 best-effort；选择器待按真实页面结构调整。
    调整此 parse 函数即可，fetch 兜底已保证失败不影响其它源。
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 4:
            continue
        variety = _match_variety(tds[0])
        if variety is None or variety in seen:
            continue
        try:
            price = float(tds[3].replace(",", ""))   # 当日价列
        except ValueError:
            continue
        seen.add(variety)
        out.append({
            "variety": variety, "region_type": "全国", "region": "全国",
            "trade_date": trade_date, "price": price, "unit": "元/吨",
            "source": SOURCE,
        })
    return out


class Ppi100Source(BaseCollector):
    name = "web_100ppi"

    def fetch(self, html=None, trade_date=None):
        trade_date = trade_date or _date.today().isoformat()
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(PPI_URL, timeout=15))
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                html = resp.text
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
