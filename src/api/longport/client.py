import asyncio
from longport.openapi import Config, AsyncQuoteContext, AsyncTradeContext
from config.settings import Settings
from src.utils.logger import logger

class LongPortClient:
    _instance = None
    _quote_ctx = None
    _trade_ctx = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LongPortClient, cls).__new__(cls)
        return cls._instance

    @property
    def config(self):
        return Config(
            app_key=Settings.LONGPORT_APP_KEY,
            app_secret=Settings.LONGPORT_APP_SECRET,
            access_token=Settings.LONGPORT_ACCESS_TOKEN
        )

    async def get_quote_context(self):
        """Get or create AsyncQuoteContext singleton"""
        if self._quote_ctx is None:
            try:
                self._quote_ctx = await AsyncQuoteContext.create(self.config)
                logger.info("LongPort AsyncQuoteContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncQuoteContext: {e}")
                raise
        return self._quote_ctx

    async def get_trade_context(self):
        """Get or create AsyncTradeContext singleton (if trading enabled)"""
        if not Settings.ENABLE_TRADING:
            logger.warning("Trading is disabled in settings")
            return None
            
        if self._trade_ctx is None:
            try:
                self._trade_ctx = await AsyncTradeContext.create(self.config)
                logger.info("LongPort AsyncTradeContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncTradeContext: {e}")
                raise
        return self._trade_ctx

# Global client instance
longport_client = LongPortClient()
