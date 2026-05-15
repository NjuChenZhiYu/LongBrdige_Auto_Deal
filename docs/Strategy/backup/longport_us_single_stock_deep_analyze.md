# 美股单一股票深度分析接口设计（LongPort + LLM + Feishu）

## 1. 背景与目标

基于现有 `src/services/llm_analyst.py` 中美股链路，参照港股单股方案，新增"美股单一股票深度分析"能力。  
当前版本聚焦三个核心产物，不强调提示词模板：

1. 基本面与估值快照（可交易、可解释）。
2. 短期记忆（复用 `build_short_window_indicator`）。
3. 中期趋势（复用 `build_mid_term_trend`）。

设计目标：

- LongPort 与 Futu 仅在"数据来源"不同，特征工程尽量复用同一套方法。
- 输入不同市场的 K 线后，统一落成标准 DataFrame，再走同一指标函数。
- 通过策略模式隔离各数据源，避免在 `llm_analyst.py` 写大量 if/else 分支。

---

## 2. 关键结论（你提的问题的直接答案）

可以做到"一个方法处理 LongPort 与 Futu 两种数据"。

前提是把两边数据先转为统一结构，再进入公共指标函数：

- 数据获取层：`LongPortProvider` / `FutuProvider`。
- 数据标准化层：输出统一 `MarketDataBundle`（snapshot + klines_df + capital_df）。
- 特征工程层：统一调用 `build_short_window_indicator` 和 `build_mid_term_trend`。

换句话说：**来源异构，处理同构**。

---

## 3. 对外接口（服务层）

建议在 `src/services/llm_analyst.py` 新增：

```python
async def generate_single_stock_report(
    self,
    symbol: str,
    market: str,  # "US" / "HK"
    trigger_type: str = "MANUAL",
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
) -> dict:
    ...
```

返回结构：

```python
{
  "ok": True/False,
  "symbol": "AAPL.US",
  "market": "US",
  "title": "...",
  "analysis_payload": {
    "fundamental": {...},
    "short_memory": {...},
    "mid_memory": {...}
  },
  "report": "...",   # 可选：后续如接 LLM 再填充
  "error": None or "error message"
}
```

说明：

1. 当前重点是 `analysis_payload`，不是 Prompt 文案。
2. `market` 决定选用哪个 Provider 拉取原始数据。
3. 分析函数保持市场无感，输入统一 DataFrame 即可。

---

## 4. 策略模式设计（核心）

## 4.1 抽象数据对象

```python
from dataclasses import dataclass
import pandas as pd
from typing import Any, Dict, Optional

@dataclass
class MarketDataBundle:
    symbol: str
    market: str
    snapshot: Dict[str, Any]
    klines_df: pd.DataFrame
    capital_df: Optional[pd.DataFrame]
    extra: Dict[str, Any]  # 如 plate_info / sentiment 等
```

统一 `klines_df` 列约定（最重要）：

- 必需列：`timestamp`, `open`, `high`, `low`, `close`, `volume`, `turnover`
- 可选列：`trade_session`, `source`
- 数值列统一为 `float` / `int`，时间统一为 `datetime64[ns]`

## 4.2 抽象 Provider 接口

```python
from abc import ABC, abstractmethod

class BaseMarketDataProvider(ABC):
    @abstractmethod
    async def fetch_snapshot(self, symbol: str) -> dict:
        ...

    @abstractmethod
    async def fetch_klines(self, symbol: str, num_days: int) -> "pd.DataFrame":
        ...

    @abstractmethod
    async def fetch_capital_flow(self, symbol: str) -> "pd.DataFrame | None":
        ...

    @abstractmethod
    async def build_bundle(self, symbol: str, num_days: int) -> MarketDataBundle:
        ...
```

## 4.3 两个实现类

- `LongPortDataProvider(BaseMarketDataProvider)`
  - `quote_ctx.quote([symbol])`
  - `quote_ctx.static_info([symbol])`
  - `quote_ctx.calc_indexes([symbol], [...])`
  - `quote_ctx.history_candlesticks_by_date(...)`
  - `quote_ctx.capital_distribution(symbol)`
  - `quote_ctx.capital_flow(symbol)`（盘中分钟级）
