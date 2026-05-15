# 美股单一股票深度分析接口调研（Futu 方案）

> **目的**：对照 `us_single_stock_deep_analyze.md`（LongPort 方案），逐项核查用 Futu API 替代后能否获取更多数据，并评估兼容性。  
> **参考文档**：`docs/Futu-API-Doc-zh-Python.md`（富途 Python SDK 官方文档）

---

## 1. 前置条件（Futu vs LongPort 架构差异）

| 维度 | LongPort | Futu |
|---|---|---|
| 接入方式 | 云端直连 `AsyncQuoteContext.create(config)` | 本地进程 `OpenQuoteContext(host, port)` 连接 FutuOpenD |
| 依赖 | 仅 SDK + token | 需本地运行 FutuOpenD 守护进程 |
| 调用风格 | `async/await` | 同步阻塞（需 `asyncio.to_thread` 包装） |
| 美股代码格式 | `AAPL.US` | `US.AAPL` |
| K 线月度额度 | **100~3000 个标的/月**（账户资产等级） | **无此限制** |
| 行情权限 | 按 LongPort 行情卡购买 | 按富途行情权限包 |

---

## 2. 接口逐项对比

### 2.1 实时行情快照：`get_market_snapshot(["US.AAPL"])`

Futu `get_market_snapshot` 一次调用即可返回绝大多数估值字段，**无需像 LongPort 那样额外调用 `calc_indexes`**。

| 字段 | Futu 字段名 | LongPort 等价 | 是否优于 LongPort |
|---|---|---|---|
| 股票名称 | `name` | `static_info.name_cn/en` | 持平 |
| 最新价 | `last_price` | `quote.last_done` | 持平 |
| 昨收 | `prev_close_price` | `quote.prev_close` | 持平 |
| 今开/高/低 | `open_price/high_price/low_price` | `quote.*` | 持平 |
| 成交量/额 | `volume`, `turnover` | `quote.*` | 持平 |
| 涨跌幅 | `(last_price-prev_close)/prev_close` | 同，需衍生 | 持平 |
| **总股本** | `issued_shares` | `static_info.total_shares` | 持平 |
| **流通股本** | `outstanding_shares` | `static_info.circulating_shares` | 持平 |
| **总市值** | `total_market_val` | `calc_indexes.total_market_value` | ✅ 快照直出，无需 calc_indexes |
| **流通市值** | `circular_market_val` | 衍生计算 | ✅ 快照直出 |
| **资产净值** | `net_asset` | 衍生（bps × shares） | ✅ 快照直出 |
| **净利润** | `net_profit` | **不可用** | ✅ Futu 独有 |
| **EPS** | `earning_per_share` | `static_info.eps` | 持平 |
| **BPS** | `net_asset_per_share` | `static_info.bps` | 持平 |
| **PE 静** | `pe_ratio` | 需衍生（price/eps） | ✅ 快照直出 |
| **PE TTM** | `pe_ttm_ratio` | `calc_indexes.pe_ttm_ratio` | ✅ 快照直出 |
| **PB** | `pb_ratio` | `calc_indexes.pb_ratio` | ✅ 快照直出 |
| 收益率(EY) | `ey_ratio` | **不可用** | ✅ Futu 独有 |
| 股息 TTM | `dividend_ttm` | `calc_indexes.dividend_ratio_ttm` | 持平 |
| 股息率 TTM | `dividend_ratio_ttm` | 持平 | 持平 |
| 换手率 | `turnover_rate` | `calc_indexes.turnover_rate` | ✅ 快照直出 |
| 量比 | `volume_ratio` | `calc_indexes.volume_ratio` | ✅ 快照直出 |
| 52周高/低 | `highest52weeks_price/lowest52weeks_price` | **不可用** | ✅ Futu 独有 |
| 历史最高/低 | `highest_history_price/lowest_history_price` | **不可用** | ✅ Futu 独有 |
| **盘前行情** | `pre_price/pre_high/pre_low/pre_volume/pre_turnover/pre_change_rate` | `quote.pre_market_quote`（字段较少） | ✅ Futu 更完整 |
| **盘后行情** | `after_price/after_high/after_low/after_change_val/after_change_rate` | `quote.post_market_quote` | ✅ Futu 更完整 |
| **夜盘行情** | `overnight_price/overnight_high/overnight_low/overnight_volume/overnight_change_rate` | **不可用** | ✅ Futu 独有 |
| **`ps_ttm`** | ❌ **快照中无此字段** | ❌ 同样无 | 持平（均无法直接获取） |

