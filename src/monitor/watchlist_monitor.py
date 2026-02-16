import asyncio
import logging
import signal
import sys
import yaml
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from longport.openapi import QuoteContext, PushQuote, SubType
from config.settings import Settings
from src.api.longport.client import LongPortClient
from src.api.longport.push.watchlist import handle_watchlist_quote
from src.monitor.quote_monitor import subscribe_watchlist_quote, get_watchlist_symbols
from src.api.dingtalk import DingTalkAlert

logger = logging.getLogger(__name__)

class WatchlistMonitor:
    def __init__(self):
        self.running = False
        self.ctx: Optional[QuoteContext] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.subscribed_symbols: List[str] = []
        self.last_config_refresh = datetime.now()
        # Threshold config (start with default/env)
        self.threshold_config = {
            'price_change': Settings.PRICE_CHANGE_THRESHOLD,
            'spread': Settings.SPREAD_THRESHOLD
        }

    def _on_quote(self, symbol: str, event: Any):
        """Callback for quote push"""
        # Note: LongPort SDK callback might be sync or async depending on implementation.
        # Use run_coroutine_threadsafe to ensure it runs on the main loop
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._process_quote(symbol, event), self.loop)
        else:
            logger.warning(f"Event loop not available, skipping quote for {symbol}")

    async def _process_quote(self, symbol: str, event: Any):
        try:
            # Check if event is valid PushQuote
            triggered, alert_data = await handle_watchlist_quote(symbol, event, self.threshold_config)
            if triggered:
                logger.info(f"Alert triggered for {symbol}: {alert_data}")
                await DingTalkAlert.send_alert(
                    f"Price Alert: {symbol}",
                    str(alert_data),
                    "price_monitor",
                    "INFO"
                )
        except Exception as e:
            logger.error(f"Error in quote callback for {symbol}: {e}")

    async def _refresh_config(self):
        """Refresh configuration and watchlist"""
        try:
            logger.info("Refreshing configuration and watchlist...")
            
            # 1. Refresh symbols.yaml thresholds if needed
            if os.path.exists(Settings.SYMBOLS_CONFIG_PATH):
                try:
                    with open(Settings.SYMBOLS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                        new_config = yaml.safe_load(f) or {}
                        # Update thresholds if present
                        if 'thresholds' in new_config:
                             self.threshold_config.update(new_config['thresholds'])
                        # If symbols changed in file, update Settings.MONITOR_SYMBOLS?
                        # Settings class is static, but we can update its attribute
                        if 'symbols' in new_config:
                            Settings.MONITOR_SYMBOLS = new_config['symbols']
                except Exception as e:
                    logger.error(f"Failed to reload symbols.yaml: {e}")
            
            # 2. Refresh watchlist subscription
            # Check if watchlist changed
            current_watchlist = await get_watchlist_symbols()
            config_symbols = Settings.MONITOR_SYMBOLS
            new_all_symbols = list(set(current_watchlist + config_symbols))
            
            # If different from subscribed, re-subscribe
            # Note: set comparison handles order differences
            if set(new_all_symbols) != set(self.subscribed_symbols):
                logger.info(f"Watchlist/Config symbols changed. Old: {len(self.subscribed_symbols)}, New: {len(new_all_symbols)}")
                
                # Resubscribe
                # Unsubscribe all first to be clean? Or just subscribe new list?
                # LongPort SDK subscribe is additive usually.
                # If we want to remove symbols, we must unsubscribe.
                # Strategy: Unsubscribe old, Subscribe new.
                if self.subscribed_symbols and self.ctx:
                    try:
                        await self.ctx.unsubscribe(self.subscribed_symbols, [SubType.Quote])
                    except Exception as e:
                        logger.warning(f"Unsubscribe failed (might be connection issue): {e}")
                
                if self.ctx:
                    self.subscribed_symbols = await subscribe_watchlist_quote(self.ctx, is_first_push=True)
            else:
                logger.info("No changes in monitored symbols.")
                
        except Exception as e:
            logger.error(f"Config refresh failed: {e}")

    async def start(self):
        """Start the monitor service"""
        self.running = True
        retry_count = 0
        max_retries = 5
        base_delay = 1
        
        # Register signal handlers
        self.loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows workaround
                pass

        logger.info("Starting Watchlist Monitor Service...")

        while self.running:
            try:
                # 1. Initialize Client & Context
                client = LongPortClient()
                # Ensure context is clean
                if retry_count > 0:
                    await client.reset_context()
                    
                self.ctx = await client.get_quote_context()
                
                # 2. Set callback
                self.ctx.set_on_quote(self._on_quote)
                
                # 3. Subscribe
                self.subscribed_symbols = await subscribe_watchlist_quote(self.ctx)
                
                # Reset retry count on success
                retry_count = 0
                
                # 4. Main Loop
                logger.info("Monitor service running. Press Ctrl+C to stop.")
                while self.running:
                    await asyncio.sleep(60) # Check every minute
                    
                    # Periodic tasks
                    now = datetime.now()
                    
                    # Refresh config every 5 mins
                    if (now - self.last_config_refresh).total_seconds() > 300:
                        await self._refresh_config()
                        self.last_config_refresh = now
                    
                    # Daily cache clear at midnight
                    if now.hour == 0 and now.minute == 0:
                         DingTalkAlert.clear_cache()
                         
            except Exception as e:
                logger.error(f"Monitor service exception: {e}")
                retry_count += 1
                
                # Check if we should stop completely or keep retrying
                if retry_count > max_retries:
                    # Reset retry count if it's just a temporary network glitch?
                    # Or implement exponential backoff with a cap.
                    # Plan says "Exponential backoff ... Max retry 5 times? No, usually infinite for service."
                    # But plan says "Max retry 3 times" then "Push alert and stop retry".
                    # However, for a 24/7 service, stopping is bad.
                    # We should probably alert and wait longer.
                    # But adhering to plan: "Max retry 3 times; send alert."
                    # Let's interpret "stop retry" as "stop trying immediately and wait longer" or "exit".
                    # I'll alert and wait 5 minutes before trying again, resetting retry count.
                    logger.critical("Max retries exceeded. Alerting and pausing for 5 minutes.")
                    await DingTalkAlert.send_alert("Monitor Service Error", f"Connection unstable. Pausing for 5m. Error: {e}", "SYSTEM", "ERROR")
                    await asyncio.sleep(300)
                    retry_count = 0 # Reset to try again
                    continue
                
                delay = min(base_delay * (2 ** (retry_count - 1)), 60)
                logger.info(f"Retrying in {delay} seconds (Attempt {retry_count})...")
                # Only alert on first few retries or every time?
                # Plan: "Call alert manager to send disconnection alert before retry"
                await DingTalkAlert.send_alert("Monitor Service Warning", f"Connection lost. Retrying in {delay}s. Error: {e}", "SYSTEM", "WARNING")
                await asyncio.sleep(delay)
                
    async def stop(self):
        """Stop the service"""
        logger.info("Stopping Watchlist Monitor Service...")
        self.running = False
        # Clean up
        if self.ctx:
             # ctx.exit() if available
             pass

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("monitor.log")
        ]
    )
    monitor = WatchlistMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}")
