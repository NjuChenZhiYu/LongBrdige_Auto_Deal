# 港股短期交易指标压缩方案（10 日）

<<<<<<< HEAD
## 1. 当前实现原则（与代码一致）

短期模块当前遵循“少字段、高信息密度”的策略：

1. 服务端只输出 Prompt 实际消费字段，删除冗余中间量。
2. 指标计算优先可复现与稳定，避免“看起来复杂但没被消费”的字段漂移。
3. 10 日统计保留“风险收益 + 筹码分布”两大块，强调可交易解释。

---

## 2. 关键口径变更（本次更新）

### 2.1 连续涨跌幅口径修正

`max_cum_up_10d_pct` 与 `max_cum_drop_10d_pct` 不再用“简单收益率直接累加”，改为：

1. 先计算逐日简单收益率 `r_t`。
2. 转换为对数收益率 `log(1+r_t)`（可加和）。
3. 用区间搜索找到最大/最小连续区间和。
4. 再通过 `exp(sum)-1` 还原为复合收益率（%）。

这等价于“乘法复利口径”，避免简单收益率线性相加的偏差。

### 2.2 最大回撤展示口径

`max_drawdown_10d_pct` 计算仍是：
=======
## 1. 设计原则

短期模块建议与中期模块保持同一分工：

1. 代码负责计算“可复现的微观事实”（OHLC、成交量、资金与导数标签）。
2. 大模型负责“语义归纳与交易推理”（阶段命名、情景推演、策略表达）。

核心要求：

1. 不直灌 10 根 K 线明细，改为“当日快照 + 10日压缩画像”。
2. 所有区间类统计必须使用 `OHLC`，尤其 `high/low`，禁止仅用 `close` 代替。
3. 输出要高信息密度、低 token、可交易。

---

## 2. 为什么短期要“压缩优先”

1. 逐日明细容易让模型把注意力浪费在噪声波动上。
2. 短期交易决策依赖“关键结构信号”而非“逐行朗读”。
3. 10 日窗口完全可压缩为 5-8 个关键指标，信息损失很小。

---

## 3. 10 日核心指标（精简版）

保留 4 个核心指标，对外输出统一简化，避免 token 冗余。

## 3.1 10 日累计上涨最大值（`max_cum_up_10d_pct`）

从窗口起点 `open_1` 到后续任一交易日 `high_t` 的最大涨幅：

$$
max\_cum\_up = \max_t\left(\frac{high_t - open_1}{open_1}\right)\times100\%
$$

## 3.2 10 日最大回撤（`max_drawdown_10d_pct`）

滚动峰值使用 `high`，回撤谷值使用后续 `low`：
>>>>>>> origin/develop

$$
MDD = \max_t\left(\frac{peak\_high_{\le t} - low_t}{peak\_high_{\le t}}\right)\times100\%
$$

<<<<<<< HEAD
但对外展示统一用负号（如 `-9.05%`），和“风险项为负”的阅读习惯一致。

---

## 3. 10 日核心字段（当前对外）

### 3.1 连续最大上涨（`max_cum_up_10d_pct`）

- 含义：10 日窗口内，按连续区间计算得到的最大复合上涨幅度（正值）。
- 计算口径：log return 累加后复利还原。

### 3.2 连续最大下跌（`max_cum_drop_10d_pct`）

- 含义：10 日窗口内，按连续区间计算得到的最大复合下跌幅度（负值）。
- 计算口径：log return 累加后复利还原。

### 3.3 最大回撤（`max_drawdown_10d_pct`）

- 含义：从历史滚动峰值 `high.cummax()` 到后续 `low` 的最深跌幅。
- 计算口径：高低点路径，不是 close-only。
- 展示约定：对外统一负号。

### 3.4 短窗口筹码分布（`short_window_price_distribute`）

1. 价格代理优先级：`VWAP > HLC3 > OHLC4`。
2. 分桶：默认 `K=5`，价格轴 `[min(low), max(high)]`。
3. 输出：仅保留成交占比 Top3 桶，并返回 `poc_range_10d`、`poc_ratio_10d_pct`。

