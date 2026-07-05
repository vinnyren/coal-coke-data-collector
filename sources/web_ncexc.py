"""全国煤炭交易中心（ncexc.com）动力煤指数 JSON 接口采集：抓取直达煤(产地)与
下水煤(港口)指数，写入 spot_regional 表。"""
import requests
from collectors.base import BaseCollector, with_retry

# 全国煤炭交易中心动力煤指数 JSON 接口（实测可用）。
# indexType: 101=下水煤指数(港口), 102=下水煤中长期, 103=直达煤指数(产地),
#            104=直达煤中长期, 105=中价指数。默认取 103(产地) + 101(港口/下水)。
NCEXC_API = "https://www.ncexc.com/DzjyServer/api/getQuotationIndexPrice.json"
INDEX_TYPES = ["103", "101"]
SOURCE = "ncexc"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.ncexc.com/MTServer/index/thermalCoal?skipType=1",
    "X-Requested-With": "XMLHttpRequest",
}


def _region_type_for(index_type_name: str) -> str:
    """由指数类型名判定地区类型：直达煤→产地，下水煤→港口，其它→全国。"""
    if "直达" in index_type_name:
        return "产地"
    if "下水" in index_type_name:
        return "港口"
    return "全国"


def parse_ncexc(data_rows: list) -> list:
    """解析 getQuotationIndexPrice.json 的 dataRows 为统一记录。

    全部为动力煤指数；region 用完整 ZSZLX（如"陕西5500K"，区分同省不同热值），
    region_type 由 INDEXTYPE 判定，price=ZS，trade_date=FBRQ。ZS/FBRQ 缺失则跳过。
    """
    out = []
    for d in data_rows:
        zs = d.get("ZS")
        zszlx = (d.get("ZSZLX") or "").strip()
        fbrq = d.get("FBRQ")
        if zs is None or not fbrq or not zszlx:
            continue
        try:
            price = float(str(zs).replace(",", ""))
        except ValueError:
            continue
        out.append({
            "variety": "动力煤",
            "region_type": _region_type_for(d.get("INDEXTYPE") or ""),
            "region": zszlx,
            "trade_date": str(fbrq)[:10],
            "price": price,
            "unit": "元/吨",
            "source": SOURCE,
        })
    return out


class NcexcSource(BaseCollector):
    """全国煤炭交易中心动力煤指数采集器，将各热值指数写入 spot_regional。"""

    name = "web_ncexc"

    def fetch(self, data_rows=None):
        """逐 indexType 抓取（或传入 data_rows）解析动力煤指数，upsert 到 spot_regional，返回行数。"""
        if data_rows is None:
            data_rows = []
            for it in INDEX_TYPES:
                index_type = it
                try:
                    resp = with_retry(lambda it=index_type: requests.get(
                        NCEXC_API, params={"indexType": it},
                        headers=_HEADERS, timeout=15))
                    resp.raise_for_status()
                    data_rows.extend(resp.json().get("dataRows", []))
                except Exception as e:  # noqa: BLE001
                    self.log.warning("ncexc 接口 indexType=%s 抓取失败: %s",
                                     index_type, e)
                    continue
        rows = parse_ncexc(data_rows)
        if not rows:
            self.log.warning("ncexc 未解析到指数行（接口返回空或结构已变）")
            return 0
        return self.store.upsert(
            "spot_regional", rows,
            ["variety", "region_type", "region", "trade_date", "source"])
