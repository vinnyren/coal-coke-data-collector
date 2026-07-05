"""期货库存采集。

采集焦煤/焦炭/动力煤的期货库存及其增减，数据源为 AKShare 东财接口
futures_inventory_em，幂等写入 inventory 表。
"""
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class InventoryCollector(BaseCollector):
    """采集各品种期货库存并写入 inventory 表。"""

    name = "inventory"

    def fetch(self):
        """逐品种拉取库存历史，写入 inventory，返回写入总行数（单品种接口失败则跳过）。"""
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
