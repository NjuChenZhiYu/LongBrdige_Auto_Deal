# 港股市场流动性分析设计（Futu API 版）

## 1. 目标

当前单股分析里的“流动性”偏泛，主要问题不是模型不会写，而是喂给模型的市场层数据太少，导致它只能围绕个股资金流做局部解释，无法回答以下三个关键问题：

1. 市场有没有钱。
2. 资金更偏向大盘权重还是高弹性题材。
3. 个股的上涨/下跌，究竟是市场顺风、板块承接，还是纯个股博弈。

本文目标是基于 `docs/Futu-API-Doc-zh-Python.md` 中已经可用的接口，先建立一套**港股市场流动性分析中间层**，用于给 `src/services/llm_analyst.py` 提供更具体的结构化输入。

---

## 2. 结论先行

基于当前富途 Python 文档，可以稳定拿到以下几类“市场流动性”原料：

1. **指数快照数据**：可拿到指数的最新价、涨跌幅、成交量、成交额、换手率等。
2. **个股资金流数据**：可拿到 `in_flow`、`main_in_flow`、`super_in_flow`、`big_in_flow` 等。
3. **板块归属数据**：可识别股票是否属于 `HK.GangGuTong`、`恒指成份股` 等。
4. **板块列表/板块成分股**：可拿到概念板块、行业板块及成分股列表。
5. **市场状态数据**：可判断港股当前是否处于可交易时段。

但是，**当前文档中没有直接暴露“南向资金净流入/净买入额”的专门接口**。因此第一版不要伪造“南向净流入”字段，而应采用以下两层方案：

1. **直接指标层**：指数成交额、指数涨跌、港股通成分活跃度、个股主力净流。
2. **代理指标层**：用 `HK.GangGuTong` 板块覆盖情况、港股通样本成交活跃度、恒指/恒科风格强弱来近似判断“南向风险偏好是否在提升”。

换句话说，第一版先做**市场流动性 proxy system**，而不是伪装成“南向资金精确监控系统”。

---

## 3. 可直接使用的数据源

## 3.1 市场状态：先判断当前数据是否有意义

### 接口

- `get_global_state()`
- `get_market_state(code_list)`

### 用途

1. 判断港股是否在 `MORNING` / `AFTERNOON` / `HK_CAS` 等有效交易时段。
2. 若市场未开盘，则不做“实时流动性强弱”判断，只输出上一交易日收盘视角。
3. 防止模型把盘前、午休、收盘后数据误读为“流动性枯竭”。

### 结论

这是一个**gating 指标**，不直接打分，但决定后续评分是否采用“实时版”还是“收盘版”。

---

## 3.2 指数快照：判断市场有没有钱

### 核心标的

至少跟踪以下港股指数：

1. `HK.800000`：恒生指数
2. 恒生科技指数：代码需在接入时二次确认
3. 如后续需要，再补恒生中国企业指数、恒指期货主连等风格锚

### 接口

- `get_market_snapshot([code1, code2, ...])`

### 可用字段

从文档看，快照中可直接提取：

1. `last_price`
2. `change_rate`
3. `volume`
4. `turnover`
5. `turnover_rate`
6. `amplitude`
7. 对板块/指数类标的，额外还有：
   - `plate_raise_count`
   - `plate_fall_count`
   - `plate_equal_count`
   - `index_raise_count`
   - `index_fall_count`
   - `index_equal_count`

### 用途

指数快照主要回答三个问题：

1. **有没有成交**：`turnover` 是否明显放大。
2. **钱在追涨还是避险**：`change_rate` 与 `turnover` 是否同步走强。
3. **是指数虚涨还是普涨**：结合 `index_raise_count / index_fall_count` 判断市场宽度。

### 建议加工指标

1. `hsi_change_rate`
2. `hsi_turnover`
3. `hsi_turnover_zscore_20d`
4. `market_breadth = index_raise_count / (index_raise_count + index_fall_count + 1e-6)`
5. `breadth_diff = index_raise_count - index_fall_count`
6. `price_volume_confirm`
   - 指数上涨且成交额放大：`+1`
   - 指数上涨但成交额缩量：`0`
   - 指数下跌且放量：`-1`

### 解释逻辑

1. 指数涨 + 成交额放大 + 市场宽度扩散：市场流动性改善。
2. 指数涨 + 成交额平淡 + 仅少数权重拉升：偏“抱团拉指数”，不能简单判定为流动性全面回暖。
3. 指数跌 + 放量 + 下跌家数扩散：流动性转弱，个股分析要整体降风险偏好。

---

## 3.3 港股通属性：判断南向风格是否在回流

### 接口

- `get_owner_plate(code_list)`
- `get_plate_stock(plate_code, sort_field, ascend)`

### 关键线索

文档示例中，股票所属板块可能包含：

- `HK.GangGuTong`
- `HK.HSI Constituent`

这意味着我们至少可以做两件事：

1. 判断某只股票是否属于港股通范围。
2. 以 `HK.GangGuTong` 作为“港股通可交易宇宙”的代理集合做样本分析。

