import sys
import os
import pandas as pd

from futu import *

# 让 pandas 打印时显示所有列
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

print("Starting Futu API...")
SysConfig.set_client_info("example", 1)
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=45575)

# 注意：必须请求正股代码，不要请求期权代码
ret, data = quote_ctx.get_market_snapshot(['HK.00700', 'HK.09888', 'HK.02269'])

if ret == RET_OK:
    # 从 get_market_snapshot 中获取的实际财务相关指标有：
    # net_profit: 净利润
    # pe_ratio: 市盈率
    # pb_ratio: 市净率
    # pe_ttm_ratio: 市盈率 (TTM)
    # total_market_val: 总市值 (估值)
    # circular_market_val: 流通市值
    # net_asset: 净资产
    # net_asset_per_share: 每股净资产
    # earning_per_share: 每股收益
    print(data[['code', 'name', 'update_time', 'total_market_val', 'circular_market_val', 'pe_ttm_ratio', 'net_profit', 'pe_ratio', 'pb_ratio']])
    
    print("\n--- 尝试获取所属板块信息 ---")
    # 获取股票所属板块
    ret_plate, plate_data = quote_ctx.get_owner_plate(['HK.00700', 'HK.09888', 'HK.02269'])
    if ret_plate == RET_OK:
        print("所属板块信息:")
        print(plate_data)
        
        # 尝试获取板块的行情快照，看看有没有平均 PE/PB
        # 提取唯一的板块代码
        plate_codes = plate_data['plate_code'].unique().tolist()
        if plate_codes:
            print(f"\n尝试获取板块 {plate_codes} 的行情快照:")
            ret_plate_snap, plate_snap_data = quote_ctx.get_market_snapshot(plate_codes)
            if ret_plate_snap == RET_OK:
                print("板块行情快照可用列:", plate_snap_data.columns.tolist())
                # 打印板块的估值相关列（如果存在）
                cols_to_print = ['code', 'name', 'update_time', 'pe_ttm_ratio', 'pe_ratio', 'pb_ratio']
                # 只打印存在的列
                avail_cols = [c for c in cols_to_print if c in plate_snap_data.columns]
                print(plate_snap_data[avail_cols])
            else:
                print('获取板块行情快照失败:', plate_snap_data)
    else:
        print('获取所属板块失败:', plate_data)
else:
    print('error:', data)

quote_ctx.close()