# 港股新股单股申购分析接口设计（Futu + LLM + Feishu）

## 1. 背景与目标

港股新股（IPO/新股认购）是散户和机构常用的低风险打新策略通道。本方案基于现有
`generate_single_stock_futu_report` 的链路范式，新增接口 `generate_new_stock_hk_report`：

1. 用户从前端输入一只股票的**代码或公司名称**。
2. 后端从 Futu 拉取该标的全量 IPO 及行情数据。
3. 按标的所处阶段（认购中 / 待上市 / 近期已上市）自动适配数据深度。
4. 构造结构化 Prompt，调用 LLM 生成单股新股深度分析报告。
5. 报告推送至 Feishu。

与 `generate_single_stock_futu_report` 的核心区别：

| 维度 | `generate_single_stock_futu_report` | `generate_new_stock_hk_report` |
|------|--------------------------------------|--------------------------------|
| 输入 | 已上市股票代码 | 新股代码 / 公司名称（IPO 标的） |
| 主数据源 | K 线 + 快照 + 资金流 | `get_ipo_list` + 阶段性补充数据 |
| 历史数据 | 近 10/90 日 K 线 | 视上市状态决定（未上市则无 K 线） |
| 分析视角 | 技术面 + 基本面 + 资金博弈 | 申购决策 + 发行估值 + 上市后表现 |

---

## 2. 接口设计

### 2.1 对外接口签名

在 `src/services/llm_analyst.py` 新增：

```python
async def generate_new_stock_hk_report(
    self,
    symbol_input: str,                    # 用户输入：HK.XXXXX / 纯数字 / 中文公司名
    trigger_type: str = "MANUAL",
    enable_grounded_search: bool = True,
) -> Dict[str, Any]:
    """
    生成单只港股新股申购分析报告。

    Args:
        symbol_input: 支持 HK.XXXXX / 纯数字代码（如 02110）/ 中文公司名（模糊匹配）
        trigger_type: 触发来源 MANUAL / CRON / API
        enable_grounded_search: 是否启用联网检索（对标同类 IPO 估值）

    Returns:
        {
            "ok": True / False,
            "symbol": "HK.XXXXX",
            "name": "公司名称",
            "stage": "SUBSCRIBING" | "PENDING" | "RECENTLY_LISTED",
            "title": "Feishu 消息标题",
            "report": "Markdown 报告正文",
            "error": None or "错误描述"
        }
    """
```

### 2.2 输入解析策略

新股标的**不会出现在 `futu_symbols.yaml`**（该文件是手动维护的已上市自选股列表），因此不能只依赖现有的 `futu_client.parse_symbol_input()`。需要扩展为两阶段解析：

**阶段 1：沿用现有 `parse_symbol_input`（代码格式匹配）**

```python
# futu_client.parse_symbol_input 内部逻辑：
# 1. 正则匹配数字代码：02110 / 2110 / HK.02110 → 补全返回 "HK.02110"
# 2. 模糊匹配 futu_symbols.yaml（special_symbols + symbols）
#    → 仅适用于 yaml 中已登记的自选股，新 IPO 标的不在此列

standard_symbol = futu_client.parse_symbol_input(symbol_input)
```

**阶段 2：从 `get_ipo_list` 的 `name` 字段做模糊匹配（新股专用）**

当阶段 1 返回 `None` 时（输入的是中文公司名且不在 yaml），从 Futu 实时 IPO 列表里搜：

```python
if not standard_symbol:
    ret, ipo_df = quote_ctx.get_ipo_list(Market.HK)
    if ret == RET_OK:
        matched = ipo_df[ipo_df['name'].str.contains(symbol_input, na=False)]
        if len(matched) == 1:
            standard_symbol = matched.iloc[0]['code']
            ipo_row = matched.iloc[0]
        elif len(matched) > 1:
            candidates = matched[['code', 'name']].to_dict('records')
            return {"ok": False, "candidates": candidates,
                    "error": f"匹配到 {len(matched)} 只标的，请提供更精确的名称或代码"}
        # len == 0 → 下方统一处理未命中
```

**完整优先级链**

