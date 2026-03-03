import asyncio
from typing import Optional, Any
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
                logger.info("Initializing LongPort AsyncQuoteContext...")
                # Native async context creation
                self._quote_ctx = await AsyncQuoteContext.create(self.config)
                logger.info("LongPort AsyncQuoteContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncQuoteContext: {e}")
                raise
        return self._quote_ctx

    async def get_trade_context(self):
        """Get or create AsyncTradeContext singleton"""
        if not Settings.ENABLE_TRADING:
            logger.warning("Trading is disabled in settings")
            return None
            
        if self._trade_ctx is None:
            try:
                logger.info("Initializing LongPort AsyncTradeContext...")
                self._trade_ctx = await AsyncTradeContext.create(self.config)
                logger.info("LongPort AsyncTradeContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncTradeContext: {e}")
                raise
        return self._trade_ctx

    async def reset_context(self):
        """Reset contexts (e.g. for reconnection)"""
        if self._quote_ctx:
            # Async context usually doesn't need explicit close if not running,
            # but ideally we should check if there's a close method.
            # LongPort SDK usually manages connection.
            self._quote_ctx = None
        if self._trade_ctx:
            self._trade_ctx = None
        logger.info("LongPort contexts reset")

    async def subscribe(self, ctx, symbols, sub_types):
        """
        Subscribe with market routing and permission isolation.
        Excludes HK symbols (starting with 'HK.').
        """
        # 1. Market Routing / Permission Isolation
        valid_symbols = []
        for s in symbols:
            # Check if it looks like a HK symbol (HK.xxxxx)
            if s.startswith("HK."):
                logger.warning(f"Market Routing: Symbol {s} excluded from LongPort subscription (HK market not supported)")
            else:
                valid_symbols.append(s)
        
        if not valid_symbols:
            logger.warning("No valid non-HK symbols to subscribe")
            return []

        # 2. Subscribe
        try:
            # ctx.subscribe is async
            return await ctx.subscribe(valid_symbols, sub_types)
        except Exception as e:
            logger.error(f"LongPort subscribe error: {e}")
            # Don't crash, return empty or re-raise if critical
            # Re-raising might be better for LongPort as it handles its own reconnections mostly,
            # but we want to avoid crashing the whole monitor task if one sub fails?
            # Actually, LongPort subscribe usually doesn't fail unless network is down.
            raise e

# Global client instance
longport_client = LongPortClient()
