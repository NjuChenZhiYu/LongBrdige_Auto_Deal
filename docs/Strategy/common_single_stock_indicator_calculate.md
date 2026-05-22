# 单股指标公共计算层设计（Common + Futu + LongPort）

## 1. 背景

当前 `src/analysis/futu_math_indicator.py` 已包含较完整的短期/中期分析能力，但同时混合了三类职责：

1. **纯数学计算**（可跨市场复用）
2. **特征组装**（可跨市场复用）
3. **数据源依赖**（Futu 专属，如 `futu_client.analyze_capital_flow`）

这会导致：

- 想复用 `build_short_term_memory` / `build_mid_term_trend` 到 LongPort 时，耦合较高。
- 市场切换成本高，方法边界不清晰。

你的方向是对的：应先抽离公共方法，再分别保留 Futu / LongPort 的市场适配层。

---

## 2. 纠偏建议（先结论）

你提出的“抽离 `classify_mid_shape`、tag 计算、`calculate_max_contiguous_drop_pct` 到公共模块”是正确方向，但有两点建议补充：

1. **不要直接复制 `build_short_term_memory` 和 `build_mid_term_trend` 到两套文件**。  
   这两个函数属于“编排层（orchestration）”，会调用市场数据和资金流标签，直接复制会形成双份逻辑漂移。

2. **先抽“纯函数 + 标准输入 DataFrame”**，再让 Futu 与 LongPort 的编排层复用。  
   也就是：
   - `single_stock_math_calculate.py`：纯数学与通用特征，不依赖外部 API。
   - `futu_stock_indicator.py`：Futu 数据编排与字段映射。
   - `longport_stock_indicator.py`：LongPort 数据编排与字段映射。

---

## 3. 模块分层设计（与当前 futu_math_indicator 对齐）

建议在 `src/analysis/` 下形成三层：

```text
src/analysis/
  single_stock_math_calculate.py        # 公共纯函数层（新增）
  single_stock_feature_builder.py       # 公共特征组装层（可选新增）
  futu_stock_indicator.py               # Futu 编排层（由 futu_math_indicator 拆出）
  longport_stock_indicator.py           # LongPort 编排层（新增）
  futu_math_indicator.py                # 过渡期兼容入口，逐步瘦身
```

### 3.1 公共计算层（single_stock_math_calculate.py）

只放“输入 DataFrame/Series -> 输出指标”的可复用计算函数，不 import `futu_client` / `longport client`：

- `extract_pivots`
- `classify_mid_shape`
- `calc_poc`
- `_calculate_max_contiguous_drop_pct`
- `_calculate_max_contiguous_up_pct`
- `_calculate_risk_metrics`
- `_build_short_window_price_distribute`
- `calculate_ema_derivatives`（建议后续拆为 `append_realtime_row + core`）
- `_safe_float`
- `_format_rt_time_label`

说明：

- 这一层允许包含“轻编排但无外部依赖”的函数，例如：
  - `build_short_window_indicator`
  - `build_mid_trade_features`
  - `build_current_day_indicator`

### 3.2 市场编排层（保留各自短/中期记忆构造）

- `futu_stock_indicator.py`（或过渡期继续保留在 `futu_math_indicator.py`）
  - 获取/消费 Futu 口径字段
  - 调用 `futu_client.analyze_capital_flow`、`calculate_hk_capital_flow_profiles`
  - 保留 Futu 自己的：
    - `build_short_term_memory`
    - `build_mid_term_trend`
    - `hk_basic_finance_data`

- `longport_stock_indicator.py`
  - 消费 LongPort 字段
  - 将 `capital_distribution` 的 `large/medium/small` 映射为主力/散户口径
  - 保留 LongPort 自己的：
    - `build_short_term_memory`（LongPort 版本）
    - `build_mid_term_trend`（LongPort 版本）
    - `build_longport_fundamental`
  - 复用 common 计算函数构建输出 `fundamental + short + mid`

---

## 4. LongPort 数据字段映射（按当前文档）

基于 `developers/docs/en/docs/quote/pull`：

1. `quote`（`quote_ctx.quote`）  
   - 关键字段：`last_done`, `open`, `high`, `low`, `volume`, `turnover`, `timestamp`

2. `static`（`quote_ctx.static_info`）  
   - 关键字段：`symbol`, `name_cn/name_en`, `currency`, `total_shares`, `circulating_shares`, `eps`, `eps_ttm`, `bps`, `dividend_yield`

