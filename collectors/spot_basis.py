"""现货基差采集。

采集焦煤/焦炭/动力煤的现货价、主力/近月合约价及基差、基差率，数据源为
AKShare 接口 futures_spot_price，按品种与日期幂等写入 spot_basis 表。
"""
from datetime import date as _date
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

_VAR_BY_SPOT = {v["spot_var"]: name for name, v in config.VARIETIES.items()}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class SpotBasisCollector(BaseCollector):
    """采集各品种现货基差并写入 spot_basis 表。"""

    name = "spot_basis"

    def fetch(self, date=None):
        """拉取指定日期（默认今日）的现货/合约价与基差，写入 spot_basis，返回写入行数。"""
        d = (date or _date.today().isoformat()).replace("-", "")
        df = with_retry(lambda: ak.futures_spot_price(d))
        if df is None or df.empty:
            self.log.warning("%s 无现货基差数据", d)
            return 0
        trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        rows = []
        for _, r in df.iterrows():
            row = r.to_dict()
            sym = _g(row, "symbol", "var")
            if sym not in _VAR_BY_SPOT:
                continue
            rows.append({
                "variety": _VAR_BY_SPOT[sym],
                "trade_date": trade_date,
                "spot_price": _g(row, "spot_price"),
                "dominant_price": _g(row, "dominant_contract_price"),
                "near_price": _g(row, "near_contract_price"),
                "basis": _g(row, "dom_basis", "near_basis"),
                "basis_rate": _g(row, "dom_basis_rate", "near_basis_rate"),
            })
        return self.store.upsert("spot_basis", rows, ["variety", "trade_date"])