```
用户输入 "极智"
    │
    ├─ [已有] parse_symbol_input("极智")
    │         → Step1: 非数字代码，跳过
    │         → Step2: 模糊匹配 yaml → 命中 "HK.02590 极智嘉-W" → 返回 "HK.02590"
    │         ✅ 若命中 → 直接进入 get_ipo_list 过滤（验证是否是新股）
    │
    └─ [新增] 若 parse_symbol_input 返回 None（不在 yaml）
              → get_ipo_list(Market.HK)
              → ipo_df['name'].str.contains(input) 模糊匹配
              → 单条命中 → standard_symbol = matched code
              → 多条命中 → 返回候选列表，要求二次确认
              → 零条命中 → ok=False，提示"不在新股列表，请用单股报告接口"
```

> **注意**：`parse_symbol_input` 命中代码后，仍需用该代码去 `get_ipo_list` 里过滤验证是否是新股。若不在 IPO 列表中（已上市超过窗口期），返回 `{"ok": False, "error": "该标的不在当前新股列表，请使用 generate_single_stock_futu_report 分析已上市股票"}`。

---

## 3. Futu API 数据资产盘点

### 3.1 核心接口：`get_ipo_list(Market.HK)`

这是新股分析的**唯一主数据源**，每次调用返回港股全量 IPO 列表，再从中过滤目标标的。

| 字段 | 类型 | 说明 | 适用阶段 |
|------|------|------|----------|
| `code` | str | 股票代码（如 `HK.02110`） | 全部 |
| `name` | str | 股票名称 | 全部 |
| `list_time` | str | 上市日期（`yyyy-MM-dd`） | 全部 |
| `list_timestamp` | float | 上市日期时间戳 | 全部 |
| `ipo_price_min` | float | **最低发售价**（港元） | 认购中 / 待上市 |
| `ipo_price_max` | float | **最高发售价**（港元） | 认购中 / 待上市 |
| `list_price` | float | **上市开盘价**（上市后回填，未上市为 0.0） | 已上市 |
| `lot_size` | int | 每手股数 | 全部 |
| `entrance_price` | float | **每手入场费**（含认购手续费） | 认购中 / 待上市 |
| `is_subscribe_status` | bool | `True`=认购中，`False`=待上市或已上市 | 全部 |
| `apply_end_time` | str | 截止认购日期（`yyyy-MM-dd`） | 认购中 |
| `apply_end_timestamp` | float | 截止认购时间戳（**富途截止早于交易所**） | 认购中 |

### 3.2 补充接口（按标的所处阶段分层调用）

| 接口 | 适用阶段 | 获取信息 |
|------|----------|----------|
| `get_owner_plate([code])` | 认购中 / 待上市 / 已上市 | 行业板块 + 概念板块标签 |
| `get_stock_basicinfo(code_list=[code])` | 认购中 / 待上市 | `lot_size` 核验、`delisting` 状态、`exchange_type` |
| `get_market_snapshot([code])` | **已上市**新股 | 实时价、总/流通市值、PE(TTM)、PB、成交量、涨跌幅 |
| `get_capital_flow(code)` | **已上市**新股 | 大单/散单净流向（主力博弈状态） |
| `get_hk_historical_klines(code, days)` | **已上市**新股 | 上市后 K 线（首日开高低走 / 稳步上扬等形态） |

---

## 4. 阶段判断与数据收集流程

### 4.1 阶段判断逻辑

```python
today = datetime.today().date()
list_date = pd.to_datetime(row['list_time']).date()

if row['is_subscribe_status'] == True:
    stage = "SUBSCRIBING"       # 认购中
elif list_date > today:
    stage = "PENDING"           # 待上市（认购截止，未挂牌）
else:
    stage = "RECENTLY_LISTED"   # 已上市（list_price > 0 可验证）
```

### 4.2 各阶段数据收集

#### [SUBSCRIBING] 认购中

```
get_ipo_list → 过滤目标 row
get_owner_plate([code])          → 行业/概念板块
get_stock_basicinfo([code])      → lot_size 核验（可选，允许失败）
```

