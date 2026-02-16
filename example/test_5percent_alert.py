import asyncio
import logging
from src.api.longport.client import longport_client
from src.api.longport.push.watchlist import handle_watchlist_quote
from src.api.longport.personalized.watchlist import get_watchlist
from src.api.dingtalk import DingTalkAlert

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_5percent_alert():
    logger.info("Starting 5% Threshold Alert Test...")
    
    # 1. Get Watchlist
    logger.info("Fetching watchlist...")
    watchlist_items = await get_watchlist()
    symbols = [item['symbol'] for item in watchlist_items]
    
    if not symbols:
        logger.warning("No symbols in watchlist.")
        return

    logger.info(f"Found {len(symbols)} symbols in watchlist.")

    # 2. Get Quotes
    logger.info("Fetching real-time quotes...")
    ctx = await longport_client.get_quote_context()
    quotes = await ctx.quote(symbols)
    
    # 3. Check Threshold (5%)
    # The user asked to "try to set threshold to 5% and push all stocks meeting the condition".
    # Since market might be closed or flat, we might not find any >5%.
    # But we run the check logic faithfully.
    
    threshold_config = {
        'price_change': 5.0
    }
    
    count_triggered = 0
    for quote in quotes:
        symbol = quote.symbol
        # Log current change for visibility
        if hasattr(quote, 'prev_close') and float(quote.prev_close) > 0:
            change_rate = ((float(quote.last_done) - float(quote.prev_close)) / float(quote.prev_close)) * 100
            logger.info(f"Checking {symbol}: Change={change_rate:.2f}%")
        else:
            logger.info(f"Checking {symbol}: Change=Unknown (No prev_close)")

        # Run alert logic
        triggered, alert_data = await handle_watchlist_quote(symbol, quote, threshold_config)
        if triggered:
            logger.info(f"--> ALERT TRIGGERED for {symbol}!")
            count_triggered += 1
            
    logger.info(f"Test complete. Triggered {count_triggered} alerts out of {len(quotes)} symbols.")

if __name__ == "__main__":
    try:
        asyncio.run(test_5percent_alert())
    except KeyboardInterrupt:
        pass