3. `history-candlestick`（`quote_ctx.history_candlesticks_by_offset`）  
   - 关键字段：`open`, `high`, `low`, `close`, `volume`, `turnover`, `timestamp`

4. `capital-distribution`（`quote_ctx.capital_distribution`）  
   - 关键字段：`capital_in.large/medium/small`, `capital_out.large/medium/small`

统一转换后，建议输出标准 K 线 DataFrame 列：

- `time_key`, `open`, `high`, `low`, `close`, `volume`, `turnover`

补充建议：

- 将 LongPort `last_done` 统一映射为内部 `last_price`
- 将 LongPort `timestamp` 统一格式化为 `time_key`（`YYYY-MM-DD HH:MM:SS`）

---

## 5. 目标接口（统一输入，分市场实现）

### 5.1 通用输入对象

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional
import pandas as pd

@dataclass
class StandardStockData:
    symbol: str
    market: str  # HK / US
    snapshot: Dict[str, Any]
    klines_df: pd.DataFrame
    capital_df: Optional[pd.DataFrame]
    extra: Dict[str, Any]
```

### 5.2 通用输出对象

```python
{
  "fundamental": {...},
  "short_memory": {...},
  "mid_memory": {...}
}
```

---

## 6. 函数迁移建议（按当前 futu_math_indicator 实际函数）

> 迁移进度（2026-05-13）：
> 已完成 3 个低风险函数下沉到 `single_stock_feature_builder.py`，并由 `futu_math_indicator.py` import 转调，行为保持不变：
> - `calculate_tag_today_by_derivatives`（原 `_calculate_tag_today_by_derivatives`）
> - `empty_short_term_payload`（原 `_empty_short_term_payload`）
> - `prepare_short_term_dataset`（原 `_prepare_short_term_dataset`）

第一批（纯函数，优先迁移）：

- `calculate_ema_derivatives`
- `extract_pivots`
- `classify_mid_shape`
- `calc_poc`
- `_calculate_max_contiguous_drop_pct`
- `_calculate_max_contiguous_up_pct`
- `_calculate_risk_metrics`
- `_build_short_window_price_distribute`
- `build_short_window_indicator`
- `build_mid_trade_features`
- `build_current_day_indicator`
- `_safe_float`
- `_format_rt_time_label`

第二批（需要轻微改造再迁移）：

- `calculate_ema_derivatives` 的内部实现细拆（可选）  
  现状将 `current_price` 直接 append 到 `df`，建议提炼为：
  - `append_realtime_row(df, current_price)`（通用）
  - `calculate_ema_derivatives_core(df_with_rt)`（纯计算）

第三批（保留市场层，不进入 common）：

- `build_short_term_memory`（Futu 资金流依赖）
- `build_mid_term_trend`（最终摘要文本与模式规则由市场层控制）
- `hk_basic_finance_data`（HK 专属字段）
- `calculate_hk_capital_flow_profiles`（HK 专属远端请求）

---

## 7. longport_stock_indicator.py 设计草案（保持“各自记忆构造”）

建议包含以下函数：

1. `normalize_longport_klines(candles) -> pd.DataFrame`
2. `build_longport_fundamental(quote_obj, static_obj) -> dict`
3. `build_longport_capital_profile(capital_dist_obj) -> dict`
4. `build_short_term_memory(standard_data, lookback_days_short=10) -> dict`（LongPort 版本）
5. `build_mid_term_trend(standard_data, lookback_days_mid=90) -> dict`（LongPort 版本）
6. `build_longport_single_stock_payload(...) -> dict`

其中 4/5 必须调用 common 层：

- `build_short_window_indicator`
- `build_mid_trade_features`
- `calculate_ema_derivatives`

---

## 8. 重构步骤（先文档后代码）

### Step 1（低风险）

- 新建 `single_stock_math_calculate.py`
- 将第一批纯函数迁移过去
- `futu_math_indicator.py` 先改为 import 转调，确保行为不变
- 已完成（本轮）：`_calculate_tag_today_by_derivatives` / `_empty_short_term_payload` / `_prepare_short_term_dataset`
  已迁移到 `single_stock_feature_builder.py`，`futu_math_indicator.py` 改为转调 common 实现

### Step 2（中风险）

- 新建 `longport_stock_indicator.py`
- 完成 LongPort 字段标准化与基础面映射
- 接入 common 层短/中期计算

### Step 3（收敛）

- 将 `futu_math_indicator.py` 逐步瘦身为 Futu 编排层
- 增加跨市场一致性测试（同构输入下计算结果一致）

---

## 9. 验收标准（DoD）

1. `single_stock_math_calculate.py` 不依赖 Futu/LongPort client。
2. LongPort 与 Futu 都能输出统一结构：`fundamental + short_memory + mid_memory`。
3. 公共函数单测覆盖以下关键逻辑：
   - 形态识别（`classify_mid_shape`）
   - 连续最大涨跌幅（`_calculate_max_contiguous_*`）
   - 短窗筹码分布（`_build_short_window_price_distribute`）
4. Futu 与 LongPort 各自保留短/中期记忆构造函数，仅共享 common 计算层。
5. `futu_math_indicator.py` 能逐步瘦身为过渡兼容层，但不改变当前产出字段语义。

---

## 10. 对 `us_single_stock_deep_analyze.md` 的后续改动建议

在本文件完成后，`us_single_stock_deep_analyze.md` 建议同步更新三点：

1. 明确引用 `single_stock_math_calculate.py` 作为公共计算层。
2. 明确 `longport_stock_indicator.py` 为 US 市场实现。
3. 删除“直接复用 `futu_math_indicator.py` 全文件”的描述，改为“复用 common 层函数 + 市场编排层”。

---

## 11. 当前共识（与你的理解一致）

你的核心判断是正确的：  
“`build_short_term_memory` / `build_mid_term_trend` 不直接硬共用，实现层各自保留；真正共用的是计算函数层。”

推荐最终形态是：

- **common 负责算（公有计算函数）**
- **futu/longport indicator 各自负责短中期记忆构造**
- **service 负责流程编排**

这样才能同时兼容 Futu 与 LongPort，并且后续再扩 A 股/美股/港股时不再重复造轮子。

---

## 12. 补充建议（建议落地）

### 12.1 增加“字段契约表”（强烈建议）

建议在本方案中固定一份 `StandardStockData` 字段契约，避免后续 LongPort/Futu 各自改字段导致隐性 bug：

- `snapshot.last_price`：统一为 `float`，单位“价格原单位”
- `klines_df.time_key`：统一 `YYYY-MM-DD HH:MM:SS` 字符串或 `datetime64[ns]`（二选一，项目内固定）
- `klines_df.open/high/low/close`：统一 `float`
- `klines_df.volume`：统一 `float`（避免 int/str 混用）
- `klines_df.turnover`：统一 `float`
- `capital_df`：统一保留 `in/out` 原始字段 + 映射后字段（如 `main_net`, `retail_net`）

补充：建议在 provider 层新增 `validate_standard_df(df)`，对列存在性与 dtype 做一次统一校验。

### 12.2 增加“单位与口径约束”

目前各接口可能有“元/万/亿”“股/手”“百分比是否带 `%`”差异，建议明确：

- `*_pct` 结尾字段：统一为数值（不带 `%` 符号）
- 资金字段：内部计算统一“原始货币金额”，展示层再格式化“万/亿”
- 时间窗字段：统一用交易日计数，不混用自然日

这样可以避免同一指标在 HK/US 结果不可比。

### 12.3 增加“黄金样本回归测试”

建议为 common 层建立固定样本（CSV 或 JSON）回归：

1. 准备 3 组样本：趋势上行、趋势下行、震荡箱体。
2. 固定输入 `klines_df + current_price`，校验关键输出：
   - `tag_today`
   - `max_cum_drop_10d_pct`
   - `shape`
   - `poc_range/poc_ratio_pct`
3. 每次重构后跑快照对比（允许设置小阈值，例如 `1e-6` 量级浮动）。

目的：防止“看似重构，实则指标漂移”。

### 12.4 增加“迁移开关”（灰度切换）

从 `futu_math_indicator.py` 拆到 common 后，建议加配置开关：

- `ENABLE_COMMON_INDICATOR_V2 = false/true`
- `false`：走旧路径
- `true`：走 common 新路径

并在日志中打出：

- `indicator_path=legacy|common_v2`
- `symbol`, `market`, `window_used`, `mode`

这样可以先小范围灰度，降低一次性切换风险。

### 12.5 明确“函数命名与职责边界”

建议统一命名规范，减少后续理解成本：

- `*_core`：纯计算，不依赖外部状态
- `build_*`：结构化组装，可依赖 DataFrame 但不做远程请求
- `compose_*` 或 `orchestrate_*`：市场编排层，可调用 client

例如：

- `calculate_ema_derivatives_core`（common）
- `build_mid_trade_features`（common）
- `orchestrate_futu_short_memory`（futu）
- `orchestrate_longport_mid_trend`（longport）

### 12.6 增加“异常与降级码”

当前降级多为自然语言描述，建议补一个机器可读状态码：

- `DATA_OK`
- `INSUFFICIENT_LT30`
- `MISSING_CAPITAL_FLOW`
- `MISSING_SNAPSHOT`
- `EMPTY_KLINES`

返回 payload 同时带：

- `status_code`
- `status_message`

便于 API 层、前端和任务调度统一处理。

### 12.7 文档同步策略

建议把本文件作为“架构总文档”，并增加一个简短“变更记录”段落，记录：

- 哪些函数已迁移到 common
- 哪些函数仍在 futu 层
- longport 层已对齐到哪一版契约

这样多人协作时不会出现“代码和文档谁是最新”的歧义。

---

## 13. 实现级模板（可直接落代码）

## 13.1 StandardStockData 契约（建议版）

```python
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import pandas as pd


