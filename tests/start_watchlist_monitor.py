import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.monitor.us_watchlist_monitor import USWatchlistMonitor

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("Starting Watchlist Monitor Example...")
    monitor = USWatchlistMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print(f"Error: {e}")
