# 港股中期交易形态分析策略（60-90 日）

## 1. 设计原则

最优雅的分工是：

1. 代码负责提取“形态骨架”（可量化、可复现）。
2. 大模型负责“图形命名与推理”（语义理解、交易叙事）。

核心理念：中期分析必须重视交易形态本身。平滑均值（如 EMA/SMA）只能做辅助，不可替代形态结构，因为过度平滑会抹除关键拐点与压缩特征。

---

## 2. 为什么中期要“形态优先”

1. 中期交易的胜率来自结构，而不仅是方向。
2. 峰谷序列、区间位置、筹码密度比均线更早反映“弹簧压缩/释放”。
3. 均线在拐点附近天然滞后，容易错过“反脆弱”启动段。

因此，中期模块应采用“形态骨架主导 + 均值指标确认”的双层架构。

---

## 3. 60-90 日宏观形态压缩方案

## 3.1 形态骨架：关键极值点（Pivot / ZigZag）

目标：从 90 根 K 线压缩出最关键的峰谷转折点序列。

实现建议：

1. 使用局部极值检测（`scipy.signal.find_peaks`）或 `5%` ZigZag 阈值。
2. 提取最近有效的 `3-5` 组波峰与波谷，保留顺序关系。

语义映射示例：

- 波峰 `[100, 95, 90]`，波谷 `[80, 82, 85]` -> 高点降低、低点抬高，偏向收敛三角形。
- 波峰 `[100, 102, 101]`，波谷 `[80, 81, 79]` -> 上下边界平直，偏向矩形震荡箱体。

## 3.2 空间边界：价格分位与通道

目标：回答“当前价格在 90 日结构中处于什么绝对位置”。

计算：

$$
Position_{90} = \frac{Current - Min_{90}}{Max_{90} - Min_{90}} \times 100\%
$$

解释模板：

- “当前价格位于 90 日空间 `15%`，属于低位区。”
- “当前价格突破 90 日空间 `85%`，接近强压筹码上沿。”

## 3.3 筹码能量：成交量密集区（VPVR/POC）

目标：判断突破是否具备“筹码承接”。

实现建议：

1. 将 90 日价格区间切分为 `10` 个价格桶（bins）。
2. 统计每个桶累计成交量。
3. 找出最大成交量桶作为 `POC`（核心控制价位）。

明确计算口径（必须程序计算，不是手填）：

1. 取窗口：最近 `N=min(90, available_days)` 根日 K。
2. 价格轴分桶：
   - `low_n = min(low)`，`high_n = max(high)`。
   - 等宽切分为 `K=10` 个桶，边界为 `edges[0..10]`。
3. 成交量分配（推荐分级口径）：
   - 价格代表值优先级：`VWAP > Typical Price(HLC3) > Close`。
   - 若存在 `vwap` 列：每日 `volume_i` 计入 `vwap_i` 所在桶（最优）。
   - 若无 `vwap` 但有 `high/low/close`：使用 `hlc3_i=(high_i+low_i+close_i)/3` 计入对应桶（推荐）。
   - 若仅有 `close`：退化为 `close_i` 分桶（兜底）。
   - 若无 `volume`，可用 `turnover` 或 `amount` 作为替代权重。
4. 得到每桶权重 `vol_bin_j` 后：
   - `poc_idx = argmax(vol_bin_j)`。
   - `POC区间 = [edges[poc_idx], edges[poc_idx+1]]`。
   - `核心区间成交占比 = vol_bin_poc / sum(vol_bin_j) * 100%`。

公式：

$$
POC\_ratio = \frac{\max_j(vol\_bin_j)}{\sum_{j=1}^{K} vol\_bin_j} \times 100\%
$$

Python 伪代码：

