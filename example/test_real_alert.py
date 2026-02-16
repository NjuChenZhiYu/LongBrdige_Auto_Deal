import asyncio
import logging
from src.api.longport.client import longport_client
from src.api.longport.push.watchlist import handle_watchlist_quote
from src.api.dingtalk import DingTalkAlert

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockQuote:
    def __init__(self, data):
        self.symbol = data.symbol
        self.last_done = data.last_done
        self.prev_close = data.prev_close
        self.open = data.open
        self.high = data.high
        self.low = data.low
        self.volume = data.volume
        self.turnover = data.turnover
        # Add bid/ask if available in snapshot, usually quote() returns basic info
        # If not, we can simulate or ignore spread check
        self.bid_price = 0
        self.ask_price = 0

async def test_real_alert():
    logger.info("Fetching real-time quote snapshot...")
    
    # 1. Get Context
    ctx = await longport_client.get_quote_context()
    
    # 2. Get Quote for AAPL
    symbol = "AAPL.US"
    quotes = await ctx.quote([symbol])
    
    if not quotes:
        logger.error("Failed to get quote for AAPL.US")
        return

    real_quote = quotes[0]
    logger.info(f"Got quote for {symbol}: Price={real_quote.last_done}, PrevClose={real_quote.prev_close}")
    
    # 3. Define Low Thresholds to force trigger
    test_config = {
        'price_change': 0.0001, # Extremely low to trigger change alert
        'spread': 0.0001
    }
    
    # 4. Process Quote
    # Convert SDK Quote object to what handle_watchlist_quote expects (PushQuote-like)
    # The SDK Quote object usually has same attributes as PushQuote for basic fields
    logger.info("Testing alert logic with real data...")
    triggered, alert_data = await handle_watchlist_quote(symbol, real_quote, test_config)
    
    if triggered:
        logger.info(f"SUCCESS: Alert triggered! Data: {alert_data}")
        logger.info("Check DingTalk for the actual message.")
    else:
        logger.error("FAILED: Alert not triggered even with low thresholds.")
        
if __name__ == "__main__":
    try:
        asyncio.run(test_real_alert())
    except KeyboardInterrupt:
        pass
