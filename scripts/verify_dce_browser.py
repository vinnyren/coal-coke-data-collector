#!/usr/bin/env python3
"""本机实测：DCE 持仓排名浏览器通道能否过瑞数动态安全 WAF 并解析入库。

沙箱/CI 无法验证真实浏览器抓取（需联网 + Chromium），故用本脚本在装了 Playwright
的机器上端到端验证：抓 zip → 复用 akshare 解析 → 打印各品种行数。只读验证，不写主库。

用法：
    pip install playwright && playwright install chromium
    .venv/bin/python scripts/verify_dce_browser.py [YYYY-MM-DD]

退出码：0=拿到并解析出数据；1=被上游拦截/缺依赖（UpstreamBlocked）；2=其它异常。
"""
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.base import UpstreamBlocked          # noqa: E402
from collectors import position_rank                 # noqa: E402
from sources import dce_browser                       # noqa: E402


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else _date.today().isoformat()
    d = arg.replace("-", "")
    print(f"[验证] 交易日={d} 浏览器通道启用={dce_browser.browser_enabled()}")
    try:
        zip_bytes = dce_browser.fetch_zip(d)
    except UpstreamBlocked as e:
        print(f"[受限] {e}")
        print("       → 未拿到数据。请确认已 `playwright install chromium` 且本机可访问 dce.com.cn。")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[异常] {type(e).__name__}: {e}")
        return 2

    print(f"[成功] 过 WAF 拿到 zip {len(zip_bytes)} 字节，交给 akshare 解析…")
    data = position_rank._dce_zip_to_dict(zip_bytes, d)
    if not data:
        print("[空] 解析出 0 个品种（可能当日非交易日或无活跃合约）。")
        return 1
    for name, df in data.items():
        print(f"  - {name}: {len(df)} 行")
    print("[通过] 浏览器通道可用，可在无人值守中启用（COAL_POSITION_RANK_BROWSER=1，默认开）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
