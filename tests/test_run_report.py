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


def test_duration_ms_clamped_to_zero_on_clock_regression():
    # NTP 回拨：finished 早于 started，顶层 duration_ms 钳位为 0 而非负值
    rep = report.build_report([_rr("a", "ok", 1)], "daily", "all",
                              "2026-06-29T00:00:05+00:00",
                              "2026-06-29T00:00:00+00:00")
    assert rep["duration_ms"] == 0


def test_write_report_no_overwrite_on_slug_collision(tmp_path):
    # 同一 finished_at（同秒 slug）连写两次：第二次不得覆盖第一次的归档
    rep = report.build_report([_rr("a", "ok", 1)], "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:01+00:00")
    p1 = report.write_report(rep, tmp_path)
    p2 = report.write_report(rep, tmp_path)
    assert p1 != p2
    assert p1.exists() and p2.exists()
    assert p1.name == "run-20260629T000001Z.json"
    assert p2.name == "run-20260629T000001Z-1.json"


def test_write_report_is_atomic_valid_json(tmp_path):
    # latest.json 始终是完整可解析 JSON（原子替换，无半截文件）
    rep = report.build_report([_rr("a", "ok", 3)], "daily", "all",
                              "2026-06-29T00:00:00+00:00",
                              "2026-06-29T00:00:01+00:00")
    report.write_report(rep, tmp_path)
    loaded = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert loaded["totals"]["rows"] == 3
    # 无遗留临时文件
    assert not list(tmp_path.glob(".tmp-report-*"))
