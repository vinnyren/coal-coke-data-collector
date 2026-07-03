"""期货主力连续日线采集。

采集焦煤/焦炭/动力煤主力连续合约的日 K 线（开高低收/成交量/持仓量），
数据源为 AKShare 新浪接口 futures_main_sina，幂等写入 futures_daily 表。
"""
from datetime import date
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
    """采集各品种主力连续日线并写入 futures_daily 表。"""

    name = "futures_daily"

    def fetch(self, start="2015-01-01", end=None):
        """拉取 [start, end] 区间各品种日线，写入 futures_daily，返回写入总行数。"""
        end = end or date.today().isoformat()
        total = 0
        for vname, v in config.VARIETIES.items():
            symbol = v["main_symbol"]
            s_date = start.replace("-", "")
            e_date = end.replace("-", "")
            df = with_retry(lambda: ak.futures_main_sina(
                symbol=symbol, start_date=s_date, end_date=e_date))
            if df is None or df.empty:
                self.log.warning("%s 无日线数据", vname)
                continue
            rows = []
            for _, r in df.iterrows():
                d = r.to_dict()
                raw_date = _pick(d, _COL["date"])
                if raw_date is None:
                    self.log.warning("%s 某行缺少日期，跳过", vname)
                    continue
                trade_date = str(raw_date)[:10]
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
