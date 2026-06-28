import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

_VAR_BY_MAIN = {v["main_symbol"]: name for name, v in config.VARIETIES.items()}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class FuturesRealtimeCollector(BaseCollector):
    name = "futures_realtime"

    def fetch(self, now=None):
        from datetime import datetime
        captured = now or datetime.now().isoformat(timespec="seconds")
        symbols = ",".join(v["main_symbol"] for v in config.VARIETIES.values())
        df = with_retry(lambda: ak.futures_zh_spot(symbol=symbols, market="CF"))
        if df is None or df.empty:
            self.log.warning("无实时行情数据")
            return 0
        rows = []
        for _, r in df.iterrows():
            row = r.to_dict()
            sym = _g(row, "symbol")
            vname = _VAR_BY_MAIN.get(sym)
            if not vname:
                continue
            rows.append({
                "variety": vname, "contract": sym, "captured_at": captured,
                "last_price": _g(row, "current_price", "现价"),
                "bid": _g(row, "bid_price", "买价"),
                "ask": _g(row, "ask_price", "卖价"),
                "volume": _g(row, "volume", "成交量"),
                "open_interest": _g(row, "hold", "持仓量"),
            })
        return self.store.upsert(
            "futures_realtime", rows, ["variety", "contract", "captured_at"])
