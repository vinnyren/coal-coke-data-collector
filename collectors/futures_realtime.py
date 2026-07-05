"""期货实时行情采集。

采集焦煤/焦炭/动力煤主力合约的实时快照（最新价/买卖价/成交量/持仓量），
数据源为 AKShare 新浪接口 futures_zh_spot，按抓取时刻幂等写入 futures_realtime 表。
"""
from datetime import datetime
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
    """采集各品种实时行情快照并写入 futures_realtime 表。"""

    name = "futures_realtime"

    def fetch(self, now=None):
        """按 now（默认当前时刻）抓取一次实时快照，写入 futures_realtime，返回写入行数。"""
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