### 现实约束

富途文档里目前**没有直接给出“南向资金净买入额”接口**，所以不能在 prompt 里写成：

```text
- 今日南向净流入：xx 亿
```

除非后续接入了港交所、Wind、同花顺 iFinD 或其他专门数据源，否则这一字段在第一版必须标记为：

```text
南向资金：暂无直接净流接口，当前采用港股通样本活跃度代理判断
```

### 可行代理指标

1. `is_ganggutong_member`
   - 个股是否属于 `HK.GangGuTong`
2. `ganggutong_sample_turnover_ratio`
   - 港股通样本成交额 / 恒指成交额
3. `ganggutong_rise_ratio`
   - 港股通样本上涨家数 / 总样本数
4. `ganggutong_top_turnover_concentration`
   - 港股通样本中前 N 大成交额个股占比

### 解释逻辑

1. 若港股通样本普遍放量、上涨家数扩散，说明内地南向风险偏好可能在修复。
2. 若只有少数超大市值票放量，其余样本低迷，则更像“权重抱团”，不应误判为南向普遍回流。
3. 若个股本身不属于 `HK.GangGuTong`，则南向因子只能作为间接环境变量，不能当作个股直接驱动。

---

## 3.4 个股资金流：判断有没有真实承接

### 接口

- `get_capital_flow(stock_code, period_type, start, end)`

### 关键字段

1. `in_flow`：整体净流入
2. `main_in_flow`：主力大单净流入
3. `super_in_flow`：特大单净流入
4. `big_in_flow`：大单净流入
5. `mid_in_flow`：中单净流入
6. `sml_in_flow`：小单净流入
7. `capital_flow_item_time`

### 用途

这部分不再只用于“个股博弈标签”，而是要升级为**流动性承接强度**判断：

1. 当日：是否有实时承接。
2. 5日：是否有短线增量资金。
3. 10日：是否有趋势资金。
4. 90日：是否有中线沉淀资金。

### 建议加工指标

1. `main_flow_today_ratio = main_in_flow_today / circular_market_val`
2. `main_flow_5d_ratio = main_in_flow_5d / circular_market_val`
3. `total_flow_10d_ratio = total_in_flow_10d / circular_market_val`
4. `smart_vs_total_consistency`
   - 主力和整体同向：承接更扎实
   - 主力正、整体负：偏“主力托底，散户抛售”
   - 主力负、整体正：偏“散户追高，主力借机派发”

### 解释逻辑

1. 如果个股上涨，但 `main_in_flow` 明显为负，则高度怀疑“无量空涨”或“散户推动”。
2. 如果个股下跌，但 `main_in_flow` 为正，可能是“回撤中的隐蔽承接”。
3. 所有资金流指标都必须和 `circular_market_val` 联动，避免大市值和小市值股票不能横向比较。

---

## 3.5 板块热度：判断板块有没有钱

### 接口

- `get_owner_plate(code_list)`
- `get_plate_list(market, plate_class)`
- `get_plate_stock(plate_code, sort_field, ascend)`
- `get_market_snapshot(...)`

### 第一版思路

对个股的主要行业板块或概念板块，提取板块成分股列表，再通过快照或样本统计构造板块活跃度：

1. 板块上涨家数占比
2. 板块成分股平均涨跌幅
3. 板块头部个股成交额集中度
4. 板块内“放量上涨”个股数量

### 建议加工指标

1. `sector_rise_ratio`
2. `sector_avg_change_rate`
3. `sector_turnover_top5_share`
4. `sector_momentum_count`
   - 涨幅 > 0 且成交额高于过去均值的个股数

### 解释逻辑

1. 个股走强但板块整体低迷，说明上涨持续性可能依赖个股事件，而不是板块合力。
2. 板块和个股同步扩散，才是真正适合在 prompt 中写“板块承接增强”。

---

## 4. 市场流动性评分框架

建议单独构造一个 `market_liquidity_score`，范围 `0-100`，作为个股五因子里的“流动性”上游输入。

### 4.1 一级拆分

1. **市场层流动性**：40分
2. **板块层流动性**：30分
3. **个股层流动性**：30分

最终：

```text
market_liquidity_score =
0.40 * market_score +
0.30 * sector_score +
0.30 * stock_score
```

### 4.2 市场层评分（40分）

可由以下维度组成：

1. 恒指涨跌与成交额共振：15分
2. 市场宽度（上涨/下跌家数）：10分
3. 港股通样本活跃度 proxy：15分

评分建议：

1. 指数涨、放量、宽度扩散：`32-40`
2. 指数震荡、成交一般、宽度中性：`18-31`
3. 指数跌、放量杀跌、宽度恶化：`0-17`

### 4.3 板块层评分（30分）

可由以下维度组成：

1. 个股所属主板块上涨家数占比：10分
2. 板块平均涨跌幅：10分
3. 板块成交额扩散而非头部独涨：10分

### 4.4 个股层评分（30分）

可由以下维度组成：