> **`ps_ttm` 说明**：Futu 在选股接口 `get_filter_stock_list` 中可返回 `ps_ttm`，但 `get_market_snapshot` 和 `get_capital_flow` 均不含此字段。若需要，可单独调用选股接口，但会增加复杂度。结论：**ps_ttm 两方均无法通过常规快照接口获取**，处理方式一致（标记为"无数据"或通过额外接口获取）。

---

### 2.2 板块信息：`get_owner_plate(["US.AAPL"])`

| 能力 | Futu | LongPort |
|---|---|---|
| 支持美股 | ✅ **支持**（`US.AAPL` 格式） | ❌ **无此接口** |
| 返回字段 | `plate_code`, `plate_name`, `plate_type`（行业/概念） | — |

```python
ret, data = quote_ctx.get_owner_plate(["US.AAPL"])
# 过滤 INDUSTRY 和 CONCEPT 类型
plate_info = "、".join(
    data[data["plate_type"].isin(["INDUSTRY", "CONCEPT"])]["plate_name"].tolist()
)
```

**结论**：这是 Futu 相对于 LongPort 最大的增量优势之一。**美股板块/行业信息可通过 Futu 获取**，LongPort 完全缺失。

---

### 2.3 历史资金流（多日）：`get_capital_flow("US.AAPL", period_type=PeriodType.DAY, ...)`

这是 Futu **最关键的优势**，直接解决了 LongPort 方案中的最大数据缺口。

| 能力 | Futu | LongPort |
|---|---|---|
| 历史多日资金流 | ✅ `period_type=PeriodType.DAY`，最长 365 天 | ❌ **完全不支持** |
| 盘中资金流 | ✅ `period_type=PeriodType.INTRADAY` | ✅ `capital_flow()` |
| 特大单(super) | ✅ `super_in_flow` | ❌ 无 super，最细为 large |
| 大单 | ✅ `big_in_flow` | ✅ `capital_in.large` |
| 中单 | ✅ `mid_in_flow` | ✅ `capital_in.medium` |
| 小单 | ✅ `sml_in_flow` | ✅ `capital_in.small` |
| 主力净流合计 | ✅ `main_in_flow`（**仅历史日/周/月有效**，盘中无此字段） | ❌ 需手动合并 large |
| 整体净流 | ✅ `in_flow` | ❌ 需手动合并 |

```python
# 获取近 90 日历史资金流（包含主力大单/整体净流）
ret, flow_df = quote_ctx.get_capital_flow(
    "US.AAPL",
    period_type=PeriodType.DAY,
    start="2026-02-13",
    end="2026-05-14",
)
# flow_df 列：in_flow, main_in_flow, super_in_flow, big_in_flow, mid_in_flow, sml_in_flow, capital_flow_item_time
```

**5/10/90 日资金流聚合**（对标港股 Futu 方案，完全一致）：

```python
def aggregate_us_capital_flow(flow_df, window_days):
    d = flow_df.tail(window_days)
    main_in = d["main_in_flow"].fillna(0.0).sum()   # 主力大单净流入
    total_in = d["in_flow"].fillna(0.0).sum()         # 整体净流入
    ...
```

**结论**：Futu 完全支持美股 5/10/90 日历史资金流聚合，**与港股 `calculate_hk_capital_flow_profiles` 逻辑完全对称**，代码可直接复用。

---

### 2.4 今日资金分布：`get_capital_distribution("US.AAPL")`