```python
import numpy as np
import pandas as pd

def calc_poc(df: pd.DataFrame, n: int = 90, k: int = 10):
    d = df.tail(min(n, len(df))).copy()
    low_n, high_n = d["low"].min(), d["high"].max()
    edges = np.linspace(low_n, high_n, k + 1)
    vol_col = "volume" if "volume" in d.columns else "turnover"

    # Price proxy priority: VWAP > HLC3 > Close
    if "vwap" in d.columns:
        d["px_proxy"] = d["vwap"]
    elif {"high", "low", "close"}.issubset(d.columns):
        d["px_proxy"] = (d["high"] + d["low"] + d["close"]) / 3.0
    else:
        d["px_proxy"] = d["close"]

    d["bin"] = pd.cut(d["px_proxy"], bins=edges, include_lowest=True, labels=False)
    vol_bin = d.groupby("bin")[vol_col].sum().reindex(range(k), fill_value=0.0)
    poc_idx = int(vol_bin.idxmax())
    poc_low, poc_high = float(edges[poc_idx]), float(edges[poc_idx + 1])
    poc_ratio = float(vol_bin.iloc[poc_idx] / vol_bin.sum() * 100) if vol_bin.sum() > 0 else 0.0
    return {
        "poc_range": [round(poc_low, 2), round(poc_high, 2)],
        "poc_ratio_pct": round(poc_ratio, 2),
        "price_proxy": "vwap|hlc3|close"
    }
```

推荐：

1. 文档与实现默认采用 `HLC3` 作为日级代理价格。
2. 当 Futu 能稳定提供日级 `VWAP` 时，自动升级为 `VWAP` 口径。

示例解释对应关系：

- “90 日核心筹码密集区（POC）：`88.0 - 95.0`” 对应 `poc_range`。
- “核心区间成交占比：`60%`” 对应 `poc_ratio_pct`。

解释模板：

- “90 日核心筹码密集区在 `88.0-95.0`，成交占比 `60%`。”
- “当前价站上密集区上沿，上方阻力相对真空。”

---

## 4. 均值指标的定位（仅辅助，不主导）

允许使用 `EMA20/EMA60`，但用途仅限：

1. 验证形态方向是否与均值方向一致。
2. 提供“均线纠缠度”作为压缩证据之一。
3. 与微观异动（如 A20 拐点）做右侧确认。

禁止将“均线斜率”作为中期结论的唯一依据。

---

## 5. 中期分析输入模板（给 LLM）

【标的宏观形态档案（过去 90 个交易日）】  
标的：`09888.HK`

1. 空间位置（Space Context）  
- 90 日极值：最高 `120.5`，最低 `85.0`  
- 当前位置：当前价 `92.0`，处于 90 日区间 `19%`（底部区域）

2. 形态骨架（Structure Skeleton）  
- 波峰序列：`120 -> 105 -> 98`（高点依次降低）  
- 波谷序列：`85 -> 86 -> 88`（低点抬高）  
- 均线纠缠度：`EMA20` 与 `EMA60` 间距缩窄至 `2%` 以内

3. 筹码能量（Volume Energy）  
- 90 日核心筹码密集区（POC）：`88.0 - 95.0`  
- 核心区间成交占比：`60%`

【微观异动（今日及近 3 日）】  
放入短期记忆标签：`V5`/`A5`、`MACD`、`机构吸筹/出逃` 等。

---

## 6. 中期分析任务定义（给 LLM）

作为资深量化分析师，请完成：

1. 基于“形态骨架 + 空间位置”识别 90 日宏观形态（如下降楔形、收敛三角形、箱体、下跌中继）。
2. 结合“筹码能量 + 微观异动”，判断当前底部筹码夯实程度。
3. 给出“反脆弱”触发条件：什么信号出现后，向上突破概率显著提升。
4. 输出可交易结论：入场触发、失效条件、风控位。

---

## 7. 实施要点（开发侧）

1. 先压缩形态，再喂给模型，避免原始 K 线直灌。
2. 输出 JSON + 文本双格式：
   - JSON 给程序消费。
   - 文本给 LLM 语义推理。
3. 保持 token 经济：90 天数据压缩到 8-12 行核心特征。
4. 当“波峰波谷收敛 + 均线纠缠 + 筹码集中”共振时，显式标注“压缩弹簧状态”。

---

## 8. 总结

各司其职：

1. 代码负责极值、分位、筹码等枯燥计算。
2. 大模型负责形态命名、交易推理与情景推演。

这样可以在低 token 成本下，最大化捕捉中期“反脆弱”机会，避免被平滑均值掩盖关键形态拐点。
