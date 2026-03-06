import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import logging
import asyncio
import aiohttp
import ssl
import certifi
from typing import Optional, Dict, Set, Tuple
from datetime import datetime, timedelta
from config.settings import Settings

logger = logging.getLogger(__name__)

class DingTalkAlert:
    """
    DingTalk Alert Sender with built-in deduplication.
    
    Deduplication strategy:
    - Same symbol + same reason within DEDUP_WINDOW_SECONDS will only trigger one alert
    - Different reasons (rise vs fall) are tracked separately
    - Cache is cleared daily via clear_cache() or at 05:30 by watchlist_monitor
    """
    
    # Alert cache: {(symbol, reason): last_alert_timestamp}
    _alert_cache: Dict[Tuple[str, str], float] = {}
    
    # Deduplication window in seconds (default: 1 hour)
    DEDUP_WINDOW_SECONDS = 3600
    
    @classmethod
    def _get_cache_key(cls, symbol: str, reason: str) -> Tuple[str, str]:
        """Generate cache key for deduplication"""
        return (symbol, reason)
    
    @classmethod
    def _should_send_alert(cls, symbol: str, reason: str) -> bool:
        """
        Check if alert should be sent based on deduplication rules.
        
        :param symbol: Stock symbol
        :param reason: Alert reason
        :return: True if alert should be sent, False if it's a duplicate
        """
        cache_key = cls._get_cache_key(symbol, reason)
        current_time = time.time()
        
        if cache_key in cls._alert_cache:
            last_alert_time = cls._alert_cache[cache_key]
            time_since_last = current_time - last_alert_time
            
            if time_since_last < cls.DEDUP_WINDOW_SECONDS:
                logger.info(f"Alert deduplicated: {symbol} - {reason} (last alert {time_since_last:.0f}s ago)")
                return False
        
        # Update cache
        cls._alert_cache[cache_key] = current_time
        return True
    
    @classmethod
    def clear_cache(cls):
        """Clear the alert cache (called daily at 05:30)"""
        cache_size = len(cls._alert_cache)
        cls._alert_cache.clear()
        logger.info(f"Alert cache cleared ({cache_size} entries removed)")
    
    @classmethod
    def get_cache_status(cls) -> Dict:
        """Get current cache status for debugging"""
        current_time = time.time()
        active_entries = []
        for (symbol, reason), timestamp in cls._alert_cache.items():
            age = current_time - timestamp
            active_entries.append({
                'symbol': symbol,
                'reason': reason,
                'age_seconds': int(age),
                'expires_in': max(0, int(cls.DEDUP_WINDOW_SECONDS - age))
            })
        return {
            'total_entries': len(cls._alert_cache),
            'dedup_window_seconds': cls.DEDUP_WINDOW_SECONDS,
            'entries': sorted(active_entries, key=lambda x: x['age_seconds'])
        }
    @staticmethod
    def _get_sign(secret: str) -> tuple[str, str]:
        """Generate DingTalk signature"""
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))
        return timestamp, sign

    @classmethod
    async def send_alert(cls, title: str, content: str, symbol: str, reason: str):
        """
        Send alert to DingTalk with deduplication.
        
        :param title: Alert title
        :param content: Alert content
        :param symbol: Stock symbol (e.g., US.AAPL)
        :param reason: Alert reason (e.g., price_change_rate, bid_ask_spread)
        """
        if not Settings.DINGTALK_ALERT_ENABLE:
            return

        if not Settings.DINGTALK_WEBHOOK:
            logger.warning("DINGTALK_WEBHOOK not configured")
            return
        
        # Deduplication check
        if not cls._should_send_alert(symbol, reason):
            return

        webhook = Settings.DINGTALK_WEBHOOK
        secret = Settings.DINGTALK_SECRET
        
        # Ensure keyword is present for security verification
        keyword = getattr(Settings, 'DINGTALK_KEYWORD', '告警')
        if keyword and keyword not in title and keyword not in content:
            content = f"【{keyword}】\n{content}"
        
        # Debug: Log masked webhook
        if webhook and len(webhook) > 20:
            logger.info(f"Using DingTalk Webhook: {webhook[:20]}... (Length: {len(webhook)})")
        else:
            logger.warning(f"DingTalk Webhook might be invalid: {webhook}")

        url = webhook
        if secret:
            timestamp, sign = cls._get_sign(secret)
            if '?' in webhook:
                url = f"{webhook}&timestamp={timestamp}&sign={sign}"
            else:
                url = f"{webhook}?timestamp={timestamp}&sign={sign}"

        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{content}"
            }
        }

        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        for attempt in range(Settings.DINGTALK_RETRY_TIMES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=data, headers=headers, ssl=ssl_context, timeout=10) as response:
                        result = await response.json()
                        if result.get("errcode") == 0:
                            logger.info(f"DingTalk alert sent successfully: {symbol} - {reason}")
                            return
                        else:
                            logger.error(f"DingTalk API error: {result}")
            except Exception as e:
                logger.error(f"Failed to send DingTalk alert (Attempt {attempt+1}/{Settings.DINGTALK_RETRY_TIMES}): {e}")
                if attempt < Settings.DINGTALK_RETRY_TIMES - 1:
                    await asyncio.sleep(Settings.DINGTALK_RETRY_INTERVAL)
        
        logger.error(f"Failed to send DingTalk alert after {Settings.DINGTALK_RETRY_TIMES} attempts")