- `FutuDataProvider(BaseMarketDataProvider)`
  - `get_market_snapshot([symbol])`
  - `get_hk_historical_klines(symbol, num_days)`
  - `get_capital_flow(symbol)`

两者都必须在 `build_bundle()` 里完成字段映射，保证 `MarketDataBundle` 结构一致。

---

## 5. 特征工程复用（重点）

在统一 Bundle 后，直接复用：

- `build_short_window_indicator(klines_df, current_price, ...)`
- `build_mid_term_trend(klines_df, current_price, ...)`

建议在 `src/analysis/futu_math_indicator.py` 增加一个"市场无关入口"（或新建 `market_indicator.py` 后转调）：

```python
def build_semantic_memory_from_bundle(bundle: MarketDataBundle) -> dict:
    current_price = float(bundle.snapshot.get("last_price") or bundle.klines_df["close"].iloc[-1])

    short_memory = build_short_window_indicator(
        bundle.klines_df,
        current_price=current_price,
    )
    mid_memory = build_mid_term_trend(
        bundle.klines_df,
        current_price=current_price,
    )
    return {
        "fundamental": _extract_fundamental(bundle.snapshot, bundle.extra),
        "short_memory": short_memory,
        "mid_memory": mid_memory,
    }
```

结论：`build_short_window_indicator` 和 `build_mid_term_trend` 本质依赖的是标准 OHLCV DataFrame，与来源是 LongPort 还是 Futu 无关。

---

## 6. LongPort 数据拉取口径（US / 确认可用接口）

基于 `developers/docs/en/docs/quote/pull` 官方文档（已验证字段）：

### 6.1 实时行情：`ctx.quote([symbol])` → `SecurityQuote`

| 字段 | 类型 | 说明 |
|---|---|---|
| `last_done` | Decimal | 最新价 → 映射为内部 `last_price` |
| `prev_close` | Decimal | 昨收价 |
| `open` | Decimal | 今开 |
| `high` | Decimal | 今高 |
| `low` | Decimal | 今低 |
| `volume` | int | 成交量 |
| `turnover` | Decimal | 成交额 |
| `timestamp` | datetime | 更新时间 |
| `pre_market_quote` | Optional | 美股盘前行情 |
| `post_market_quote` | Optional | 美股盘后行情 |

**不含**：`change_rate`（需自行计算 `(last_done - prev_close) / prev_close`）、pe/pb/市值等估值字段。

### 6.2 基础静态信息：`ctx.static_info([symbol])` → `SecurityStaticInfo`

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | str | 代码 |
| `name_cn` / `name_en` | str | 中英文名称 |
| `currency` | str | `USD` / `HKD` 等 |
| `total_shares` | int | 总股本 |
| `circulating_shares` | int | 流通股本 |
| `eps` | Decimal | 每股盈利（静） |
| `eps_ttm` | Decimal | 每股盈利（TTM） |
| `bps` | Decimal | 每股净资产 |
| `dividend_yield` | Decimal | 股息率（%） |
| `exchange` | str | 交易所 |
| `lot_size` | int | 每手股数 |

**不含**：`pe_ratio`、`pb_ratio`、`ps_ratio`、市值、板块（所属行业/概念板块 LongPort 无此接口）。

### 6.3 计算指标：`ctx.calc_indexes([symbol], indexes)` → `SecurityCalcIndex`

| 字段 | 类型 | 说明 |
|---|---|---|
| `total_market_value` | string | **总市值** ✓ |
| `pe_ttm_ratio` | string | **PE（TTM）** ✓ |
| `pb_ratio` | string | **PB** ✓ |
| `dividend_ratio_ttm` | string | 股息率（TTM） |
| `change_rate` | string | 涨跌幅 |
| `turnover_rate` | string | 换手率 |
| `volume_ratio` | string | 量比 |
| `capital_flow` | string | 今日资金净流入（快照） |
| `five_day_change_rate` | string | 5 日涨跌幅 |
| `ten_day_change_rate` | string | 10 日涨跌幅 |
| `half_year_change_rate` | string | 半年涨跌幅 |

