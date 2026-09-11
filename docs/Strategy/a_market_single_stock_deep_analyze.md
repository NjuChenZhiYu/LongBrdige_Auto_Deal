# A 股单一股票深度分析接口设计（Futu + LLM + Feishu）

## 1. 结论：深证数据是否支持采集

支持第一版深证单股深度分析的数据构造。根据 `docs/Futu-API-Doc-zh-Python.md`，A 股市场代码使用 `SH/SZ` 前缀，例如：

- 深证股票：`SZ.000001`
- 上海股票：`SH.600519`

第一版可稳定接入并复用港股链路的数据：

1. `get_market_snapshot`：实时快照、价格、涨跌幅、当日累计成交量、成交额、换手率、总市值、流通市值、总股本、流通股本、净资产等；同时可获取上证指数与深证成指的大盘快照。
2. `request_history_kline`：日 K 线，使用前复权 `QFQ`；对大盘指数使用 `NONE`，其 `volume/turnover` 字段可构造 5/30/90/180 日市场成交基线。
3. `get_capital_distribution`：当日资金分布，用于主力/散户净流入与短线资金博弈。
4. `get_capital_flow`：历史资金流，用于 5/10/90 日主力与整体资金流。
5. `get_owner_plate`：所属行业/概念板块，用于展示，不直接做行业估值中位数。
6. `get_financials_revenue_breakdown`：主营构成，支持产品、行业、地区、业务等维度；若当前 SDK 未暴露该接口则降级为“无数据”。

第一版不强依赖或暂缓的数据：

1. Longbridge 营收披露：港股链路里使用 `longport_client.get_revenue_disclosure_profile`，A 股第一版不复用，避免跨市场代码不匹配。
2. A 股营收兑现对比：当前 Longbridge Fundamental 文档示例仅覆盖港美代码，Futu 当前 SDK 也未稳定暴露财务报表方法，第一版不放入 Prompt。
3. 行业相对估值：不使用本地板块估值筛选，交由 LLM 联网检索可比公司与行业估值。

---

## 2. 目标

新增一个类似 `LLMAnalyst.generate_hk_single_stock_report` 的 A 股单股深度分析函数，第一版重点放在数据构造：

1. 支持 `SZ.000001`、`000001.SZ`、`000001` 等输入解析。
2. 深证与沪市统一走 A 股函数，纯数字按 A 股常见代码段推断 `SH/SZ`。
3. 复用现有 Futu 客户端、短期记忆、多周期趋势、Feishu 推送与 LLM 重试。
4. Prompt 结构与港股保持相近，便于后续横向比较。

返回结构与港股函数一致：

```python
{
    "ok": True,
    "symbol": "SZ.000001",
    "title": "...",
    "report": "...",
    "error": None,
}
```

---

## 3. 第一版函数设计

在 `src/services/llm_analyst.py` 新增：

```python
async def generate_a_market_single_stock_report(
    self,
    symbol_input: str,
    trigger_type: str = "MANUAL",
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
    enable_grounded_search: bool = True,
) -> Dict[str, Any]:
    ...
```

代码解析规则：

1. 已带前缀：`SZ.000001` / `SH.600519` 原样标准化为大写。
2. 后缀格式：`000001.SZ` / `600519.SH` 转换为 Futu 原生格式。
3. 纯 6 位数字：
   - `600/601/603/605/688/689` 开头：推断为 `SH.xxxxxx`。
   - `000/001/002/003/300/301` 开头：推断为 `SZ.xxxxxx`。
   - 其他代码段：返回错误，要求显式输入 `SH.` 或 `SZ.`。

---

## 4. 数据构造流程

第一版按串行校验执行，避免前置数据为空时继续喂给 LLM：

