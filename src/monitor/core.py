import asyncio
from longport.openapi import SubType
from config.settings import Settings
from src.utils.logger import logger
from src.api.longport.client import longport_client
from src.api.longport.push.handler import push_handler

class Monitor:
    def __init__(self):
        self.ctx = None

    async def start(self):
        """Start the monitoring system"""
        logger.info(f"Monitored Symbols: {Settings.MONITOR_SYMBOLS}")
        
        try:
            self.ctx = await longport_client.get_quote_context()
            
            # Set callback
            self.ctx.set_on_quote(push_handler.on_quote)
            
            # Subscribe to quotes
            # Note: SubType.Quote is standard for basic price updates
            # is_first_push is not supported in 3.0.18
            await self.ctx.subscribe(Settings.MONITOR_SYMBOLS, [SubType.Quote])
            logger.info("Subscribed to quotes successfully.")
            
        except Exception as e:
            logger.critical(f"System crashed during startup: {e}")
            raise

    async def stop(self):
        logger.info("Stopping system...")
        # Add unsubscribe or context cleanup if SDK supports it
        pass