1. 当日主力净流 / 流通市值：10分
2. 5日与10日资金流趋势：10分
3. 主力与整体资金流方向是否一致：10分

### 4.5 特殊惩罚项

以下情况需要强制扣分：

1. 市场未开盘却误用实时数据：`-15`
2. 指数放量下跌且板块宽度恶化：`-10`
3. 个股上涨但主力持续净流出：`-10`
4. 个股不在港股通范围且流通市值过小：`-5`

---

## 5. 结构化输出建议

建议新增一个“市场流动性中间层”输出，而不是把原始字段直接塞给 LLM。

建议输出结构：

```json
{
  "market_liquidity": {
    "market_state": "MORNING",
    "southbound_direct_available": false,
    "proxy_method": "ganggutong_activity",
    "market_score": 34,
    "sector_score": 26,
    "stock_score": 21,
    "market_liquidity_score": 28,
    "hsi_change_rate": 1.42,
    "hsi_turnover": 126500000000,
    "market_breadth": 0.64,
    "ganggutong_rise_ratio": 0.61,
    "ganggutong_sample_turnover_ratio": 0.48,
    "stock_main_flow_5d_ratio": 0.012,
    "stock_flow_status": "主力托底，但市场总承接一般",
    "summary": "市场有增量资金回流，但更偏权重与港股通主线，个股处于顺风环境。"
  }
}
```

这段结构化输出的价值在于：

1. Python 先完成计算，避免模型自由发挥。
2. LLM 只负责“解释”和“交易化表达”，不负责从生数据中瞎猜。
3. 后续可回测 `market_liquidity_score` 与策略收益的关系。

---

## 6. 写入 Prompt 的方式

在 `_build_single_stock_prompt` 中，建议新增一个独立段落：

```text
【市场流动性环境】
- 市场状态：{market_state}
- 恒生指数：涨跌幅 {hsi_change_rate}% ，成交额 {hsi_turnover}
- 市场宽度：上涨占比 {market_breadth}
- 南向资金：当前无直接净流接口，采用港股通活跃度代理
- 港股通活跃度：上涨占比 {ganggutong_rise_ratio} ，成交额占比 {ganggutong_sample_turnover_ratio}
- 板块承接评分：{sector_score}/30
- 个股承接评分：{stock_score}/30
- 流动性综合评分：{market_liquidity_score}/100
- 流动性结论：{summary}
```

同时明确约束模型：

1. 只有当 `market_liquidity_score >= 60`，才能把“流动性”写成加强项。
2. 若 `market_liquidity_score < 40`，即便基本面优秀，也必须提示“交易上可能有故事、没承接”。
3. 若 `southbound_direct_available = false`，模型不得写成“今日南向净流入 xx 亿”，只能写“港股通活跃度代理显示”。

---

## 7. 第一版最小落地方案

为了尽快产出可用结果，建议先只做以下最小闭环：

### 第一步：市场层

1. 用 `get_global_state()` 判断时段。
2. 用 `get_market_snapshot([HK.800000])` 拿恒指涨跌幅、成交额、宽度。

### 第二步：港股通代理层

1. 通过 `get_owner_plate(symbol)` 判断目标股票是否属于 `HK.GangGuTong`。
2. 后续补充 `HK.GangGuTong` 样本池统计，不在第一步就把范围做太大。

### 第三步：个股承接层

1. 复用现有 `get_capital_flow`。
2. 将当日/5日/10日/90日资金流统一除以 `circular_market_val`，形成可比较指标。

### 第四步：Prompt 注入

先让 LLM 明确回答一句：

```text
市场有没有钱，板块有没有钱，个股有没有钱。
```

这句话是第一版最重要的目标，比“多加几个字段”更重要。

---

## 8. 暂不建议做的事

第一版先不要做以下内容：

1. 不要伪造“南向资金净流入额”字段。
2. 不要一开始就全市场扫描所有港股通成分股，成本高、稳定性差。
3. 不要让 LLM 自己从原始数字推导市场流动性结论，必须先由 Python 做结构化计算。
4. 不要把“指数涨了”直接等价为“市场流动性变好”，必须结合成交额和宽度。

---

## 9. 后续迭代路线

### V1

1. 恒指快照
2. 个股资金流标准化
3. 港股通成员识别
4. Prompt 新增“市场流动性环境”

### V2

1. 增加恒生科技指数
2. 增加港股通样本池活跃度统计
3. 增加板块扩散指标

### V3

1. 若接入外部数据源，再新增真实“南向净流入”字段
2. 回测 `market_liquidity_score` 对单股胜率和盈亏比的解释力

---

## 10. 最终设计原则

这一模块的核心原则只有三条：

1. **先承认数据边界**：没有直接南向数据，就明确写 proxy，不自欺欺人。
2. **先做结构化计算**：让 Python 给出市场、板块、个股三层流动性结论。
3. **再让 LLM 做交易表达**：模型负责解释，不负责猜数据。

只要这三条守住，单股研报里的“流动性”才会从泛泛而谈，升级为真正可交易的分析维度。
