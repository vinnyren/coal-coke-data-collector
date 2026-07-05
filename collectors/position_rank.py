"""大商所持仓排名采集。

采集焦煤/焦炭（大商所 dce 品种）的会员多空持仓排名及增减，数据源为
AKShare 接口 futures_dce_position_rank，按多/空两侧幂等写入 position_rank 表。
"""
from datetime import date as _date
import akshare as ak
import config
from collectors.base import BaseCollector, with_retry

_DCE_VARIETIES = {v["dce_name"]: name
                  for name, v in config.VARIETIES.items()
                  if v["exchange"] == "dce" and v["dce_name"]}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class PositionRankCollector(BaseCollector):
    """采集大商所品种会员多空持仓排名并写入 position_rank 表。"""

    name = "position_rank"

    def fetch(self, date=None):
        """拉取指定日期（默认今日）各 dce 品种多空持仓排名，写入 position_rank，返回写入总行数。"""
        d = (date or _date.today().isoformat()).replace("-", "")
        data = with_retry(lambda: ak.futures_dce_position_rank(date=d))
        if not data:
            self.log.warning("%s 无持仓排名数据", d)
            return 0
        trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        total = 0
        for dce_name, vname in _DCE_VARIETIES.items():
            df = data.get(dce_name)
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.iterrows():
                row = r.to_dict()
                rank_no = int(_g(row, "rank") or 0)
                rows.append({
                    "variety": vname, "trade_date": trade_date, "side": "long",
                    "rank_no": rank_no, "member": _g(row, "long_party_name"),
                    "volume": _g(row, "long_open_interest"),
                    "change": _g(row, "long_open_interest_chg"),
                })
                rows.append({
                    "variety": vname, "trade_date": trade_date, "side": "short",
                    "rank_no": rank_no, "member": _g(row, "short_party_name"),
                    "volume": _g(row, "short_open_interest"),
                    "change": _g(row, "short_open_interest_chg"),
                })
            total += self.store.upsert(
                "position_rank", rows,
                ["variety", "trade_date", "side", "rank_no"])
        return total
