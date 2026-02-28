
import asyncio
import logging
from src.api.longport.client import longport_client
from config.settings import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_quote():
    try:
        ctx = await longport_client.get_quote_context()
        
        # Get option chain for AAPL
        logger.info("Getting option chain for AAPL.US...")
        expiry_date = await ctx.option_chain_expiry_date_list("AAPL.US")
        if not expiry_date:
            logger.warning("No expiry dates found for AAPL.US")
            return
            
        first_expiry = expiry_date[0]
        logger.info(f"Using expiry date: {first_expiry}")
        
        chain = await ctx.option_chain_info_by_date("AAPL.US", first_expiry)
        if not chain:
            logger.warning("No option chain found.")
            return
            
        first_option = chain[0]
        logger.info(f"First option info: {dir(first_option)}")
        
        # Try to guess symbol attribute
        symbol = getattr(first_option, 'call_symbol', None) or getattr(first_option, 'put_symbol', None)
        if not symbol:
             logger.warning("Could not find symbol in option info")
             return

        logger.info(f"Found option symbol: {symbol}")
        
        logger.info(f"Fetching quote for {symbol}...")
        quotes = await ctx.option_quote([symbol]) # Use option_quote method if available, else quote

        
        if not quotes:
            logger.warning("No quote returned.")
            return

        q = quotes[0]
        logger.info(f"Quote Type: {type(q)}")
        logger.info(f"Dir(quote): {dir(q)}")
        
        # Check for Greeks and other fields
        fields = [
            'symbol', 'last_done', 'prev_close', 'volume', 'turnover', 
            'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho',
            'open_interest'
        ]
        
        for f in fields:
            val = getattr(q, f, 'N/A')
            logger.info(f"{f}: {val}")

    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_quote())
