import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

# 列名兼容映射：AKShare 不同版本列名可能不同
_COL = {
    "date": ["date", "日期"],
    "open": ["open", "开盘价"],
    "high": ["high", "最高价"],
    "low": ["low", "最低价"],
    "close": ["close", "收盘价"],
    "volume": ["volume", "成交量"],
    "hold": ["hold", "持仓量"],
}


def _pick(row, keys):
    for k in keys:
        if k in row and row[k] == row[k]:   # 非 NaN
            return row[k]
    return None


class FuturesDailyCollector(BaseCollector):
    name = "futures_daily"

    def fetch(self, start="2015-01-01", end=None):
        from datetime import date
        end = end or date.today().isoformat()
        total = 0
        for vname, v in config.VARIETIES.items():
            df = with_retry(lambda: ak.futures_main_sina(
                symbol=v["main_symbol"],
                start_date=start.replace("-", ""),
                end_date=end.replace("-", "")))
            if df is None or df.empty:
                self.log.warning("%s 无日线数据", vname)
                continue
            rows = []
            for _, r in df.iterrows():
                d = r.to_dict()
                trade_date = str(_pick(d, _COL["date"]))[:10]
                rows.append({
                    "variety": vname, "contract": v["main_symbol"],
                    "trade_date": trade_date,
                    "open": _pick(d, _COL["open"]), "high": _pick(d, _COL["high"]),
                    "low": _pick(d, _COL["low"]), "close": _pick(d, _COL["close"]),
                    "settle": None,
                    "volume": _pick(d, _COL["volume"]),
                    "open_interest": _pick(d, _COL["hold"]),
                })
            total += self.store.upsert(
                "futures_daily", rows, ["variety", "contract", "trade_date"])
        return total
