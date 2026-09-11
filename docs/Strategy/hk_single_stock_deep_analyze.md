# 单一股票深度分析接口设计（Futu + LLM + Feishu）

## 1. 背景与目标

基于现有 `src/services/llm_analyst.py` 中 `generate_futu_hk_report` 的成熟链路，新增一个“单一股票深度分析”接口，支持：

1. 输入单个港股代码（如 `HK.00700`）。
2. 从 Futu 拉取该股票实时行情、资金流、历史 K 线等数据。
3. 按 `docs/single_stock_analyze.md` 的要求，将原始时序数据清洗为“语义化序列”（短期记忆 / 多周期趋势）。
4. 将标签化结果拼装为高质量 Prompt，调用大模型生成单股深度分析报告。
5. 将分析结果发送到 Feishu。

设计目标是“最小改动复用现有能力 + 可快速落地 + 可扩展到多市场或多模型”。

---

## 2. 参考现有实现（可复用资产）

### 2.1 服务层参考

- `LLMAnalyst.generate_futu_hk_report` 已具备完整流程：取数 -> 标签化 -> Prompt -> LLM 重试 -> Feishu 发送。
- 可复用的工程模式：
  - `asyncio.to_thread(...)` 调用同步 Futu API，避免阻塞事件循环。
  - 单标的并发拉取多类数据（资金流 + K 线）。
  - LLM 3 次重试 + 文本完整性校验（长度、结尾符号）。
  - 失败时发送错误通知到 Feishu。

### 2.2 数据层参考

- `src/api/futu/client.py`
  - `get_special_quotes(...)` / `get_threshold_quotes(...)`：快照行情思路可复用。
  - `get_capital_flow(symbol)`：资金流分布。
  - `get_hk_historical_klines(code, num_days)`：历史 K 线。
  - `analyze_capital_flow(capital_data, current_price_change)`：资金博弈标签（机构吸筹 / 机构出逃等）。
- `src/analysis/futu_math_indicator.py`
  - `calculate_ema_derivatives(df, current_price)`：一阶/二阶导 + Bias20 + 技术面标签，可作为短期记忆核心字段。

### 2.3 通知层参考

- `src/api/feishu.py` 中 `FeishuAlert.send_alert(title, content)` 可直接复用，无需新增通知通道。

---

## 3. 新接口设计

## 3.1 对外接口（服务层）

在 `src/services/llm_analyst.py` 新增：

```python
async def generate_single_stock_futu_report(
    self,
    symbol: str,
    trigger_type: str = "MANUAL",
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90  # 兼容旧参数，作为多周期中的核心窗口
    # lookback_days_anchor: int = 365  # 暂不启用：长周期锚点分析先关闭
) -> dict:
    ...
```

返回值建议统一结构：

```python
{
  "ok": True/False,
  "symbol": "HK.00700",
  "title": "...",
  "report": "...",
  "error": None or "error message"
}
```

说明：

1. `symbol` 必填，格式限制为 `HK.` 前缀（第一版先聚焦港股）。
2. `trigger_type` 用于日志与后续审计（`MANUAL`/`CRON`/`API`）。
3. 当前启用的窗口分别对应：
   - `10`：短期记忆窗口（近 10 个交易日高清快照）。
   - `30/90/180`：多周期趋势窗口，分别覆盖短中期、中期、半年级别趋势结构与位置判断。
4. 长周期锚点（原 `365/250`）暂不启用，待短期与多周期趋势效果验证后再恢复。
5. 标的展示建议统一为“代码 + 名称”，避免仅显示代码导致语义不完整。
   - 例如：`HK.02590 连连数字`
   - 服务层需在快照取数后优先提取名称字段（如 `name`），用于标题、Prompt 标的字段、前端返回值展示。

> Tip（输入简化，默认港股）：
> 面向未来触发式交互，用户输入应尽量简洁。前端/调用侧可仅输入 `02590` 或 `连连数字`，后台负责自动补全与解析为标准代码（如 `HK.02590`）后再进入分析流程。
> 建议解析优先级：`完整代码` > `纯数字代码` > `中文名称模糊匹配`。若命中多只标的，返回候选列表要求用户二次确认。

