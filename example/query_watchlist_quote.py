import asyncio
import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.longport.personalized import get_watchlist
from src.api.longport.pull import get_quote
from config.settings import Settings

async def main():
    print("Initializing LongBridge Client...")
    try:
        Settings.validate()
    except Exception as e:
        print(f"Configuration Error: {e}")
        return

    print("Fetching Watchlist...")
    watchlist = await get_watchlist()
    
    if not watchlist:
        print("Watchlist is empty or failed to fetch.")
        return

    print(f"Found {len(watchlist)} securities in watchlist.")
    
    # Extract unique symbols
    symbols = list(set([item['symbol'] for item in watchlist]))
    print(f"Querying quotes for {len(symbols)} symbols: {symbols}")
    
    quotes = await get_quote(symbols)
    
    print("\n--- Real-time Quotes ---")
    print(json.dumps(quotes, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"An error occurred: {e}")
