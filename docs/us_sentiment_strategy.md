# 美股 Reddit 情绪分析策略 (Adanos API)

## 1. 策略概述
通过调用 Adanos API (`https://api.adanos.org/docs#tag/reddit-stocks/GET/reddit/stocks/v1/stock/{ticker}`) 获取海外核心散户社区（如 Reddit 的 wallstreetbets, stocks 等）的讨论热度与多空情绪。
此策略将对触发了价格异动阈值的美股自选标的进行情绪扫描，通过打标签的方式，帮助 AI 分析师和用户更直观地判断该标的的“异动”是否由散户狂热、机构分歧或突发利好/利空引起。

## 2. 数据结构与字段参考
API 返回示例片段：
```json
{
  "ticker": "TSLA",
  "buzz_score": 87.5,
  "bullish_pct": 45,
  "bearish_pct": 18,
  "top_subreddits": [{"subreddit": "wallstreetbets", "count": 89}],
  "daily_trend": [
    {"date": "2025-12-28", "buzz_score": 42.8},
    {"date": "2025-12-27", "buzz_score": 38.5}
  ]
}
```

## 3. 标签判定规则

### 3.1 热度解析 (Buzz Score)
*   **【全网极度狂热】**: `buzz_score >= 80`。说明当前该标的在海外社交媒体讨论度极高，极易发生散户逼空（Short Squeeze）或情绪顶部的剧烈波动。
*   **【情绪冰点】**: `buzz_score < 30`。说明该标的尽管价格异动，但散户关注度极低，可能由机构资金主导或仅为随大盘波动。

### 3.2 多空解析 (Bullish/Bearish Percentage)
*   **【散户强烈看多】**: `bullish_pct > 60`。情绪一面倒看涨，可能带来短期极强动能。
*   **【极度恐慌】**: `bearish_pct > 50`。情绪极度看空，可能存在抛售踩踏或潜在的超跌反弹机会。
*   **【计算分歧度】 (Divergence)**: `divergence = abs(bullish_pct - bearish_pct)`
    *   如果 `divergence < 10`：返回标签 **【多空极端分歧：方向选择中】**
    *   如果 `bullish_pct > 2 * bearish_pct`：返回标签 **【单边乐观：注意回调风险】**
    *   如果 `bearish_pct > 2 * bullish_pct`：返回标签 **【单边悲观：注意反弹机会】**

### 3.3 边际解析 (Daily Trend)
*   **【热度脉冲爆发】**: 读取 `daily_trend`，对比最近一天的 `buzz_score` 和前一天的 `buzz_score`。如果 `当天热度 > 前一天热度 * 2`，则触发该标签。说明该标的是刚刚爆发的新热点。

## 4. 整合与执行流程 (被动触发机制)
此情绪分析策略作为大模型研报的辅助数据源，采用**被动触发**机制，完全依赖于美股异动监控的触发。

1.  **触发条件**：定时任务或实时监控发现自选股列表（`config/longport_symbols.yaml`）中，有股票的涨跌幅超过设定的异动阈值（`threshold`）。
2.  **启动研报生成**：系统调用 `src/services/llm_analyst.py` 中的 `generate_longport_us_report` 方法，并将达到阈值的股票列表（`threshold_stocks`）传入。
3.  **获取情绪**：对于 `threshold_stocks` 中的每一只股票，系统调用 `src/api/adanos_client.py` 中封装的异步方法请求 Adanos API。
4.  **计算标签**：等待 API 返回数据后，根据上述判定规则计算出对应的策略标签列表（例如：`["全网极度狂热", "散户强烈看多", "WSB赌徒资金主导"]`）。
5.  **注入报告**：将这些标签拼接到送给大模型的 `alert_text` 提示词中（例如：`1. AAPL.US: 现价 $150.00, 上涨 +5.20% [全网极度狂热, 散户强烈看多]`）。
6.  **生成研报**：LLM 结合量价异动数据和附带的海外社区情绪标签，输出更全面深入的市场研报。
