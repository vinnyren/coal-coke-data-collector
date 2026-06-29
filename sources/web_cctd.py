import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector, with_retry
from sources.region_classify import classify

CCTD_URL = "https://www.cctd.com.cn/index.php?m=content&c=index&a=lists&catid=520"
SOURCE = "cctd"


def parse_index(html):
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
    name = "web_cctd"

    def fetch(self, html=None):
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