核心衍生字段：
- `days_to_deadline`：`(apply_end_timestamp - time.time()) / 3600`（剩余小时数）
- `price_midpoint`：`(ipo_price_min + ipo_price_max) / 2`
- `price_spread_pct`：`(ipo_price_max - ipo_price_min) / ipo_price_min * 100`
- `lots_affordable_10k`：`floor(10000 / entrance_price)`（1万港元能认购几手，参考性）

> ⚠️ 认购中标的**无行情、无 K 线、无资金流**数据，这些 API 调用会失败，代码层必须跳过。

#### [PENDING] 待上市

```
get_ipo_list → 过滤目标 row
get_owner_plate([code])          → 行业/概念板块
```

核心衍生字段：
- `days_to_listing`：`(list_timestamp - time.time()) / 86400`（距上市天数）
- 发行价已确定，`ipo_price_min / ipo_price_max` 均有效

#### [RECENTLY_LISTED] 已上市（推荐窗口：上市后 ≤ 90 天）

```
get_ipo_list → 过滤目标 row
get_owner_plate([code])          → 板块信息
get_market_snapshot([code])      → 实时价格与估值快照
get_capital_flow(code)           → 资金流向（允许为空并降级）
get_hk_historical_klines(code, days=min(days_since_listing+5, 60))
                                 → 上市后 K 线
```

核心衍生字段：
- `vs_ipo_pct`：`(current_price - ipo_price_max) / ipo_price_max * 100`（相对发行上限）
- `vs_list_price_pct`：`(current_price - list_price) / list_price * 100`（相对上市开盘价）
- `days_since_listing`：`(today - list_date).days`
- K 线形态标签：复用 `build_short_term_memory(klines_df, snapshot, capital_data, lookback_days=days_since_listing)`
- 资金博弈标签：复用 `analyze_capital_flow(capital_data, change_rate)`

---

## 5. 特征结构（输入 Prompt 前的结构化 dict）

### SUBSCRIBING

```python
{
    # --- IPO 核心参数 ---
    "code": "HK.02110",
    "name": "裕勤控股",
    "stage": "SUBSCRIBING",
    "ipo_price_min": 0.225,
    "ipo_price_max": 0.270,
    "price_midpoint": 0.2475,
    "price_spread_pct": 20.0,           # 区间弹性 %
    "lot_size": 10000,
    "entrance_price": 2727.21,          # 每手入场费（含手续费）
    "lots_affordable_10k": 3,           # 1万港元可认购手数
    "apply_end_time": "2020-11-27",
    "days_to_deadline": 36.5,           # 距富途截止（小时）
    "futu_deadline_warning": True,      # 提示：富途截止早于交易所
    "list_time": "2020-12-07",

    # --- 板块 ---
    "plate_info": ["行业：房地产", "概念：内房股"],
}
```

### PENDING

```python
{
    "code": "HK.XXXXX",
    "name": "某某科技",
    "stage": "PENDING",
    "ipo_price_min": 3.20,
    "ipo_price_max": 4.00,
    "price_midpoint": 3.60,
    "lot_size": 1000,
    "entrance_price": 4060.00,
    "list_time": "2026-05-18",
    "days_to_listing": 5,
    "plate_info": ["行业：软件服务", "概念：SaaS概念"],
}
```

### RECENTLY_LISTED

```python
{
    # --- IPO 参数 ---
    "code": "HK.06666",
    "name": "恒大物业",
    "stage": "RECENTLY_LISTED",
    "ipo_price_min": 8.50,
    "ipo_price_max": 9.75,
    "list_price": 10.20,                # 上市开盘价
    "lot_size": 500,
    "days_since_listing": 12,

    # --- 上市后表现 ---
    "current_price": 11.30,
    "vs_ipo_pct": +15.9,                # 相对发行上限 %
    "vs_list_price_pct": +10.8,         # 相对上市开盘价 %

    # --- 估值快照 ---
    "total_market_val": "约100亿HKD",
    "circular_market_val": "约30亿HKD",
    "pe_ttm": 35.2,
    "pb_ratio": 3.1,
    "turnover": "4500万HKD",

    # --- 资金流 ---
    "capital_flow_tag": "主力净流入，散户跟风",
    "main_in_flow_5d": "+2.3亿HKD",
    "total_in_flow_5d": "+1.1亿HKD",

    # --- K 线形态（短期记忆标签） ---
    "short_memory": { ... },            # build_short_term_memory 输出，结构与单股报告一致

    # --- 板块 ---
    "plate_info": ["行业：房地产服务", "概念：内房股"],
}
```