@dataclass
class StandardStockData:
    symbol: str                  # 例: HK.00700 / AAPL.US
    market: str                  # HK / US
    snapshot: Dict[str, Any]     # 至少包含 last_price
    klines_df: pd.DataFrame      # 至少包含 time_key, open, high, low, close, volume, turnover
    capital_df: Optional[pd.DataFrame] = None
    extra: Dict[str, Any] = field(default_factory=dict)
```
```

必填约束（最小集）：

- `snapshot.last_price`：`float`，无值时允许 fallback 到 `klines_df.close.iloc[-1]`
- `klines_df` 必须有：`time_key/open/high/low/close/volume/turnover`
- `klines_df` 按 `time_key` 升序
- `capital_df` 可为空，不应阻断短中期指标

## 13.2 validate_standard_df(df) 规范（建议版）

```python
import pandas as pd


REQUIRED_KLINE_COLUMNS = ("time_key", "open", "high", "low", "close", "volume", "turnover")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "turnover")


def validate_standard_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("EMPTY_KLINES")

    missing = [c for c in REQUIRED_KLINE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"MISSING_COLUMNS:{','.join(missing)}")

    out = df.copy()
    out["time_key"] = pd.to_datetime(out["time_key"], errors="coerce")
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["time_key", "close"]).sort_values("time_key").reset_index(drop=True)
    if out.empty:
        raise ValueError("INVALID_KLINES_AFTER_CLEAN")

    # high/low 兜底，防止脏数据破坏指标
    out["high"] = out[["high", "open", "close"]].max(axis=1)
    out["low"] = out[["low", "open", "close"]].min(axis=1)

    return out
```
```

校验失败状态码建议映射：

- `EMPTY_KLINES`
- `MISSING_COLUMNS:*`
- `INVALID_KLINES_AFTER_CLEAN`

## 13.3 Provider 输出模板（LongPort/Futu 统一）

```python
def build_standard_stock_data(...) -> StandardStockData:
    # 1) 拉取 quote/static/kline/capital
    # 2) 字段映射到统一列名
    # 3) validate_standard_df()
    # 4) 返回 StandardStockData
    ...
