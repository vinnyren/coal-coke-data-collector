import re
import requests
from collectors.base import BaseCollector, with_retry

# 中国太原煤炭价格指数（中国煤炭交易中心 ctctc.cn）综合指数全量 JSON 接口。
# 一次返回全部历史期数；字段 INDEX_NAME/CURRENT_PRICE/STAGE_DATE/TYPE。
CTCTC_API = "https://cj.ctctc.cn/newjgzs/rest/jgzsfl/v3/zhIndexDataAll"
SOURCE = "ctctc"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://cj.ctctc.cn/"}
# 精煤类（气精煤/焦精煤/肥精煤/瘦精煤/贫瘦精煤/1/3焦精煤）均属炼焦煤=焦煤
_JIAOMEI_KW = ("精煤", "焦煤", "肥煤", "瘦煤", "气煤")
_CALORIFIC_RE = re.compile(r"(?:4500|5000|5500)")


def _ctctc_variety(name: str):
    """ctctc 指数名 → 品种。精煤类→焦煤；含动力煤或热值(4500/5000/5500)→动力煤；
    喷吹煤/无烟/块煤/烧结煤等非三品种→None(跳过)。"""
    if any(kw in name for kw in _JIAOMEI_KW):
        return "焦煤"
    if "动力煤" in name or _CALORIFIC_RE.search(name):
        return "动力煤"
    return None


def parse_ctctc(data_rows: list) -> list:
    """解析 zhIndexDataAll 的 data 为统一记录。

    region 用完整 INDEX_NAME（保留地区+品质+品种区分），region_type 固定产地，
    price=CURRENT_PRICE，trade_date=STAGE_DATE。无品种映射或价格缺失则跳过。
    """
    out = []
    for d in data_rows:
        name = (d.get("INDEX_NAME") or "").strip()
        price_raw = d.get("CURRENT_PRICE")
        trade_date = d.get("STAGE_DATE")
        if not name or price_raw is None or not trade_date:
            continue
        variety = _ctctc_variety(name)
        if variety is None:
            continue
        try:
            price = float(str(price_raw).replace(",", ""))
        except ValueError:
            continue
        out.append({
            "variety": variety,
            "region_type": "产地",
            "region": name,
            "trade_date": str(trade_date)[:10],
            "price": price,
            "unit": "元/吨",
            "source": SOURCE,
        })
    return out


class CtctcSource(BaseCollector):
    name = "web_ctctc"

    def fetch(self, data_rows=None):
        if data_rows is None:
            try:
                resp = with_retry(lambda: requests.get(
                    CTCTC_API, headers=_HEADERS, timeout=30))
                resp.raise_for_status()
                data_rows = resp.json().get("data", [])
            except Exception as e:  # noqa: BLE001
                self.log.warning("ctctc 接口抓取失败: %s", e)
                return 0
        rows = parse_ctctc(data_rows)
        if not rows:
            self.log.warning("ctctc 未解析到煤焦指数行（接口返回空或结构已变）")
            return 0
        return self.store.upsert(
            "spot_regional", rows,
            ["variety", "region_type", "region", "trade_date", "source"])
