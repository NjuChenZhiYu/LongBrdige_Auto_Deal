import logging
import datetime
from typing import Dict, Tuple, Optional, Any
from config.settings import Settings
from src.api.dingtalk import DingTalkAlert

logger = logging.getLogger(__name__)

async def handle_watchlist_quote(symbol: str, quote: Any, threshold_config: Dict, force_alert: bool = False) -> Tuple[bool, Dict]:
    """
    Handle watchlist quote push and check thresholds
    
    :param symbol: Stock symbol
    :param quote: Quote object (PushQuote or QuoteSnapshot)
    :param threshold_config: Threshold configuration
    :param force_alert: If True, force send alert even if duplicate
    :return: (triggered, alert_data)
    """
    try:
        # Check if quote has necessary attributes
        # Some SDK versions might return PushQuote without symbol
        # We use the passed symbol
        
        # Debug available attributes
        # logger.info(f"Quote attributes for {symbol}: {dir(quote)}")
        
        last_done = float(quote.last_done)
        
        # prev_close might be named differently or missing
        if hasattr(quote, 'prev_close'):
             prev_close = float(quote.prev_close)
        elif hasattr(quote, 'pre_close'):
             prev_close = float(quote.pre_close)
        elif hasattr(quote, 'last_close'):
             prev_close = float(quote.last_close)
        else:
             # Fallback: cannot calculate change rate without prev_close
             # Maybe use open? No.
             logger.debug(f"Missing prev_close for {symbol}, attributes: {dir(quote)}")
             prev_close = 0.0

        # Check if bid/ask available (PushQuote might not have them, or they might be named differently)
        # Standard LongPort PushQuote usually has: last_done, open, high, low, timestamp, volume, turnover
        # It may NOT have bid/ask. If we need bid/ask, we might need PushDepth or check if available.
        # We'll use getattr with default 0.
        bid = float(getattr(quote, 'bid_price', 0))
        ask = float(getattr(quote, 'ask_price', 0))
        
        # Log for debugging structure if needed
        # logger.debug(f"Quote for {symbol}: {quote}")
        
    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"Invalid quote data structure for {symbol}: {e}")
        return False, {}

    triggered = False
    alert_data = {}
    current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. Price Change Rate Check
    # Avoid division by zero
    if prev_close > 0:
        change_rate = ((last_done - prev_close) / prev_close) * 100
        
        # Get threshold from config or default
        # threshold_config might be { 'price_change': 2.0, ... }
        price_change_threshold = threshold_config.get('price_change', Settings.PRICE_CHANGE_THRESHOLD)
        
        if abs(change_rate) >= price_change_threshold:
            direction = "涨" if change_rate > 0 else "跌"
            title = f"[LongBridge Alert] {symbol} {direction}幅≥{price_change_threshold}%"
            content = f"""
### 价格异动告警
* **标的**：{symbol}
* **最新价**：{last_done} USD
* **涨跌幅**：{change_rate:.2f}% (昨收：{prev_close})
* **触发规则**：{direction}幅≥{price_change_threshold}%
* **更新时间**：{current_time_str}
* **Keywords**: LongBridge, Alert, 美股, 监控, 告警
            """
            # Asynchronous alert sending
            # Differentiate reason by direction (rise/fall) to allow separate alerts for both in one day
            reason_suffix = "rise" if change_rate > 0 else "fall"
            await DingTalkAlert.send_alert(title, content, symbol, f"price_change_{reason_suffix}", force=force_alert)
            triggered = True
            alert_data['price_change'] = change_rate

    return triggered, alert_data