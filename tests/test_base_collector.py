import pytest
from collectors.base import BaseCollector, with_retry


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


def test_run_isolates_exception_and_returns_zero():
    class Boom(BaseCollector):
        name = "boom"
        def fetch(self, **kwargs):
            raise RuntimeError("explode")
    assert Boom(store=None).run() == 0


def test_run_returns_fetch_count():
    class Good(BaseCollector):
        name = "good"
        def fetch(self, **kwargs):
            return 7
    assert Good(store=None).run() == 7