## 3.2 可选 API 层（若需 HTTP 调用）

若项目使用 FastAPI，可加一个薄路由：

```python
POST /api/v1/reports/futu/single-stock
{
  "symbol": "HK.00700",
  "trigger_type": "MANUAL"
}
```

路由仅做参数校验与调用 service，不承载业务逻辑。

---

## 4. 数据处理与“语义化序列”方案

核心原则：不把杂乱 K 线原样喂给模型，而是先转成机器可读、语义稳定的结构化记忆。
补充原则：短期强弱与区间统计必须使用 OHLC（开高低收）完整信息，尤其要纳入交易日 `high/low`，禁止仅以 `close` 单点比较替代区间波动。

## 4.1 数据拉取（串行校验）

针对单个 symbol 按“先快照、后补全”的顺序拉取与校验：

1. 实时与财务快照：价格、涨跌幅、昨收，以及基础估值（总市值、流通市值、市盈率（静）`pe_ratio`、市盈率 TTM `pe_ttm_ratio`、PB、净利润等）（复用 `get_market_snapshot([symbol])` 方式，字段名以 `docs/Futu-API-Doc-zh-Python.md` 为准）。
2. 历史 K 线：`get_hk_historical_klines(symbol, num_days)`，若为空则直接失败返回，不进入后续分析。
3. 资金流：`get_capital_flow(symbol)`（允许为空并降级）。
4. 历史 K 线窗口建议：
  - 短期：至少 30 天（保证 MACD 等指标 warm-up 后取近 10 天）。
  - 多周期趋势：至少覆盖 180 日窗口，并额外保留 warm-up 数据。
  - 长周期：目标 365 天（用于覆盖 250 日锚点）。
  - 大盘流动性：至少保留恒生指数、恒生科技指数、恒生生物科技指数各 180 个已完成交易日的 `turnover`，用于计算 5/30/90/180 日市场成交额基线。

建议一次拉取 `365 + warmup` 天，再切片，减少重复请求；但执行顺序上必须先确认 K 线可用，再进入指标构建。

## 4.2 清洗与特征工程

在服务内新增私有函数（或单独模块）：

```python
def _build_semantic_memory(klines_df, snapshot, capital_data) -> dict:
    ...
```

输出两层记忆（当前启用）：

### 实时价格拼接口径（Short / Multi-Window Trend 统一）

为避免指标停留在“前一交易日收盘价”，短期与多周期趋势都采用同一口径：

1. **Short (`build_short_term_memory`)**  
   - 历史基底：`get_hk_historical_klines`。  
   - 实时价来源：`snapshot.last_price`（无值时退化为最近收盘）。  
   - 处理方式：将实时价作为一条“RT 行”追加到序列末端，再计算 EMA/MACD/Bias 与 10 日统计。

2. **Multi-Window Trend (`build_mid_term_trend` / `build_multi_window_trends`)**  
   - 历史基底：`get_hk_historical_klines`。  
   - 实时价来源：服务层传入 `current_price`（来自实时快照）。  
   - 处理方式：同样将实时价作为末端样本追加后，按 `30/90/180` 三个窗口分别计算形态位置、POC、波动率、回撤、波峰波谷与均线状态。

结论：**Short 与 Multi-Window Trend 均以“当前价格”作为 Pandas 序列最后一个数据点，而不是前一交易日收盘价。**

### A) 短期记忆（近 10 个交易日）

短期策略不在本文重复维护，统一引用：

- `docs/short_trade_indicator.md`

约定：

1. `build_short_term_memory` 的字段定义、计算口径、降级策略以该文档为唯一标准。
2. 本文只声明“短期记忆模块存在并参与 Prompt”，不再展开短期公式与规则细节。
3. 若短期策略调整，仅更新 `docs/short_trade_indicator.md`，本文无需同步粘贴。

### B) 多周期趋势（30/90/180 日）

由规则引擎生成多窗口描述标签，示例：

- “近 30 日处于三角收敛末端”
- “近 90 日位于区间低位，仍跌破 20/60 日均线”
- “近 180 日显示半年级别高波动回撤，尚未形成趋势反转”
- “MACD 位于零轴上方并出现 2 次金叉”
- “近 20 天波动率下降，疑似变盘前压缩”

