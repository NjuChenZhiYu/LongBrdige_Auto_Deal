import asyncio
import functools
from typing import Optional, Any
from longport.openapi import Config, QuoteContext, TradeContext
import functools
from typing import Optional, Any
from longport.openapi import Config, QuoteContext, TradeContext
import functools
from typing import Optional, Any
from longport.openapi import Config, QuoteContext, TradeContext
from config.settings import Settings
from src.utils.logger import logger

class AsyncContextAdapter:
    """
    Adapter to wrap synchronous LongPort Contexts into async-compatible interface.
    Uses asyncio.to_thread (or run_in_executor) to offload blocking calls.
    """
    def __init__(self, ctx: Any):
        self._ctx = ctx

    async def _run_sync(self, func_name: str, *args, **kwargs):
        try:
            func = getattr(self._ctx, func_name)
            # partial is needed because to_thread/run_in_executor expects a callable
            # to_thread (Py3.9+) is simpler, but run_in_executor is more compatible
            if hasattr(asyncio, 'to_thread'):
                return await asyncio.to_thread(func, *args, **kwargs)
            else:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
        except Exception as e:
            logger.error(f"Error executing sync method '{func_name}' in thread: {e}", exc_info=True)
            raise

    # Explicitly wrap common methods to provide IDE hints and clearer code
    async def quote(self, symbols):
        return await self._run_sync('quote', symbols)

    async def subscribe(self, symbols, sub_types, is_first_push=False):
        # v3.0.18 sync subscribe does NOT support is_first_push
        # We ignore this parameter to maintain compatibility with older SDK
        if is_first_push:
            logger.debug("AsyncContextAdapter: Dropping is_first_push=True for v3 compatibility")
        return await self._run_sync('subscribe', symbols, sub_types)

    async def unsubscribe(self, symbols, sub_types):
        return await self._run_sync('unsubscribe', symbols, sub_types)
    
    async def static_info(self, symbols):
        return await self._run_sync('static_info', symbols)
        
    async def watchlist(self):
        return await self._run_sync('watchlist')
        
    async def history_candlesticks_by_offset(self, symbol, period, adjust_type, forward, count, offset=None):
        return await self._run_sync('history_candlesticks_by_offset', symbol, period, adjust_type, forward, count, offset)

    # For callback setters, we just pass through because they usually just register a function
    # and don't block significantly.
    def set_on_quote(self, callback):
        return self._ctx.set_on_quote(callback)
        
    def set_on_trades(self, callback):
        return self._ctx.set_on_trades(callback)
        
    # Delegate other attributes
    def __getattr__(self, name):
        return getattr(self._ctx, name)


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
        """Get or create QuoteContext singleton (wrapped in Adapter)"""
        # Note: Sync Context doesn't have an event loop to check against
        if self._quote_ctx is None:
            try:
                logger.info("Initializing LongPort QuoteContext (Sync->Async Adapter)...")
                # Create context in thread to avoid blocking if it connects immediately
                def _create():
                    return QuoteContext(self.config)
                
                if hasattr(asyncio, 'to_thread'):
                    ctx = await asyncio.to_thread(_create)
                else:
                    ctx = await asyncio.get_running_loop().run_in_executor(None, _create)
                    
                self._quote_ctx = AsyncContextAdapter(ctx)
                logger.info("LongPort QuoteContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize QuoteContext: {e}")
                raise
        return self._quote_ctx

    async def get_trade_context(self):
        """Get or create TradeContext singleton (wrapped in Adapter)"""
        if not Settings.ENABLE_TRADING:
            logger.warning("Trading is disabled in settings")
            return None
            
        if self._trade_ctx is None:
            try:
                logger.info("Initializing LongPort TradeContext (Sync->Async Adapter)...")
                def _create():
                    return TradeContext(self.config)
                    
                if hasattr(asyncio, 'to_thread'):
                    ctx = await asyncio.to_thread(_create)
                else:
                    ctx = await asyncio.get_running_loop().run_in_executor(None, _create)
                    
                self._trade_ctx = AsyncContextAdapter(ctx)
                logger.info("LongPort TradeContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize TradeContext: {e}")
                raise
        return self._trade_ctx

    async def reset_context(self):
        """Reset contexts (e.g. for reconnection)"""
        if self._quote_ctx:
            # Sync context usually doesn't need explicit close, or we can look for exit/close method
            # if hasattr(self._quote_ctx._ctx, 'exit'): self._quote_ctx._ctx.exit()
            self._quote_ctx = None
        if self._trade_ctx:
            self._trade_ctx = None
        logger.info("LongPort contexts reset")

# Global client instance
longport_client = LongPortClient()
