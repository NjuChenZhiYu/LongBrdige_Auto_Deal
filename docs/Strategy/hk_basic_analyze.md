# 港股单股研报：基本面字段对齐说明

本文用于约束 `src/services/llm_analyst.py` 当前 Prompt 中的【基本面与估值快照】字段，确保文档与实现一致。

## 1. 数据来源与字段
基础数据来自富途 `get_market_snapshot([symbol])` 的完整快照，并与实时行情数据合并后传入 `hk_basic_finance_data`。当前对外字段如下：

- `plate_info`：所属板块（`get_owner_plate` 的 `INDUSTRY`/`CONCEPT` 聚合）
- `total_market_val`：总市值
- `circular_market_val`：流通市值
- `net_profit`：净利润
- `pe_ratio`：PE(静)
- `pe_ttm_ratio`：PE(TTM)
- `pb_ratio`：PB

## 2. Prompt 片段（与代码一致）
```text
    【基本面与估值快照】
    - 所属板块：{fundamental_data.get('plate_info', '无数据')}
    - 总市值：{fundamental_data.get('total_market_val', '无数据')}
    - 流通市值：{fundamental_data.get('circular_market_val', '无数据')}
    - 净利润：{fundamental_data.get('net_profit', '无数据')}
    - PE(静)：{fundamental_data.get('pe_ratio', '无数据')}
    - PE(TTM)：{fundamental_data.get('pe_ttm_ratio', '无数据')}
    - PB：{fundamental_data.get('pb_ratio', '无数据')}
```

## 3. 输出结构（与代码一致）
```text
    请按以下结构输出（Markdown）：
    1. 核心结论（先给方向，40-80字）
    2. 基本面与中长期推演（结合估值数据与内置知识分析业务质地、景气度与安全边际，150-200字）
    3. 技术面证据链（短期当日信号 + 10日风险收益 + 10日筹码分布 + 中期形态，180-260字）
    4. 交易计划（入场条件、止损位、失效条件，80-120字）
```