建议产出结构：

```json
{
  "window_trends": [
    {
      "window_days": 30,
      "mode": "FULL_30",
      "summary": "...",
      "poc_range": [17.6, 17.92],
      "poc_ratio_pct": 24.36,
      "volatility_pct": 59.47,
      "peaks": [19.03, 19.58],
      "troughs": [17.15, 17.32]
    }
  ],
  "summary": "90日核心窗口摘要（兼容旧字段）"
}
```

### C) 锚点记忆（长周期，暂不启用）

当前版本先关闭锚点记忆，避免过早引入长周期噪声。后续如需恢复，可启用 `MA250/年内高低点/成交密集区`。

### D) 基本面与估值特征（买方重构版）

完全采纳 `docs/Strategy/hk_basic_analyze.md` 当前策略：保留 Futu 的“标的自身快照 + 资金流”，废弃本地板块估值对比（`get_stock_filter` / `get_plate_stock`），行业对标改由 LLM 联网检索完成。

当前实现基于以下数据源：
- **标的快照**：`get_market_snapshot`（总/流通市值、总/流通股本、PB、PS、EPS、BPS、净资产、**市盈率 TTM**（`pe_ttm_ratio` → 结构化字段 `pe_ttm`）、**市盈率（静）**（`pe_ratio` → 结构化字段 `pe_static`）等）。
- **所属板块文本**：`get_owner_plate` 仅用于展示 `plate_info`（不参与行业估值计算）。
- **资金流分层**：`get_capital_flow` + `calculate_hk_capital_flow(window=5/10/90)`，输出短中长三段主力/整体净流。
- **行业相对估值**：通过 Prompt 中的“联网对标指令”由模型检索全球可比公司 PS，不再依赖本地板块中位数。

### E) 港股大盘流动性与交易热度

该指标衡量的是**港股大盘环境**，不是当前个股的成交活跃度。主数据源选择 Futu，第一版同时跟踪三个指数：

1. `HK.800000` 恒生指数：港股大盘与蓝筹流动性主锚。
2. `HK.800700` 恒生科技指数：科技成长板块及高弹性风险偏好。
3. `HK.800805` 恒生生物科技指数：创新药、生物科技等高风险成长方向的流动性。

当日数据通过一次 `get_market_snapshot(["HK.800000", "HK.800700", "HK.800805"])` 批量获取；历史数据分别调用 `request_history_kline(code, ktype=KLType.K_DAY, autype=AuType.NONE)`。同时保留各指数涨跌幅及可用的 `index_raise_count/index_fall_count/index_equal_count`，用于区分放量上涨、放量下跌及市场宽度。

实测三个指数的快照与历史 K 线均为 `volume=0`，但 `turnover` 有稳定数值，因此港股大盘热度**必须比较成交额，不能比较指数成交量**。指数成交额属于对应成分股集合的代理口径，不是港交所全市场精确总成交额。

三个指数的成分股可能重叠，严禁将三者 `turnover` 相加，否则会重复计算。每个指数必须独立与自身历史均值比较：

- 恒指热度回答“港股大盘有没有钱”。
- 恒科热度回答“科技成长有没有增量资金”。
- 恒生生物科技热度回答“高风险创新成长方向是否获得资金承接”。
- 最终输出三者的共振/分化状态，不用人为加总成一个虚假的全市场成交额。

Longport 可作为后备源：官方接口支持 `HSI.HK` 的 `quote` 与 `candlesticks/history_candlesticks`，K 线对象也声明了 `volume/turnover` 字段；但指数 `volume` 同样可能为 0，而且当前项目 Longport 客户端与已安装 SDK 的 `Config/create` 调用方式不兼容，实测连接令牌端点也不可达。因此第一版不把 Longport 放在主链路。

计算前将三个指数各自的历史 K 线按 `time_key` 升序排列，并排除当日未完成 K 线。对每个指数分别计算：

```text
avg_turnover(index, N) = 该指数最近 N 个已完成交易日 turnover 的算术平均值
turnover_ratio(index, N) = comparable_turnover_today(index) / avg_turnover(index, N)
N = 5, 30, 90, 180
```

