"""CCTD（中国煤炭市场网）公开指数页采集：解析指数名/日期/价格写入 index_price，
再经地区分类器 classify 结构化后写入 spot_regional 表。"""
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector, with_retry
from sources.region_classify import classify

CCTD_URL = "https://www.cctd.com.cn/index.php?m=content&c=index&a=lists&catid=520"
SOURCE = "cctd"


def parse_index(html):
    """解析 CCTD 指数页 <tr>，产出 {index_name, trade_date, price, source} 记录列表。"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        name, date_str, price_str = tds[0], tds[1], tds[2]
        try:
            price = float(price_str.replace(",", ""))
        except ValueError:
            continue
        out.append({"index_name": name, "trade_date": date_str,
                    "price": price, "source": SOURCE})
    return out


class CctdIndexSource(BaseCollector):
    """CCTD 公开指数页采集器，写入 index_price 并经 classify 写入 spot_regional。"""

    name = "web_cctd"

    def fetch(self, html=None):
        """抓取（或传入 html）解析指数写 index_price，再经地区分类器写 spot_regional，返回总行数。"""
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(CCTD_URL, timeout=15))
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                html = resp.text
            except Exception as e:  # noqa: BLE001
                self.log.warning("CCTD 页面抓取失败: %s", e)
                return 0
        rows = parse_index(html)
        if not rows:
            self.log.warning("CCTD 未解析到指数行（页面结构可能已变）")
            return 0
        n = self.store.upsert("index_price", rows, ["index_name", "trade_date"])
        regional = []
        for r in rows:
            hit = classify(r["index_name"])
            if hit is None:
                continue
            variety, region_type, region = hit
            regional.append({
                "variety": variety, "region_type": region_type,
                "region": region, "trade_date": r["trade_date"],
                "price": r["price"], "unit": None, "source": SOURCE,
            })
        n += self.store.upsert(
            "spot_regional", regional,
            ["variety", "region_type", "region", "trade_date", "source"])
        return n