| 字段 | Futu | LongPort |
|---|---|---|
| 特大单流入 | `capital_in_super` | ❌ 无 |
| 大单流入 | `capital_in_big` | `capital_in.large` |
| 中单流入 | `capital_in_mid` | `capital_in.medium` |
| 小单流入 | `capital_in_small` | `capital_in.small` |
| 流出各档 | `capital_out_super/big/mid/small` | `capital_out.large/medium/small` |
| 更新时间 | `update_time`（格式化字符串） | `timestamp`（datetime） |

**Futu 额外提供"特大单"维度**，可区分机构超大单 vs 一般大单，信号更精细。

---

### 2.5 历史 K 线：`request_history_kline("US.AAPL", ...)`

| 能力 | Futu | LongPort |
|---|---|---|
| 返回格式 | `pd.DataFrame` | `List[Candlestick]` 需转换 |
| 字段 | `time_key, open, close, high, low, volume, turnover, pe_ratio, turnover_rate, change_rate, last_close` | `timestamp, open, high, low, close, volume, turnover, trade_session` |
| **K 线内含 pe_ratio** | ✅ 每根 K 线含当时 PE | ❌ 无 |
| 盘前/盘后 | `extended_time=True` | `trade_sessions=TradeSessions.All` |
| 美股夜盘 | `session=Session.ALL`（注：不支持 Session.OVERNIGHT） | 同 |
| 分页支持 | ✅ `page_req_key` 翻页 | ❌ 单次最多 1000 根 |
| 月度额度限制 | ❌ **无** | ✅ **100~3000 标的/月** |
| 数据起始时间 | 更早（待确认具体日期） | 2010-06-01 |

```python
ret, klines_df, page_req_key = quote_ctx.request_history_kline(
    "US.AAPL",
    start="2026-01-01",
    end="2026-05-14",
    ktype=KLType.K_DAY,
    autype=AuType.QFQ,          # 前复权（美股通常不复权也可）
    max_count=200,
    extended_time=False,         # 日线分析只用正式时段
)
# klines_df 已是标准 DataFrame，time_key 为字符串格式
```

**结论**：Futu 返回直接是 `pd.DataFrame`，**无需转换即可进入公共指标计算层**（只需列名映射 `time_key` 已一致）。且无月度额度限制，对高频扫描更友好。

---

## 3. 综合对比矩阵

| 数据项 | LongPort 方案 | Futu 方案 | 胜者 |
|---|---|---|---|
| 实时快照（基本字段） | `quote()` ✓ | `get_market_snapshot()` ✓ | 持平 |
| 总市值、流通市值 | `calc_indexes()` 额外调用 | 快照直出 | **Futu** |
| PE 静、PE TTM、PB | `calc_indexes()` 额外调用 | 快照直出 | **Futu** |
| 净利润 | ❌ 无 | `net_profit` 快照直出 | **Futu** |
| **PS TTM** | ❌ 无（均无法快照获取） | ❌ 快照无（需选股 API） | 持平（均无） |
| 收益率 EY | ❌ 无 | `ey_ratio` 快照直出 | **Futu** |
| 52周高/低、历史高/低 | ❌ 无 | 快照直出 | **Futu** |
| 盘前/盘后完整行情 | 部分字段 | 完整（价/量/幅） | **Futu** |
| 夜盘行情 | ❌ 无 | `overnight_*` 快照直出 | **Futu** |
| **板块/行业信息** | ❌ 无接口 | `get_owner_plate()` ✓ | **Futu** |
| **历史多日资金流（5/10/90日）** | ❌ 无 | `get_capital_flow(PeriodType.DAY)` ✓ | **Futu** |
| 特大单资金 | ❌ 无 | `capital_in_super` ✓ | **Futu** |
| 今日资金分布快照 | `capital_distribution()` ✓ | `get_capital_distribution()` ✓ | 持平 |
| 历史 K 线 | `history_candlesticks_by_date()` ✓ | `request_history_kline()` ✓ | **Futu**（无月度额度限制） |
| K 线月度标的额度 | 100~3000/月（限制） | **无限制** | **Futu** |
| 调用方式 | 纯云端 async | 本地 FutuOpenD + 同步 | **LongPort**（运维更简单） |
| 代码格式 | `AAPL.US` | `US.AAPL` | 需适配 |

