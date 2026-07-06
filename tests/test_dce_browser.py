"""DCE 浏览器抓取通道（可选插件）与降级语义测试。

DCE 全站受瑞数动态安全 WAF 保护，纯 requests 请求返回 412 JS 挑战页。
本模块用无头浏览器过挑战拿 zip，缺依赖/未启用/失败时抛 UpstreamBlocked。
浏览器真实抓取无法离线测试，这里覆盖：开关逻辑、缺依赖降级、proxy 注入机制。
"""
import sys
import pytest

from collectors.base import UpstreamBlocked
from sources import dce_browser


def test_browser_enabled_default_true(monkeypatch):
    monkeypatch.delenv("COAL_POSITION_RANK_BROWSER", raising=False)
    assert dce_browser.browser_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", ""])
def test_browser_disabled_by_env(monkeypatch, val):
    monkeypatch.setenv("COAL_POSITION_RANK_BROWSER", val)
    assert dce_browser.browser_enabled() is False


def test_fetch_zip_raises_when_disabled(monkeypatch):
    monkeypatch.setenv("COAL_POSITION_RANK_BROWSER", "0")
    with pytest.raises(UpstreamBlocked):
        dce_browser.fetch_zip("20260703")


def test_fetch_zip_raises_when_playwright_missing(monkeypatch):
    monkeypatch.setenv("COAL_POSITION_RANK_BROWSER", "1")
    # 模拟未安装 playwright：import playwright.sync_api 时抛 ImportError
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(UpstreamBlocked) as ei:
        dce_browser.fetch_zip("20260703")
    assert "playwright" in str(ei.value).lower()