```
```

统一字段映射建议：

- LongPort `last_done` -> `snapshot.last_price`
- LongPort/Futu kline 时间戳 -> `time_key`
- 统一输出 `turnover`（若无则补 0.0）

## 13.4 迁移开关与埋点（实现模板）

配置项（`config/settings.py`）：

```python
ENABLE_COMMON_INDICATOR_V2 = False
```
```

服务层分流（示例）：

```python
if Settings.ENABLE_COMMON_INDICATOR_V2:
    indicator_path = "common_v2"
    # 调 common + market indicator
else:
    indicator_path = "legacy"
    # 调现有 futu_math_indicator
```
```

日志埋点建议（每次请求都打）：

- `indicator_path`
- `symbol`
- `market`
- `window_short/window_mid`
- `window_used_short/window_used_mid`
- `status_code`
- `elapsed_ms`

## 13.5 最小回归用例（建议先建 6 条）

1. HK 正常样本（90+ 天）
2. HK 压缩样本（30-89 天）
3. HK 不足样本（<30 天）
4. US 正常样本（90+ 天）
5. US 缺失资金流（`capital_df=None`）
6. 异常 K 线（缺列/时间脏数据，触发 `status_code`）

每条用例至少断言：

- `short_memory.short_window_incomplete`
- `mid_memory.mode`
- `mid_memory.shape`
- `summary_10d.max_cum_drop_10d_pct`
- 无异常抛出或抛出预期状态码
