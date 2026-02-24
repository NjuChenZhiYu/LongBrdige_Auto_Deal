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
        # Check if existing context is valid for current loop
        if self._quote_ctx:
            try:
                # Check if context's loop matches current running loop
                # Try to access internal _loop (common in asyncio objects) or loop property
                ctx_loop = getattr(self._quote_ctx, "_loop", None) or getattr(self._quote_ctx, "loop", None)
                
                if ctx_loop:
                    current_loop = asyncio.get_running_loop()
                    if ctx_loop.is_closed() or ctx_loop != current_loop:
                        logger.warning(f"Context loop mismatch (ctx: {id(ctx_loop)}, cur: {id(current_loop)}) or closed. Resetting context.")
                        self._quote_ctx = None
            except Exception as e:
                logger.warning(f"Error checking context loop: {e}. Resetting context.")
                self._quote_ctx = None

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

    async def reset_context(self):
        """Reset contexts (e.g. for reconnection)"""
        if self._quote_ctx:
            # Try to close/exit if possible?
            # self._quote_ctx.exit() # If available
            self._quote_ctx = None
        if self._trade_ctx:
            self._trade_ctx = None
        logger.info("LongPort contexts reset")

# Global client instance
longport_client = LongPortClient()
