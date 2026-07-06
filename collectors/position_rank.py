"""大商所持仓排名采集。

采集焦煤/焦炭（大商所 dce 品种）的会员多空持仓排名及增减，按多/空两侧幂等写入
position_rank 表。

DCE 全站受瑞数动态安全 WAF 保护，akshare 的裸 requests 请求会被 412 拦截，
故本采集器改由浏览器通道（sources/dce_browser，可选 Playwright 插件）过挑战拿到
持仓排名 zip 字节，再复用 akshare 的成熟解析逻辑（_ReqProxy 仅替换其内部请求、
不改解析）。未装浏览器插件时抛 UpstreamBlocked，run() 降级为 status=skipped
（非代码错误，不触发 exit 3），不影响其它采集器。
"""
from datetime import date as _date
import akshare as ak
import config
from collectors.base import BaseCollector
from sources import dce_browser

_DCE_VARIETIES = {v["dce_name"]: name
                  for name, v in config.VARIETIES.items()
                  if v["exchange"] == "dce" and v["dce_name"]}


def _g(row, *keys):
    for k in keys:
        if k in row and row[k] == row[k]:
            return row[k]
    return None


class _ReqProxy:
    """代理 requests 模块：仅把 .post 固定为返回预置 zip 的假响应，其余属性回退真实 requests。

    用于把浏览器通道拿到的 zip 字节喂给 akshare 的 futures_dce_position_rank，
    从而复用其解析逻辑而不触发真实（会被 WAF 拦截的）网络请求。
    """

    class _Resp:
        def __init__(self, content):
            self.content = content

    def __init__(self, real, content):
        self._real = real
        self._content = content

    def __getattr__(self, name):
        return getattr(self._real, name)

    def post(self, *args, **kwargs):
        return _ReqProxy._Resp(self._content)


def _dce_zip_to_dict(zip_bytes, date_str):
    """把浏览器拿到的持仓排名 zip 字节交给 akshare 解析（仅替换其请求，不改解析逻辑）。"""
    import akshare.futures.cot as cot
    real = cot.requests
    cot.requests = _ReqProxy(real, zip_bytes)
    try:
        return ak.futures_dce_position_rank(date=date_str)
    finally:
        cot.requests = real


class PositionRankCollector(BaseCollector):
    """采集大商所品种会员多空持仓排名并写入 position_rank 表。"""

    name = "position_rank"

    def fetch(self, date=None, zip_fetcher=None):
        """拉取指定日期（默认今日）各 dce 品种多空持仓排名，写入 position_rank，返回写入总行数。

        zip_fetcher: 拿持仓排名 zip 字节的可调用（默认走浏览器通道 dce_browser.fetch_zip）；
        缺浏览器插件/被 WAF 拦截时抛 UpstreamBlocked，由 run() 降级为 status=skipped。
        参数化便于测试注入。
        """
        d = (date or _date.today().isoformat()).replace("-", "")
        fetch_zip = zip_fetcher or dce_browser.fetch_zip
        zip_bytes = fetch_zip(d)  # UpstreamBlocked 时向上传播 → run() 标 skipped
        data = _dce_zip_to_dict(zip_bytes, d)
        if not data:
            self.log.warning("%s 无持仓排名数据", d)
            return 0
        trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        total = 0
        for dce_name, vname in _DCE_VARIETIES.items():
            df = data.get(dce_name)
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.iterrows():
                row = r.to_dict()
                rank_no = int(_g(row, "rank") or 0)
                rows.append({
                    "variety": vname, "trade_date": trade_date, "side": "long",
                    "rank_no": rank_no, "member": _g(row, "long_party_name"),
                    "volume": _g(row, "long_open_interest"),
                    "change": _g(row, "long_open_interest_chg"),
                })
                rows.append({
                    "variety": vname, "trade_date": trade_date, "side": "short",
                    "rank_no": rank_no, "member": _g(row, "short_party_name"),
                    "volume": _g(row, "short_open_interest"),
                    "change": _g(row, "short_open_interest_chg"),
                })
            total += self.store.upsert(
                "position_rank", rows,
                ["variety", "trade_date", "side", "rank_no"])
        return total