---

## 4. Futu 美股 fundamental_data 输出定义（对标 LongPort §8.1）

有了 Futu 数据，`fundamental_data` 可以填充的字段**显著增多**：

```json
{
  "name": "苹果",
  "currency": "USD",
  "total_shares": "1.50亿股",
  "circulating_shares": "1.50亿股",
  "total_market_val": "2.83万亿",
  "circular_market_val": "2.83万亿",
  "net_asset": "667.58亿",
  "net_profit": "913.34亿（快照直出）",
  "earning_per_share": "6.08",
  "net_asset_per_share": "4.44",
  "pe_ratio": "30.98（PE静，快照直出）",
  "pe_ttm": "29.90（快照直出）",
  "pb_ratio": "42.39（快照直出）",
  "ps_ttm": "无数据（快照不含，需选股 API）",
  "ey_ratio": "1.42（收益率，Futu 独有）",
  "dividend_ratio_ttm": "0.53%",
  "plate_info": "科技、硬件设备（get_owner_plate 支持美股）",
  "capital_flow": {
    "flow_5d": {
      "main_in_flow": "XX万",
      "total_in_flow": "XX万",
      "flow_status_tag": "主力持续净流入"
    },
    "flow_10d": {...},
    "flow_90d": {...},
    "flow_status_tag": "主力持续净流入"
  }
}
```

**与 LongPort 方案对比**：
- 不再需要"无数据"的字段从 6 个（板块、PE静、流通市值、净资产、净利润、EY）降至 **1 个**（ps_ttm）。
- `capital_flow` 从"仅今日快照"升级为**完整 5/10/90 日历史汇总**，与港股 Futu 方案对称。

---

## 5. Futu 美股短期记忆 `short_memory` 增量

| 字段 | LongPort | Futu |
|---|---|---|
| `smart_net_wan`（主力净流） | 今日快照单值 | **10日历史累计值**（`main_in_flow` 日级聚合） |
| `retail_net_wan`（散户净流） | 今日快照单值 | **10日历史累计值**（`sml_in_flow + mid_in_flow` 聚合） |
| 特大单净流 | ❌ 无 | `super_in_flow` 可纳入分析 |
| 语义准确性 | "今日快照"（非真正的10日窗口） | **真正的10日窗口累计**（与港股语义一致） |

**直接影响**：`build_short_term_memory` 中 `smart_net_wan` / `retail_net_wan` 的语义，Futu 版与港股版**完全等价**，无需在 Prompt 中加特殊说明。

---

## 6. 字段映射表（Provider 层参考）

