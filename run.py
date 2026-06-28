# run.py
import argparse
import datetime
import config
from storage.sqlite_store import SqliteStore
from collectors.futures_daily import FuturesDailyCollector
from collectors.futures_realtime import FuturesRealtimeCollector
from collectors.spot_basis import SpotBasisCollector
from collectors.position_rank import PositionRankCollector
from collectors.inventory import InventoryCollector
from sources.web_cctd import CctdIndexSource


def build_store():
    store = SqliteStore(str(config.DB_PATH))
    store.init_schema(config.SCHEMA_PATH)
    return store


def _collectors_for_kind(store, kind):
    groups = {
        "futures": [FuturesDailyCollector(store), FuturesRealtimeCollector(store)],
        "spot": [SpotBasisCollector(store)],
        "rank": [PositionRankCollector(store)],
        "inventory": [InventoryCollector(store)],
        "index": [CctdIndexSource(store)],
    }
    if kind == "all":
        out = []
        for v in groups.values():
            out.extend(v)
        return out
    return groups.get(kind, [])


def run_pipeline(store, mode, kind="all", start="2015-01-01"):
    result = {}
    for i, c in enumerate(_collectors_for_kind(store, kind)):
        key = c.name if c.name not in result else f"{c.name}_{i}"
        if c.name == "futures_daily":
            result[key] = c.run(start=start)
        else:
            result[key] = c.run()
    return result


def main():
    p = argparse.ArgumentParser(description="煤焦交易数据采集")
    p.add_argument("--mode", choices=["backfill", "daily"], default="daily")
    p.add_argument("--kind",
                   choices=["all", "futures", "spot", "rank", "inventory", "index"],
                   default="all")
    p.add_argument("--start", default="2015-01-01")
    args = p.parse_args()
    store = build_store()
    start = args.start if args.mode == "backfill" else \
        datetime.date.today().isoformat()
    result = run_pipeline(store, args.mode, args.kind, start)
    store.close()
    print("采集完成:", result)


if __name__ == "__main__":
    main()
