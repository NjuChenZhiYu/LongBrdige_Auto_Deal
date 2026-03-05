import os
import yaml
import asyncio
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from flask import Flask, render_template, request, redirect, url_for, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from config.settings import Settings
from src.api.longport.client import longport_client
from src.api.longport.personalized.watchlist import get_watchlist
from src.api.longport.push.watchlist import handle_watchlist_quote
from longport.openapi import SubType
from tinydb import TinyDB, Query
from src.api.notification import AlertManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

CONFIG_PATH = os.path.join(os.getcwd(), 'config', 'symbols.yaml')
FUTU_CONFIG_PATH = Settings.FUTU_SYMBOLS_CONFIG_PATH
FUTU_DB_PATH = os.path.join(os.getcwd(), 'data', 'futu_quotes.json')

CST_TZ = dt_timezone(timedelta(hours=8))

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)

def load_futu_config():
    if os.path.exists(FUTU_CONFIG_PATH):
        with open(FUTU_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_futu_config(config):
    with open(FUTU_CONFIG_PATH, 'w', encoding='utf-8') as f:
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

import threading
from src.monitor.option_monitor import option_monitor
from src.services.llm_analyst import llm_analyst

def run_async_loop(coro):
    """Helper to run a coroutine in a new event loop in a thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.run_forever()

def start_option_monitor():
    """Start option monitor in background thread"""
    t = threading.Thread(target=run_async_loop, args=(option_monitor.start(),), daemon=True)
    t.start()
    logger.info("Option Monitor thread started")

def scheduled_report_job():
    """Wrapper for scheduled report generation - generates live reports for both markets"""
    logger.info("Running scheduled live report generation...")
    # Generate live reports for both US and HK markets (same as manual button)
    asyncio.run(llm_analyst.generate_longport_us_report())
    asyncio.run(llm_analyst.generate_futu_hk_report())

# Scheduler Setup
scheduler = BackgroundScheduler(timezone=CST_TZ)
# Existing alerts
scheduler.add_job(scheduled_job, 'cron', hour=22, minute=50)
scheduler.add_job(scheduled_job, 'cron', hour=7, minute=50)

# LLM Report
scheduler.add_job(scheduled_report_job, 'cron', hour=22, minute=50)
scheduler.add_job(scheduled_report_job, 'cron', hour=7, minute=50)

scheduler.start()

# Start Option Monitor
start_option_monitor()

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

def get_futu_quotes():
    """Fetch Futu quotes from TinyDB"""
    try:
        db = TinyDB(FUTU_DB_PATH)
        quotes = db.all()
        db.close()
        return quotes
    except Exception as e:
        logger.error(f"Error reading Futu DB: {e}")
        return []

@app.route('/')
async def index():
    try:
        # LongPort Data
        config = load_config()
        symbols = config.get('symbols', [])
        thresholds = config.get('thresholds', {
            'price_change': Settings.PRICE_CHANGE_THRESHOLD
        })
        market_data = await get_longport_data(symbols)
        
        # Futu Data
        futu_config = load_futu_config()
        futu_symbols = futu_config.get('symbols', [])
        futu_thresholds = futu_config.get('thresholds', {})
        futu_quotes = get_futu_quotes()
        
        return render_template('index.html', 
                               symbols=symbols, 
                               thresholds=thresholds, 
                               market_data=market_data,
                               futu_symbols=futu_symbols,
                               futu_thresholds=futu_thresholds,
                               futu_quotes=futu_quotes)
    except Exception as e:
        logger.error(f"Error in index route: {e}", exc_info=True)
        return f"Internal Server Error: {e}", 500

@app.route('/api/futu/quotes')
def api_futu_quotes():
    return jsonify(get_futu_quotes())

from src.api.futu.client import futu_client
from src.monitor.utils import handle_quote_alert

@app.route('/update_futu_thresholds', methods=['POST'])
def update_futu_thresholds():
    try:
        futu_config = load_futu_config()
        
        # Update global price change threshold
        price_change = request.form.get('price_change')
        if price_change:
            if 'thresholds' not in futu_config:
                futu_config['thresholds'] = {}
            futu_config['thresholds']['price_change'] = float(price_change)
        
        # Remove individual symbol thresholds logic as per request for unified setting
        # We can optionally clear other keys if needed, but keeping them harmless is safer for now.
                
        save_futu_config(futu_config)
    except ValueError:
        pass # Handle invalid input
        
    return redirect(url_for('index'))

@app.route('/sync_futu_watchlist', methods=['POST'])
def sync_futu_watchlist():
    """Sync futu_symbols.yaml with Futu Watchlist"""
    try:
        # Initialize client if needed
        futu_client.get_quote_context(host=Settings.FUTU_HOST, port=Settings.FUTU_PORT)
        
        hk_symbols = futu_client.get_hk_user_securities("全部")
        
        if hk_symbols:
            config = load_futu_config()
            config['symbols'] = hk_symbols
            save_futu_config(config)
            logger.info(f"Synced {len(hk_symbols)} Futu symbols.")
            
    except Exception as e:
        logger.error(f"Sync Futu watchlist failed: {e}")
        
    return redirect(url_for('index'))

async def check_futu_alerts(send_alert=False):
    quotes = get_futu_quotes()
    config = load_futu_config()
    thresholds = config.get('thresholds', {})
    
    count = 0
    for q in quotes:
        code = q['code']
        name = q.get('name', '')
        symbol = f"{code} {name}" if name and name != code else code
        last_price = q['last_price']
        prev_close = q['prev_close']
        volume = q.get('volume', 0)
        # Calculate approximate turnover (volume * price)
        turnover = volume * last_price if volume and last_price else 0
        
        triggered, _ = await handle_quote_alert(
            symbol=symbol, 
            last_price=last_price, 
            prev_close=prev_close, 
            threshold_config=thresholds, 
            market_type="HK", 
            send_alert=send_alert,
            volume=volume,
            turnover=turnover
        )
        if triggered:
            count += 1
    return count

@app.route('/trigger_futu_check', methods=['POST'])
def trigger_futu_check():
    """Manual trigger to check Futu prices against thresholds and send alerts if matched"""
    try:
        asyncio.run(check_futu_alerts(send_alert=True))
    except Exception as e:
        logger.error(f"Futu trigger check failed: {e}")
    return redirect(url_for('index'))

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

@app.route('/test_alert', methods=['POST'])
def test_alert():
    """Send test alerts to verify configuration"""
    try:
        # Test DingTalk (US Market default)
        AlertManager.send_dingtalk("Test Alert (DingTalk): This is a test message to verify DingTalk configuration.")
        
        # Test Feishu (HK Market default)
        AlertManager.send_feishu("This is a test message to verify Feishu configuration.", title="Test Alert (Feishu)")
        
        logger.info("Test alerts sent.")
    except Exception as e:
        logger.error(f"Test alert failed: {e}")
    return redirect(url_for('index'))

@app.route('/generate_ai_report', methods=['POST'])
def generate_ai_report():
    """Generate AI analysis report for current watchlist stocks"""
    try:
        market_type = request.form.get('market_type', 'US')
        logger.info(f"Manual AI report generation triggered for {market_type} market")
        
        # Run the report generation with live data
        if market_type == 'US':
            asyncio.run(llm_analyst.generate_longport_us_report())
        elif market_type == 'HK':
            asyncio.run(llm_analyst.generate_futu_hk_report())
        else:
            logger.warning(f"Unknown market type: {market_type}")
            return redirect(url_for('index'))
        
        logger.info(f"AI report for {market_type} generated and sent successfully")
    except Exception as e:
        logger.error(f"AI report generation failed: {e}")
    return redirect(url_for('index'))

@app.route('/generate_futu_kimi_report', methods=['POST'])
def generate_futu_kimi_report():
    """Generate Kimi AI analysis report specifically for Futu HK stocks"""
    try:
        logger.info("Manual Futu Kimi report generation triggered")
        
        # Run the Futu HK report generation using Kimi
        asyncio.run(llm_analyst.generate_futu_hk_report())
        
        logger.info("Futu Kimi report generated and sent successfully")
    except Exception as e:
        logger.error(f"Futu Kimi report generation failed: {e}")
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
