import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.api.longport.client import longport_client
from src.api.longport.personalized.watchlist import get_watchlist

async def main():
    print("Initializing LongPort Client...")
    try:
        ctx = await longport_client.get_quote_context()
        print(f"Client initialized successfully. Context: {ctx}")
    except Exception as e:
        print(f"ERROR initializing client: {e}")
        return

    print("Fetching Watchlist...")
    try:
        watchlist = await get_watchlist()
        print(f"Watchlist fetched. Count: {len(watchlist)}")
        for item in watchlist:
            print(f" - {item}")
    except Exception as e:
        print(f"ERROR fetching watchlist: {e}")

if __name__ == "__main__":
    asyncio.run(main())
