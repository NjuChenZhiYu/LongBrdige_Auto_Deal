from datetime import datetime
from src.api.longport.client import longport_client
from src.utils.logger import logger

async def get_quote(symbols: list[str]):
    """
    Get real-time quotes for symbols.
    
    Args:
        symbols (list[str]): List of symbols (e.g. ["US.AAPL", "HK.00700"])
        
    Returns:
        dict: key is symbol, value is quote info
    """
    if not symbols:
        return {}
    
    try:
        ctx = await longport_client.get_quote_context()
        
        # Get quotes
        quotes = await ctx.quote(symbols)
        
        # Get static info for names
        static_infos = await ctx.static_info(symbols)
        name_map = {info.symbol: info.name_cn or info.name_en for info in static_infos}
        
        result = {}
        for q in quotes:
            last = float(q.last_done)
            prev = float(q.prev_close)
            change_rate = (last - prev) / prev if prev != 0 else 0
            
            result[q.symbol] = {
                "name": name_map.get(q.symbol, q.symbol),
                "last_price": last,
                "change_rate": "{:+.2%}".format(change_rate),  # Format as percentage with sign (e.g. +1.23%)
                "pre_close_price": prev,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        return result
    except Exception as e:
        logger.error(f"Failed to get quotes for {symbols}: {e}")
        return {}