---

## 6. Prompt 设计

### 6.1 角色 + 背景

```
你是一位专注港股打新申购的量化分析师。我将提供该新股的结构化数据，
请根据其当前所处阶段（认购中 / 待上市 / 已上市）生成深度分析报告。
```

### 6.2 SUBSCRIBING 阶段 Prompt 模板

```
【报告时间】{current_time}
【标的】{code} {name}｜当前状态：认购中

【IPO 核心参数】
- 发行价区间：HKD {ipo_price_min} ~ {ipo_price_max}（价格弹性 {price_spread_pct:.1f}%）
- 每手入场费：HKD {entrance_price}（每手 {lot_size} 股）
- 发行价中枢：HKD {price_midpoint}
- 认购截止日：{apply_end_time}（距今约 {days_to_deadline:.0f} 小时）
  ⚠️ 注意：富途认购截止时间早于交易所公布日期，请以富途平台实际截止时间为准
- 预计上市日：{list_time}

【所属板块】
{plate_info_text}

请按以下结构输出（Markdown）：
1. **申购推荐评级**
   - 格式：`【申购评级：★★★★☆ (X/100) - 一句话结论】`
   - 评分 0-100；0-39=★，40-59=★★，60-74=★★★，75-89=★★★★，90-100=★★★★★
   - 第二行 40-80 字说明该评分的核心驱动因子

2. **发行估值合理性**（150-200字）
   - 基于行业板块，判断发行价区间相对同类已上市公司的 PE/PB/PS 水平
   - 是否存在"折价发行"或"溢价发行"；是否有估值安全边际
   - 【买方公理映射】：出海能力(40%) / AI产业层级(30%) / 老龄化(20%) / 效率跃升(10%)；
     不符合任何一条则给出"建议回避"结论

3. **打新胜率判断**（100字）
   - 入场费门槛高低对超额认购率的影响
   - 当前港股打新市场温度（联网检索：近期同期 IPO 认购倍数参考）
   - 预估首日上市溢价区间（乐观 / 中性 / 悲观）

4. **操作建议**（100字）
   - 是否值得顶格认购（`entrance_price * 最大手数`）
   - 资金分配建议（如：建议投入不超过总仓位 X%）
   - 首日开盘卖出 or 持有条件

5. **核心风险**（50-80字）
   - 必须给出 1 条非结构化风险（非"破发"泛化描述），如政策风险、行业监管、大股东锁定期等

6. **联网检索证据**（固定三行）
   - 检索时间：YYYY-MM-DD HH:MM（北京时间）
   - 参考来源：至少 2 个域名（如 aastocks.com | hkex.com.hk | futunn.com）
   - 同类可比公司估值：公司A PE=xx；公司B PE=yy

要求：结论必须可执行，禁止"仅供参考"式空泛表述。
```

### 6.3 PENDING 阶段 Prompt 模板

```
【报告时间】{current_time}
【标的】{code} {name}｜当前状态：待上市（{days_to_listing} 天后挂牌）

【IPO 参数】
- 发行价：HKD {ipo_price_min} ~ {ipo_price_max}（已定价）
- 每手入场费：HKD {entrance_price}（每手 {lot_size} 股）
- 预计上市日：{list_time}

【所属板块】
{plate_info_text}

请按以下结构输出（Markdown）：
1. **首日走势预判**
   - 高开 / 平开 / 低开，信心度（低/中/高），预估波动区间（如 +5%~+15%）

2. **关键盯盘条件**（80字）
   - 上市首日需重点观察的价格位（如：若开盘低于发行中枢 {price_midpoint} 则建议离场）
   - 量能参考（首日成交额参考值）

3. **已中签操作策略**（100字）
   - 首日开盘卖 / 盘中减仓 / 持有至特定条件
   - 明确止盈止损价位

4. **核心风险**（50字）

5. **联网检索证据**（固定三行）
```

