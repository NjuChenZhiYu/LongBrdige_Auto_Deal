import asyncio
import yaml
import sys
import os

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.api.adanos_client import adanos_client
from config.settings import Settings

async def test_adanos():
    print(f"Checking Adanos API Key in settings: {'Configured' if Settings.ADANOS_API_KEY else 'Missing'}")
    
    # Load symbols from yaml
    yaml_path = os.path.join(project_root, "config", "longport_symbols.yaml")
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            symbols = config.get('symbols', [])
    except Exception as e:
        print(f"Error loading yaml: {e}")
        return

    # Filter out options (they usually have long names with numbers and C/P), keep only basic stocks for test
    # e.g., NVDA.US, AAPL.US
    stock_symbols = [s for s in symbols if len(s.split('.')[0]) <= 5]
    
    # Pick top 5 to test
    test_symbols = list(set(stock_symbols))[:5]
    
    # Add a known hot stock just in case the yaml ones don't return data
    if "TSLA.US" not in test_symbols:
        test_symbols.append("TSLA.US")
        
    print(f"\nTesting Adanos Sentiment API for {len(test_symbols)} symbols: {test_symbols}")
    print("-" * 50)
    
    for symbol in test_symbols:
        print(f"\nFetching sentiment for {symbol}...")
        try:
            # 1. Test the raw sync fetch just to see the raw data
            ticker = symbol.split('.')[0] if '.' in symbol else symbol
            raw_data = adanos_client._fetch_sentiment_sync(ticker)
            
            if raw_data and raw_data.get("found"):
                buzz = raw_data.get('buzz_score', 'N/A')
                bullish = raw_data.get('bullish_pct', 'N/A')
                bearish = raw_data.get('bearish_pct', 'N/A')
                print(f"  [Raw Data] Buzz: {buzz}, Bullish: {bullish}%, Bearish: {bearish}%")
            else:
                print(f"  [Raw Data] No sentiment data found or API error.")

            # 2. Test the async label generator
            labels = await adanos_client.get_sentiment_labels(symbol)
            print(f"  [Labels] {labels if labels else '无特殊标签'}")
            
        except Exception as e:
            print(f"  Error processing {symbol}: {e}")
            
    print("\n" + "-" * 50)
    print("Test completed.")

if __name__ == "__main__":
    asyncio.run(test_adanos())
