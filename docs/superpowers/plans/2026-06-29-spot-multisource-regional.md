# 现货多源 + 多地结构化 + 跨地区统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有煤焦采集技能上增加现货数据源（CCTD 结构化、全国煤炭交易中心、生意社全国价），把地区指数/参考价按"地区类型+地区名"结构化入库，并计算跨地区统计。

**Architecture:** 新增 `spot_regional` 与 `spot_regional_stats` 两表；纯函数地区分类器 `classify()` 把价格名称归类到 (品种, 地区类型, 地区)；三个可插拔 web 源写 `spot_regional`；`SpotStatsCollector` 读 `spot_regional` 算统计写 `spot_regional_stats`；run.py 新增有序 `regional` kind（三源→统计）。

**Tech Stack:** Python 3.9+，requests，beautifulsoup4，标准库 sqlite3，pytest。

## Global Constraints

- Python 版本下限：3.9；数据库仅用标准库 sqlite3，所有写库走 `SqliteStore.upsert` 且幂等。
- `region_type` 取值固定：`产地 | 港口 | 进口 | 消费地 | 全国`；统计表额外用 `ALL` 表示跨全部地区类型。
- 所有 web 源 best-effort：网络/解析失败仅记 WARN、返回 0，不抛出、不中断其它源。
- web 源解析器必须是纯函数（输入 HTML 字符串，输出记录列表），用 fixture 单测；真实页面选择器首次联网运行后核对。
- 统一记录结构：`{variety, region_type, region, trade_date, price, unit, source}`。
- 写 `spot_regional` 主键 `["variety","region_type","region","trade_date","source"]`；写 `spot_regional_stats` 主键 `["variety","region_type","trade_date"]`。
- 品种固定焦煤/焦炭/动力煤；炼焦煤归为焦煤。
- 现有 `index_price`、`spot_basis` 表与行为保留不变。

---

### Task 1: 配置关键词表 + 两张新表 + 白名单

**Files:**
- Modify: `config.py`
- Modify: `db/schema.sql`
- Modify: `storage/sqlite_store.py`
- Create: `tests/test_region_config.py`

**Interfaces:**
- Produces: `config.VARIETY_KEYWORDS`（dict 品种→关键词列表）、`config.PORT_NAMES`、`config.PRODUCTION_AREAS`、`config.IMPORT_KEYWORDS`、`config.CONSUMPTION_AREAS`（list[str]）；`spot_regional`、`spot_regional_stats` 表；`storage.sqlite_store.VALID_TABLES` 含两新表。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_region_config.py
import config
from storage.sqlite_store import SqliteStore, VALID_TABLES


def test_keyword_tables_present():
    assert set(config.VARIETY_KEYWORDS) == {"焦煤", "焦炭", "动力煤"}
    assert "炼焦煤" in config.VARIETY_KEYWORDS["焦煤"]
    assert "秦皇岛" in config.PORT_NAMES
    assert "山西" in config.PRODUCTION_AREAS
    assert any("蒙煤" == k or "蒙煤" in k for k in config.IMPORT_KEYWORDS)
    assert "唐山" in config.CONSUMPTION_AREAS


def test_valid_tables_include_regional():
    assert {"spot_regional", "spot_regional_stats"} <= VALID_TABLES


