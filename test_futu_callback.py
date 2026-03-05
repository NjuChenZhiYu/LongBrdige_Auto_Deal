
import logging
import time
import sys
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append(os.getcwd())

# Ensure we can import futu
try:
    from futu import OpenQuoteContext, StockQuoteHandlerBase, RET_OK, SubType
except ImportError:
    print("Futu SDK not found. Install with pip install futu-api")
    sys.exit(1)

class TestHandler(StockQuoteHandlerBase):
    def on_recv_rsp(self, rsp_pb):
        ret_code, data, str_msg = super(TestHandler, self).on_recv_rsp(rsp_pb)
        if ret_code != RET_OK:
            logger.error(f"Callback Error: {str_msg}")
            return
        logger.info(f"Callback Received! {len(data)} rows")
        print(data)

def test_callback():
    host = '127.0.0.1'
    port = 45575
    
    try:
        logger.info(f"Connecting to {host}:{port}...")
        ctx = OpenQuoteContext(host=host, port=port)
        ctx.start()
        logger.info("Connected.")
        
        handler = TestHandler()
        ctx.set_handler(handler)
        logger.info("Handler set.")
        
        symbol = 'HK.00700' # Tencent
        logger.info(f"Subscribing to {symbol} (TICKER)...")
        # Try snapshot first
        logger.info("Testing get_market_snapshot...")
        ret, data = ctx.get_market_snapshot([symbol])
        if ret == RET_OK:
            logger.info(f"Snapshot Data: \n{data}")
        else:
            logger.error(f"Snapshot Failed: {data}")
            
        ret, data = ctx.subscribe([symbol], [SubType.QUOTE], is_first_push=True)
        
        logger.info(f"Subscribe Ret: {ret}")
        if ret == RET_OK:
            logger.info("Subscription successful.")
            if data is not None:
                logger.info(f"Initial data rows: {len(data)}")
            else:
                logger.info("Initial data is None")
        else:
            logger.info(f"Subscription failed: {data}")
            
        logger.info("Waiting for callbacks (30s)...")
        time.sleep(30)
        
        ctx.close()
        logger.info("Done.")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    test_callback()
