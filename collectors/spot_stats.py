"""现货地区价格统计（本地聚合，无外部数据源）。

读取已入库的 spot_regional 表，按品种+地区类型（及全部 ALL）计算样本数、
均价、最高/最低价与价差等，幂等写入 spot_regional_stats 表。
"""
from collectors.base import BaseCollector


def _stats_for(samples):
    """samples: list[(region, price)]，price 已非空。返回统计 dict 或 None。"""
    if not samples:
        return None
    prices = [p for _, p in samples]
    lo = min(samples, key=lambda x: x[1])
    hi = max(samples, key=lambda x: x[1])
    return {
        "sample_count": len(samples),
        "avg_price": round(sum(prices) / len(prices), 4),
        "min_price": float(lo[1]), "max_price": float(hi[1]),
        "spread": float(hi[1]) - float(lo[1]),
        "min_region": lo[0], "max_region": hi[0],
    }


class SpotStatsCollector(BaseCollector):
    """基于 spot_regional 计算跨地区价格统计并写入 spot_regional_stats 表。"""

    name = "spot_stats"

    def fetch(self, date=None):
        """按交易日（默认全部已入库日期）聚合各品种地区价格统计，写入 spot_regional_stats，返回写入行数。"""
        if date is None:
            dates = [r["trade_date"] for r in self.store.query(
                "SELECT DISTINCT trade_date FROM spot_regional")]
        else:
            dates = [date]
        out = []
        for td in dates:
            rows = self.store.query(
                "SELECT variety, region_type, region, price FROM spot_regional "
                "WHERE trade_date=? AND price IS NOT NULL", (td,))
            by_type = {}      # (variety, region_type) -> [(region, price)]
            by_all = {}       # variety -> [(region, price)]
            for r in rows:
                key = (r["variety"], r["region_type"])
                by_type.setdefault(key, []).append((r["region"], r["price"]))
                by_all.setdefault(r["variety"], []).append((r["region"], r["price"]))
            for (variety, region_type), samples in by_type.items():
                st = _stats_for(samples)
                if st:
                    out.append({"variety": variety, "region_type": region_type,
                                "trade_date": td, **st})
            for variety, samples in by_all.items():
                st = _stats_for(samples)
                if st:
                    out.append({"variety": variety, "region_type": "ALL",
                                "trade_date": td, **st})
        return self.store.upsert(
            "spot_regional_stats", out,
            ["variety", "region_type", "trade_date"])