```python
# ============================================================
# Futu get_market_snapshot → snapshot（美股）
# ============================================================
snap = snapshot_df.iloc[0].to_dict()

snapshot["name"]                  = snap["name"]
snapshot["last_price"]            = float(snap["last_price"])
snapshot["prev_close"]            = float(snap["prev_close_price"])
snapshot["open"]                  = float(snap["open_price"])
snapshot["high"]                  = float(snap["high_price"])
snapshot["low"]                   = float(snap["low_price"])
snapshot["volume"]                = int(snap["volume"])
snapshot["turnover"]              = float(snap["turnover"])
snapshot["change_rate"]           = (snapshot["last_price"] - snapshot["prev_close"]) / snapshot["prev_close"]

# 估值（快照直出，无需 calc_indexes）
snapshot["total_shares"]          = int(snap["issued_shares"])
snapshot["circulating_shares"]    = int(snap["outstanding_shares"])
snapshot["total_market_val"]      = float(snap["total_market_val"])
snapshot["circular_market_val"]   = float(snap["circular_market_val"])
snapshot["net_asset"]             = float(snap["net_asset"])
snapshot["net_profit"]            = float(snap["net_profit"])
snapshot["earning_per_share"]     = float(snap["earning_per_share"])
snapshot["net_asset_per_share"]   = float(snap["net_asset_per_share"])
snapshot["pe_ratio"]              = float(snap["pe_ratio"])         # PE 静
snapshot["pe_ttm"]                = float(snap["pe_ttm_ratio"])
snapshot["pb"]                    = float(snap["pb_ratio"])
snapshot["ey_ratio"]              = float(snap["ey_ratio"])
snapshot["dividend_ratio_ttm"]    = float(snap["dividend_ratio_ttm"])
snapshot["turnover_rate"]         = float(snap["turnover_rate"])
snapshot["volume_ratio"]          = float(snap["volume_ratio"])
snapshot["ps_ttm"]                = None  # 快照无此字段，保持与 LongPort 一致

# 盘前/盘后/夜盘（美股独有）
snapshot["pre_price"]             = snap.get("pre_price")
snapshot["pre_change_rate"]       = snap.get("pre_change_rate")
snapshot["after_price"]           = snap.get("after_price")
snapshot["after_change_rate"]     = snap.get("after_change_rate")
snapshot["overnight_price"]       = snap.get("overnight_price")
snapshot["overnight_change_rate"] = snap.get("overnight_change_rate")

# ============================================================
# Futu request_history_kline → klines_df
# 列名已与公共层约定一致（time_key, open, close, high, low, volume, turnover）
# ============================================================
# klines_df 可直接传入 build_short_window_indicator / build_mid_term_trend

# ============================================================
# Futu get_capital_flow(PeriodType.DAY) → flow_df
# ============================================================
# 复用 _aggregate_hk_capital_flow_from_df 逻辑（列名需映射）
# main_in_flow → 主力大单净流入
# in_flow     → 整体净流入
```

---

## 7. 代码格式适配（`US.AAPL` vs `AAPL.US`）

Futu 与 LongPort 代码格式相反，Provider 层需做转换：

```python
def futu_to_standard(futu_code: str) -> str:
    """US.AAPL → AAPL.US"""
    if "." in futu_code:
        market, ticker = futu_code.split(".", 1)
        return f"{ticker}.{market}"
    return futu_code

def standard_to_futu(standard_code: str) -> str:
    """AAPL.US → US.AAPL"""
    if "." in standard_code:
        ticker, market = standard_code.rsplit(".", 1)
        return f"{market}.{ticker}"
    return standard_code
```

---

## 8. 落地建议（与 LongPort 方案对比）

### 8.1 使用 Futu 的推荐场景

1. **已有 FutuOpenD 本地部署**（Futu 港股已在跑）：直接复用同一 OpenD 实例，成本最低。
2. **需要完整资金流历史（5/10/90日）**：LongPort 无此接口，Futu 方案是唯一选择。
3. **需要板块/行业信息**：LongPort 无此接口，Futu `get_owner_plate` 支持美股。
4. **需要夜盘/完整盘前盘后行情**：Futu 快照字段更完整。
5. **标的数量多、扫描频繁**：Futu 无月度 K 线额度限制，LongPort 有瓶颈。

### 8.2 使用 LongPort 的推荐场景

1. **纯云端部署，无法运行本地 FutuOpenD**。
2. **只需最基础的快照 + K 线 + 今日资金**，不需历史资金流。
3. **简洁 async 架构优先**，不希望引入同步调用包装层。

### 8.3 推荐：Futu 方案（US 市场）

| 结论 | 原因 |
|---|---|
| **数据完整度更高** | 历史资金流、板块、夜盘、净利润等字段在 LongPort 缺失 |
| **与港股 Futu 链路对称** | 同一套 `_aggregate_capital_flow`、`build_short_term_memory` 逻辑可直接复用 |
| **无月度 K 线额度约束** | 对监控列表较大时无瓶颈 |
| **代价** | FutuOpenD 本地运行依赖；代码格式需适配（`US.AAPL` ↔ `AAPL.US`） |

---

## 9. 数据缺口汇总（Futu 版）

