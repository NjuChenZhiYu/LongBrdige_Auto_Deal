import sys
import os
import asyncio
from datetime import datetime

# 设置工作目录
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.llm_analyst import LLMAnalyst
from src.api.futu.client import futu_client

async def test_generate_prompt(symbol: str):
    print(f"Starting test for {symbol}...")
    
    # 初始化
    analyst = LLMAnalyst()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    lookback_days_short = 10
    lookback_days_mid = 90
    
    standard_symbol = futu_client.parse_symbol_input(symbol)
    if not standard_symbol:
        print(f"Invalid symbol: {symbol}")
        return
        
    print(f"Parsed symbol: {standard_symbol}")
    
    # 1. 获取实时快照
    print("Fetching market snapshot...")
    snapshot_list = futu_client.get_special_quotes([standard_symbol])
    if not snapshot_list:
        print("Failed to get market snapshot.")
        return
        
    stock = snapshot_list[0]
    price = float(stock.get("last_price", 0.0))
    stock_name = str(stock.get("name", "") or "").strip()
    symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol
    
    # 2. 获取资金流
    print("Fetching capital flow...")
    capital_data = futu_client.get_capital_flow(standard_symbol)
    
    # 3. 获取板块信息
    print("Fetching plate info...")
    ret_plate, plate_data = futu_client.quote_ctx.get_owner_plate([standard_symbol])
    plate_info = "无数据"
    if ret_plate == 0 and plate_data is not None and not plate_data.empty:
        valid_plates = plate_data[plate_data['plate_type'].isin(['INDUSTRY', 'CONCEPT'])]
        if not valid_plates.empty:
            plate_names = valid_plates['plate_name'].tolist()
            plate_info = "、".join(plate_names)
            
    # 4. 获取历史 K 线
    print("Fetching historical klines...")
    klines_df = futu_client.get_hk_historical_klines(
        standard_symbol,
        max(lookback_days_mid + 30, 120),
    )
    
    if klines_df is None or klines_df.empty:
        print("Failed to get historical klines.")
        return
        
    print("Building indicators...")
    from src.analysis.futu_math_indicator import build_short_term_memory, build_mid_term_trend, hk_basic_finance_data
    
    short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
    mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
    
    fundamental_data = hk_basic_finance_data(stock)
    fundamental_data['plate_info'] = plate_info
    
    # 生成 Prompt
    print("Building prompt...")
    prompt = analyst._build_single_stock_prompt(
        symbol_for_prompt, 
        current_time, 
        fundamental_data, 
        short_memory, 
        mid_trend
    )
    
    # 写入文件
    output_file = os.path.join(os.path.dirname(__file__), f"single_stock_prompt_{standard_symbol.replace('HK.', '')}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
        
    print(f"Successfully wrote prompt to {output_file}")
    
    # 关闭富途连接
    futu_client.quote_ctx.close()

if __name__ == "__main__":
    asyncio.run(test_generate_prompt("02590"))