# 现货多源 + 多地结构化 + 跨地区统计 — 设计文档

- 日期：2026-06-29
- 基线：在已有煤焦采集技能（PR #1，分支 feat/data-collector）之上扩展
- 状态：已确认，待实现

## 1. 背景与现实约束

现有现货数据仅 `spot_basis`（AKShare `futures_spot_price`，全国一价 + 基差）。需求：**增加现货数据源**并**统计多地数据**。

实测结论（已联网验证）：结构化、免费、分地区的现货**市场报价**基本被 Mysteel/SMM 付费墙锁住；生意社 100ppi 公开页只有全国价。免费免登录可得的"多地"数据主要是**已发布的地区价格指数**（港口价、产地参考价），而非逐矿/逐地市场报价。

采用**路线 A**：把可得的地区**指数/参考价**按"地区类型 + 地区名"结构化入库，并做跨地区统计；生意社作为额外的全国现货源。进口/消费地维度能拿到多少算多少。

## 2. 新增数据表（SQLite）

```sql
-- 分地区现货/指数价（结构化）
CREATE TABLE IF NOT EXISTS spot_regional (
    variety TEXT NOT NULL,
    region_type TEXT NOT NULL,   -- 产地 | 港口 | 进口 | 消费地 | 全国
    region TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL,
    unit TEXT,
    source TEXT NOT NULL,
    UNIQUE(variety, region_type, region, trade_date, source)
);

-- 跨地区统计（派生）
CREATE TABLE IF NOT EXISTS spot_regional_stats (
    variety TEXT NOT NULL,
    region_type TEXT NOT NULL,   -- 具体类型，或 'ALL' 表示跨全部地区类型
    trade_date TEXT NOT NULL,
    sample_count INTEGER,
    avg_price REAL, min_price REAL, max_price REAL, spread REAL,
    min_region TEXT, max_region TEXT,
    UNIQUE(variety, region_type, trade_date)
);
```

`index_price`（CCTD 原始指数行，审计用）与 `spot_basis`（AKShare 全国基差）保留不变。

## 3. 地区分类器（纯函数）

`sources/region_classify.py`：
```
classify(name: str) -> tuple[variety, region_type, region] | None
```
- 关键词表集中在 `config.py`：
  - `VARIETY_KEYWORDS`: {"焦煤": ["焦煤","炼焦煤","主焦"], "焦炭": ["焦炭","冶金焦","准一级","二级焦"], "动力煤": ["动力煤","电煤"]}
  - `PORT_NAMES`: ["秦皇岛","京唐","曹妃甸","日照","天津","连云港","黄骅","广州","环渤海"]
  - `PRODUCTION_AREAS`: ["山西","陕西","内蒙","内蒙古","鄂尔多斯","新疆","榆林","大同","吕梁"]
  - `IMPORT_KEYWORDS`: ["进口","蒙煤","澳煤","俄煤","甘其毛都","满都拉"]
  - `CONSUMPTION_AREAS`: ["唐山","华北","华东","华中","华南","西南","钢厂","焦化厂"]
- 判定顺序：进口 → 港口 → 产地 → 消费地 → 全国（兜底）。品种由 `VARIETY_KEYWORDS` 命中；无品种命中则返回 None。
- 例：`"CCTD秦皇岛动力煤(Q5500)"` → ("动力煤","港口","秦皇岛")；`"新疆煤现货参考价"` → ("动力煤","产地","新疆")；`"环渤海动力煤指数"` → ("动力煤","港口","环渤海")。无法归类（无品种）返回 None。

## 4. 数据源（可插拔，best-effort，失败仅 WARN 返回 0）

统一记录结构：`{variety, region_type, region, trade_date, price, unit, source}`。每个源解析器为纯函数（fixture 单测）。

**数据源状态（2026-06-29 实测可用）**：三源均已联网实测写入真实数据。
- `web_cctd`：解析公开指数页 → `index_price`（约 46 行原始）+ `spot_regional`（可分类约 13 行：产地/全国）。
- `web_100ppi`：页面有 `HW_CHECK` JS 反爬挑战，采集器先抓挑战页取校验值、带 cookie 重放后解析现货表；当日价取数据行倒数第二列。实测写入焦炭/动力煤/焦煤全国价 3 行。
- `web_ncexc`：改用真实 JSON 接口 `www.ncexc.com/DzjyServer/api/getQuotationIndexPrice.json?indexType=103|101`（直达煤=产地、下水煤=港口），`ZSZLX`=区域、`ZS`=指数值、`FBRQ`=日期；实测写入产地(陕西/山西/蒙西/蒙东)+港口约 17 行。
- 任一源失败仅 WARN、返回 0，不影响其它源与统计。

