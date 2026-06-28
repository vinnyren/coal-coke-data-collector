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
    name = "spot_basis"

    def fetch(self, date=None):
        from datetime import date as _date
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
