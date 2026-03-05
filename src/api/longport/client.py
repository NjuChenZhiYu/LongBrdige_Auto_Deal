import asyncio
from typing import Optional, Any
from longport.openapi import Config, AsyncQuoteContext, AsyncTradeContext
from config.settings import Settings
from src.utils.logger import logger

from src.api.longport.personalized.watchlist import get_watchlist

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

    async def get_threshold_quotes(self, threshold: float = 0.0) -> list:
        """
        Get real-time quotes for US stocks from watchlist that exceed the threshold.
        
        Args:
            threshold (float): Price change percentage threshold. Default 0.0 (return all valid quotes).
            
        Returns:
            list: List of dicts with stock data [{'symbol':..., 'last_price':..., 'change_rate':...}]
        """
        try:
            # Get watchlist symbols (with deduplication)
            watchlist_items = await get_watchlist()
            symbols = list(set([item['symbol'] for item in watchlist_items if item['symbol'].endswith(".US")]))
            
            if not symbols:
                logger.warning(f"No US symbols in watchlist")
                return []
            
            # Fetch real-time quotes from LongPort
            ctx = await self.get_quote_context()
            quotes = await ctx.quote(symbols)
            
            if not quotes:
                logger.warning(f"No quotes returned for US market")
                return []
            
            # Filter stocks
            threshold_stocks = []
            seen_symbols = set()
            for q in quotes:
                if q is None: continue
                symbol = getattr(q, 'symbol', None)
                if not symbol or symbol in seen_symbols: continue
                
                prev_close = float(getattr(q, 'prev_close', 0) or 0)
                last_done = float(getattr(q, 'last_done', 0) or 0)
                
                if prev_close > 0:
                    change_rate = ((last_done - prev_close) / prev_close) * 100
                    
                    # If threshold is 0, return all; otherwise filter by absolute change
                    if threshold == 0 or abs(change_rate) >= threshold:
                        threshold_stocks.append({
                            'symbol': symbol,
                            'last_price': last_done,
                            'change_rate': change_rate,
                            'prev_close': prev_close
                        })
                        seen_symbols.add(symbol)
            
            return threshold_stocks
            
        except Exception as e:
            logger.error(f"Error fetching LongPort threshold quotes: {e}")
            return []

# Global client instance
longport_client = LongPortClient()
