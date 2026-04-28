# 港股短期交易指标压缩方案（10 日）

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

$$
MDD = \max_t\left(\frac{peak\_high_{\le t} - low_t}{peak\_high_{\le t}}\right)\times100\%
$$

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

建议输出两段：

1. 当日快照（用于“现在发生了什么”）
2. 10 日压缩画像（用于“最近怎么演化到这里”）

```json
{
  "today": {
    "date": "2026-04-21",
    "open": 12.30,
    "high": 12.88,
    "low": 12.05,
    "close": 12.76,
    "change_rate": 2.31,
    "bias20": 1.82,
    "volume_ratio": 0.18,
    "tag_today": "今日转多",
    "intraday_range_pct": 6.72
  },
  "summary_10d": {
    "max_cum_up_10d_pct": 7.32,
    "max_drawdown_10d_pct": 5.68,
    "shape_10d_tag": "窄幅压缩后上沿试探",
    "short_window_price_distribute": [
      {"bucket_range": "20.00-25.00", "volume_ratio_pct": 30.0},
      {"bucket_range": "25.00-30.00", "volume_ratio_pct": 25.0},
      {"bucket_range": "15.00-20.00", "volume_ratio_pct": 18.0}
    ],
    "poc_range_10d": "20.00-25.00",
    "poc_ratio_10d_pct": 30.0
  }
}
```

---

## 5. 给 LLM 的短期输入模板

```text
【微观10日画像】
- 当日信号：当日标签 {tag_today}
- 风险收益：10日累计最大上涨 {max_cum_up_10d_pct}% ，10日最大回撤 {max_drawdown_10d_pct}%
- 形态标签：{shape_10d_tag}
- 10日筹码分布：主峰区间 {poc_range_10d}（占比 {poc_ratio_10d_pct}%），其余集中区 {short_window_price_distribute}
```

---

## 6. 实施要点（开发侧）

1. 默认窗口 `N=min(10, available_days)`，不足 10 日时显式标记 `short_window_incomplete=true`。
2. 若缺失 `open/high/low`，先做字段映射修复；仍缺失则标记 `insufficient_ohlc=true` 并降级结论。
3. 指标先计算再喂模型，保持“先事实、后推理”。
4. 输出数字统一保留 `2-4` 位小数，避免模型误判尺度。

---

## 7. 总结

短期模块建议保持“当日快照 + 4个10日核心指标（含筹码分布）”。  
这样既保留核心风险/形态信息，也能让模型理解价格与成交量的结构分布。
