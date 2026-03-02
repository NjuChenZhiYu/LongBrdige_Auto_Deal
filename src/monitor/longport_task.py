import logging
import asyncio
from src.api.longport.client import longport_client
from src.monitor.watchlist_monitor import WatchlistMonitor
from src.monitor.option_monitor import OptionMonitor
from src.monitor.quote_monitor import subscribe_watchlist_quote
from longport.openapi import SubType

logger = logging.getLogger(__name__)

class LongPortMonitorTask:
    def __init__(self):
        self.watchlist_monitor = WatchlistMonitor()
        self.option_monitor = OptionMonitor()
        self.ctx = None

    def _on_quote_dispatch(self, symbol, event):
        """Dispatch quote event to monitors"""
        # Dispatch to OptionMonitor
        try:
            # Ensure OptionMonitor has the loop set if it wasn't already
            if not self.option_monitor.loop:
                 try:
                     self.option_monitor.loop = asyncio.get_running_loop()
                 except:
                     pass
            self.option_monitor._on_quote_update(symbol, event)
        except Exception as e:
            logger.error(f"OptionMonitor dispatch error: {e}")
            
        # Dispatch to WatchlistMonitor
        try:
            if not self.watchlist_monitor.loop:
                 try:
                     self.watchlist_monitor.loop = asyncio.get_running_loop()
                 except:
                     pass
            self.watchlist_monitor._on_quote(symbol, event)
        except Exception as e:
            logger.error(f"WatchlistMonitor dispatch error: {e}")

    async def start(self):
        logger.info("Starting LongPort Monitor Task...")
        
        # 0. Capture loop for monitors
        loop = asyncio.get_running_loop()
        self.watchlist_monitor.loop = loop
        self.option_monitor.loop = loop
        
        # 1. Get Context
        self.ctx = await longport_client.get_quote_context()
        
        # 2. Set Master Callback
        self.ctx.set_on_quote(self._on_quote_dispatch)
        
        # 3. Inject Context into Monitors
        self.watchlist_monitor.ctx = self.ctx
        self.option_monitor.ctx = self.ctx
        
        # 4. Initialize OptionMonitor (captures loop, sets running flag)
        await self.option_monitor.start(setup_context=False)
        
        # 5. Subscribe
        # OptionMonitor symbols
        option_symbols = list(set(self.option_monitor.monitored_options + self.option_monitor.monitored_stocks))
        
        # WatchlistMonitor symbols (subscribes to watchlist + config symbols)
        # subscribe_watchlist_quote uses the context to subscribe
        logger.info("Subscribing to Watchlist symbols...")
        watchlist_symbols = await subscribe_watchlist_quote(self.ctx)
        self.watchlist_monitor.subscribed_symbols = watchlist_symbols
        
        # Subscribe option symbols
        if option_symbols:
            logger.info(f"Subscribing to Option symbols: {option_symbols}")
            # Use client wrapper for Market Routing
            await longport_client.subscribe(self.ctx, option_symbols, [SubType.Quote])
            
        logger.info("LongPort Monitor Task started successfully.")
        
        # 6. Run WatchlistMonitor (blocks with infinite loop for periodic tasks)
        await self.watchlist_monitor.start(setup_context=False)

def run_monitor():
    """Entry point for LongPort process"""
    # Create new event loop for this process
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    task = LongPortMonitorTask()
    
    try:
        loop.run_until_complete(task.start())
    except KeyboardInterrupt:
        logger.info("LongPort Monitor stopping...")
    except Exception as e:
        logger.error(f"LongPort Monitor crashed: {e}")
    finally:
        loop.close()
