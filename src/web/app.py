import os
import yaml
import asyncio
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from flask import Flask, render_template, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from config.settings import Settings
from src.api.longport.client import longport_client
from src.api.longport.personalized.watchlist import get_watchlist
from src.api.longport.push.watchlist import handle_watchlist_quote
from longport.openapi import SubType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

CONFIG_PATH = os.path.join(os.getcwd(), 'config', 'symbols.yaml')
CST_TZ = dt_timezone(timedelta(hours=8))

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)

async def check_and_alert(send_alert: bool = False):
    """
    Check all monitored stocks and send alerts if thresholds are met.
    This function is used by both manual trigger and scheduled tasks.
    """
    logger.info(f"Starting check_and_alert (send_alert={send_alert})...")
    try:
        config = load_config()
        symbols = config.get('symbols', [])
        thresholds = config.get('thresholds', {})
        
        # Get all symbols (config + watchlist)
        watchlist_items = await get_watchlist()
        unique_symbols = set(symbols)
        for item in watchlist_items:
            unique_symbols.add(item['symbol'])
        all_symbols = list(unique_symbols)
        
        if not all_symbols:
            logger.info("No symbols to check.")
            return 0
            
        ctx = await longport_client.get_quote_context()
        quotes = await ctx.quote(all_symbols)
        
        count = 0
        for quote in quotes:
            symbol = quote.symbol
            # Check thresholds and optionally send alert
            triggered, _ = await handle_watchlist_quote(symbol, quote, thresholds, send_alert=send_alert)
            if triggered:
                count += 1
        
        logger.info(f"Check completed. Triggered alerts: {count}")
        return count
    except Exception as e:
        logger.error(f"Check and alert failed: {e}", exc_info=True)
        return 0

def scheduled_job():
    """Wrapper for scheduled task to run async code"""
    logger.info("Running scheduled alert check...")
    asyncio.run(check_and_alert(send_alert=True))

# Scheduler Setup
scheduler = BackgroundScheduler(timezone=CST_TZ)
# Schedule at 22:50 CST
scheduler.add_job(scheduled_job, 'cron', hour=22, minute=50)
# Schedule at 07:50 CST
scheduler.add_job(scheduled_job, 'cron', hour=7, minute=50)
scheduler.start()

async def get_longport_data(configured_symbols):
    """Fetch watchlist and quotes from LongPort"""
    try:
        # 1. Get LongPort Watchlist
        watchlist_items = await get_watchlist()
        
        unique_symbols = set(configured_symbols)
        watchlist_map = {}
        for item in watchlist_items:
            s = item['symbol']
            unique_symbols.add(s)
            watchlist_map[s] = item['name']
            
        all_symbols = list(unique_symbols)
        
        if not all_symbols:
            return []

        # 3. Get Real-time Quotes
        ctx = await longport_client.get_quote_context()
        quotes = await ctx.quote(all_symbols)
        
        result = []
        for q in quotes:
            symbol = q.symbol
            prev_close = float(q.prev_close)
            last_done = float(q.last_done)
            change_rate = 0.0
            if prev_close > 0:
                change_rate = ((last_done - prev_close) / prev_close) * 100
            
            result.append({
                'symbol': symbol,
                'name': watchlist_map.get(symbol, symbol), # Use symbol as name if not in watchlist map
                'price': last_done,
                'change_rate': change_rate,
                'is_watchlist': symbol in watchlist_map,
                'is_config': symbol in configured_symbols
            })
            
        return result
    except Exception as e:
        print(f"Error fetching data: {e}")
        # Return empty list or basic info for configured symbols if API fails
        return [{'symbol': s, 'name': s, 'price': 0, 'change_rate': 0} for s in configured_symbols]

@app.route('/')
async def index():
    config = load_config()
    symbols = config.get('symbols', [])
    thresholds = config.get('thresholds', {
        'price_change': Settings.PRICE_CHANGE_THRESHOLD
    })
    
    # Fetch real-time data
    market_data = await get_longport_data(symbols)
    
    return render_template('index.html', symbols=symbols, thresholds=thresholds, market_data=market_data)

from src.api.longport.push.watchlist import handle_watchlist_quote

@app.route('/update_thresholds', methods=['POST'])
def update_thresholds():
    config = load_config()
    try:
        price_change = float(request.form.get('price_change', 0))
        
        config['thresholds'] = {
            'price_change': price_change
        }
        save_config(config)
    except ValueError:
        pass # Handle invalid input
        
    return redirect(url_for('index'))

@app.route('/trigger_check', methods=['POST'])
def trigger_check():
    """Manual trigger to check current prices against thresholds and send alerts if matched"""
    try:
        asyncio.run(check_and_alert(send_alert=True))
    except Exception as e:
        print(f"Trigger check failed: {e}")

    return redirect(url_for('index'))

@app.route('/sync_watchlist', methods=['POST'])
def sync_watchlist():
    """Sync symbols.yaml with LongPort Watchlist"""
    try:
        async def run_sync():
            watchlist_items = await get_watchlist()
            symbols = [item['symbol'] for item in watchlist_items]
            return symbols
            
        new_symbols = asyncio.run(run_sync())
        
        if new_symbols:
            config = load_config()
            config['symbols'] = new_symbols
            save_config(config)
            logger.info(f"Synced {len(new_symbols)} symbols from LongPort watchlist.")
            
    except Exception as e:
        logger.error(f"Sync watchlist failed: {e}")
        
    return redirect(url_for('index'))

@app.route('/add_symbol', methods=['POST'])
def add_symbol():
    symbol = request.form.get('symbol').strip().upper()
    if symbol:
        config = load_config()
        symbols = config.get('symbols', [])
        if symbol not in symbols:
            symbols.append(symbol)
            config['symbols'] = symbols
            save_config(config)
    return redirect(url_for('index'))

@app.route('/remove_symbol', methods=['POST'])
def remove_symbol():
    symbol = request.form.get('symbol')
    config = load_config()
    symbols = config.get('symbols', [])
    if symbol in symbols:
        symbols.remove(symbol)
        config['symbols'] = symbols
        save_config(config)
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Use 0.0.0.0 to be accessible if needed, port 5001
    app.run(host='0.0.0.0', port=5001, debug=True)
