# 煤焦交易数据采集技能

采集焦煤(jm)、焦炭(j)、动力煤(zc)的期货与现货数据，幂等写入本地 SQLite，支持历史回补与每日增量。

- 主通道：AKShare（期货行情/基差/持仓/库存）。
- 现货多源：CCTD、生意社(100ppi)、全国煤炭交易中心(ncexc)；地区分类器把指数/参考价结构化为 `spot_regional`，并做跨地区统计 `spot_regional_stats`。
- 入口：`python run.py --mode backfill|daily --kind all|futures|spot|rank|inventory|regional`。
- 测试：`python -m pytest`。

## 发布

发布/发版严格按 **`docs/发布流程.md`** 执行：测试全绿 → VERSION 判级（四段式）→ 写 CHANGELOG 条目 → 对齐指南头部版本 → 分块提交（VERSION+CHANGELOG 放最后一个提交）→ push（分叉则 rebase 保线性，禁止 force push）→ `bash scripts/release.sh` 打 tag + GitHub Release（幂等，发布说明取自 CHANGELOG）。本仓惯例为直接提交 `main`（无 feature 分支/PR），gstack `/ship` 的分支前置不适用。

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
