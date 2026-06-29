import json
import report


def _rr(name, status, rows):
    return {"name": name, "status": status, "rows": rows,
            "error": None if status != "error" else "X: boom",
            "duration_ms": 1}


def test_exit_code_zero_when_no_error():
    rs = [_rr("a", "ok", 3), _rr("b", "empty", 0)]
    assert report.compute_exit_code(rs) == 0


def test_exit_code_three_when_any_error():
    rs = [_rr("a", "ok", 3), _rr("b", "error", 0)]
    assert report.compute_exit_code(rs) == 3


def test_exit_code_two_when_no_collectors():
    assert report.compute_exit_code([]) == 2


def test_build_report_totals_and_exit():
    rs = [_rr("a", "ok", 3), _rr("b", "empty", 0), _rr("c", "error", 0)]
    rep = report.build_report(rs, "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:05+00:00")
    assert rep["totals"] == {"rows": 3, "ok": 1, "empty": 1, "error": 1}
    assert rep["exit_code"] == 3
    assert rep["mode"] == "daily" and rep["kind"] == "all"
    assert rep["duration_ms"] == 5000


def test_write_report_creates_latest_and_timestamped(tmp_path):
    rs = [_rr("a", "ok", 3)]
    rep = report.build_report(rs, "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:01+00:00")
    rep["timestamp_slug"] = "20260629T000001Z"
    path = report.write_report(rep, tmp_path)
    assert (tmp_path / "latest.json").exists()
    assert path.exists() and path.name == "run-20260629T000001Z.json"
    loaded = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert loaded["totals"]["rows"] == 3


def test_format_text_has_summary():
    rs = [_rr("a", "ok", 3), _rr("b", "error", 0)]
    rep = report.build_report(rs, "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:01+00:00")
    txt = report.format_text(rep)
    assert "a" in txt and "error" in txt and "exit_code" in txt