### 6.4 RECENTLY_LISTED 阶段 Prompt 模板

```
【报告时间】{current_time}
【标的】{code} {name}｜当前状态：上市 {days_since_listing} 天

【IPO 基础参数】
- 发行价区间：HKD {ipo_price_min} ~ {ipo_price_max}；上市开盘价：HKD {list_price}
- 每手 {lot_size} 股；入场费：HKD {entrance_price}

【上市后表现】
- 当前价：HKD {current_price}
  - 相对发行上限涨跌：{vs_ipo_pct:+.1f}%
  - 相对上市开盘价：{vs_list_price_pct:+.1f}%
- 总市值：{total_market_val}；流通市值：{circular_market_val}
- PE(TTM)：{pe_ttm}；PB：{pb_ratio}；日成交额：{turnover}

【筹码与资金博弈】
- 近5日主力净流：{main_in_flow_5d}；整体净流：{total_in_flow_5d}
- 博弈标签：{capital_flow_tag}

【上市后短期技术快照（近{days_since_listing}日）】
{short_memory_text}   ← 复用 build_short_term_memory 输出格式，与单股报告一致

【所属板块】
{plate_info_text}

请按以下结构输出（Markdown）：
1. **上市表现评级**
   - 格式：`【上市表现：★★★☆☆ (X/100) - 一句话总结】`
   - 横向对比：相对同期港股新股表现，超预期 / 符合预期 / 低于预期

2. **基本面与估值透视**（150-200字）
   - 当前市值与发行价隐含估值对比（是否已消化 IPO 溢价）
   - 【买方公理映射】（同单股报告标准，需给出定性结论）
   - 若是轻资产科技股，使用 PS 对标，禁用 BPS/PB

3. **资金博弈分析**（100字）
   - 基于筹码与资金博弈标签，判断主力意图：
     拉升出货 / 机构持续吸筹 / 散户承接 / 主力托底等

4. **技术面证据链**（100字）
   - 短期 K 线结构 + 关键支撑/压力位

5. **当前交易建议**（100-150字）
   - 追入 / 持有 / 减仓 / 回避（含明确条件）
   - 入场价位 + 止损位 + 失效条件

6. **核心风险**（50-80字）
   - 1 条非结构化证伪风险（锁定期解禁 / 行业监管突变等）

7. **联网检索证据**（固定三行）
   - 检索时间、参考来源域名、同类可比公司估值

要求：
- 结论必须可交易，禁止空泛表述。
- 若 days_since_listing < 10，显式标注"K线样本不足，技术面结论仅供参考"。
```

---

## 7. 执行流程（端到端时序）

```
generate_new_stock_hk_report(symbol_input)
│
├─ Step 1: 输入解析
│          parse_symbol_input(symbol_input) → 尝试代码匹配
│          get_ipo_list(Market.HK)           → 全量 IPO 列表（用于名称模糊匹配）
│          filter_ipo_row(ipo_df, input)     → 目标标的单行 row
│          若未命中 → return {"ok": False, "error": "未在新股列表中找到该标的"}
│
├─ Step 2: 阶段判断
│          stage = detect_stage(row)
│          → "SUBSCRIBING" / "PENDING" / "RECENTLY_LISTED"
│
├─ Step 3: 补充取数（asyncio.gather，按阶段分支）
│   ├─ [ALL]          get_owner_plate([code])
│   ├─ [SUBSCRIBING]  get_stock_basicinfo([code])          # 可选，允许失败
│   └─ [RECENTLY_LISTED]
│       ├─ get_market_snapshot([code])
│       ├─ get_capital_flow(code)
│       └─ get_hk_historical_klines(code, days)
│
├─ Step 4: 特征构建
│          build_new_stock_features(stage, row, plate_info, ...)
│          [RECENTLY_LISTED] 额外调用：
│          ├─ build_short_term_memory(klines_df, snapshot, capital_data, lookback)
│          └─ analyze_capital_flow(capital_data, change_rate)
│
├─ Step 5: 组装 Prompt
│          按 stage 选择对应 Prompt 模板，填入特征字典
│
├─ Step 6: _call_llm_with_retry(prompt, enable_grounded_search=True)
│          → report_content (Markdown)
│
├─ Step 7: FeishuAlert.send_alert(title, report_content)
│          标题：[新股研报] {name}（{code}）{stage_label} {current_time}
│
└─ Step 8: return {"ok": True, "symbol": ..., "name": ..., "stage": ..., "report": ...}
```