| 数据项 | 状态 | 说明 |
|---|---|---|
| `ps_ttm` | ⚠️ 需额外调用 | 选股接口 `get_filter_stock_list` 可获取，但增加复杂度；当前方案标记"无数据" |
| 历史多日资金流 | ✅ 完全支持 | `get_capital_flow(PeriodType.DAY)` |
| 板块信息 | ✅ 支持 | `get_owner_plate(["US.AAPL"])` |
| 夜盘行情 | ✅ 支持 | `overnight_*` 字段 |
| FutuOpenD 依赖 | ⚠️ 运维约束 | 需保证 OpenD 本地进程稳定运行 |
| 代码格式差异 | ⚠️ 需适配 | Provider 层转换，对上层透明 |

---

## 10. `generate_us_single_stock_report` 接口设计

> **目标**：在 `src/services/llm_analyst.py` 中新增 `generate_us_single_stock_report`，与已有的 `generate_hk_single_stock_report` 对称，支持通过 Web API / 手动触发 对单只美股生成深度研报并推送飞书。

---

### 10.1 方法签名

```python
async def generate_us_single_stock_report(
    self,
    symbol_input: str,           # 支持 AUR / AUR.US / US.AUR 三种格式
    trigger_type: str = "MANUAL",
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
    enable_grounded_search: bool = True,
) -> Dict[str, Any]:
    """Generate single-stock deep analysis report for US symbols (Futu data source)."""
```

返回结构与 `generate_hk_single_stock_report` 完全一致：
```python
{"ok": bool, "symbol": str, "title": str | None, "report": str | None, "error": str | None}
```

---

### 10.2 数据流水线（对标 HK 版本）

| 步骤 | HK 版本 | US 版本 |
|---|---|---|
| ① Symbol 解析 | `futu_client.parse_symbol_input(symbol_input)` | `parse_us_symbol(symbol_input)` → `US.TICKER` |
| ② 实时快照 | `futu_client.get_special_quotes([hk_symbol])` | `futu_client.get_special_quotes([us_symbol])` |
| ③ 历史 K 线 | `futu_client.get_hk_historical_klines(symbol, max_days)` | `futu_client.get_historical_klines(us_symbol, max_days)` |
| ④ 历史资金流 | `futu_client.get_capital_flow(symbol)` (盘中分布) | `futu_client.get_capital_flow_history(us_symbol, 90)` (90日历史日级) |
| ⑤ 基本面数据 | `build_hk_fundamental_data(symbol, stock, (5,10,90))` | `build_us_fundamental_data(us_symbol, stock, (5,10,90))` |
| ⑥ 短期记忆 | `build_short_term_memory(klines_df, stock, capital_data)` | `us_indicator.build_short_term_memory(klines_df, stock, capital_data)` |
| ⑦ 中期趋势 | `build_mid_term_trend(klines_df, price)` | `us_indicator.build_mid_term_trend(klines_df, price)` |
| ⑧ Prompt 构建 | `self._build_single_stock_prompt(...)` | `self._build_us_single_stock_prompt(...)` |
| ⑨ LLM 调用 | `self._call_llm_with_retry(prompt, grounded=True)` | 同左，复用 Gemini Grounded Search |
| ⑩ 推送 | `FeishuAlert.send_alert(title, full_report)` | 同左 |

**关键差异**：
- US 使用 `get_capital_flow_history`（历史日级多窗口），HK 用 `get_capital_flow`（盘中分布快照）
- US Prompt 多出【盘前/盘后/夜盘行情】段落
- US Prompt 公理体系为**三大公理**（见 §10.4），HK 为四大公理

---

### 10.3 代码骨架

