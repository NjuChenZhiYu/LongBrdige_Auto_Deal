import logging
import datetime
import asyncio
import time
import os
import yaml
import threading
from typing import Dict, Tuple, Optional, List
from tinydb import TinyDB, Query

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
from src.monitor.base_monitor import BaseMonitor
from src.api.futu.client import futu_client
from src.api.futu.callback import FutuQuoteCallback
from src.api.dingtalk import DingTalkAlert
from src.api.feishu import FeishuAlert
from src.services.signal_recorder import signal_recorder
from config.settings import Settings

logger = logging.getLogger(__name__)

class HKWatchlistMonitor(BaseMonitor):
    def __init__(self):
        super().__init__()
        self.running = False
        self.ctx = None
        self.loop = None
        self.db = None
        self.db_lock = threading.Lock()
        
    @staticmethod
    async def handle_quote_alert(
        symbol: str, 
        last_price: float, 
        prev_close: float, 
        threshold_config: Dict, 
        market_type: str = "US",
        send_alert: bool = False,
        volume: int = 0,
        turnover: float = 0.0
    ) -> Tuple[bool, Dict]:
        """
        Generic handler for quote alerts with LLM analysis. Checks thresholds and sends alerts if triggered.
        Records alert to SignalRecorder for daily report generation.
        
        :param symbol: Stock symbol (e.g., 'AAPL', 'HK.00700')
        :param last_price: Current price
        :param prev_close: Previous closing price
        :param threshold_config: Configuration for thresholds (e.g., {'price_change': 2.0})
        :param market_type: Market identifier for the alert message (e.g., 'US', 'HK')
        :param send_alert: Whether to actually send the alert
        :param volume: Trading volume
        :param turnover: Trading turnover
        :return: (triggered, alert_data)
        """
        triggered = False
        alert_data = {}
        current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            if prev_close > 0:
                change_rate = ((last_price - prev_close) / prev_close) * 100
                
                # Get threshold from config or default (5.0% as a fallback default)
                price_change_threshold = threshold_config.get('price_change', 5.0)
                
                if abs(change_rate) >= price_change_threshold:
                    direction = "涨" if change_rate > 0 else "跌"
                    market_name = "美股" if market_type == "US" else "港股" if market_type == "HK" else market_type
                    
                    # Record alert to SignalRecorder for daily report
                    signal_recorder.add_stock_alert({
                        "symbol": symbol,
                        "market_type": market_type,
                        "last_price": last_price,
                        "change_rate": change_rate,
                        "volume": volume,
                        "turnover": turnover,
                        "timestamp": current_time_str
                    })
                    
                    # LLM analysis for individual stocks is DEPRECATED/REMOVED to prevent token burnout.
                    # Only basic alerts are sent if send_alert is True.
                    
                    title = f"[{market_type} Alert] {symbol} {direction}幅≥{price_change_threshold}%"
                    content = f"""### {market_name}价格异动告警
* **标的**：{symbol}
* **最新价**：{last_price}
* **涨跌幅**：{change_rate:.2f}% (昨收：{prev_close})
* **触发规则**：{direction}幅≥{price_change_threshold}%
* **更新时间**：{current_time_str}
* **Keywords**: {market_type}, Alert, {market_name}, 监控, 告警
"""
                    
                    # Asynchronous alert sending
                    reason_suffix = "rise" if change_rate > 0 else "fall"
                    
                    if send_alert:
                        if market_type == "HK":
                            # Use Feishu for HK market
                            feishu_content = f"{content}\n\n[Feishu Alert Channel]"
                            await FeishuAlert.send_alert(title, feishu_content)
                            logger.info(f"Feishu alert sent for {symbol}: {change_rate:.2f}%")
                        else:
                            # Use DingTalk for other markets (US)
                            await DingTalkAlert.send_alert(title, content, symbol, f"price_change_{reason_suffix}")
                            logger.info(f"DingTalk alert sent for {symbol}: {change_rate:.2f}%")
                    else:
                        logger.info(f"Alert condition met for {symbol} ({change_rate:.2f}%), but sending skipped (send_alert=False)")
                        
                    triggered = True
                    alert_data['price_change'] = change_rate
                    
        except Exception as e:
            logger.error(f"Error in handle_quote_alert for {symbol}: {e}")
            return False, {}

        return triggered, alert_data

    def fetch_initial_snapshot(self, ctx, symbols):
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
                    
                    try:
                        with self.db_lock:
                            self.db.upsert(quote_data, Quote.code == code)
                    except Exception as e:
                        logger.error(f"Error updating DB in fetch_initial_snapshot: {e}")
                    count += 1
                
                logger.info(f"Updated DB with {count} snapshot records")
                
            except Exception as e:
                logger.error(f"Error fetching snapshot: {e}")

    def sync_user_securities(self):
        """
        Fetch user securities from Futu and update futu_symbols.yaml
        """
        try:
            logger.info("Syncing user securities from Futu...")
            # Get HK symbols from "全部" group (default for All)
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

    async def start(self):
        """
        Start the HK Watchlist Monitor service.
        """
        logger.info("Starting HK Watchlist Monitor Service...")
        self.running = True
        
        # Initialize TinyDB
        data_dir = os.path.join(os.getcwd(), 'data')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        db_path = os.path.join(data_dir, 'futu_quotes.json')
        self.db = TinyDB(db_path)
        
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
        try:
            # Get Futu Context
            try:
                self.ctx = futu_client.get_quote_context(host=Settings.FUTU_HOST, port=Settings.FUTU_PORT)
            except Exception as e:
                logger.error(f"Failed to connect to Futu OpenD: {e}")
                logger.warning("Please ensure Futu OpenD is running and listening on the configured port.")
                # We don't raise here to allow retry logic if we wanted, but for now we'll fail fast as per original logic
                raise

            # Sync user securities
            self.sync_user_securities()

            # Set callback
            thresholds = Settings.FUTU_SYMBOLS_CONFIG.get('thresholds', {})
            # Pass handle_quote_alert as the alert handler and the db_lock
            handler = FutuQuoteCallback(
                self.loop, 
                thresholds, 
                db=self.db, 
                alert_handler=self.handle_quote_alert,
                db_lock=self.db_lock
            )
            self.ctx.set_handler(handler)
            
            # Subscribe to symbols
            symbols = Settings.FUTU_SYMBOLS_CONFIG.get('symbols', [])
            clean_symbols = [s.split(' ')[0] if ' ' in s else s for s in symbols]
            
            if clean_symbols:
                logger.info(f"Subscribing to Futu symbols: {symbols}")
                ret, data = futu_client.subscribe(symbols, [SubType.QUOTE], is_first_push=True)
                if ret == RET_OK:
                    logger.info(f"Successfully subscribed to Futu symbols")
                    # Fetch initial snapshot
                    self.fetch_initial_snapshot(self.ctx, clean_symbols)
                else:
                    logger.error(f"Failed to subscribe: {data}")
            else:
                logger.warning("No Futu symbols configured in futu_symbols.yaml")
                
            # Main loop
            logger.info("HK Monitor is running...")
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"HK Monitor crashed: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the service"""
        logger.info("Stopping HK Watchlist Monitor Service...")
        self.running = False
        if self.ctx:
            self.ctx.close()
            self.ctx = None
        if self.db:
            self.db.close()
            self.db = None