---

## 8. LLM 选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 主模型 | **Kimi（hk_client）** | 港股中文语境，与现有 HK 分析一致 |
| 联网检索 | Gemini Grounded（`enable_grounded_search=True`） | 发行估值对标、近期港股打新市场温度需实时信息 |
| `max_tokens` | 4000 | 单股报告，篇幅适中 |
| `temperature` | 0.7 | 分析类任务，适度创意 |
| 重试 | 3 次（复用 `_call_llm_with_retry`） | 与现有逻辑一致 |

---

## 9. Feishu 消息设计

**标题格式**：

```
[新股研报] 恒大物业（HK.06666）已上市12天 | 2026-05-13 17:30
[新股研报] 某某科技（HK.XXXXX）认购中 截止05-15 | 2026-05-13 17:30
[新股研报] 某某控股（HK.XXXXX）待上市 05-18挂牌 | 2026-05-13 17:30
```

**失败消息**：
```
[新股研报-异常] 某某科技（HK.XXXXX）| 2026-05-13 17:30
原因：{error}
```

---

## 10. 错误处理与降级

| 场景 | 降级策略 |
|------|----------|
| `get_ipo_list` 中未找到目标标的 | `ok=False`，提示"不在新股列表，请用单股报告接口" |
| `get_owner_plate` 失败 | `plate_info = ["板块信息暂不可用"]`，不阻断流程 |
| `get_stock_basicinfo` 失败 | 跳过核验，直接使用 `get_ipo_list` 中的 `lot_size` |
| 已上市股 `get_market_snapshot` 失败 | `ok=False`，返回"行情数据不可用" |
| 已上市股 K 线为空 | `kline_shape = "K线数据不足"`，短期记忆段跳过 |
| 已上市股资金流为空 | `capital_flow_tag = "资金流数据暂不可用"`，不阻断 |
| LLM 3次重试失败 | 发送 Feishu 失败告警 |

---

## 11. 关键约束与注意事项

1. **`apply_end_timestamp` 时间差**：富途截止认购时间会**早于**交易所公布日期，报告中必须显式提示用户以富途平台实际截止时间为准。

2. **认购中 / 待上市标的无行情数据**：`get_market_snapshot` / `get_capital_flow` / `get_hk_historical_klines` 仅适用于已上市标的，实现时必须用 `stage` 做条件保护，不可无条件调用。

3. **`list_price = 0.0` 是上市前默认值**：用于区分 PENDING 和 RECENTLY_LISTED 时，需同时验证 `list_timestamp < now` 且 `list_price > 0`。

4. **`entrance_price` 含手续费**：入场费 ≠ `ipo_price × lot_size`，Prompt 中需注明这是综合入场费，便于 LLM 正确推算认购成本。

5. **已上市新股 K 线 `lookback` 动态适配**：K 线天数取 `min(days_since_listing + 5, 60)`，避免对上市仅 3-5 天的新股要求过长历史窗口。

6. **`build_short_term_memory` 复用**：RECENTLY_LISTED 阶段的短期技术分析直接复用现有函数，`lookback_days_short = min(days_since_listing, 10)`，保持字段格式与单股报告一致，降低维护成本。

---

## 12. 后续扩展方向

1. **打新历史归档**：每次报告生成后写入本地或数据库，上市后自动回填实际首日涨跌幅，建立打新建议准确率台账。
2. **认购决策评分模型**：引入近期同类 IPO 破发率、行业景气度，构建 0-100 量化打新胜率评分，辅助评级打分更客观。
3. **多市场扩展**：框架可复用接入 `Market.US`（美股 IPO）；A 股打新中签逻辑差异较大需单独处理。
4. **定时触发**：配置 Cron，在每个港股交易日收盘后（16:10）自动扫描当前认购中标的并逐一生成报告。