---

## 4. 输出结构（与当前代码一致）

当前 `build_short_term_memory` 对外结构如下：

```json
{
  "window_target": 10,
  "window_used": 10,
  "short_window_incomplete": false,
  "smart_net_wan": -72.28,
  "retail_net_wan": -70.92,
  "today": {
    "date": "2026-05-07 15:30:12(RT)",
    "rt_price": 5.76,
    "bias20": -2.89,
    "tag_today": "【跌势放缓：左侧建仓观察区】"
  },
  "summary_10d": {
    "max_cum_up_10d_pct": 2.61,
    "max_cum_drop_10d_pct": -5.39,
    "max_drawdown_10d_pct": -9.05,
    "short_window_price_distribute": [
      {"bucket_range": "5.86-5.98", "volume_ratio_pct": 33.2},
      {"bucket_range": "5.75-5.86", "volume_ratio_pct": 32.43},
      {"bucket_range": "5.98-6.09", "volume_ratio_pct": 23.25}
    ],
    "poc_range_10d": "5.86-5.98",
    "poc_ratio_10d_pct": 33.2
=======
说明：不得用 close-only 口径替代。

## 3.3 10 日形态特征（`shape_10d_tag`）

使用单一标签表达过去 10 日结构，不再输出一堆微观子指标。

建议规则（示例）：

1. 先算 `amp_10d_pct` 与 `close_percentile_10d`（内部计算，不对外单独返回）。
2. 再按区间映射形态标签：
   - `amp_10d_pct < 4` 且 `close_percentile_10d >= 0.7` -> `窄幅压缩后上沿试探`
   - `amp_10d_pct < 4` 且 `close_percentile_10d <= 0.3` -> `窄幅压缩后下沿承压`
   - `amp_10d_pct >= 10` 且 `close_percentile_10d >= 0.6` -> `高波动上行推进`
   - `amp_10d_pct >= 10` 且 `close_percentile_10d <= 0.4` -> `高波动下行探底`
   - 其他 -> `区间震荡`

说明：

1. `shape_10d_tag` 是唯一的“形态描述字段”。
2. 其余用于判断的子指标保留在内部，不直接暴露给 prompt。

## 3.4 短窗口筹码分布（`short_window_price_distribute`）

目标：输出过去 10 日“筹码（成交量）主要集中在哪些价格区间”。

关键约束：

1. **不能**使用 `close -> volume` 做单点映射。
2. 每日价格映射必须优先使用 `price_proxy`：
   - 优先 `VWAP`（若有）
   - 次选 `HLC3=(high+low+close)/3`
   - 兜底 `OHLC4=(open+high+low+close)/4`
3. 再把当日成交量映射到对应价格桶做聚合。

分桶方案（默认）：

1. 价格轴范围：`[min(low_10d), max(high_10d)]`
2. 桶数：`K=5`（10 日窗口下可解释性与稳定性较平衡）
3. 每桶统计：
   - `bucket_range`: 价格区间字符串，如 `"20.00-25.00"`
   - `volume_ratio_pct`: 该桶成交量占比（%）

输出建议：

1. 仅保留前 3 个占比最高桶（降 token）。
2. 返回时按占比从高到低排序。
3. 额外返回 `poc_range_10d`（主峰桶区间）与 `poc_ratio_10d_pct`（主峰占比）。

---

## 4. 输出结构（给服务层）

按当前 Prompt 实际展示口径（参考 `single_stock_prompt_0428_02590.txt`），短期结构应为：

```json
{
  "window_used": 10,
  "short_window_incomplete": false,
  "flow_label": "资金博弈不明",
  "smart_net_wan": -72.28,
  "retail_net_wan": -70.92,
  "today": {
    "date": "2026-04-27 18:16:47(RT)",
    "rt_price": 18.3,
    "open": 18.15,
    "high": 18.5,
    "low": 17.96,
    "close": 18.3,
    "change_rate": 0.0,
    "bias20": -1.35,
    "volume_ratio": 0.0,
    "tag_today": "【跌势放缓：左侧建仓观察区】",
    "intraday_range_pct": 2.95
  },
  "summary_10d": {
    "max_cum_up_10d_pct": 3.64,
    "max_cum_drop_10d_pct": -4.94,
    "max_drawdown_10d_pct": 10.3,
    "shape_10d_tag": "高波动下行探底",
    "short_window_price_distribute": [
      {"bucket_range": "18.72-19.12", "volume_ratio_pct": 46.83},
      {"bucket_range": "17.91-18.31", "volume_ratio_pct": 31.49},
      {"bucket_range": "18.31-18.72", "volume_ratio_pct": 21.68}
    ],
    "poc_range_10d": "18.72-19.12",
    "poc_ratio_10d_pct": 46.83
>>>>>>> origin/develop
  }
}
```

说明：
<<<<<<< HEAD

1. 已删除旧字段：`flow_label`、`shape_10d_tag`、`open/high/low/close`、`change_rate`、`volume_ratio`、`intraday_range_pct`、`recent_days` 等。
2. 文档仅维护当前 Prompt 实际消费字段，防止文档与实现再次漂移。

---

## 5. 给 LLM 的短期输入模板（当前）

```text
【短期记忆（近10日）】
- window_used: {window_used}
- short_window_incomplete: {short_window_incomplete}
- 主力净流(万): {smart_net_wan}
- 散户净流(万): {retail_net_wan}
- 当日快照: date={date}, rt_price={rt_price}, bias20={bias20}, tag_today={tag_today}
- 10日压缩画像:
  - max_cum_up_10d_pct={max_cum_up_10d_pct}%
  - max_cum_drop_10d_pct={max_cum_drop_10d_pct}%
  - max_drawdown_10d_pct={max_drawdown_10d_pct}
  - short_window_price_distribute={short_window_price_distribute}
  - poc_range_10d={poc_range_10d}
  - poc_ratio_10d_pct={poc_ratio_10d_pct}%
