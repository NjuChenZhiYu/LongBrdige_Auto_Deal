# 港股短期交易指标压缩方案（10 日）

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


$$
MDD = \max_t\left(\frac{peak\_high_{\le t} - low_t}{peak\_high_{\le t}}\right)\times100\%
$$

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
  }
}
```

说明：

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
```

---

## 6. 实施要点

1. 默认窗口 `N=min(10, available_days)`，不足 10 日必须标记 `short_window_incomplete=true`。
2. 风险收益统计必须保留“连续涨跌幅 + 最大回撤”双口径，不可互相替代。
3. 若后续 Prompt 新增短期字段，必须同步更新本文第 4/5 节。