```python
async def generate_us_single_stock_report(
    self,
    symbol_input: str,
    trigger_type: str = "MANUAL",
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
    enable_grounded_search: bool = True,
) -> Dict[str, Any]:
    from src.api.futu.client import futu_client
    from src.analysis.us_single_stock_indicator import (
        build_us_fundamental_data,
        build_short_term_memory,
        build_mid_term_trend,
    )

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        # ① 解析为 Futu 原生格式 US.TICKER
        futu_symbol = futu_client.parse_us_symbol_input(symbol_input)
        if not futu_symbol:
            msg = "未匹配到有效美股代码（支持 AUR / AUR.US / US.AUR）"
            return {"ok": False, "symbol": symbol_input, "title": None, "report": None, "error": msg}

        standard_symbol = futu_symbol.split(".", 1)[1] + ".US"  # US.AUR → AUR.US

        # ② 快照
        snapshot_list = await asyncio.to_thread(futu_client.get_special_quotes, [futu_symbol])
        if not snapshot_list:
            return {"ok": False, "symbol": standard_symbol, "title": None, "report": None,
                    "error": "未获取到股票快照数据，请确认代码或行情权限。"}

        stock = snapshot_list[0]
        price = float(stock.get("last_price", 0.0))
        stock_name = str(stock.get("name", "") or "").strip()
        symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol

        # ③ K 线 + ④ 历史资金流（并发）
        klines_task = asyncio.to_thread(
            futu_client.get_historical_klines, futu_symbol, max(lookback_days_mid + 30, 120)
        )
        capital_task = asyncio.to_thread(futu_client.get_capital_flow_history, futu_symbol, 90)
        klines_df, capital_data = await asyncio.gather(klines_task, capital_task)

        if klines_df is None or klines_df.empty:
            return {"ok": False, "symbol": standard_symbol, "title": None, "report": None,
                    "error": f"未获取到 {standard_symbol} 历史K线数据。"}

        # ⑤⑥⑦ 三模块（基本面、短期、中期）
        short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
        mid_trend    = build_mid_term_trend(klines_df, price, lookback_days_mid)
        fundamental_data = await asyncio.to_thread(
            build_us_fundamental_data, futu_symbol, stock, (5, 10, 90)
        )

        # ⑧ Prompt
        prompt = self._build_us_single_stock_prompt(
            symbol_for_prompt, current_time, fundamental_data, short_memory, mid_trend
        )

        # ⑨ LLM（Gemini Grounded Search）
        report_content = await self._call_llm_with_retry(prompt, enable_grounded_search=enable_grounded_search)
        if not report_content:
            raise ValueError("LLM生成报告失败（3次重试后仍不满足完整性校验）")

        # ⑩ 飞书推送
        full_report = (
            f"🦅 **Gemini 美股单股深度研报** | {standard_symbol} | {current_time}\n\n"
            f"---\n\n{report_content}\n\n---\n\n"
            f"📊 **数据窗口**：短期{lookback_days_short}天 | 中期{lookback_days_mid}天\n"
            f"🔔 **触发类型**：{trigger_type}\n"
            f"🧠 **AI模型**：{self.us_model}"
        )
        title = f"[美股单股深度研报] {standard_symbol} ({current_time})"
        await FeishuAlert.send_alert(title, full_report)

        return {"ok": True, "symbol": standard_symbol, "title": title, "report": full_report, "error": None}

    except Exception as e:
        logger.error(f"[Gemini/US-SingleStock] failed for {symbol_input}: {e}", exc_info=True)
        await FeishuAlert.send_alert(
            f"[美股单股研报错误] {symbol_input} ({current_time})",
            f"❌ 分析失败：{str(e)}"
        )
        return {"ok": False, "symbol": symbol_input, "title": None, "report": None, "error": str(e)}
```

---

### 10.4 Prompt 设计（`_build_us_single_stock_prompt`）

与 HK 版本的核心差异：

#### 10.4.1 新增数据段落

**【盘前/盘后/夜盘行情（美股独有）】**（Futu 独有字段，LongPort 缺失）：
```
- 盘前价/涨跌幅：{pre_price} / {pre_change_rate}
- 盘后价/涨跌幅：{after_price} / {after_change_rate}
- 夜盘价/涨跌幅：{overnight_price} / {overnight_change_rate}
```

**【基本面与估值快照】** 精简为以下字段（科技股估值锚以 PS/PB 为主，去除冗余财务细项）：
```
- 所属板块
- 总市值 / 流通市值
- 总股本 / 流通股本
- 资产净值
- PB
- 52周高 / 52周低
```