其中：

1. `15:00` 前：当日成交尚未充分，统一使用上一完整交易日成交额作为 `comparable_turnover`，并从历史均值基线中排除该交易日。
2. `15:00` 后且快照 `data_date` 确认为当日：使用当日实际累计成交额，不进行线性投影，标记 `TODAY_CUMULATIVE_AFTER_1500`。
3. `16:00` 收盘后：使用当日最终成交额，标记 `CLOSED`。
4. 禁止使用 `current_turnover / elapsed_trading_fraction` 推算全天成交额，因为港股成交在开盘、午后和收盘竞价阶段分布不均，线性投影会造成明显失真。
5. 每个指数使用四周期加权值作为最终热度数值，近期窗口权重更高：

```text
weighted_heat_ratio(index)
  = turnover_ratio(index, 5)   × 40%
  + turnover_ratio(index, 30)  × 30%
  + turnover_ratio(index, 90)  × 20%
  + turnover_ratio(index, 180) × 10%
```

权重解释：

- 5 日占 40%：反映最近一周资金热度，快速识别当日相对近期是否继续放量。
- 30 日占 30%：反映约一个半月的主要成交中枢，降低单周异常扰动。
- 90 日占 20%：反映季度级别流动性环境。
- 180 日占 10%：提供半年结构锚点，避免长期低迷后的局部放量被低估。

最终将 `weighted_heat_ratio` 直接代入下方 `0.50/0.80/1.30/1.80` 阈值分级。四个原始周期比值仍须完整输出，便于识别“短期突发放量”与“中长期持续活跃”的差异。

若某窗口因样本不足不可用，按剩余可用权重重新归一化：

```text
weighted_heat_ratio = Σ(available_ratio × original_weight) / Σ(available_weight)
```

缺少 90 日或 180 日窗口时标记 `REDUCED_CONFIDENCE`；缺少 5 日或 30 日窗口时不生成加权热度，只输出 `INSUFFICIENT`。

6. 不对三个指数之间再设置权重，也不汇总三者成交额。跨指数结论只输出：
   - `全面共振升温`：三个指数自身热度均不低于“明显放量”。
   - `大盘与成长共振`：恒指、恒科放量，生物科技未放量。
   - `结构性科技行情`：恒科放量，但恒指未放量。
   - `结构性医药行情`：恒生生物科技放量，但恒指与恒科未放量。
   - `全面降温`：三个指数自身热度均为“明显缩量”或“流动性低迷”。
   - `整体常态`：三个指数加权热度均处于 `0.80 <= ratio < 1.30`。
   - `明显分化`：不满足以上模式时，直接描述各指数差异。

统一分级：

- `>= 1.80`：极度活跃
- `1.30 <= ratio < 1.80`：明显放量
- `0.80 <= ratio < 1.30`：常态成交
- `0.50 <= ratio < 0.80`：明显缩量
- `< 0.50`：流动性低迷

建议结构化输出：

```json
{
  "source": "FUTU",
  "market_proxies": ["HK.800000", "HK.800700", "HK.800805"],
  "metric": "turnover",
  "is_intraday": true,
  "confidence": "NORMAL",
  "indices": {
    "HK.800000": {
      "name": "恒生指数",
      "current_turnover": 228512338234.79,
      "ratios": {"5": 1.24, "30": 1.37, "90": 1.49, "180": 1.58},
      "weighted_heat_ratio": 1.36,
      "heat_level": "明显放量"
    },
    "HK.800700": {
      "name": "恒生科技指数",
      "current_turnover": 67926821954.0,
      "ratios": {"5": 1.18, "30": 1.42, "90": 1.55, "180": 1.61},
      "weighted_heat_ratio": 1.37,
      "heat_level": "明显放量"
    },
    "HK.800805": {
      "name": "恒生生物科技指数",
      "current_turnover": 11223916093.0,
      "ratios": {"5": 0.92, "30": 1.08, "90": 1.16, "180": 1.21},
      "weighted_heat_ratio": 1.05,
      "heat_level": "常态成交"
    }
  },
  "cross_index_state": "大盘与成长共振",
  "summary": "恒指与恒科成交额明显放大，生物科技维持常态，资金主要向大盘蓝筹与科技成长扩散"
}
```

