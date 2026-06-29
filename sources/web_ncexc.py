from datetime import date as _date
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector, with_retry
from sources.region_classify import classify

NCEXC_URL = "https://www.ncexc.cn/"
SOURCE = "ncexc"


def parse_ncexc(html, trade_date):
    """解析全国煤炭交易中心指数表：名称→classify 归类，价格 float 化。

    【选择器现状说明】
    以下解析逻辑基于"假设的页面表格结构"（<table><tr><td>名称/价格），实测对当前真实页面
    返回 0 行（页面结构与假设不同，实际页面可能为 JS 渲染或不同 HTML 结构）。
    属 best-effort；选择器待按真实页面结构调整。
    调整此 parse 函数即可，fetch 兜底已保证失败不影响其它源。
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        name, price_str = tds[0], tds[1]
        hit = classify(name)
        if hit is None:
            continue
        try:
            price = float(price_str.replace(",", ""))
        except ValueError:
            continue
        variety, region_type, region = hit
        out.append({
            "variety": variety, "region_type": region_type, "region": region,
            "trade_date": trade_date, "price": price, "unit": None,
            "source": SOURCE,
        })
    return out


class NcexcSource(BaseCollector):
    name = "web_ncexc"

    def fetch(self, html=None, trade_date=None):
        trade_date = trade_date or _date.today().isoformat()
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(NCEXC_URL, timeout=15))
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                html = resp.text
            except Exception as e:  # noqa: BLE001
                self.log.warning("ncexc 页面抓取失败: %s", e)
                return 0
        rows = parse_ncexc(html, trade_date)
        if not rows:
            self.log.warning("ncexc 未解析到可分类指数行（页面结构可能已变）")
            return 0
        return self.store.upsert(
            "spot_regional", rows,
            ["variety", "region_type", "region", "trade_date", "source"])