| 文件 | 来源 | 产出 |
|---|---|---|
| `sources/web_cctd.py`（改造） | CCTD（已接入） | 原始行→`index_price`（保留）；可分类行→`spot_regional`（source="cctd"） |
| `sources/web_ncexc.py`（新） | 全国煤炭交易中心 JSON 接口 `getQuotationIndexPrice.json` | `spot_regional`（source="ncexc"） |
| `sources/web_100ppi.py`（新） | 生意社现货表全国价（过 HW_CHECK 反爬） | `spot_regional`（region="全国", region_type="全国", source="100ppi"） |

- `web_cctd.fetch` 改造：解析得到原始行后，写 `index_price`（同今），再对每行调用 `classify`，命中者组装并 upsert `spot_regional`。两步互不影响，任一为空仅 WARN。
- `web_100ppi`：先过 `HW_CHECK` JS 反爬挑战（取校验值带 cookie 重放），解析现货表中焦炭/动力煤/炼焦煤的全国价（当日价取数据行倒数第二列），region_type/region 固定"全国"。
- `web_ncexc`：直接调用 JSON 接口（indexType 103 直达煤=产地、101 下水煤=港口），按 `ZSZLX/ZS/FBRQ` 组装；region 保留完整 `ZSZLX` 以区分同省不同热值。

## 5. 统计步骤

`collectors/spot_stats.py` → `SpotStatsCollector(store)`：
- `fetch(date=None) -> int`：date 为 None 时对 `spot_regional` 中所有 distinct `trade_date` 计算；否则只算该日。
- 对每个 `(variety, region_type, trade_date)` 计算：`sample_count`、`avg_price`、`min_price`、`max_price`、`spread=max-min`、`min_region`、`max_region`（取价格最低/最高的 region；并列取首个）。
- 额外对每个 `(variety, trade_date)` 跨全部地区类型计算一条 `region_type='ALL'`。
- 幂等 upsert `spot_regional_stats`，主键 `(variety, region_type, trade_date)`。
- 仅统计 price 非空的行；某组无有效样本则跳过。

## 6. run.py 接线

- 新增 `--kind regional`，**有序**执行：`web_100ppi → web_cctd → web_ncexc → spot_stats`（统计最后，确保读到本轮写入）。
- 取消独立 `--kind index`（CCTD 并入 regional，避免 `all` 重复运行 CCTD）。
- `all` = futures + spot + rank + inventory + regional。
- 这些 web 源只给"最新值"，regional 为每日快照（无历史回补）；`spot_stats` 按库中已有日期计算。
- `VALID_TABLES` 白名单新增 `spot_regional`、`spot_regional_stats`。

## 7. 目录结构变更

```
config.py                       # + 关键词表（VARIETY_KEYWORDS/PORT_NAMES/...）
db/schema.sql                   # + spot_regional, spot_regional_stats
sources/
  region_classify.py            # 新：classify() 纯函数
  web_cctd.py                   # 改：增 spot_regional 产出
  web_ncexc.py                  # 新
  web_100ppi.py                 # 新
collectors/
  spot_stats.py                 # 新：跨地区统计
run.py                          # 改：regional kind + 接线 + 白名单
storage/sqlite_store.py         # 改：VALID_TABLES 增两表
SKILL.md / README.md            # 改：用法补 regional、移除 index
tests/                          # + test_region_classify / test_web_ncexc /
                                #   test_web_100ppi / test_spot_stats；改 test_web_cctd / test_run
```

## 8. 测试

- `classify()`：各 region_type 命中、品种映射（炼焦煤→焦煤）、无品种返回 None。
- 三个 `parse_*()`：注入样例 HTML 断言提取行。
- `web_cctd` 改造：注入 HTML 后断言 index_price 与 spot_regional 双写、不可分类行不进 spot_regional。
- `SpotStatsCollector`：种入多地 spot_regional 行，断言 avg/min/max/spread/min_region/max_region 与 ALL 汇总；幂等。
- `run.py`：regional kind 组装顺序、白名单含新表、聚合计数。

## 9. 非目标（YAGNI）

- 不解析新闻标题文本里的逐地报价（路线 B，脆弱，后续可作可选插件）。
- 不爬付费/登录站点。
- 不为 regional 做历史回补（公开页只给最新值）。
- 不做地区价格的预测/可视化。