样本不足时按每个指数的实际交易日计算并输出 `actual_days_N`；任一指数少于 30 个完整交易日时，该指数标签降级为 `LOW_CONFIDENCE`，跨指数结论需明确指出缺失项。

## 4.3 样本不足补偿机制（必须实现）

为避免新股或次新股因为历史数据不足导致分析不可用，需引入分层补偿：

1. **长周期锚点补偿（250 日不足）**
   - 若 `available_days >= 250`：正常计算 `MA250`、年内锚点。
   - 若 `90 <= available_days < 250`：降级为 `MA90` 作为中长期价值中枢，并标注 `anchor_mode=MA90_FALLBACK`。
   - 若 `10 <= available_days < 90`：降级为 `MA10 + 区间高低点` 作为临时锚点，并标注 `anchor_mode=MA10_RANGE_FALLBACK`。
   - 若 `available_days < 10`：仅输出“数据不足”+ 实时快照，不给出锚点交易建议。

1. **多周期趋势补偿（30/90/180 日不足）**
   - 每个窗口独立计算 `mode`：样本满足目标窗口输出 `FULL_xx`，样本达到半数或 20 日以上输出 `REDUCED_xx`，更少则输出 `INSUFFICIENT`。
   - 30 日窗口优先保证近期形态可用；90 日窗口作为核心趋势字段兼容旧 prompt；180 日窗口用于识别半年级别位置与回撤。
   - 若任一关键窗口非 `FULL_xx`，Prompt 必须显式提示该周期不确定性，避免把压缩样本误读为完整趋势。

2. **短期记忆补偿（10 日不足）**
   - 目标窗口固定为 10 个交易日。
   - 若不足 10 日，按可用天数输出，并在 Prompt 显式声明 `short_window_incomplete=true`。

---

## 5. Prompt 设计（标签化输入）

## 5.1 Prompt 结构

建议模板：

1. 角色设定：港股量化深度分析师。
2. 输入数据声明：以下数据来自 Futu，已做语义清洗。
3. 核心数据块：
  - `【基本面与估值快照】`
  - `【港股大盘流动性与交易热度】`
  - `【短期记忆】`
  - `【多周期趋势与位置】`
4. 分析任务：
  - 基本面与中长期推演：结合估值数据与内置知识，分析公司质地、产业景气度及安全边际。
  - 趋势判断（短中长一致性）。
  - 主力/散户博弈识别。
  - 当前所处交易阶段（启动、加速、派发、探底等）。
  - 明确交易建议（触发条件、失效条件、风控位）。
  - 极端场景风控滤网：必须给出 1 条“非结构化证伪条件”（非价格/均线/止损触发），用于防止线性外推。

短期块字段与口径统一参考 `docs/short_trade_indicator.md`。

## 5.2 Prompt 示例骨架

