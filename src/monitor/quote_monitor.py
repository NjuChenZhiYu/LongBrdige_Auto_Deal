import logging
import asyncio
from typing import List, Optional
from longport.openapi import SubType, QuoteContext
from src.api.longport.client import LongPortClient
from src.api.longport.personalized.watchlist import get_watchlist
from config.settings import Settings

logger = logging.getLogger(__name__)

async def get_watchlist_symbols() -> List[str]:
    """Get unique symbols from watchlist"""
    try:
        watchlist_items = await get_watchlist()
        if not watchlist_items:
            # Fallback to configured symbols if watchlist fetch fails or is empty?
            # No, just return empty list and let caller decide.
            return []
        
        # Extract symbols and remove duplicates
        symbols = list(set([item['symbol'] for item in watchlist_items]))
        return symbols
    except Exception as e:
        logger.error(f"Error extracting watchlist symbols: {e}")
        return []

async def subscribe_watchlist_quote(ctx: QuoteContext, is_first_push: bool = True) -> List[str]:
    """
    Subscribe to watchlist quotes.
    
    :param ctx: Initialized QuoteContext
    :param is_first_push: Whether to push current quote immediately
    :return: List of subscribed symbols
    """
    try:
        # 1. Fetch watchlist symbols
        watchlist_symbols = await get_watchlist_symbols()
        
        # 2. Add monitored symbols from config/env
        config_symbols = Settings.MONITOR_SYMBOLS
        
        # Combine and deduplicate
        all_symbols = list(set(watchlist_symbols + config_symbols))
        
        if not all_symbols:
            logger.warning("No symbols to subscribe (Watchlist empty and MONITOR_SYMBOLS empty)")
            return []

        logger.info(f"Subscribing to {len(all_symbols)} symbols: {all_symbols}")
        
        # 3. Subscribe
        # SubType.Quote for real-time quote
        # Note: LongPort SDK 2.0+ might not support is_first_push in subscribe, checking docs or try/except
        try:
             # Try without is_first_push first as it is more likely to be compatible with 3.0.18
             await ctx.subscribe(all_symbols, [SubType.Quote])
        except TypeError:
             # Fallback if needed, though adapter should handle it
             logger.warning("Subscribe method failed, retrying with is_first_push.")
             await ctx.subscribe(all_symbols, [SubType.Quote], is_first_push=is_first_push)
        
        logger.info("Subscription request sent successfully")
        
        return all_symbols
    except Exception as e:
        logger.error(f"Failed to subscribe watchlist quotes: {e}")
        raise