**不含**：`ps_ratio`（LongPort 无此字段）、流通市值（需衍生计算）、PE 静（需衍生计算）。

### 6.4 历史 K 线：`history_candlesticks_by_date` / `history_candlesticks_by_offset`

#### 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `timestamp` | int64 (→ datetime) | K 线时间戳（Unix 秒） |
| `open` | string (→ float) | 开盘价 |
| `high` | string (→ float) | 最高价 |
| `low` | string (→ float) | 最低价 |
| `close` | string (→ float) | 收盘价 |
| `volume` | int64 | 成交量 |
| `turnover` | string (→ float) | 成交额 |
| `trade_session` | int32 | 交易时段（0=盘中/100=全时段含盘前后） |

#### 两种调用方式（Python async）

```python
from datetime import date, datetime, timedelta
from longbridge.openapi import AsyncQuoteContext, Period, AdjustType, TradeSessions

ctx = await AsyncQuoteContext.create(config)

# 方式一：按日期区间（推荐用于短/中期回看）
end   = date.today()
start = end - timedelta(days=120)  # 拉 120 日，保证 90 个交易日充足
candles = await ctx.history_candlesticks_by_date(
    "AAPL.US",
    Period.Day,
    AdjustType.NoAdjust,       # 不复权；复权用 AdjustType.ForwardAdjust
    start=start,
    end=end,
    trade_sessions=TradeSessions.Intraday,  # 只取正式交易时段，排除盘前/盘后
)

# 方式二：按 offset（从某时间点向前/向后取 N 根）
candles = await ctx.history_candlesticks_by_offset(
    "AAPL.US",
    Period.Day,
    AdjustType.NoAdjust,
    forward=False,             # False = 向历史方向取，即取最近 count 根
    count=120,                 # 最大 1000
    time=None,                 # None = 默认从最新交易日起算
    trade_sessions=TradeSessions.Intraday,
)
```

#### 关键约束

| 约束项 | 说明 |
|---|---|
| 单次上限 | 最多返回 **1000** 根；日线 90 天回看单次足够 |
| 美股日线数据起始 | **2010-06-01** 至今，所有上市满 90 日的标的均可覆盖 |
| 分钟线数据起始 | 2023-12-04 至今（短/中期日线分析不依赖此） |
| 速率限制 | **60 次 / 30 秒** |
| 月度标的额度 | 按账户资产等级，**100 ~ 3000 个不同标的 / 月**（同一标的重复请求只计 1 次） |
| `trade_session` | 日线级分析必须传 `TradeSessions.Intraday`，否则会包含盘前/盘后虚假 OHLCV |

#### 月度额度等级参考（按账户 HKD 资产）

| 账户资产 | 可查标的数/月 |
|---|---|
| 开户即享 | 100 |
| ≥ 1 万 HKD | 400 |
| ≥ 8 万 HKD | 600 |
| ≥ 40 万 HKD 或月交易 ≥ 160 次 | 1000 |
| ≥ 400 万 HKD 或月交易 ≥ 1600 次 | 2000 |
| ≥ 600 万 HKD 或月交易 ≥ 2500 次 | 3000 |

> **运营建议**：对"每日定时扫描监控列表"场景，需控制每月请求的唯一标的总数在账户额度内。同一标的当日多次调用不额外消耗额度。

### 6.5 资金分布快照：`ctx.capital_distribution(symbol)` → `CapitalDistributionResponse`

| 字段 | 类型 | 说明 |
|---|---|---|
| `timestamp` | datetime | 数据更新时间 |
| `capital_in.large/medium/small` | Decimal | 今日大/中/小单流入额 |
| `capital_out.large/medium/small` | Decimal | 今日大/中/小单流出额 |

**重要限制**：
- 这是**今日截至当前时刻的累计快照**，不是历史日线数据。
- 无法直接获取昨日或过去 N 日的分日资金分布。
- 与 Futu 的 `get_capital_flow_history`（可返回历史每日资金流）不同，LongPort **没有对应的历史资金流接口**。

