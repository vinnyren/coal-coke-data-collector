# run.py
"""统一采集入口：装配采集器、跑管道、生成报告并按退出码退出。

run_pipeline 依 --kind 选择采集器组并逐个运行；run_once 完成建库、跑管道、
构建并持久化报告，且把致命失败（建库/写报告/逃逸异常）收敛为 exit 2；
main 解析 --mode/--kind/--start/--format 命令行参数，打印 JSON 或 text 报告，
并以 {0,2,3} 退出码结束，面向 cron/systemd 等无人值守调度。
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import config
import report
from storage.sqlite_store import SqliteStore
from collectors.futures_daily import FuturesDailyCollector
from collectors.futures_realtime import FuturesRealtimeCollector
from collectors.spot_basis import SpotBasisCollector
from collectors.position_rank import PositionRankCollector
from collectors.inventory import InventoryCollector
from sources.web_cctd import CctdIndexSource
from sources.web_100ppi import Ppi100Source
from sources.web_ncexc import NcexcSource
from sources.web_ctctc import CtctcSource
from collectors.spot_stats import SpotStatsCollector


def build_store():
    """按配置路径建立 SqliteStore 并初始化 schema，返回可用的存储实例。"""
    store = SqliteStore(str(config.resolve_db_path()))
    store.init_schema(config.SCHEMA_PATH)
    return store


def _utcnow():
    return datetime.now(timezone.utc)


def _configure_stdout():
    """确保中文/非 ASCII 报告可写到 stdout（cron/systemd 常无 UTF-8 locale，
    否则 print 抛 UnicodeEncodeError → 采集成功却以 exit 1 崩溃）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # 非 TextIOWrapper（如测试捕获流）：忽略
        pass


def _collectors_for_kind(store, kind):
    """按 kind 返回对应采集器列表；kind=all 返回所有组，未知 kind 返回空列表。"""
    groups = {
        "futures": [FuturesDailyCollector(store), FuturesRealtimeCollector(store)],
        "spot": [SpotBasisCollector(store)],
        "rank": [PositionRankCollector(store)],
        "inventory": [InventoryCollector(store)],
        "regional": [Ppi100Source(store), CctdIndexSource(store),
                     NcexcSource(store), CtctcSource(store),
                     SpotStatsCollector(store)],
    }
    if kind == "all":
        out = []
        for v in groups.values():
            out.extend(v)
        return out
    return groups.get(kind, [])


def run_pipeline(store, kind="all", start=config.BACKFILL_START):
    """依次运行选定采集器并收集其 RunResult；仅 futures_daily 接收 start 参数。"""
    results = []
    for c in _collectors_for_kind(store, kind):
        if c.name == "futures_daily":
            results.append(c.run(start=start))
        else:
            results.append(c.run())
    return results


def _fatal_report(mode, kind, started, finished, error):
    """致命失败（DB 初始化 / 兜底异常）时构造 exit_code=2 的报告。"""
    rep = report.build_report([], mode, kind,
                              started.isoformat(), finished.isoformat())
    return {**rep, "exit_code": config.EXIT_FATAL, "error": error}


def _close_quietly(store):
    """关闭 store；关闭异常不应掩盖已得的采集结果/退出码。"""
    try:
        store.close()
    except Exception:  # noqa: BLE001
        pass


def _finalize(rep):
    """尽力持久化报告（含致命报告，避免旧成功报告掩盖失败）；
    写出失败降级为 exit 2 但不再抛，并保留原有 error。"""
    try:
        report.write_report(rep, config.resolve_runs_dir())
    except Exception as e:  # noqa: BLE001 — 报告写出失败属致命，退出码 2
        note = f"write_report failed: {type(e).__name__}: {e}"
        prior = rep.get("error")
        return {**rep, "exit_code": config.EXIT_FATAL,
                "error": f"{prior} | {note}" if prior else note}
    return rep


def run_once(mode, kind="all", start=config.BACKFILL_START):
    """执行一轮采集：建库→跑管道→构建并持久化报告，返回最终报告字典。

    建库失败、写报告失败等致命情况均收敛为 exit_code=2 的报告，不向外抛异常。
    """
    started = _utcnow()
    try:
        store = build_store()
    except Exception as e:  # noqa: BLE001 — DB 初始化失败属致命，退出码 2
        return _finalize(_fatal_report(mode, kind, started, _utcnow(),
                                       f"build_store failed: {type(e).__name__}: {e}"))
    try:
        results = run_pipeline(store, kind, start)
    finally:
        _close_quietly(store)
    finished = _utcnow()
    rep = report.build_report(results, mode, kind,
                              started.isoformat(), finished.isoformat())
    return _finalize(rep)


def main():
    """CLI 入口：解析参数、运行 run_once、打印报告（json/text）并按退出码退出。"""
    _configure_stdout()
    p = argparse.ArgumentParser(description="煤焦交易数据采集")
    p.add_argument("--mode", choices=["backfill", "daily"], default="daily")
    p.add_argument("--kind",
                   choices=["all", "futures", "spot", "rank",
                            "inventory", "regional"],
                   default="all")
    p.add_argument("--start", default=config.BACKFILL_START)
    p.add_argument("--format", choices=["json", "text"], default="json")
    args = p.parse_args()
    start = args.start if args.mode == "backfill" else _utcnow().date().isoformat()
    try:
        rep = run_once(args.mode, args.kind, start)
    except Exception as e:  # noqa: BLE001 — 兜底任何逃逸异常，维持 {0,2,3} 退出码契约
        rep = _finalize(_fatal_report(args.mode, args.kind, _utcnow(), _utcnow(),
                                      f"fatal: {type(e).__name__}: {e}"))
    if args.format == "text":
        print(report.format_text(rep))
    else:
        print(json.dumps(rep, ensure_ascii=False))
    sys.exit(rep["exit_code"])


if __name__ == "__main__":
    main()
