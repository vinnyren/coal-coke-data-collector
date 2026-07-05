"""运行报告构建与持久化：汇总采集结果、判定退出码、原子写归档。

build_report 把各采集器结果汇总成报告字典（含 totals 与 exit_code）；
compute_exit_code 依据结果实现 {0,2,3} 退出码契约（空结果→2、含 error→3、否则→0）；
write_report 以临时文件+os.replace 原子写出时间戳报告与 latest.json 指针；
format_text 渲染人类可读的文本摘要。
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import config

# 时间戳文件名格式：UTC、无冒号、文件名安全
_SLUG_FMT = "%Y%m%dT%H%M%SZ"


def compute_exit_code(results):
    """按结果判定进程退出码：空→EXIT_FATAL(2)、含 error→3、否则 EXIT_OK(0)。"""
    if not results:
        return config.EXIT_FATAL
    if any(r.get("status") == config.STATUS_ERROR for r in results):
        return config.EXIT_COLLECTOR_ERROR
    return config.EXIT_OK


def _iso_to_ms(start_iso, end_iso):
    a = datetime.fromisoformat(start_iso)
    b = datetime.fromisoformat(end_iso)
    # 顶层用墙钟时间，NTP 回拨可能使 finished < started —— 钳位为 0，不产生负值
    return max(0, int((b - a).total_seconds() * 1000))


def slug_from_iso(finished_iso):
    """由 finished_at 派生时间戳 slug（报告文件名单一来源）。"""
    return datetime.fromisoformat(finished_iso).strftime(_SLUG_FMT)


def build_report(results, mode, kind, started_at, finished_at):
    """汇总采集结果为报告字典：含 mode/kind、耗时、totals 统计与 exit_code。"""
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


def _atomic_write(path, payload):
    """原子写：临时文件 + os.replace，避免被 kill/并发时截断成半个文件。"""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-report-",
                               suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)  # 同盘 rename，原子替换
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _unique_ts_path(runs_dir, slug):
    """秒级 slug 同秒冲突时追加 -N，避免静默覆盖已归档报告。"""
    cand = runs_dir / f"run-{slug}.json"
    i = 1
    while cand.exists():
        cand = runs_dir / f"run-{slug}-{i}.json"
        i += 1
    return cand


def write_report(report_dict, runs_dir):
    """原子写出报告到 runs_dir：归档 run-<slug>.json 并刷新 latest.json，返回归档路径。"""
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    # slug 优先用调用方显式提供的，否则由 finished_at 派生（不再回退占位符）
    slug = report_dict.get("timestamp_slug") or slug_from_iso(report_dict["finished_at"])
    payload = json.dumps(report_dict, ensure_ascii=False, indent=2)
    ts_path = _unique_ts_path(runs_dir, slug)
    _atomic_write(ts_path, payload)
    _atomic_write(runs_dir / "latest.json", payload)  # 指针文件最后写，原子
    return ts_path


def format_text(report_dict):
    """将报告字典渲染为人类可读的多行文本摘要（表头、totals、逐采集器结果）。"""
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