### 6.6 盘中资金流：`ctx.capital_flow(symbol)` → `List[CapitalFlowLine]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `inflow` | Decimal | 该分钟净流入额 |
| `timestamp` | datetime | 分钟起始时间戳 |

- **仅提供今日盘中分钟级数据**，不提供跨日历史。
- 可用于今日资金趋势分析（盘中走势图），但不能替代多日历史资金流。

---

## 7. 衍生字段计算（LongPort 无直接返回，需在 Provider 层计算）

| 输出字段 | 计算方式 | 依赖接口 |
|---|---|---|
| `change_rate`（数值） | `(last_done - prev_close) / prev_close` | `quote` |
| `circulating_market_value` | `last_done × circulating_shares` | `quote` + `static_info` |
| `net_asset` | `bps × total_shares` | `static_info` |
| `pe_static` | `last_done / eps`（eps > 0 时） | `quote` + `static_info` |
| `smart_net_today`（万） | `(capital_in.large - capital_out.large) / 10000` | `capital_distribution` |
| `retail_net_today`（万） | `((capital_in.medium + capital_in.small) - (capital_out.medium + capital_out.small)) / 10000` | `capital_distribution` |

---

## 8. 输出定义（当前版本）

当前先输出"结构化分析数据"，不绑定 Prompt：

### 8.1 fundamental（基本面快照）

```json
{
  "name": "Apple Inc.",
  "currency": "USD",
  "total_shares": "1.63亿股",
  "circulating_shares": "1.63亿股",
  "total_market_value": "2.13万亿",
  "circulating_market_value": "2.13万亿（衍生）",
  "net_asset": "71.8亿（衍生：bps × total_shares）",
  "eps": "5.669",
  "eps_ttm": "6.077",
  "bps": "4.402",
  "pe_ttm": "21.26",
  "pe_static": "23.27（衍生）",
  "pb": "31.71",
  "ps_ttm": "无数据（LongPort 不提供）",
  "dividend_yield": "0.85%",
  "dividend_ratio_ttm": "0.64",
  "plate_info": "无数据（LongPort 无板块接口）",
  "capital_flow_today_snapshot": {
    "smart_net_today_wan": 46640.0,
    "retail_net_today_wan": -12345.0,
    "flow_status_tag": "主力抢筹/主升浪"
  }
}
```

**说明：**
- `ps_ttm`：LongPort `calc_indexes` 不提供 PS 字段，**必须标记为"无数据"**，不得填 0 或猜测。
- `plate_info`：LongPort 无行业/概念板块 API，**必须标记为"无数据"**。Prompt 层引用此字段时需做判空处理。
- `capital_flow_today_snapshot`：仅为今日当前快照，**不含 5/10/90 日历史资金流**（见 §9 数据缺口）。

### 8.2 short_memory（短期记忆，近 10 日）

```json
{
  "window_used": 10,
  "short_window_incomplete": false,
  "smart_net_wan": 0.0,
  "retail_net_wan": 0.0,
  "today": {
    "date": "2026-05-14 10:30:00(RT)",
    "rt_price": 131.88,
    "bias20": 3.45,
    "tag_today": "【主升浪加速：长短共振】"
  },
  "summary_10d": {
    "window_used": 10,
    "short_window_incomplete": false,
    "max_cum_up_10d_pct": 8.5,
    "max_cum_drop_10d_pct": -3.2,
    "max_drawdown_10d_pct": -5.1,
    "short_window_price_distribute": [...],
    "poc_range_10d": "128.5-131.2",
    "poc_ratio_10d_pct": 35.0
  }
}
```

**说明：**
- `smart_net_wan` / `retail_net_wan`：来自 `capital_distribution` 的**今日快照**（非 10 日累计），与港股版的多日历史累计值语义不同，应在 Prompt 中明确标注"今日快照"。
- 技术类字段（price_distribute、poc、bias20、tag_today）完全依赖 OHLCV K 线，与 LongPort/Futu 无关，可直接复用公共计算层。