```text
你是港股量化深度分析师。请基于下述“结构化历史记忆档案”分析单一标的：{symbol}

【基本面与估值快照】
所属板块：{plate_info}
总市值：{total_market_val}，流通市值：{circular_market_val}
总股本：{issued_shares}，流通股本：{outstanding_shares}
资产净值：{net_asset}，每股盈利(EPS)：{earning_per_share}，每股净资产(BPS)：{net_asset_per_share}
PB：{pb_ratio}
市盈率TTM：{pe_ttm}
市盈率（静）：{pe_static}

【筹码与流动性档案】
近5日资金：主力大单净流入 {main_in_flow_5d}，整体净流 {total_in_flow_5d}
近10日资金：主力大单净流入 {main_in_flow_10d}，整体净流 {total_in_flow_10d}
近90日资金：主力大单净流入 {main_in_flow_90d}，整体净流 {total_in_flow_90d}
当前盘口定性：{flow_status_tag}

【港股大盘流动性与交易热度】
统计口径：指数成交额代理，不是港交所全市场精确总额；三个指数成交额不相加
恒生指数：当日成交额 {hsi_turnover}；相对5/30/90/180日均额 {hsi_ratio_5}/{hsi_ratio_30}/{hsi_ratio_90}/{hsi_ratio_180}；加权热度值 {hsi_weighted_heat_ratio}；热度 {hsi_heat_level}
恒生科技指数：当日成交额 {hstech_turnover}；相对5/30/90/180日均额 {hstech_ratio_5}/{hstech_ratio_30}/{hstech_ratio_90}/{hstech_ratio_180}；加权热度值 {hstech_weighted_heat_ratio}；热度 {hstech_heat_level}
恒生生物科技指数：当日成交额 {hshkbio_turnover}；相对5/30/90/180日均额 {hshkbio_ratio_5}/{hshkbio_ratio_30}/{hshkbio_ratio_90}/{hshkbio_ratio_180}；加权热度值 {hshkbio_weighted_heat_ratio}；热度 {hshkbio_heat_level}
跨指数状态：{cross_index_state}
市场流动性结论：{market_liquidity_summary}

【实时快照】
...

【短期记忆（近10日语义化序列）】
...

【多周期趋势与位置】
    - 30日：{summary} POC={poc_range}，POC占比={poc_ratio_pct}%，年化波动={volatility_pct}%，波峰={peaks}，波谷={troughs}
    - 90日：{summary} POC={poc_range}，POC占比={poc_ratio_pct}%，年化波动={volatility_pct}%，波峰={peaks}，波谷={troughs}
    - 180日：{summary} POC={poc_range}，POC占比={poc_ratio_pct}%，年化波动={volatility_pct}%，波峰={peaks}，波谷={troughs}

请按以下结构输出（Markdown）：
1. 核心结论（先给方向，40-80字）
2. 基本面与估值透视（中长期推演，250-300字）
    * 严禁单纯罗列数据，必须穿透财务快照形成定价逻辑。
    * 【买方四大公理映射】：必须审视标的业务契合了以下哪几条底层公理，并据此定性资产属性（防御型现金奶牛 vs 进攻型高爆发成长）。公理存在权重差异：1.出海与全球化能力(40%，即中外剪刀差：成本RMB化，收益外汇化，这是硬科技公司活下去的首要条件)；2.AI产业层级与关联度(30%，精准定位标的在AI产业链上下游传导的位置，区分是算力基建Tier1/核心模型与强关联组件Tier2/深度赋能Tier3，还是仅仅作为辅助工具的边缘应用Tier4，只有Tier1-3才能享受高赔率期权溢价)；4.老龄化不可逆(20%)；3.物理世界运转效率跃升(10%)。若不符合任何一条，直接给出“不予买入”结论；若同时满足1和2（双核驱动），必须给予极高溢价并大幅上调中长期评分；满足其他组合则适度上调。
    * 重塑估值锚：对于轻资产科技股（18C等），严禁使用 BPS/PB 评估安全边际，必须使用 PS (市销率)；行业可比估值需通过联网检索全球对标公司获取，不再使用本地板块均值。
    * 筹码与流动性：直接基于【筹码与流动性档案】中明确的短中长期“主力”与“整体”资金流向数据进行研判，结合【总/流通市值】定性真实的盘口博弈状态（如：主力托底散户抛售、主力出逃散户接盘等），无需主观猜测机构动向。
 3. 技术面证据链（港股大盘流动性热度 + 短期当日信号 + 10日风险收益 + 10日筹码分布 + 30/90/180日趋势共振，200字左右）
 4. 交易计划（入场条件、止损位、失效条件，100-150字）
5. 核心风险/证伪条件（除常规止损外，必须给出1条可导致逻辑瞬间崩塌的非结构化风险触发，如宏观事件/产业政策，40-80字）
6. 联网检索证据（固定三行）
   * 检索时间：YYYY-MM-DD HH:MM（北京时间）
   * 对标来源域名：至少3个，格式示例 `finance.yahoo.com | companiesmarketcap.com | wsj.com`
   * 对标公司与PS时点：公司A(代码) PS=xx（时点）；公司B(代码) PS=yy（时点）

要求：
- 结论必须可交易，禁止空泛表述。
- 必须主动寻找“反面逻辑”，禁止只做线性外推（单边看多或单边看空）。
- 若样本不足（short_window_incomplete=true 或多周期趋势中任一关键窗口实际样本少于目标窗口），必须显式提示不确定性。
```

