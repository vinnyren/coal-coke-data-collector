# 第二阶段清理报告

- **状态**: 完成
- **提交哈希**: （见下方 git commit 后更新）
- **测试结果**: 46 passed in 0.35s（全绿）
- **烟测**: `python run.py --mode daily --kind regional` 正常退出；CCTD 46 行，spot_stats 26 行；100ppi/ncexc 按预期返回 0 行并 WARN
- **Concern**: 无

## 执行项

1. **选择器现状标注**: `parse_spot_table`（web_100ppi）、`parse_ncexc`（web_ncexc）顶部各加了选择器现状说明注释；设计文档第 4 节更新了状态。
2. **SKILL.md kind 顺序**: 注释改为 `all | futures | spot | rank | inventory | regional`，与 argparse choices 一致。
3. **100ppi 单位**: `unit` 由 `None` 改为 `"元/吨"`；`test_web_100ppi.py` 补充断言 `r["unit"] == "元/吨"`。
4. **DRY**: `web_100ppi` 删除本地 `_match_variety`，改为 `from sources.region_classify import _match_variety` 复用。签名一致（name -> variety|None）。
5. **spot_stats date=None 测试**: `test_spot_stats.py` 新增 `test_fetch_date_none_covers_all_dates`，种入两个不同日期行，验证两日期均有 stats 写出。
