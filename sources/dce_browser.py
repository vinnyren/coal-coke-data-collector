"""大商所（DCE）持仓排名的浏览器抓取通道（可选插件）。

DCE 全站受瑞数动态安全 WAF 保护：纯 requests 请求返回 HTTP 412 + 一段动态混淆
JS 挑战页（特征 `$_ts` 全局对象、动态名 cookie、外链混淆 JS、结尾 `_$mp()`），
放行 token 由 JS 在真实浏览器 VM 里用指纹+时间动态生成，requests 补 headers/cookie
均无法绕过。本模块用无头浏览器（Playwright）加载页面让挑战执行、拿到放行 cookie，
再下载持仓排名 zip 字节，交回 akshare 的解析逻辑（见 collectors/position_rank）。

Playwright 是**可选依赖**：未安装 / 被开关关闭 / 抓取失败时抛 UpstreamBlocked，
由采集器降级为 status=skipped（非代码错误，不触发 exit 3）。核心行情不受影响。

启用需在装了 playwright 的环境执行一次：
    pip install playwright && playwright install chromium
关闭浏览器通道：设 COAL_POSITION_RANK_BROWSER=0。
"""
import json
import os

from collectors.base import UpstreamBlocked

# 与 akshare futures_dce_position_rank 内部一致的批量下载接口与页面 Referer
BATCH_URL = ("http://www.dce.com.cn/dcereport/publicweb/dailystat/"
             "memberDealPosi/batchDownload")
REFERER = ("http://www.dce.com.cn/dalianshangpin/xqsj/tjsj26/rtj/"
           "rcjccpm/index.html")
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_ZIP_MAGIC = b"PK\x03\x04"

_FALSEY = {"0", "false", "no", ""}


def browser_enabled():
    """浏览器通道开关：默认启用；COAL_POSITION_RANK_BROWSER 为 0/false/no/空 时关闭。"""
    return os.environ.get("COAL_POSITION_RANK_BROWSER", "1").strip().lower() \
        not in _FALSEY


def fetch_zip(date_str, timeout_ms=30000):
    """用无头浏览器过瑞数 WAF，下载指定交易日（YYYYMMDD）的持仓排名 zip 字节。

    返回 zip 二进制（bytes）。缺 Playwright / 通道被关闭 / 挑战未通过 / 当日无数据
    → 抛 UpstreamBlocked（采集器据此标 skipped）。
    """
    if not browser_enabled():
        raise UpstreamBlocked(
            "DCE 持仓排名浏览器通道被 COAL_POSITION_RANK_BROWSER=0 关闭")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise UpstreamBlocked(
            "DCE 持仓排名受瑞数动态安全 WAF 保护，需浏览器渲染；未安装 playwright "
            "（pip install playwright && playwright install chromium）") from e

    payload = {"tradeDate": date_str, "varietyId": "a",
               "contractId": "a2601", "tradeType": "1", "lang": "zh"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=_UA)
                page = ctx.new_page()
                # 先访问持仓排名页面，让瑞数 JS 挑战在真浏览器里执行并写入放行 cookie
                page.goto(REFERER, wait_until="networkidle", timeout=timeout_ms)
                # 复用已放行的浏览器上下文（含 cookie）发批量下载请求，拿 zip 二进制。
                # 显式发 JSON body 以匹配 akshare 的 requests.post(url, json=payload)，
                # 避免 Playwright 把 dict 当表单编码导致接口不识别。
                resp = ctx.request.post(
                    BATCH_URL, headers={"Referer": REFERER,
                                        "Content-Type": "application/json"},
                    data=json.dumps(payload), timeout=timeout_ms)
                body = resp.body()
            finally:
                browser.close()
    except UpstreamBlocked:
        raise
    except Exception as e:  # noqa: BLE001  # 浏览器/网络/超时等一律归为上游受限
        raise UpstreamBlocked(
            f"浏览器抓取 DCE 持仓排名失败: {type(e).__name__}: {e}") from e

    if not body or body[:4] != _ZIP_MAGIC:
        raise UpstreamBlocked(
            "浏览器请求 DCE 持仓排名未拿到 zip（瑞数挑战未通过或当日无数据）")
    return body