## 6. 执行流程（端到端）

1. 参数校验：symbol 非空、格式合法、市场合法。
2. 串行取数与校验：先快照，再历史 K 线，最后资金流。
3. 数据清洗：字段标准化、缺失处理、窗口切片，并排除三个指数历史 K 线中的当日未完成记录。
4. 语义化：生成港股大盘流动性热度、短期序列与多周期趋势描述。
5. 组装 Prompt：包含标签与结构化摘要。
6. 调用 LLM：复用 `generate_futu_hk_report` 的流式 + 重试策略。
7. 结果校验：长度/完整性/敏感兜底。
8. 发送 Feishu：标题带 symbol 与时间。
9. 返回结构化结果：供 API 或任务调度消费。

---

## 7. Feishu 消息设计

标题建议：

- `[单股深度研报] HK.00700 (2026-04-21 14:30)`

正文建议：

1. 报告正文（LLM 输出）。
2. 附加元数据（可选）：数据窗口、生成耗时、模型名。
3. 若失败：发送明确错误原因（API 失败 / 数据不足 / 超时）。

---

## 8. 错误处理与降级策略

1. 行情缺失：直接返回失败并通知 Feishu（“标的不存在或无权限”）。
2. K 线不足：允许降级，只输出可用窗口并在 Prompt 声明数据不足。
3. 资金流缺失：`flow_status_tag=资金流数据缺失`，但不阻断整条链路。
4. 三个指数全部缺失时：`market_heat_level=数据不足`，不阻断报告；不得退回使用指数 `volume=0` 计算。
5. 单个指数缺失时：保留其余指数结果并标记 `cross_index_state=数据不完整`，不得推断全面共振。
6. LLM 连续失败：按现有 3 次重试，最终发送失败告警。
7. Feishu 失败：记录日志并返回 `ok=False`，上层可重试。

---

## 9. 配置项建议

在 `config/settings.py` 增加（或复用）：

- `SINGLE_STOCK_MAX_TOKENS`（默认 4000）
- `SINGLE_STOCK_TEMPERATURE`（默认 0.7~1.0）
- `SINGLE_STOCK_LOOKBACK_SHORT`（10）
- `SINGLE_STOCK_LOOKBACK_MID`（90，兼容旧参数，作为多周期核心窗口）
- `SINGLE_STOCK_FEISHU_PREFIX`（`[单股深度研报]`）

---

## 10. 代码落地建议（最小改动版）

第一阶段（推荐）：

1. 仅修改 `src/services/llm_analyst.py`，新增 `generate_single_stock_futu_report`。
2. 内部复用 `futu_client` 与 `calculate_ema_derivatives`。
3. 复用 `FeishuAlert.send_alert`。
4. 先不新建 controller，通过手动调用验证链路。

第二阶段：

1. 抽离语义化函数到 `src/analysis/single_stock_memory_builder.py`。
2. 增加 API 路由 + 参数模型。
3. 增加单元测试（数据清洗规则、标签生成、Prompt 拼接）。

---

## 11. 验收标准（DoD）

1. 输入任意合法港股代码，可在 30~60 秒内生成报告并推送 Feishu。
2. 报告必须分别包含恒指、恒科、恒生生物科技的成交额热度及跨指数共振/分化结论，同时保留个股短期及多周期趋势信息。
3. 报告给出明确交易条件与风险，不出现“仅供参考”式空泛段落。
4. 任一数据源失败时，系统可解释地降级或报错，不静默失败。
5. 日志可追踪一次请求全链路（symbol、耗时、失败点、重试次数）。

---

## 12. 后续可扩展方向

1. 接入 A 股/美股单股分析（抽象 market adapter）。
2. 引入多模型投票（Gemini + Kimi）降低单模型幻觉。
3. 加入历史报告归档与回测（验证建议命中率）。
4. 增加“图形卡片消息”输出到 Feishu（关键指标可视化）。
