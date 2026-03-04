import logging
import asyncio
from futu import StockQuoteHandlerBase, RET_OK
from src.monitor.utils import handle_quote_alert
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)

class FutuQuoteCallback(StockQuoteHandlerBase):
    """
    Callback handler for Futu quote updates.
    """
    def __init__(self, loop, thresholds, db=None):
        """
        Initialize the callback handler.
        
        :param loop: The asyncio event loop to run async tasks in.
        :param thresholds: The threshold configuration dictionary.
        :param db: The TinyDB instance for storing quotes.
        """
        self.loop = loop
        self.thresholds = thresholds
        self.db = db
        self.Quote = Query()
        super().__init__()

    def on_recv_rsp(self, rsp_pb):
        """
        Callback method when quote data is received.
        """
        ret_code, data, str_msg = super(FutuQuoteCallback, self).on_recv_rsp(rsp_pb)
        
        if ret_code != RET_OK:
            logger.error(f"Futu Quote Callback Error: {str_msg}")
            return
        
        # logger.info(f"Received quote data for {len(data)} symbols") # Verbose logging
        
        # data is a pandas DataFrame
        try:
            for index, row in data.iterrows():
                code = row['code']
                last_price = float(row['last_price'])
                
                # Check for previous close price column
                prev_close = 0.0
                if 'prev_close_price' in row:
                    prev_close = float(row['prev_close_price'])
                
                # Update TinyDB if available
                if self.db:
                    # If prev_close is missing in push, try to get from DB
                    if prev_close <= 0:
                        existing = self.db.get(self.Quote.code == code)
                        if existing and 'prev_close' in existing:
                            prev_close = float(existing['prev_close'])

                    # Calculate change rate
                    change_rate = 0.0
                    change_amount = 0.0
                    if prev_close > 0:
                        change_amount = last_price - prev_close
                        change_rate = (change_amount / prev_close) * 100
                    
                    volume = int(row.get('volume', 0))
                    
                    # Prepare update data
                    quote_data = {
                        'code': code,
                        'last_price': last_price,
                        'change_amount': change_amount,
                        'change_rate': change_rate,
                        'update_time': row.get('data_time', '') or row.get('time_key', '')
                    }
                    
                    # Only update fields that exist or matter
                    if prev_close > 0:
                        quote_data['prev_close'] = prev_close
                    if volume > 0:
                        quote_data['volume'] = volume
                    if 'name' in row:
                        quote_data['name'] = row['name']

                    self.db.upsert(quote_data, self.Quote.code == code)

                # Determine market type from code (e.g., HK.00700 -> HK, US.AAPL -> US)
                market_type = "HK"
                if "US." in code:
                    market_type = "US"
                elif "SH." in code or "SZ." in code:
                    market_type = "CN"
                
                # Get name for display
                name = row.get('name', '')
                if not name and self.db:
                    # Try to find name in DB
                    existing = self.db.get(self.Quote.code == code)
                    if existing:
                        name = existing.get('name', '')
                
                display_symbol = f"{code} {name}" if name and name != code else code

                # Dispatch the alert check to the asyncio loop
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        handle_quote_alert(
                            symbol=display_symbol,
                            last_price=last_price,
                            prev_close=prev_close,
                            threshold_config=self.thresholds,
                            market_type=market_type,
                            send_alert=True
                        ),
                        self.loop
                    )
                else:
                    logger.warning("Event loop is not running, skipping alert check")
                    
        except Exception as e:
            logger.error(f"Error processing Futu quote data: {e}")
