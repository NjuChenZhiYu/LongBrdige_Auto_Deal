# 单一股票深度分析接口设计（Futu + LLM + Feishu）

## 1. 背景与目标

基于现有 `src/services/llm_analyst.py` 中 `generate_futu_hk_report` 的成熟链路，新增一个“单一股票深度分析”接口，支持：

1. 输入单个港股代码（如 `HK.00700`）。
2. 从 Futu 拉取该股票实时行情、资金流、历史 K 线等数据。
3. 按 `docs/single_stock_analyze.md` 的要求，将原始时序数据清洗为“语义化序列”（短期记忆 / 中期趋势）。
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
    lookback_days_mid: int = 90
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
3. 三段 `lookback` 分别对应：
   - `10`：短期记忆窗口（近 10 个交易日高清快照）。
   - `90`：中期趋势窗口（近 90 个交易日趋势结构判断）。
4. 长周期锚点（原 `365/250`）暂不启用，待短中期效果验证后再恢复。
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

1. 实时与财务快照：价格、涨跌幅、昨收，以及基础估值（总市值、流通市值、PE、PE-TTM、PB、净利润）等（复用 `get_market_snapshot([symbol])` 方式）。
2. 历史 K 线：`get_hk_historical_klines(symbol, num_days)`，若为空则直接失败返回，不进入后续分析。
3. 资金流：`get_capital_flow(symbol)`（允许为空并降级）。
4. 历史 K 线窗口建议：
  - 短期：至少 30 天（保证 MACD 等指标 warm-up 后取近 10 天）。
  - 中期：90 天。
  - 长周期：目标 365 天（用于覆盖 250 日锚点）。

建议一次拉取 `365 + warmup` 天，再切片，减少重复请求；但执行顺序上必须先确认 K 线可用，再进入指标构建。

## 4.2 清洗与特征工程

在服务内新增私有函数（或单独模块）：

```python
def _build_semantic_memory(klines_df, snapshot, capital_data) -> dict:
    ...
```

输出两层记忆（当前启用）：

### 实时价格拼接口径（Short / Mid 统一）

为避免指标停留在“前一交易日收盘价”，短期与中期都采用同一口径：

1. **Short (`build_short_term_memory`)**  
   - 历史基底：`get_hk_historical_klines`。  
   - 实时价来源：`snapshot.last_price`（无值时退化为最近收盘）。  
   - 处理方式：将实时价作为一条“RT 行”追加到序列末端，再计算 EMA/MACD/Bias 与 10 日统计。

2. **Mid (`build_mid_term_trend`)**  
   - 历史基底：`get_hk_historical_klines`。  
   - 实时价来源：服务层传入 `current_price`（来自实时快照）。  
   - 处理方式：同样将实时价作为末端样本追加后，再计算形态位置、POC、波动率、MACD 交叉。

结论：**Short 与 Mid 均以“当前价格”作为 Pandas 序列最后一个数据点，而不是前一交易日收盘价。**

### A) 短期记忆（近 10 个交易日）

短期策略不在本文重复维护，统一引用：

- `docs/short_trade_indicator.md`

约定：

1. `build_short_term_memory` 的字段定义、计算口径、降级策略以该文档为唯一标准。
2. 本文只声明“短期记忆模块存在并参与 Prompt”，不再展开短期公式与规则细节。
3. 若短期策略调整，仅更新 `docs/short_trade_indicator.md`，本文无需同步粘贴。

### B) 中期趋势（近 3 个月）

由规则引擎生成描述标签，示例：

- “过去 60 天处于三角收敛末端”
- “MACD 位于零轴上方并出现 2 次金叉”
- “近 20 天波动率下降，疑似变盘前压缩”

建议产出结构：

```json
{
  "trend_labels": ["...", "..."],
  "volatility_state": "...",
  "macd_cross_count": 2,
  "mid_summary": "..."
}
```

### C) 锚点记忆（长周期，暂不启用）

当前版本先关闭锚点记忆，避免过早引入长周期噪声。后续如需恢复，可启用 `MA250/年内高低点/成交密集区`。

### D) 基本面与估值特征（实时快照）

基于富途 `get_market_snapshot` 提取基本财务指标，并基于 `get_owner_plate` 提取板块归属：
- **所属板块**：行业板块 (`INDUSTRY`)、概念板块 (`CONCEPT`) 等。
- **盈利数据**：净利润 (`net_profit`)
- **估值水平**：市盈率 (`pe_ratio`)、市盈率 TTM (`pe_ttm_ratio`)、市净率 (`pb_ratio`)
- **规模体量**：总市值 (`total_market_val`)、流通市值 (`circular_market_val`)

*注：将这些数值格式化为文本（如“所属板块: 互联网/人工智能, 总市值: 4.39万亿, PE(TTM): 17.6”），作为 LLM 进行基本面质地、行业景气度及安全边际中长期推演的核心依据。*