1. 解析输入为 Futu 原生 A 股代码：`SZ.xxxxxx` 或 `SH.xxxxxx`。
2. `get_special_quotes([symbol])` 获取实时快照，用于价格、涨跌幅、名称、当日高低点。
3. `get_historical_klines(symbol, max(lookback_days_mid + 60, 240))` 获取历史日 K。
4. `get_capital_flow(symbol)` 获取当日资金分布，允许为空但不阻断。
5. `build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)` 复用港股短期记忆。
6. `build_mid_term_trend(klines_df, price, lookback_days_mid)` 复用港股/通用多周期趋势。
7. `get_financials_revenue_breakdown(symbol)` 获取主营构成，压缩为产品/行业/地区/业务收入占比摘要；不可用时降级。
8. 基于 `SH.000001` 与 `SZ.399001` 的快照及历史 K 线，构造沪深两市 5/30/90/180 日大盘成交量与成交额热度。
9. `build_a_market_fundamental_data(symbol, stock, (5, 10, 90), klines_df)` 构造 A 股基本面、主营构成、资金流与流动性承接。
10. `_build_a_market_single_stock_prompt(...)` 组装 Prompt。
11. `_call_llm_with_retry(...)` 生成报告并推送 Feishu。

---

## 5. 复用与新增边界

直接复用：

- `futu_client.get_special_quotes`
- `futu_client.get_historical_klines`
- `futu_client.get_capital_flow`
- `futu_client.get_capital_flow_history`
- `build_short_term_memory`
- `build_mid_term_trend`
- `common_build_liquidity_profiles`
- 大盘指数历史 K 线中已有的 `volume/turnover` 字段
- `_call_llm_with_retry`
- `FeishuAlert.send_alert`

新增薄封装：

- `_parse_a_market_symbol`：A 股代码解析。
- `_build_a_market_single_stock_prompt`：A 股角色与 Prompt。
- `src.analysis.a_market_single_stock_indicator`：A 股基本面/资金流构造，内部复用港股短期与趋势指标。

---

## 6. Prompt 输入字段

与港股第一版保持同构，核心字段包括：

```text
【基本面与估值快照】
- 所属板块
- 总市值 / 流通市值
- 总股本 / 流通股本
- 资产净值
- 主营构成（产品 / 行业 / 地区 / 业务维度，取可用维度 Top 项）

【资金流与流动性】
- 当日实时主力/整体净流入
- 5/10/90 日主力/整体净流入
- 沪深大盘当日成交量/成交额相对 5/30/90/180 日均值的倍数与综合市场热度
- 成交额承接
- 换手率承接
- 解读约束：筹码判断仅基于资金流、量价位置、成交额与换手率，不得虚构长期持有人证据。

【趋势筹码与短期结构】
- 短期记忆：复用 `build_short_term_memory`，内部沿用 `prepare_short_term_dataset`、`build_current_day_indicator`、`build_short_window_indicator`
- 当日快照：`today`（`rt_price`、`day_high_low`、`intraday_position`、`change_rate`、`bias20`、`tag_today`、`bb_summary`）
- 10 日压缩画像：`summary_10d`（最大涨幅/跌幅/回撤、价格分布、`poc_range_10d`、`poc_ratio_10d_pct`）
- 多周期趋势：复用 `build_mid_term_trend`，内部沿用 `build_multi_window_trends` 输出 30/90/180 日趋势、POC、波动率、窗口高低点
```

---

## 7. A 股大盘流动性与交易热度

### 7.1 数据来源与接口结论

该指标表示**A 股大盘成交环境**，不是当前个股的成交活跃度。主数据源选择 Futu，第一版使用：

- 上交所代理：上证指数 `SH.000001`
- 深交所代理：深证成指 `SZ.399001`
- 当日数据：一次调用 `get_market_snapshot(["SH.000001", "SZ.399001"])`
- 历史数据：分别调用 `request_history_kline(..., ktype=KLType.K_DAY, autype=AuType.NONE)`

实测 Futu 当前返回结果中，两只指数的快照和历史 K 线均有非零 `volume/turnover`，可以直接构造沪深大盘热度。Longport 官方也支持 A 股指数及历史 K 线，但当前项目 Longport 客户端与已安装 SDK 的初始化方式不兼容，且实测令牌连接失败，因此第一版 Futu 更稳定、改动更小。

计算前按交易日期对齐沪深两组历史 K 线，排除当日未完成记录；只有两市同日数据均有效时才汇总：

```text
market_volume_day = SH.000001.volume + SZ.399001.volume
market_turnover_day = SH.000001.turnover + SZ.399001.turnover
```

该口径覆盖沪深两市，不含北交所；Prompt 必须标注为“沪深大盘代理”，不能写成包含所有交易所的精确 A 股全市场总量。

### 7.2 计算口径

