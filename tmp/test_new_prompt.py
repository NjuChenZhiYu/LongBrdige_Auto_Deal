import sys
import os
import pandas as pd
from datetime import datetime

from futu import *
from src.analysis.futu_math_indicator import hk_basic_finance_data
from src.services.llm_analyst import LLMAnalyst

# 配置信息
print("Starting Futu API for Prompt Test...")
SysConfig.set_client_info("example", 1)
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=45575)

symbol = 'HK.00916'

ret, snapshot_list = quote_ctx.get_market_snapshot([symbol])
if ret != RET_OK or len(snapshot_list) == 0:
    print("获取快照失败:", snapshot_list)
    quote_ctx.close()
    sys.exit(1)

# 获取 stock 数据和基本面
# 注意 get_market_snapshot 返回的是 dataframe，所以转换成 dict 列表形式方便提取
stock = snapshot_list.iloc[0].to_dict() if isinstance(snapshot_list, pd.DataFrame) else snapshot_list[0]
stock_name = str(stock.get("name", "") or "").strip()
symbol_for_prompt = f"{symbol} {stock_name}" if stock_name else symbol

fundamental_data = hk_basic_finance_data(stock)

# 获取板块信息
ret_plate, plate_data = quote_ctx.get_owner_plate([symbol])
plate_info = "无数据"
if ret_plate == 0 and plate_data is not None and not plate_data.empty:
    valid_plates = plate_data[plate_data['plate_type'].isin(['INDUSTRY', 'CONCEPT'])]
    if not valid_plates.empty:
        plate_names = valid_plates['plate_name'].tolist()
        plate_info = "、".join(plate_names)
fundamental_data['plate_info'] = plate_info

# 模拟一些历史数据
current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
short_memory = {
    "window_used": 10,
    "short_window_incomplete": False,
    "flow_label": "资金博弈不明",
    "smart_net_wan": 0.0,
    "retail_net_wan": -527.47,
    "latest_tech_tag": "【跌势放缓：左侧建仓观察区】",
    "today": {
        "date": "2026-04-27 11:28:05(RT)",
        "open": 6.33, "high": 6.35, "low": 6.24, "close": 6.29,
        "change_rate": 0.0, "bias20": -6.13, "tag_today": "【跌势放缓：左侧建仓观察区】"
    },
    "summary_10d": {
        "max_cum_up_10d_pct": 3.21,
        "max_cum_drop_10d_pct": -4.04,
        "max_drawdown_10d_pct": 5.26,
        "shape_10d_tag": "区间震荡",
        "short_window_price_distribute": [{'bucket_range': '6.33-6.40', 'volume_ratio_pct': 43.52}],
        "poc_range_10d": "6.33-6.40",
        "poc_ratio_10d_pct": 43.52
    }
}

mid_trend = {
    "mode": "FULL_90",
    "window_used": 90,
    "summary": "近90日形态为混合震荡结构，已融合实时价格，当前位于90日空间6.94%，POC区间6.86-7.1（占比22.32%）。",
    "shape": "混合震荡结构",
    "position_pct": 6.94,
    "peaks": [7.17, 8.44, 8.1],
    "troughs": [6.84, 7.7, 6.17],
    "poc_range": [6.86, 7.1],
    "poc_ratio_pct": 22.32,
    "price_proxy": "hlc3",
    "macd_cross_count": 6,
    "volatility_state": "中波动"
}

# 调用 LLMAnalyst 的 _build_single_stock_prompt 方法
analyst = LLMAnalyst()
prompt = analyst._build_single_stock_prompt(symbol_for_prompt, current_time, fundamental_data, short_memory, mid_trend)

print("\n--- 生成的 Prompt ---")
print(prompt)

quote_ctx.close()
