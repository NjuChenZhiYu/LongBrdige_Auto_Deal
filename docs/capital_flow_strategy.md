# Global_Quant_System V2.2 资金流向增强版 (Capital Flow Middleware) 

## 0. 针对futu_hk_report 进行设计
## 1. 核心业务逻辑重构 (Business Logic)
废弃原有的“成交量均值对比”方案。针对盘中预警标的，系统将通过富途 OpenAPI 的 `GetCapitalDistribution` 接口，实时拉取该标的的主力资金与散户资金的分布形态。
由本地 Python 内部函数先进行“资金博弈状态”的打标，再将结构化标签传递给 LLM。

## 2. 内部函数设计: `analyze_capital_flow(futu_data, current_price_change)`

**输入数据结构 (模拟富途 API 返回值)**：
* `capital_in_super` / `capital_out_super` (特大单流入/流出)
* `capital_in_large` / `capital_out_large` (大单流入/流出)
* `capital_in_mid` / `capital_out_mid` (中单流入/流出)
* `capital_in_small` / `capital_out_small` (小单流入/流出)
* `current_price_change` (当前涨跌幅)

**第一步：计算净流量 (Net Flow)**
* $Net\_Smart\_Money$ (主力净流) = (特大单流入 + 大单流入) - (特大单流出 + 大单流出)
* $Net\_Retail\_Money$ (散户净流) = (中单流入 + 小单流入) - (中单流出 + 小单流出)

**第二步：博弈状态矩阵标定 (State Machine)**
Python 函数内部根据净流量和当前股价涨跌幅，输出以下字符串标签传给 LLM：

1. **【主力洗盘 / 机构吸筹】**
   * *条件*：股价大跌 (`change_rate < threshold`) + 主力净流为**正** (`Net_Smart_Money > 0`) + 散户净流为**负** (`Net_Retail_Money < 0`)
   * *含义*：散户在恐慌割肉，机构在暗中接盘。这是极佳的右侧关注信号。
2. **【机构出逃 / 踩踏砸盘】**
   * *条件*：股价大跌 (`change_rate < threshold`) + 主力净流为**大负数**。
   * *含义*：不要接飞刀，这是真砸盘。
3. **【主力抢筹 / 主升浪】**
   * *条件*：股价大涨 (`change_rate > threshold`) + 主力净流为**大正数**。
   * *含义*：真金白银在扫货，趋势确立。
4. **【散户诱多 / 诱多出货】**
   * *条件*：股价上涨 (`change_rate > threshold`) + 主力净流为**负** + 散户净流为**正**。
   * *含义*：散户在追高，主力在趁机派发筹码，极度危险。

## 3. LLM Prompt 组装引擎 (Prompt Payload Update)

将 Python 函数运算出的结论，无缝注入到给 Gemini 的 Prompt 中。

```python
# Trae: 请在此处调用 analyze_capital_flow 函数获取 flow_label 和具体金额
flow_label, smart_money_net, retail_money_net = analyze_capital_flow(api_data, stock['change_rate'])

prompt_payload = f"""
你是一个顶级的量化分析师。以下是触发监控阈值的异动股票列表及【底层资金流向数据】：

【分析标的】
- {stock['symbol']} ({stock['name']}): 现价 ${stock['last_price']:.2f}, 涨跌幅 {stock['change_rate']:+.2f}%
- 【内部量化系统研判】：{flow_label} 
  (支撑数据：主力净流入 {smart_money_net} 万，散户净流入 {retail_money_net} 万)

请严格按照以下结构和字数要求，生成一份专业的市场快报：
1. **市场综述**（80-100字）：基于涨跌分布判断市场整体情绪。
2. **板块热点**（80-100字）：识别是否有机器人、物流、航天、能源、半导体等板块的集中异动。
3. **重点个股与资金博弈**（100-150字）：结合系统提供的【内部量化系统研判】标签（如：主力洗盘、机构出逃），深度点评主力和散户的博弈状态，刺穿涨跌幅的表象。
4. **策略建议**（70-100字）：基于资金流向和宏观基本面，给出冷血、理性的操作建议。
"""