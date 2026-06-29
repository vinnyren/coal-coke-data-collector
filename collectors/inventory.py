import akshare as ak
import config
from collectors.base import BaseCollector, with_retry


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class InventoryCollector(BaseCollector):
    name = "inventory"

    def fetch(self):
        total = 0
        for vname, v in config.VARIETIES.items():
            symbol = v["inventory_name"]
            try:
                df = with_retry(
                    lambda sym=symbol: ak.futures_inventory_em(symbol=sym))
            except Exception as e:  # noqa: BLE001
                self.log.warning("%s 库存接口失败: %s", vname, e)
                continue
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.iterrows():
                row = r.to_dict()
                td = str(_g(row, "日期", "date"))[:10]
                rows.append({
                    "variety": vname, "trade_date": td,
                    "inventory": _g(row, "库存", "inventory"),
                    "change": _g(row, "增减", "change"),
                })
            total += self.store.upsert("inventory", rows, ["variety", "trade_date"])
        return total