```text
avg_market_volume_N = 最近 N 个已完成交易日 market_volume_day 的算术平均值
market_volume_ratio_N = comparable_market_volume_today / avg_market_volume_N

avg_market_turnover_N = 最近 N 个已完成交易日 market_turnover_day 的算术平均值
market_turnover_ratio_N = comparable_market_turnover_today / avg_market_turnover_N

N = 5, 30, 90, 180
```

当日可比口径：

1. 收盘后直接使用沪深指数快照汇总的实际 `volume/turnover`。
2. 盘中保留原始累计值，并计算
   `projected_market_volume = current_market_volume / elapsed_trading_fraction`、
   `projected_market_turnover = current_market_turnover / elapsed_trading_fraction`；
   A 股交易时段按 `09:30-11:30`、`13:00-15:00`，合计 240 分钟，午休不计入进度。
3. 盘中标签必须带 `is_intraday=true` 和“盘中估算”；收盘后使用实际值。
4. 开盘不足 30 分钟时投影噪声较大，标记 `LOW_CONFIDENCE`，仅展示比值，不输出强热度结论。

每个周期独立输出成交量与成交额比值；综合热度优先采用成交额，取可用 `market_turnover_ratio_30/90/180` 的中位数，成交量作为交叉验证。5 日比值仅用于识别最近一周的持续放量/缩量背景。分级统一为：

- `>= 1.80`：极度活跃
- `1.30 <= ratio < 1.80`：明显放量
- `0.80 <= ratio < 1.30`：常态成交
- `0.50 <= ratio < 0.80`：明显缩量
- `< 0.50`：流动性低迷

建议输出结构：

```json
{
  "source": "FUTU",
  "market_proxies": ["SH.000001", "SZ.399001"],
  "current_market_volume": 126906445592,
  "current_market_turnover": 2511042521252.81,
  "comparable_market_volume_today": 140000000000,
  "comparable_market_turnover_today": 2800000000000,
  "is_intraday": true,
  "confidence": "NORMAL",
  "market_windows": {
    "5": {"volume_ratio": 1.16, "turnover_ratio": 1.22},
    "30": {"volume_ratio": 1.31, "turnover_ratio": 1.38},
    "90": {"volume_ratio": 1.42, "turnover_ratio": 1.51},
    "180": {"volume_ratio": 1.48, "turnover_ratio": 1.57}
  },
  "overall_ratio": 1.51,
  "market_heat_level": "明显放量",
  "summary": "沪深大盘盘中估算成交额较30/90/180日均额明显放大，市场交易热度升温"
}
```

样本不足时，各窗口使用沪深共同有效的实际交易日并输出 `actual_days_N`；少于 30 个完整交易日时综合标签必须降级为 `LOW_CONFIDENCE`。

### 7.3 Prompt 解读约束

1. 大盘放量只表示参与度上升，不直接等于看多；必须结合指数方向、个股资金流和区间位置区分放量上涨、放量下跌。
2. 缩量只表示参与度下降，不直接等于见底；下跌趋势中的缩量可能是承接不足。
3. 报告中必须明确区分“实际收盘数据”和“盘中投影数据”，并声明“不含北交所”。

---

## 8. 降级策略

1. 快照为空：直接失败，提示代码或行情权限问题。
2. K 线为空：直接失败，因为短期记忆和多周期趋势无法构造。
3. 当日资金为空：保留报告，资金字段输出“无数据”。
4. 历史资金为空：5/10/90 日资金流输出“无数据”或 0 值标签。
5. 板块为空：输出“无数据”，不影响报告。
6. 主营构成不可用：输出“无数据”，基本面只保留市值、板块和快照字段，不阻断报告。
7. 任一沪深指数的当日或历史 `volume/turnover` 缺失：大盘流动性输出“数据不足”，不使用单边市场冒充沪深汇总。

---

## 9. 验收标准

1. 输入 `SZ.000001` 可完成快照、K 线、资金流、基本面结构化数据构造。
2. 输入 `000001` 可推断为 `SZ.000001`。
3. 输入 `600519` 可推断为 `SH.600519`。
4. A 股报告 Prompt 与港股报告具有相同的主干数据块。
5. 任一可降级数据为空时，报告生成链路不因非核心字段中断。
6. Prompt 必须展示沪深大盘当日成交量与成交额相对 5/30/90/180 日均值的比值、综合热度和盘中/收盘口径。
