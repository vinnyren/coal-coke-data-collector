import pandas as pd
import pytest
from storage.sqlite_store import SqliteStore
import config
from collectors import position_rank
from collectors.base import UpstreamBlocked


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


_JM = pd.DataFrame({
    "long_party_name": ["永安", "中信"],
    "long_open_interest": [1200, 1100],
    "long_open_interest_chg": [10, -5],
    "short_party_name": ["国泰", "海通"],
    "short_open_interest": [1300, 1000],
    "short_open_interest_chg": [20, -8],
    "rank": [1, 2],
})


def test_fetch_writes_long_and_short(tmp_path, monkeypatch):
    # 浏览器通道拿到 zip 字节，解析复用 akshare（此处 mock 解析，专注编排+入库）
    monkeypatch.setattr(position_rank, "_dce_zip_to_dict",
                        lambda zip_bytes, date_str: {"焦煤": _JM})
    s = make_store(tmp_path)
    n = position_rank.PositionRankCollector(s).fetch(
        date="2023-01-03", zip_fetcher=lambda d: b"PK\x03\x04fake-zip")
    assert n == 4                       # 2 long + 2 short
    longs = s.query("SELECT * FROM position_rank WHERE side='long'")
    assert len(longs) == 2
    assert longs[0]["member"] in ("永安", "中信")


def test_fetch_propagates_upstream_blocked(tmp_path):
    # 无浏览器/被 WAF 拦：zip_fetcher 抛 UpstreamBlocked，fetch 原样传播（run 会标 skipped）
    def blocked(_d):
        raise UpstreamBlocked("需浏览器渲染")
    s = make_store(tmp_path)
    with pytest.raises(UpstreamBlocked):
        position_rank.PositionRankCollector(s).fetch(
            date="2023-01-03", zip_fetcher=blocked)


def test_run_marks_skipped_when_blocked(tmp_path, monkeypatch):
    # 端到端：默认 zip_fetcher（浏览器）不可用时，run() 应返回 status=skipped 而非 error
    def blocked(_d):
        raise UpstreamBlocked("DCE 受瑞数 WAF 保护，需浏览器渲染；未安装 playwright")
    monkeypatch.setattr(position_rank.dce_browser, "fetch_zip", blocked)
    s = make_store(tmp_path)
    r = position_rank.PositionRankCollector(s).run(date="2023-01-03")
    assert r["status"] == config.STATUS_SKIPPED
    assert r["rows"] == 0
    assert "playwright" in r["error"].lower()


def test_fetch_zero_rows_when_parse_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(position_rank, "_dce_zip_to_dict",
                        lambda zip_bytes, date_str: {})
    s = make_store(tmp_path)
    n = position_rank.PositionRankCollector(s).fetch(
        date="2023-01-03", zip_fetcher=lambda d: b"PK\x03\x04")
    assert n == 0


def test_req_proxy_post_returns_zip_others_fallthrough():
    # proxy 机制：仅 .post 固定返回预置 zip 的假响应，其它属性回退真实 requests
    import requests
    proxy = position_rank._ReqProxy(requests, b"PK\x03\x04payload")
    resp = proxy.post("http://x", json={"a": 1})
    assert resp.content == b"PK\x03\x04payload"
    # 回退：get 仍是真实 requests.get（同一函数对象）
    assert proxy.get is requests.get
