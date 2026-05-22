结论：不建议长期保存完整 prompt 文本，也不建议重复保存富途可回放的原始 K 线。建议只持久化“当时计算出来、未来难以完全复原或需要对比演化”的轻量快照。

## 为什么完整 prompt 没必要长期存

`tmp/stock_promt_storage` 里的 prompt 更像一次性 LLM 输入物料，主要由以下几类数据拼出来：

- 富途可重新拉取的数据：K 线、快照、市值、资金流、成交量、涨跌幅等。
- 本地规则计算的数据：`tag_today`、`bias20`、10日风险收益、筹码分布、90日形态、POC、窗口完整度等。
- Prompt 模板文本：固定规则，应该由代码和版本控制管理，不应当每次重复存一份。

完整 prompt 的问题是冗余大、格式半结构化、后续分析困难，而且模板一改，历史 prompt 之间会混入“数据变化”和“提示词变化”两种差异，不利于做量化回测或复盘。

## 建议保存什么

建议保存“结构化特征快照”，而不是保存完整 prompt。每只股票每次生成研报时，保存一条 JSONL 或 SQLite 记录即可。

优先保存这些字段：

- 基础元数据：`symbol`、`name`、`report_time`、`market`、`source`、`prompt_template_version`。
- 当时实时快照：`rt_price`、`change_rate`、`volume`、`turnover`、`snapshot_time`。
- 资金流结果：当日、5日、10日、90日的主力净流和整体净流。
- 本地计算特征：`bias20`、`tag_today`、`window_used`、`short_window_incomplete`。
- 10日压缩画像：最大涨幅、最大跌幅、最大回撤、筹码主峰区间、主峰占比。
- 90日趋势画像：`mode`、`window_used`、`shape`、`position_pct`、`peaks`、`troughs`、`poc_range`、`poc_ratio_pct`。
- LLM 输出摘要：最终评分、评级、方向结论、是否建议买入、止损位、失效条件。

不建议保存这些内容：

- 完整 K 线明细，除非富途接口限流、断供或你要做离线回测。
- 完整 prompt 文本，除非用于调试 LLM 提示词效果。
- 大段研报正文，除非你要做历史观点检索。

## 推荐落地方式

你的弗吉尼亚 2核4GB 服务器足够做轻量持久化，不需要上复杂数据库。

第一阶段建议用 SQLite：

- 文件：`data/single_stock_snapshots.sqlite`
- 表：`hk_single_stock_feature_snapshots`
- 写入频率：每次生成单股 prompt/研报时写一条。
- 保留周期：原始特征长期保留；完整 prompt 最多保留 7-30 天用于排错。

如果想更简单，可以先用 JSONL：

- 文件：`data/hk_single_stock_feature_snapshots.jsonl`
- 优点：追加写最简单、方便排查。
- 缺点：后续筛选、统计、去重不如 SQLite。

JSONL 是保存在本地项目目录里的普通文本文件。它的特点是“一行就是一条完整 JSON 记录”，每次生成研报时向文件末尾追加一行即可。

示例路径：

```text
data/hk_single_stock_feature_snapshots.jsonl
```

示例单行记录：

```json
{"symbol":"HK.07666","name":"剂泰科技-P","market":"HK","report_time":"2026-05-21 10:03","prompt_template_version":"hk_single_stock_v1","snapshot":{"rt_price":18.02,"bias20_pct":-17.95,"tag_today":"数据不足","window_used":8,"short_window_incomplete":true},"capital_flow":{"today_main_net_wan":-170.53,"today_total_net_wan":-103.87,"main_net_5d_wan":-5844.95,"total_net_5d_wan":-14500.0,"main_net_10d_wan":-3036.86,"total_net_10d_wan":-37500.0},"short_window":{"max_cum_up_10d_pct":7.65,"max_cum_drop_10d_pct":-28.68,"max_drawdown_10d_pct":-42.63,"poc_range_10d":"24.87-27.42","poc_ratio_10d_pct":71.28},"mid_trend":{"mode":"INSUFFICIENT_LT30","window_used":7,"summary":"可用历史仅7日（已融合实时价格），中期趋势样本不足，谨慎解读。","peaks":[],"troughs":[18.0]},"llm_summary":{"score":null,"rating":null,"direction":null,"stop_loss":null,"invalid_condition":null}}
```

注意：上面虽然显示成多行代码块方便阅读，但真实 JSONL 文件里应该是一整行。下一次生成 `HK.03696` 时，再追加第二行；不会覆盖上一条。

我的建议是：本地开发阶段先 JSONL，稳定后迁移 SQLite。不要一开始就做 PostgreSQL、ClickHouse 或对象存储，当前数据量和机器配置都不需要。

## 最小保存策略

最终可以采用三层：

- `tmp/stock_promt_storage/`：完整 prompt 临时保存，7-30 天自动清理。
- `data/hk_single_stock_feature_snapshots.jsonl` 或 SQLite：长期保存结构化计算特征。
- `docs/Persistent/`：只保存设计说明、字段口径、决策规则，不保存运行数据。

一句话判断：富途能重拉的原始数据不存；代码能稳定重算的普通指标可以少存；带有“当时实时状态、当时代码版本、当时LLM结论”的结果值得存。
