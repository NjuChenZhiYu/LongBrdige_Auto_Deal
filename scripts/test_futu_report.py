import sys
import os
import asyncio

# Set up path to allow importing from src
sys.path.append(r"c:\Users\lichade\Documents\trae_projects\LongBrdige_Auto_Deal")

# Redirect Futu logs to local logs directory (must be before importing futu)
futu_log_dir = os.path.join(os.getcwd(), "logs", "futu_appdata")
if not os.path.exists(futu_log_dir):
    try:
        os.makedirs(futu_log_dir)
    except:
        pass
os.environ["appdata"] = futu_log_dir

from src.services.llm_analyst import LLMAnalyst
from config.settings import Settings
from src.api.futu.client import futu_client

async def test_futu_report():
    print("Initializing LLM Analyst...")
    analyst = LLMAnalyst()
    
    # 1. Print configuration
    config = getattr(Settings, 'FUTU_SYMBOLS_CONFIG', {})
    print("\n--- Current Configuration ---")
    print("Config keys:", config.keys())
    
    # Let's check all possible typo variations in the config
    print("special sysmbol:", config.get('special sysmbol', []))
    print("special_sysmbol:", config.get('special_sysmbol', []))
    print("special_symbols:", config.get('special_symbols', []))
    
    # 2. Test special quotes fetching
    print("\n--- Testing Data Fetching ---")
    special_symbols = config.get('special_symbols', config.get('special_sysmbol', config.get('special sysmbol', [])))
    if special_symbols:
        special_stock_codes = [s.split(' ')[0] for s in special_symbols]
        print(f"Extracted codes for special stocks: {special_stock_codes}")
        
        try:
            print("Fetching quotes for special stocks from Futu...")
            # Futu OpenD must be running for this to work
            special_stocks = futu_client.get_special_quotes(special_stock_codes)
            print(f"Fetched {len(special_stocks)} special stocks quotes.")
            for stock in special_stocks:
                print(f"  - {stock.get('code', 'N/A')}: {stock.get('last_price', 'N/A')} (Change: {stock.get('change_rate', 'N/A')}%)")
        except Exception as e:
            print(f"Failed to fetch quotes: {e}")
    else:
        print("No special symbols found in config.")
        
    # 3. Actually trigger the report generation (with a low threshold to ensure it picks up something)
    # We will override the config temporarily to test the function's internal logic
    print("\n--- Testing generate_futu_hk_report() ---")
    print("Calling generate_futu_hk_report with threshold=0.0...")
    
    # Since we found the typo in llm_analyst.py, we know it will miss the special symbols if we don't fix it.
    # The user asked to see if it can get special_symbols and market data.
    try:
        # Warning: This might send a Feishu alert if configured!
        # For a pure test, we might just want to check the data extraction parts.
        await analyst.generate_futu_hk_report(threshold=0.0)
        print("generate_futu_hk_report executed successfully.")
    except Exception as e:
        print(f"Error during report generation: {e}")

if __name__ == "__main__":
    asyncio.run(test_futu_report())
