import json
from pathlib import Path


def compute_exit_code(results):
    if not results:
        return 2
    if any(r.get("status") == "error" for r in results):
        return 3
    return 0


def _iso_to_ms(start_iso, end_iso):
    from datetime import datetime
    a = datetime.fromisoformat(start_iso)
    b = datetime.fromisoformat(end_iso)
    return int((b - a).total_seconds() * 1000)


def build_report(results, mode, kind, started_at, finished_at):
    totals = {
        "rows": sum(int(r.get("rows") or 0) for r in results),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "empty": sum(1 for r in results if r.get("status") == "empty"),
        "error": sum(1 for r in results if r.get("status") == "error"),
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
    slug = report_dict.get("timestamp_slug", "run")
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
    for r in report_dict["results"]:
        line = f"  {r['name']}: {r['status']} rows={r['rows']}"
        if r.get("error"):
            line += f" error={r['error']}"
        lines.append(line)
    return "\n".join(lines)
