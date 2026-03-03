import logging
import asyncio
import time
import os
import yaml

# Redirect Futu logs to local logs directory (must be before importing futu)
# This fixes PermissionError on Windows AppData
futu_log_dir = os.path.join(os.getcwd(), "logs", "futu_appdata")
if not os.path.exists(futu_log_dir):
    try:
        os.makedirs(futu_log_dir)
    except:
        pass
os.environ["appdata"] = futu_log_dir

from futu import SubType, RET_OK
from src.api.futu.client import futu_client
from src.api.futu.callback import FutuQuoteCallback
from config.settings import Settings
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)

def fetch_initial_snapshot(ctx, symbols, db):
    """
    Fetch initial market snapshot and populate DB.
    """
    if not symbols:
        return

    logger.info(f"Fetching initial market snapshot for {len(symbols)} symbols...")
    # Split into chunks of 200 (limit for get_market_snapshot usually 200 or 400)
    chunk_size = 200
    Quote = Query()
    
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        try:
            ret, data = ctx.get_market_snapshot(chunk)
            if ret != RET_OK:
                logger.error(f"Failed to get snapshot for chunk {i}: {data}")
                continue
            
            # data is DataFrame
            count = 0
            for index, row in data.iterrows():
                code = row['code']
                last_price = float(row['last_price'])
                prev_close = float(row['prev_close_price'])
                
                change_amount = 0.0
                change_rate = 0.0
                if prev_close > 0:
                    change_amount = last_price - prev_close
                    change_rate = (change_amount / prev_close) * 100
                
                quote_data = {
                    'code': code,
                    'name': row.get('name', code),
                    'last_price': last_price,
                    'prev_close': prev_close,
                    'change_amount': change_amount,
                    'change_rate': change_rate,
                    'volume': int(row['volume']),
                    'update_time': row['update_time']
                }
                
                db.upsert(quote_data, Quote.code == code)
                count += 1
            
            logger.info(f"Updated DB with {count} snapshot records")
            
        except Exception as e:
            logger.error(f"Error fetching snapshot: {e}")

def sync_user_securities():
    """
    Fetch user securities from Futu and update futu_symbols.yaml
    """
    try:
        logger.info("Syncing user securities from Futu...")
        # Get HK symbols from "全部" group (default for All)
        # Note: If user has a specific group, we might need to change this.
        hk_symbols = futu_client.get_hk_user_securities("全部")
        
        if not hk_symbols:
            logger.warning("No HK symbols found in user security list or failed to fetch.")
            return

        # Load existing config to preserve thresholds
        config_path = Settings.FUTU_SYMBOLS_CONFIG_PATH
        current_config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f) or {}
        
        # Update symbols
        old_symbols = current_config.get('symbols', [])
        # Convert to list if it's not (though yaml load usually returns list)
        if not isinstance(old_symbols, list):
            old_symbols = []
            
        # Check if change is needed to avoid unnecessary writes
        if set(old_symbols) == set(hk_symbols):
            logger.info("User securities match local config. No update needed.")
            return

        current_config['symbols'] = hk_symbols
        
        # Save back to yaml
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, default_flow_style=False)
            
        logger.info(f"Updated futu_symbols.yaml with {len(hk_symbols)} symbols (was {len(old_symbols)})")
        
        # Update Settings in-memory
        Settings.FUTU_SYMBOLS_CONFIG = current_config
        
    except Exception as e:
        logger.error(f"Failed to sync user securities: {e}")

def run_futu_monitor():
    """
    Entry point for Futu monitoring process.
    """
    logger.info("Starting Futu Monitoring Task...")
    
    # Initialize TinyDB
    data_dir = os.path.join(os.getcwd(), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    db_path = os.path.join(data_dir, 'futu_quotes.json')
    db = TinyDB(db_path)
    
    # Create an event loop for async tasks (alerts)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Get Futu Context
        try:
            ctx = futu_client.get_quote_context(host=Settings.FUTU_HOST, port=Settings.FUTU_PORT)
        except Exception as e:
            logger.error(f"Failed to connect to Futu OpenD: {e}")
            logger.warning("Please ensure Futu OpenD is running and listening on the configured port.")
            time.sleep(10)
            raise

        # Sync user securities (Added step)
        sync_user_securities()

        # Set callback
        thresholds = Settings.FUTU_SYMBOLS_CONFIG.get('thresholds', {})
        handler = FutuQuoteCallback(loop, thresholds, db=db)
        ctx.set_handler(handler)
        
        # Subscribe to symbols
        symbols = Settings.FUTU_SYMBOLS_CONFIG.get('symbols', [])
        # Parse 'Code Name' format to get clean codes for snapshot
        clean_symbols = [s.split(' ')[0] if ' ' in s else s for s in symbols]
        
        if clean_symbols:
            logger.info(f"Subscribing to Futu symbols: {symbols}")
            # Subscribe to Quote using client wrapper for Market Routing
            ret, data = futu_client.subscribe(symbols, [SubType.QUOTE], is_first_push=True)
            if ret == RET_OK:
                logger.info(f"Successfully subscribed to Futu symbols")
                # Fetch initial snapshot to populate DB immediately
                fetch_initial_snapshot(ctx, clean_symbols, db)
            else:
                logger.error(f"Failed to subscribe: {data}")
        else:
            logger.warning("No Futu symbols configured in futu_symbols.yaml")
        
        # Keep running the event loop to process alerts
        logger.info("Futu Monitor is running (Press Ctrl+C to stop)")
        loop.run_forever()
            
    except Exception as e:
        logger.error(f"Futu Monitor crashed: {e}")
    except KeyboardInterrupt:
        logger.info("Futu Monitor stopping...")
    finally:
        if 'ctx' in locals():
            ctx.close()
        loop.close()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    run_futu_monitor()