def test_schema_creates_regional_tables(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    names = {r["name"] for r in s.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "spot_regional" in names and "spot_regional_stats" in names
    s.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_region_config.py -v`
Expected: FAIL（`AttributeError: module 'config' has no attribute 'VARIETY_KEYWORDS'`）

- [ ] **Step 3: Write minimal implementation**

在 `config.py` 末尾追加：
```python
# 地区分类关键词表（用于把价格名称归类到 品种/地区类型/地区）
VARIETY_KEYWORDS = {
    "焦煤": ["焦煤", "炼焦煤", "主焦", "肥煤", "瘦煤"],
    "焦炭": ["焦炭", "冶金焦", "准一级", "一级焦", "二级焦"],
    "动力煤": ["动力煤", "电煤"],
}
PORT_NAMES = ["秦皇岛", "京唐", "曹妃甸", "日照", "天津", "连云港",
              "黄骅", "广州", "环渤海"]
PRODUCTION_AREAS = ["山西", "陕西", "内蒙古", "内蒙", "鄂尔多斯",
                    "新疆", "榆林", "大同", "吕梁"]
IMPORT_KEYWORDS = ["进口", "蒙煤", "澳煤", "俄煤", "甘其毛都", "满都拉"]
CONSUMPTION_AREAS = ["唐山", "华北", "华东", "华中", "华南", "西南",
                     "钢厂", "焦化厂"]
```

在 `db/schema.sql` 末尾追加：
```sql
CREATE TABLE IF NOT EXISTS spot_regional (
    variety TEXT NOT NULL,
    region_type TEXT NOT NULL,
    region TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL,
    unit TEXT,
    source TEXT NOT NULL,
    UNIQUE(variety, region_type, region, trade_date, source)
);

CREATE TABLE IF NOT EXISTS spot_regional_stats (
    variety TEXT NOT NULL,
    region_type TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    sample_count INTEGER,
    avg_price REAL, min_price REAL, max_price REAL, spread REAL,
    min_region TEXT, max_region TEXT,
    UNIQUE(variety, region_type, trade_date)
);
```

在 `storage/sqlite_store.py` 的 `VALID_TABLES` 集合中加入两表：
```python
VALID_TABLES = {"futures_daily", "futures_realtime", "spot_basis",
                "position_rank", "inventory", "index_price",
                "spot_regional", "spot_regional_stats"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_region_config.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add config.py db/schema.sql storage/sqlite_store.py tests/test_region_config.py
git commit -m "feat: 地区关键词表与 spot_regional/stats 建表"
```

---

### Task 2: 地区分类器 classify()

**Files:**
- Create: `sources/region_classify.py`
- Create: `tests/test_region_classify.py`

**Interfaces:**
- Consumes: `config.VARIETY_KEYWORDS/PORT_NAMES/PRODUCTION_AREAS/IMPORT_KEYWORDS/CONSUMPTION_AREAS`。
- Produces: `classify(name) -> (variety, region_type, region) | None`。判定顺序：进口→港口→产地→消费地→全国(兜底)；无品种命中返回 None。region 取命中的关键词原文。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_region_classify.py
from sources.region_classify import classify


def test_port_index():
    assert classify("CCTD秦皇岛动力煤(Q5500)") == ("动力煤", "港口", "秦皇岛")


def test_production_area():
    assert classify("新疆煤现货参考价") == ("动力煤", "产地", "新疆")


def test_import_keyword_takes_priority():
    # 含"进口"应判为进口，即使也含港口名
    assert classify("京唐港进口炼焦煤") == ("焦煤", "进口", "进口")


def test_lianjiao_maps_to_jiaomei():
    v, _, _ = classify("吕梁主焦煤车板价")
    assert v == "焦煤"


def test_consumption_area():
    assert classify("唐山二级冶金焦到厂价") == ("焦炭", "消费地", "唐山")


def test_national_fallback():
    assert classify("动力煤全国均价") == ("动力煤", "全国", "全国")


def test_no_variety_returns_none():
    assert classify("螺纹钢华东价格") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_region_classify.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'sources.region_classify'`）

- [ ] **Step 3: Write minimal implementation**

```python
# sources/region_classify.py
import config


def _match_variety(name):
    for variety, kws in config.VARIETY_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return variety
    return None


def _first_hit(name, names):
    for n in names:
        if n in name:
            return n
    return None


def classify(name):
    """把价格名称归类为 (品种, 地区类型, 地区)；无品种命中返回 None。

    判定顺序：进口 → 港口 → 产地 → 消费地 → 全国(兜底)。
    """
    if not name:
        return None
    variety = _match_variety(name)
    if variety is None:
        return None

    if any(kw in name for kw in config.IMPORT_KEYWORDS):
        hit = _first_hit(name, config.IMPORT_KEYWORDS)
        # 进口来源若是具体口岸/国别用原文，否则用"进口"
        region = hit if hit and hit != "进口" else "进口"
        return (variety, "进口", region)

    port = _first_hit(name, config.PORT_NAMES)
    if port:
        return (variety, "港口", port)

    area = _first_hit(name, config.PRODUCTION_AREAS)
    if area:
        return (variety, "产地", area)

    cons = _first_hit(name, config.CONSUMPTION_AREAS)
    if cons:
        return (variety, "消费地", cons)

    return (variety, "全国", "全国")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_region_classify.py -v`
Expected: PASS（7 passed）

> 注：`test_import_keyword_takes_priority` 期望 region="进口"（因名称含通用词"进口"，按规则口岸名未命中时用"进口"）。若实现取到具体口岸名则同样合规——但本测试用例不含具体口岸关键词，故应为"进口"。

- [ ] **Step 5: Commit**

```bash
git add sources/region_classify.py tests/test_region_classify.py
git commit -m "feat: 地区分类器 classify()"
```

---

### Task 3: 改造 CCTD 源，双写 index_price + spot_regional

**Files:**
- Modify: `sources/web_cctd.py`
- Modify: `tests/test_web_cctd.py`

**Interfaces:**
- Consumes: `classify`、`SqliteStore.upsert`、`config`。
- Produces: `CctdIndexSource.fetch(html=None)` 仍返回写入行数（index_price 行数 + spot_regional 行数之和）；新增内部把可分类行写 `spot_regional`（source="cctd"，region_type/region 来自 classify，price 取原值，unit=None）。`parse_index` 保持不变。

- [ ] **Step 1: Write the failing test**

在 `tests/test_web_cctd.py` 追加（保留原有两个测试）：
```python
def test_fetch_also_writes_spot_regional(tmp_path):
    s = make_store(tmp_path)
    html = """
    <table><tr><td>CCTD秦皇岛动力煤(Q5500)</td><td>2023-01-03</td><td>880</td></tr>
    <tr><td>螺纹钢华东</td><td>2023-01-03</td><td>4000</td></tr></table>
    """
    web_cctd.CctdIndexSource(s).fetch(html=html)
    # index_price 收两行（含不可分类的螺纹钢）
    assert len(s.query("SELECT * FROM index_price")) == 2
    # spot_regional 只收可分类的动力煤一行
    reg = s.query("SELECT * FROM spot_regional")
    assert len(reg) == 1
    assert reg[0]["variety"] == "动力煤"
    assert reg[0]["region_type"] == "港口"
    assert reg[0]["region"] == "秦皇岛"
    assert reg[0]["source"] == "cctd"
```

（`make_store` 已在该文件中存在，会 `init_schema`，新表自动建好。）

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_cctd.py::test_fetch_also_writes_spot_regional -v`
Expected: FAIL（spot_regional 行数为 0）

- [ ] **Step 3: Write minimal implementation**

修改 `sources/web_cctd.py`：顶部增加 `from sources.region_classify import classify`；把 `CctdIndexSource.fetch` 改为双写：
```python
    def fetch(self, html=None):
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(CCTD_URL, timeout=15))
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                html = resp.text
            except Exception as e:  # noqa: BLE001
                self.log.warning("CCTD 页面抓取失败: %s", e)
                return 0
        rows = parse_index(html)
        if not rows:
            self.log.warning("CCTD 未解析到指数行（页面结构可能已变）")
            return 0
        n = self.store.upsert("index_price", rows,
                              ["index_name", "trade_date"])
        regional = []
        for r in rows:
            hit = classify(r["index_name"])
            if hit is None:
                continue
            variety, region_type, region = hit
            regional.append({
                "variety": variety, "region_type": region_type,
                "region": region, "trade_date": r["trade_date"],
                "price": r["price"], "unit": None, "source": SOURCE,
            })
        n += self.store.upsert(
            "spot_regional", regional,
            ["variety", "region_type", "region", "trade_date", "source"])
        return n
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_cctd.py -v`
Expected: PASS（3 passed：原 2 + 新 1）

- [ ] **Step 5: Commit**

```bash
git add sources/web_cctd.py tests/test_web_cctd.py
git commit -m "feat: CCTD 源双写 index_price 与 spot_regional"
```

---

### Task 4: 生意社全国现货源 web_100ppi

**Files:**
- Create: `sources/web_100ppi.py`
- Create: `tests/test_web_100ppi.py`

**Interfaces:**
- Consumes: `BaseCollector`、`with_retry`、`config.VARIETY_KEYWORDS`。
- Produces: `parse_spot_table(html, trade_date) -> list[dict]`（纯函数，解析现货表中焦炭/动力煤/炼焦煤行，region_type/region 固定"全国"，source="100ppi"）；`Ppi100Source(store)`，`fetch(html=None, trade_date=None) -> int` 写 `spot_regional`，网络失败 WARN 返回 0。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_100ppi.py
from storage.sqlite_store import SqliteStore
import config
from sources import web_100ppi

SAMPLE = """
<table>
 <tr><td>焦炭</td><td>等级:准一级冶金焦</td><td>1950</td><td>1955</td><td>0%</td></tr>
 <tr><td>动力煤</td><td>发热量:5500</td><td>860</td><td>865</td><td>0%</td></tr>
 <tr><td>炼焦煤</td><td>类别:焦煤</td><td>1900</td><td>1911</td><td>0%</td></tr>
 <tr><td>螺纹钢</td><td>HRB400</td><td>4000</td><td>4010</td><td>0%</td></tr>
</table>
"""


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_keeps_only_coal_varieties():
    rows = web_100ppi.parse_spot_table(SAMPLE, "2023-01-03")
    varieties = {r["variety"] for r in rows}
    assert varieties == {"焦炭", "动力煤", "焦煤"}     # 炼焦煤→焦煤；排除螺纹钢
    for r in rows:
        assert r["region_type"] == "全国" and r["region"] == "全国"
        assert r["source"] == "100ppi"


def test_parse_uses_current_price_column():
    rows = web_100ppi.parse_spot_table(SAMPLE, "2023-01-03")
    coke = next(r for r in rows if r["variety"] == "焦炭")
    assert coke["price"] == 1955.0          # 取"当日价"列（第4列）


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_100ppi.Ppi100Source(s).fetch(html=SAMPLE, trade_date="2023-01-03")
    assert n == 3
    assert len(s.query("SELECT * FROM spot_regional WHERE source='100ppi'")) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_100ppi.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'sources.web_100ppi'`）

- [ ] **Step 3: Write minimal implementation**

```python
# sources/web_100ppi.py
from datetime import date as _date
import requests
from bs4 import BeautifulSoup
import config
from collectors.base import BaseCollector, with_retry

PPI_URL = "https://www.100ppi.com/xhb/"
SOURCE = "100ppi"


def _match_variety(name):
    for variety, kws in config.VARIETY_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return variety
    return None


def parse_spot_table(html, trade_date):
    """解析生意社现货表，保留煤焦三品种的当日价，全国维度。"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 4:
            continue
        variety = _match_variety(tds[0])
        if variety is None or variety in seen:
            continue
        try:
            price = float(tds[3].replace(",", ""))   # 当日价列
        except ValueError:
            continue
        seen.add(variety)
        out.append({
            "variety": variety, "region_type": "全国", "region": "全国",
            "trade_date": trade_date, "price": price, "unit": None,
            "source": SOURCE,
        })
    return out


class Ppi100Source(BaseCollector):
    name = "web_100ppi"

    def fetch(self, html=None, trade_date=None):
        trade_date = trade_date or _date.today().isoformat()
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(PPI_URL, timeout=15))
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                html = resp.text
            except Exception as e:  # noqa: BLE001
                self.log.warning("100ppi 页面抓取失败: %s", e)
                return 0
        rows = parse_spot_table(html, trade_date)
        if not rows:
            self.log.warning("100ppi 未解析到煤焦现货行（页面结构可能已变）")
            return 0
        return self.store.upsert(
            "spot_regional", rows,
            ["variety", "region_type", "region", "trade_date", "source"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_100ppi.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add sources/web_100ppi.py tests/test_web_100ppi.py
git commit -m "feat: 生意社全国现货源 web_100ppi"
```

---

### Task 5: 全国煤炭交易中心源 web_ncexc

**Files:**
- Create: `sources/web_ncexc.py`
- Create: `tests/test_web_ncexc.py`

**Interfaces:**
- Consumes: `BaseCollector`、`with_retry`、`classify`。
- Produces: `parse_ncexc(html, trade_date) -> list[dict]`（纯函数，解析指数表行 名称/价格，经 classify 归类，仅保留可分类行）；`NcexcSource(store)`，`fetch(html=None, trade_date=None) -> int` 写 `spot_regional`（source="ncexc"），网络失败 WARN 返回 0。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_ncexc.py
from storage.sqlite_store import SqliteStore
import config
from sources import web_ncexc

SAMPLE = """
<table>
 <tr><th>指数名称</th><th>数值</th></tr>
 <tr><td>陕西动力煤价格指数</td><td>720</td></tr>
 <tr><td>大同动力煤价格指数</td><td>700</td></tr>
 <tr><td>沪深300</td><td>3500</td></tr>
</table>
"""


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def test_parse_classifies_and_filters():
    rows = web_ncexc.parse_ncexc(SAMPLE, "2023-01-03")
    # 陕西→产地, 大同→产地；沪深300 无品种被过滤
    assert len(rows) == 2
    regions = {r["region"] for r in rows}
    assert regions == {"陕西", "大同"}
    for r in rows:
        assert r["variety"] == "动力煤"
        assert r["region_type"] == "产地"
        assert r["source"] == "ncexc"


def test_fetch_with_injected_html_writes(tmp_path):
    s = make_store(tmp_path)
    n = web_ncexc.NcexcSource(s).fetch(html=SAMPLE, trade_date="2023-01-03")
    assert n == 2
    assert len(s.query("SELECT * FROM spot_regional WHERE source='ncexc'")) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_ncexc.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'sources.web_ncexc'`）

- [ ] **Step 3: Write minimal implementation**

```python
# sources/web_ncexc.py
from datetime import date as _date
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector, with_retry
from sources.region_classify import classify

NCEXC_URL = "https://www.ncexc.cn/"
SOURCE = "ncexc"


def parse_ncexc(html, trade_date):
    """解析全国煤炭交易中心指数表：名称→classify 归类，价格 float 化。"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        name, price_str = tds[0], tds[1]
        hit = classify(name)
        if hit is None:
            continue
        try:
            price = float(price_str.replace(",", ""))
        except ValueError:
            continue
        variety, region_type, region = hit
        out.append({
            "variety": variety, "region_type": region_type, "region": region,
            "trade_date": trade_date, "price": price, "unit": None,
            "source": SOURCE,
        })
    return out


class NcexcSource(BaseCollector):
    name = "web_ncexc"

    def fetch(self, html=None, trade_date=None):
        trade_date = trade_date or _date.today().isoformat()
        if html is None:
            try:
                resp = with_retry(lambda: requests.get(NCEXC_URL, timeout=15))
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                html = resp.text
            except Exception as e:  # noqa: BLE001
                self.log.warning("ncexc 页面抓取失败: %s", e)
                return 0
        rows = parse_ncexc(html, trade_date)
        if not rows:
            self.log.warning("ncexc 未解析到可分类指数行（页面结构可能已变）")
            return 0
        return self.store.upsert(
            "spot_regional", rows,
            ["variety", "region_type", "region", "trade_date", "source"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_ncexc.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add sources/web_ncexc.py tests/test_web_ncexc.py
git commit -m "feat: 全国煤炭交易中心源 web_ncexc"
```

---

### Task 6: 跨地区统计 SpotStatsCollector

**Files:**
- Create: `collectors/spot_stats.py`
- Create: `tests/test_spot_stats.py`

**Interfaces:**
- Consumes: `BaseCollector`、`SqliteStore.query/upsert`。
- Produces: `SpotStatsCollector(store)`，`fetch(date=None) -> int`。读 `spot_regional`，按 `(variety, region_type, trade_date)` 与每个 `(variety, trade_date)` 的 `ALL` 汇总，计算 sample_count/avg/min/max/spread/min_region/max_region，幂等写 `spot_regional_stats`。仅统计 price 非空行；无样本组跳过。date 为 None 时统计库中所有 distinct trade_date。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spot_stats.py
from storage.sqlite_store import SqliteStore
import config
from collectors.spot_stats import SpotStatsCollector


def make_store(tmp_path):
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    return s


def seed(s, rows):
    s.upsert("spot_regional", rows,
             ["variety", "region_type", "region", "trade_date", "source"])


def test_stats_per_region_type(tmp_path):
    s = make_store(tmp_path)
    seed(s, [
        {"variety": "动力煤", "region_type": "港口", "region": "秦皇岛",
         "trade_date": "2023-01-03", "price": 900, "unit": None, "source": "cctd"},
        {"variety": "动力煤", "region_type": "港口", "region": "日照",
         "trade_date": "2023-01-03", "price": 800, "unit": None, "source": "cctd"},
    ])
    SpotStatsCollector(s).fetch(date="2023-01-03")
    row = s.query(
        "SELECT * FROM spot_regional_stats "
        "WHERE variety='动力煤' AND region_type='港口'")[0]
    assert row["sample_count"] == 2
    assert row["avg_price"] == 850.0
    assert row["min_price"] == 800.0 and row["max_price"] == 900.0
    assert row["spread"] == 100.0
    assert row["min_region"] == "日照" and row["max_region"] == "秦皇岛"


def test_all_rollup_across_region_types(tmp_path):
    s = make_store(tmp_path)
    seed(s, [
        {"variety": "动力煤", "region_type": "港口", "region": "秦皇岛",
         "trade_date": "2023-01-03", "price": 900, "unit": None, "source": "cctd"},
        {"variety": "动力煤", "region_type": "产地", "region": "山西",
         "trade_date": "2023-01-03", "price": 600, "unit": None, "source": "ncexc"},
    ])
    SpotStatsCollector(s).fetch(date="2023-01-03")
    allrow = s.query(
        "SELECT * FROM spot_regional_stats "
        "WHERE variety='动力煤' AND region_type='ALL'")[0]
    assert allrow["sample_count"] == 2
    assert allrow["min_region"] == "山西" and allrow["max_region"] == "秦皇岛"
    assert allrow["spread"] == 300.0


def test_idempotent_and_skips_null_price(tmp_path):
    s = make_store(tmp_path)
    seed(s, [
        {"variety": "焦炭", "region_type": "全国", "region": "全国",
         "trade_date": "2023-01-03", "price": None, "unit": None, "source": "100ppi"},
        {"variety": "焦炭", "region_type": "全国", "region": "全国",
         "trade_date": "2023-01-03", "price": 1955, "unit": None, "source": "cctd"},
    ])
    SpotStatsCollector(s).fetch(date="2023-01-03")
    SpotStatsCollector(s).fetch(date="2023-01-03")
    rows = s.query("SELECT * FROM spot_regional_stats WHERE variety='焦炭' AND region_type='全国'")
    assert len(rows) == 1                 # 幂等不翻倍
    assert rows[0]["sample_count"] == 1   # None 价被跳过
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_spot_stats.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'collectors.spot_stats'`）

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/spot_stats.py
from collectors.base import BaseCollector


def _stats_for(samples):
    """samples: list[(region, price)]，price 已非空。返回统计 dict 或 None。"""
    if not samples:
        return None
    prices = [p for _, p in samples]
    lo = min(samples, key=lambda x: x[1])
    hi = max(samples, key=lambda x: x[1])
    return {
        "sample_count": len(samples),
        "avg_price": round(sum(prices) / len(prices), 4),
        "min_price": float(lo[1]), "max_price": float(hi[1]),
        "spread": float(hi[1]) - float(lo[1]),
        "min_region": lo[0], "max_region": hi[0],
    }


class SpotStatsCollector(BaseCollector):
    name = "spot_stats"

    def fetch(self, date=None):
        if date is None:
            dates = [r["trade_date"] for r in self.store.query(
                "SELECT DISTINCT trade_date FROM spot_regional")]
        else:
            dates = [date]
        out = []
        for td in dates:
            rows = self.store.query(
                "SELECT variety, region_type, region, price FROM spot_regional "
                "WHERE trade_date=? AND price IS NOT NULL", (td,))
            by_type = {}      # (variety, region_type) -> [(region, price)]
            by_all = {}       # variety -> [(region, price)]
            for r in rows:
                key = (r["variety"], r["region_type"])
                by_type.setdefault(key, []).append((r["region"], r["price"]))
                by_all.setdefault(r["variety"], []).append((r["region"], r["price"]))
            for (variety, region_type), samples in by_type.items():
                st = _stats_for(samples)
                if st:
                    out.append({"variety": variety, "region_type": region_type,
                                "trade_date": td, **st})
            for variety, samples in by_all.items():
                st = _stats_for(samples)
                if st:
                    out.append({"variety": variety, "region_type": "ALL",
                                "trade_date": td, **st})
        return self.store.upsert(
            "spot_regional_stats", out,
            ["variety", "region_type", "trade_date"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_spot_stats.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add collectors/spot_stats.py tests/test_spot_stats.py
git commit -m "feat: 跨地区统计 SpotStatsCollector"
```

---

### Task 7: run.py 接线 regional kind + 文档

**Files:**
- Modify: `run.py`
- Modify: `tests/test_run.py`
- Modify: `SKILL.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Ppi100Source`、`CctdIndexSource`、`NcexcSource`、`SpotStatsCollector`。
- Produces: `_collectors_for_kind(store, "regional")` 返回有序列表 `[Ppi100Source, CctdIndexSource, NcexcSource, SpotStatsCollector]`；`all` 包含 regional；移除 `index` kind；argparse choices 更新。

- [ ] **Step 1: Write the failing test**

在 `tests/test_run.py` 追加：
```python
def test_regional_kind_order_and_membership(tmp_path):
    import config
    from storage.sqlite_store import SqliteStore
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    names = [c.name for c in run._collectors_for_kind(s, "regional")]
    assert names == ["web_100ppi", "web_cctd", "web_ncexc", "spot_stats"]


def test_all_includes_regional_not_index(tmp_path):
    import config
    from storage.sqlite_store import SqliteStore
    s = SqliteStore(str(tmp_path / "t.db"))
    s.init_schema(config.SCHEMA_PATH)
    names = [c.name for c in run._collectors_for_kind(s, "all")]
    assert "spot_stats" in names and "web_100ppi" in names
    # index kind 已移除
    assert run._collectors_for_kind(s, "index") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL（regional 分组不存在 / index 仍返回 CCTD）

- [ ] **Step 3: Write minimal implementation**

修改 `run.py`：
- 顶部 import 增加：
```python
from sources.web_100ppi import Ppi100Source
from sources.web_ncexc import NcexcSource
from collectors.spot_stats import SpotStatsCollector
```
- `_collectors_for_kind` 的 `groups` 改为（删除 `index`，新增有序 `regional`）：
```python
    groups = {
        "futures": [FuturesDailyCollector(store), FuturesRealtimeCollector(store)],
        "spot": [SpotBasisCollector(store)],
        "rank": [PositionRankCollector(store)],
        "inventory": [InventoryCollector(store)],
        "regional": [Ppi100Source(store), CctdIndexSource(store),
                     NcexcSource(store), SpotStatsCollector(store)],
    }
```
- `main()` 的 argparse `--kind` choices 改为：
```python
    p.add_argument("--kind",
                   choices=["all", "futures", "spot", "rank",
                            "inventory", "regional"],
                   default="all")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run.py -v`
Expected: PASS

- [ ] **Step 5: 更新文档**

在 `SKILL.md` 的用法段，把 `--kind` 说明中的 `index` 替换为 `regional`，并补一行：
```markdown
# 只更现货多地与统计（生意社/CCTD/全国煤炭交易中心 + 跨地区统计）
python run.py --mode daily --kind regional
```
数据表段补充：`spot_regional`（分地区现货/指数价）、`spot_regional_stats`（跨地区统计）。

在 `README.md` 数据类别处补充“分地区现货指数与跨地区统计”。

- [ ] **Step 6: 全量回归 + 烟测**

Run: `python -m pytest -v`
Expected: PASS（全部通过）

Run: `python run.py --mode daily --kind regional`
Expected: 正常退出，打印“采集完成: {...}”（含 web_100ppi/web_cctd/web_ncexc/spot_stats 计数；网络不可用时各为 0 但不报错）

- [ ] **Step 7: Commit**

```bash
git add run.py tests/test_run.py SKILL.md README.md
git commit -m "feat: run.py 接线 regional kind 并更新文档"
```

---

## Self-Review

- **Spec coverage:** 两新表+白名单→Task1；classify→Task2；CCTD 双写→Task3；100ppi→Task4；ncexc→Task5；跨地区统计(含 ALL)→Task6；regional kind 有序接线+移除 index+文档→Task7。spec 各节均覆盖。
- **Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码与可运行命令。
- **Type consistency:** 统一记录键 `variety/region_type/region/trade_date/price/unit/source` 在 Task3-5 一致；`spot_regional` 主键 `["variety","region_type","region","trade_date","source"]`、`spot_regional_stats` 主键 `["variety","region_type","trade_date"]` 在 Task1/3/4/5/6 一致；`classify` 返回三元组 (variety, region_type, region) 在 Task2/3/5 一致；source 标识 cctd/100ppi/ncexc 一致；采集器 `name` 属性（web_100ppi/web_cctd/web_ncexc/spot_stats）与 Task7 顺序断言一致。
- **风险提示:** 100ppi/ncexc 真实页面选择器以实测为准，已用纯函数 fixture 测 + best-effort 兜底；首次联网运行后按实测调整解析（与现有 CCTD 模式一致）。统计 avg 用 round(…,4) 避免浮点误差。