=======
1. 第 4 节以“服务层对 Prompt 的直接供给字段”为准，仅保留 Prompt 当前消费到的短期字段。
2. 若后续 Prompt 新增字段（如 `window_target/current_price/price_source`），再同步更新此结构。

---

## 5. 给 LLM 的短期输入模板

```text
【微观10日画像】
- 当日信号：当日标签 {tag_today}
- 风险收益：10日累计最大上涨 {max_cum_up_10d_pct}% ，10日最大回撤 {max_drawdown_10d_pct}%
- 形态标签：{shape_10d_tag}
- 10日筹码分布：主峰区间 {poc_range_10d}（占比 {poc_ratio_10d_pct}%），其余集中区 {short_window_price_distribute}
>>>>>>> origin/develop
```

---

<<<<<<< HEAD
## 6. 实施要点

1. 默认窗口 `N=min(10, available_days)`，不足 10 日必须标记 `short_window_incomplete=true`。
2. 风险收益统计必须保留“连续涨跌幅 + 最大回撤”双口径，不可互相替代。
3. 若后续 Prompt 新增短期字段，必须同步更新本文第 4/5 节。
=======
## 6. 实施要点（开发侧）

1. 默认窗口 `N=min(10, available_days)`，不足 10 日时显式标记 `short_window_incomplete=true`。
2. 若缺失 `open/high/low`，先做字段映射修复；仍缺失则标记 `insufficient_ohlc=true` 并降级结论。
3. 指标先计算再喂模型，保持“先事实、后推理”。
4. 输出数字统一保留 `2-4` 位小数，避免模型误判尺度。

---

## 7. 总结

短期模块建议保持“当日快照 + 4个10日核心指标（含筹码分布）”。  
这样既保留核心风险/形态信息，也能让模型理解价格与成交量的结构分布。
>>>>>>> origin/develop