#### 10.4.2 买方三大公理（替换 HK 四大公理）

> 适配美股科技股投资逻辑，去除"出海与全球化能力"（在美股场景不适用）和"东亚老龄化"（地域性过强），聚焦成长赛道、AI 定价与效率跃升。

| # | 公理 | 权重 | 说明 |
|---|---|---|---|
| 1 | **行业潜力与增长度** | 40% | 所在赛道是否处于高成长阶段、市场空间是否足够大（e.g. 无人驾驶汽车赛道预估市场规模超1万亿美金） |
| 2 | **AI产业层级与关联度** | 40% | 精准定位在 AI 产业链的位置：算力基建 Tier1 / 核心模型与强关联组件 Tier2 / 深度赋能 Tier3 / 边缘辅助应用 Tier4，只有 Tier1-3 才能享受高赔率期权溢价 |
| 3 | **物理世界运转效率跃升** | 20% | 降本增效的直接受益者 |

评分规则：
- 不符合任何一条 → 直接给出**"不予买入"**结论
- 同时满足公理1+2（双核驱动）→ 给予极高溢价，**大幅上调**中长期评分

#### 10.4.3 完整 Prompt 结构

```
【报告时间】
【标的】
【基本面与估值快照】  ← US 版比 HK 版多：净利润、EY、52周高低、历史高低
【盘前/盘后/夜盘行情（美股独有）】  ← 新增
【筹码与流动性档案】  ← 同 HK 版
【短期记忆（近10日）】  ← 同 HK 版
【中期趋势（近90日）】  ← 同 HK 版

请按以下结构输出（Markdown）：
1. 核心结论（量化综合做多指数 X/100）
2. 基本面与估值透视（买方三大公理映射 + PS 对标 + 资金研判）
3. 技术面证据链
4. 交易计划
5. 核心风险/证伪条件
6. 联网检索证据
```

---

### 10.5 Web API 接入点

需在 `src/web/app.py` 新增路由，与 HK 版对称：

```python
@app.route('/api/us_single_stock_report', methods=['POST'])
async def trigger_us_single_stock_report():
    """Generate single-stock US report by symbol from frontend."""
    payload = request.get_json(silent=True) or {}
    symbol = (payload.get('symbol') or '').strip()
    if not symbol:
        return jsonify({'status': 'error', 'message': 'symbol 不能为空'}), 400

    result = await llm_analyst.generate_us_single_stock_report(
        symbol_input=symbol,
        trigger_type='MANUAL',
    )
    if result.get('ok'):
        return jsonify({
            'status': 'success',
            'symbol': result.get('symbol'),
            'title': result.get('title'),
            'report': result.get('report'),
        }), 200
    return jsonify({
        'status': 'error',
        'message': result.get('error') or '美股单股研报生成失败',
        'symbol': result.get('symbol'),
    }), 500
```

---

### 10.6 `futu_client` 新增接口需求

| 接口 | 状态 | 说明 |
|---|---|---|
| `parse_us_symbol_input(symbol_input)` | ⚠️ 需新增 | 对标 `parse_symbol_input`（HK），支持 AUR/AUR.US/US.AUR 三种格式，统一返回 `US.TICKER` |
| `get_historical_klines(us_symbol, days)` | ✅ 已有 | 现有 `get_hk_historical_klines` 底层调用 `request_history_kline`，需确认 US 市场代码能直通（`US.AAPL` 格式） |
| `get_capital_flow_history(us_symbol, 90)` | ✅ 已有 | `src/api/futu/client.py` 已实现 |

---

### 10.7 实施顺序

1. `futu_client.py` — 新增 `parse_us_symbol_input` 方法
2. `llm_analyst.py` — 将 `generate_us_single_stock_report` 的 `raise NotImplementedError` 替换为完整实现（参照 §10.3 骨架）
3. `src/web/app.py` — 新增 `/api/us_single_stock_report` 路由（参照 §10.5）
4. 手动运行 `scripts/generate_us_single_stock_prompt.py NVDA` 验证 Prompt 输出格式正确后，再接入 LLM