### 8.3 mid_memory（中期趋势，近 90 日）

```json
{
  "mode": "FULL_90 | COMPRESSED_30_89 | INSUFFICIENT_LT30",
  "window_used": 90,
  "summary": "...",
  "shape": "混合震荡结构",
  "position_pct": 94.24,
  "peaks": [128.5, 135.0, 131.88],
  "troughs": [118.0, 125.0, 127.5],
  "poc_range": [122.0, 127.0],
  "poc_ratio_pct": 18.5
}
```

**说明：** 中期趋势全部依赖 OHLCV K 线，LongPort `history_candlesticks_by_date` 完整支持，**无数据缺口**。

---

## 9. 数据缺口说明（LongPort vs Futu 差异）

| 数据项 | 港股 Futu | 美股 LongPort | 处理方式 |
|---|---|---|---|
| 板块/行业信息 | `get_owner_plate()` ✓ | **无接口** | 输出 `"无数据"`，Prompt 层判空跳过 |
| PE 静 | 快照直接返回 | 需衍生：`price / eps` | Provider 层计算，标注"衍生值" |
| PS TTM | 快照直接返回 | **无此字段** | 输出 `"无数据"`，不能填 0 |
| 历史资金流（5/10/90日） | `get_capital_flow_history()` ✓ | **无历史接口** | 降级：仅输出今日快照，Prompt 明确标注 |
| 今日资金分布快照 | `get_capital_flow()` ✓ | `capital_distribution()` ✓ | 字段已映射（large=主力，small=散户） |
| 历史 K 线 | `get_hk_historical_klines()` ✓ | `history_candlesticks_by_date()` ✓ | 已统一映射到标准 DataFrame |
| 估值指标（PE TTM / PB） | 快照直接返回 | `calc_indexes()` ✓ | 需单独调用 `calc_indexes` |
| 实时价格 | 快照直接返回 | `quote()` ✓（`last_done`） | 映射为 `last_price` |

### 9.1 资金流数据缺口的降级策略

由于 LongPort 无历史多日资金流，美股版 `fundamental_data` 不再提供 5/10/90 日资金流汇总。改为：

1. **今日资金快照**：调用 `capital_distribution()`，输出 `smart_net_today_wan` + `retail_net_today_wan` + `flow_status_tag`。
2. **Prompt 层降级文案**：在 `【筹码与流动性档案】` 段落中明确说明：
   ```
   - 今日资金快照（非历史多日汇总）：主力大单净流入 XXXX 万
   - 历史多日资金流（LongPort 不支持）：数据缺失，结合技术面研判
   ```
3. **不填充虚假数据**：禁止用今日快照值重复填充成"5日/10日资金"，会误导研判逻辑。

---

## 10. 样本不足与降级

1. `available_days >= 90`：完整中期规则。
2. `30 <= available_days < 90`：压缩版中期规则。
3. `10 <= available_days < 30`：只给短期，不给中期结构结论。
4. `< 10`：只给基本面 + 实时快照，标记样本不足。

---

## 11. 最小改动落地建议

第一阶段（推荐）：

1. 在 `src/analysis/futu_math_indicator.py` 保持原函数不动，仅补一个市场无关入口函数。
2. 新增 `src/data/providers/base_provider.py`、`longport_provider.py`、`futu_provider.py`（或放在现有 client 层旁边）。
3. `LongPortDataProvider.build_bundle()` 需串行调用（以下均为 `await`）：
   ```python
   static_list  = await ctx.static_info([symbol])
   quote_list   = await ctx.quote([symbol])
   calc_list    = await ctx.calc_indexes([symbol], [
       CalcIndex.TotalMarketValue, CalcIndex.PeTtmRatio, CalcIndex.PbRatio,
       CalcIndex.DividendRatioTtm, CalcIndex.ChangeRate, CalcIndex.TurnoverRate,
   ])
   end   = date.today()
   start = end - timedelta(days=max(lookback_days_mid + 30, 120))
   candles = await ctx.history_candlesticks_by_date(
       symbol, Period.Day, AdjustType.NoAdjust,
       start=start, end=end,
       trade_sessions=TradeSessions.Intraday,   # 排除盘前/盘后
   )
   capital_dist = await ctx.capital_distribution(symbol)
   ```
   注意：K 线接口有**月度标的额度限制**（见 §6.4），高频监控场景需规划额度预算。
