from src.api.longport.client import longport_client
from src.utils.logger import logger

async def get_watchlist():
    """
    Get user's watchlist from LongPort.
    
    Returns:
        list[dict]: List of securities in watchlist.
        Example:
        [
            {"symbol": "US.AAPL", "name": "Apple Inc.", "watchlist_name": "My Watchlist"}
        ]
    """
    try:
        ctx = await longport_client.get_quote_context()
        # Use watchlist() method for v3 SDK
        groups = await ctx.watchlist()
        
        result = []
        for group in groups:
            for security in group.securities:
                result.append({
                    "symbol": security.symbol,
                    "name": security.name,
                    "watchlist_name": group.name
                })
        return result
    except Exception as e:
        logger.error(f"Failed to get watchlist: {e}")
        return []
