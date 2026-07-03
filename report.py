import json
from datetime import datetime
from pathlib import Path

import config

# 时间戳文件名格式：UTC、无冒号、文件名安全
_SLUG_FMT = "%Y%m%dT%H%M%SZ"


def compute_exit_code(results):
    if not results:
        return config.EXIT_FATAL
    if any(r.get("status") == config.STATUS_ERROR for r in results):
        return config.EXIT_COLLECTOR_ERROR
    return config.EXIT_OK


def _iso_to_ms(start_iso, end_iso):
    a = datetime.fromisoformat(start_iso)
    b = datetime.fromisoformat(end_iso)
    return int((b - a).total_seconds() * 1000)


def slug_from_iso(finished_iso):
    """由 finished_at 派生时间戳 slug（报告文件名单一来源）。"""
    return datetime.fromisoformat(finished_iso).strftime(_SLUG_FMT)


def build_report(results, mode, kind, started_at, finished_at):
    totals = {
        "rows": sum(int(r.get("rows") or 0) for r in results),
        "ok": sum(1 for r in results if r.get("status") == config.STATUS_OK),
        "empty": sum(1 for r in results if r.get("status") == config.STATUS_EMPTY),
        "error": sum(1 for r in results if r.get("status") == config.STATUS_ERROR),
    }
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": _iso_to_ms(started_at, finished_at),
        "mode": mode,
        "kind": kind,
        "results": results,
        "totals": totals,
        "exit_code": compute_exit_code(results),
    }


def write_report(report_dict, runs_dir):
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    # slug 优先用调用方显式提供的，否则由 finished_at 派生（不再回退占位符）
    slug = report_dict.get("timestamp_slug") or slug_from_iso(report_dict["finished_at"])
    payload = json.dumps(report_dict, ensure_ascii=False, indent=2)
    (runs_dir / "latest.json").write_text(payload, encoding="utf-8")
    ts_path = runs_dir / f"run-{slug}.json"
    ts_path.write_text(payload, encoding="utf-8")
    return ts_path


def format_text(report_dict):
    lines = [
        f"采集完成 mode={report_dict['mode']} kind={report_dict['kind']} "
        f"exit_code={report_dict['exit_code']}",
        f"totals: {report_dict['totals']}",
    ]
    if report_dict.get("error"):
        lines.append(f"fatal: {report_dict['error']}")
    for r in report_dict["results"]:
        line = f"  {r['name']}: {r['status']} rows={r['rows']}"
        if r.get("error"):
            line += f" error={r['error']}"
        lines.append(line)
    return "\n".join(lines)
