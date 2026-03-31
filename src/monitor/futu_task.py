import logging
import asyncio
import sys
from src.monitor.hk_watchlist_monitor import HKWatchlistMonitor

logger = logging.getLogger(__name__)

def run_futu_monitor():
    """
    Entry point for Futu monitoring process.
    """
    logger.info("Starting Futu Monitoring Task via HKWatchlistMonitor...")
    
    monitor = HKWatchlistMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}")

if __name__ == "__main__":
    from src.utils.logger import setup_logger
    logger = setup_logger("futu_task", "logs/monitor_futu.log")
    run_futu_monitor()