## 4.3 样本不足补偿机制（必须实现）

为避免新股或次新股因为历史数据不足导致分析不可用，需引入分层补偿：

1. **长周期锚点补偿（250 日不足）**
   - 若 `available_days >= 250`：正常计算 `MA250`、年内锚点。
   - 若 `90 <= available_days < 250`：降级为 `MA90` 作为中长期价值中枢，并标注 `anchor_mode=MA90_FALLBACK`。
   - 若 `10 <= available_days < 90`：降级为 `MA10 + 区间高低点` 作为临时锚点，并标注 `anchor_mode=MA10_RANGE_FALLBACK`。
   - 若 `available_days < 10`：仅输出“数据不足”+ 实时快照，不给出锚点交易建议。

1. **中期趋势补偿（90 日不足）**
   - 若 `available_days >= 90`：使用完整中期趋势规则。
   - 若 `30 <= available_days < 90`：使用“压缩版中期规则”（波动率 + EMA20 斜率 + MACD 近端交叉）。
   - 若 `available_days < 30`：不输出中期结构结论，只输出“趋势样本不足”风险提示。

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
  - `【短期记忆】`
  - `【中期趋势】`
4. 分析任务：
  - 基本面与中长期推演：结合估值数据与内置知识，分析公司质地、产业景气度及安全边际。
  - 趋势判断（短中长一致性）。
  - 主力/散户博弈识别。
  - 当前所处交易阶段（启动、加速、派发、探底等）。
  - 明确交易建议（触发条件、失效条件、风控位）。
  - 极端场景风控滤网：必须给出 1 条“非结构化证伪条件”（非价格/均线/止损触发），用于防止线性外推。
5. 输出格式约束：Markdown，分节、字数范围、禁止空话。

短期块字段与口径统一参考 `docs/short_trade_indicator.md`。

## 5.2 Prompt 示例骨架

```text
你是港股量化深度分析师。请基于下述“结构化历史记忆档案”分析单一标的：{symbol}

【基本面与估值快照】
所属板块：{plate_info}
总市值：{total_market_val}，流通市值：{circular_market_val}，净利润：{net_profit}
PE(静)：{pe_ratio}，PE(TTM)：{pe_ttm_ratio}，PB：{pb_ratio}

【实时快照】
...

【短期记忆（近10日语义化序列）】
...

【中期趋势（近3个月）】
...

请输出：
1) 核心结论（先给方向）
2) 基本面与中长期推演（结合估值数据分析业务质地、景气度与安全边际）
3) 技术面证据链（资金 + 技术 + 结构）
4) 交易计划（入场条件/止损位/失效条件）
5) 核心风险/证伪条件（除常规止损外，给出 1 条可导致逻辑瞬间崩塌的非结构化风险触发）
```

证伪条件示例（择一）：
1. 海外关键市场突发加征关税，导致核心产品毛利与出海节奏被快速压缩。
2. 核心耗材/服务被集采或行政限价，盈利模型在短期内失真。
3. 核心算法能力被开源平替或竞品降维打击，估值溢价逻辑失效。

---

## 6. 执行流程（端到端）

1. 参数校验：symbol 非空、格式合法、市场合法。
2. 串行取数与校验：先快照，再历史 K 线，最后资金流。
3. 数据清洗：字段标准化、缺失处理、窗口切片。
4. 语义化：生成短期序列与中期描述。
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
3. 资金流缺失：`flow_label=数据缺失`，但不阻断整条链路。
4. LLM 连续失败：按现有 3 次重试，最终发送失败告警。
5. Feishu 失败：记录日志并返回 `ok=False`，上层可重试。

---

## 9. 配置项建议

在 `config/settings.py` 增加（或复用）：

- `SINGLE_STOCK_MAX_TOKENS`（默认 4000）
- `SINGLE_STOCK_TEMPERATURE`（默认 0.7~1.0）
- `SINGLE_STOCK_LOOKBACK_SHORT`（10）
- `SINGLE_STOCK_LOOKBACK_MID`（90）
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
2. 报告必须包含短期/中期两段信息，不得只输出泛化评论。
3. 报告给出明确交易条件与风险，不出现“仅供参考”式空泛段落。
4. 任一数据源失败时，系统可解释地降级或报错，不静默失败。
5. 日志可追踪一次请求全链路（symbol、耗时、失败点、重试次数）。

---

## 12. 后续可扩展方向

1. 接入 A 股/美股单股分析（抽象 market adapter）。
2. 引入多模型投票（Gemini + Kimi）降低单模型幻觉。
3. 加入历史报告归档与回测（验证建议命中率）。
4. 增加“图形卡片消息”输出到 Feishu（关键指标可视化）。
