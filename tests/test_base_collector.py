import pytest
import config
from collectors.base import BaseCollector, with_retry, UpstreamBlocked


def test_with_retry_succeeds_after_failures(monkeypatch):
    import collectors.base as base
    monkeypatch.setattr(base.time, "sleep", lambda *_: None)
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"
    assert with_retry(flaky, retries=3, backoff=0) == "ok"
    assert calls["n"] == 3


def test_with_retry_raises_after_exhaustion(monkeypatch):
    import collectors.base as base
    monkeypatch.setattr(base.time, "sleep", lambda *_: None)
    def always_fail():
        raise ValueError("nope")
    with pytest.raises(ValueError):
        with_retry(always_fail, retries=2, backoff=0)


def test_run_ok_status_with_rows():
    class Good(BaseCollector):
        name = "good"
        def fetch(self, **kwargs):
            return 7
    r = Good(store=None).run()
    assert r["name"] == "good" and r["status"] == "ok" and r["rows"] == 7
    assert r["error"] is None and isinstance(r["duration_ms"], int)


def test_run_empty_status_when_zero_rows():
    class Empty(BaseCollector):
        name = "empty"
        def fetch(self, **kwargs):
            return 0
    r = Empty(store=None).run()
    assert r["status"] == "empty" and r["rows"] == 0 and r["error"] is None


def test_run_error_status_on_exception():
    class Boom(BaseCollector):
        name = "boom"
        def fetch(self, **kwargs):
            raise RuntimeError("explode")
    r = Boom(store=None).run()
    assert r["status"] == "error" and r["rows"] == 0
    assert "explode" in r["error"]


def test_run_skipped_status_on_upstream_blocked():
    # 已知外部限制（反爬 WAF 需浏览器）应标 skipped，而非 error（不触发 exit 3）
    class Blocked(BaseCollector):
        name = "blocked"
        def fetch(self, **kwargs):
            raise UpstreamBlocked("受瑞数 WAF 保护，需浏览器渲染")
    r = Blocked(store=None).run()
    assert r["status"] == config.STATUS_SKIPPED
    assert r["status"] != config.STATUS_ERROR
    assert r["rows"] == 0
    assert "浏览器" in r["error"]