4. 在 `generate_single_stock_report` 中通过 `provider_factory(market)` 获取数据，再统一调用指标函数。
5. 输出结构化 `analysis_payload`，后续再按需接入 LLM 文本化。

第二阶段：

1. 把 HK 和 US 单股逻辑都切换到同一入口，逐步收敛重复代码。
2. 补单元测试：字段映射、DataFrame 标准化、短/中期函数跨市场一致性。

---

## 12. LongPort 字段完整映射表（Provider 层参考）

```python
# static_info → snapshot 基础面部分
snapshot["name"]               = static.name_cn or static.name_en
snapshot["currency"]           = static.currency          # "USD"
snapshot["total_shares"]       = int(static.total_shares)
snapshot["circulating_shares"] = int(static.circulating_shares)
snapshot["eps"]                = float(static.eps)
snapshot["eps_ttm"]            = float(static.eps_ttm)
snapshot["bps"]                = float(static.bps)
snapshot["dividend_yield"]     = float(static.dividend_yield)

# quote → snapshot 实时部分
snapshot["last_price"]         = float(quote.last_done)   # 统一内部字段名
snapshot["prev_close"]         = float(quote.prev_close)
snapshot["open"]               = float(quote.open)
snapshot["high"]               = float(quote.high)
snapshot["low"]                = float(quote.low)
snapshot["volume"]             = int(quote.volume)
snapshot["turnover"]           = float(quote.turnover)
snapshot["change_rate"]        = (snapshot["last_price"] - snapshot["prev_close"]) / snapshot["prev_close"]

# calc_indexes → snapshot 估值部分（需指定 CalcIndex 枚举请求）
snapshot["total_market_value"] = float(calc.total_market_value or 0)
snapshot["pe_ttm"]             = float(calc.pe_ttm_ratio or 0)
snapshot["pb"]                 = float(calc.pb_ratio or 0)
snapshot["dividend_ratio_ttm"] = float(calc.dividend_ratio_ttm or 0)
snapshot["turnover_rate"]      = float(calc.turnover_rate or 0)

# 衍生计算（Provider 层）
snapshot["circulating_market_value"] = snapshot["last_price"] * snapshot["circulating_shares"]
snapshot["net_asset"]                = snapshot["bps"] * snapshot["total_shares"]
snapshot["pe_static"]                = (snapshot["last_price"] / snapshot["eps"]) if snapshot["eps"] > 0 else None
snapshot["ps_ttm"]                   = None   # LongPort 无此字段，明确置 None

# capital_distribution → 今日资金快照
cap_in  = capital_dist.capital_in
cap_out = capital_dist.capital_out
snapshot["smart_net_today_wan"]  = (float(cap_in.large) - float(cap_out.large)) / 10000
snapshot["retail_net_today_wan"] = ((float(cap_in.medium) + float(cap_in.small))
                                   - (float(cap_out.medium) + float(cap_out.small))) / 10000
# flow_status_tag 逻辑沿用 longport_client.analyze_us_capital_flow()
```

---

## 13. Prompt 层使用注意（字段判空规则）

| 字段 | 判空规则 | 缺失时 Prompt 占位 |
|---|---|---|
| `plate_info` | `None` 或 `"无数据"` | 省略板块行，不输出该行 |
| `ps_ttm` | `None` | 输出 `PS(TTM): 数据缺失` |
| `pe_static` | `None`（eps ≤ 0 时） | 输出 `PE(静): 亏损/无意义` |
| 5/10/90日资金流 | 不存在 | 输出 `历史资金流: LongPort 不支持，仅提供今日快照` |
| `smart_net_today_wan` | `capital_distribution` 失败时为 0 | 输出 `今日资金快照: 数据缺失` |
