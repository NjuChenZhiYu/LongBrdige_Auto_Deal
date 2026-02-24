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
from typing import Optional, Dict
from datetime import datetime, timedelta
from config.settings import Settings

logger = logging.getLogger(__name__)

# Deduplication cache
# Key: {symbol}_{reason} -> Value: trading_date (str: YYYY-MM-DD)
ALERT_CACHE: Dict[str, str] = {}

class DingTalkAlert:
    @staticmethod
    def _get_sign(secret: str) -> tuple[str, str]:
        """Generate DingTalk signature"""
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    @staticmethod
    def get_trading_date() -> str:
        """
        Get the current trading date string (YYYY-MM-DD).
        Assumes CST timezone logic:
        - If time is before 12:00 PM, it belongs to the previous day's trading session (US market closes early morning CST).
        - If time is after 12:00 PM, it belongs to today's trading session.
        """
        now = datetime.now()
        if now.hour < 12:
            return (now - timedelta(days=1)).strftime('%Y-%m-%d')
        return now.strftime('%Y-%m-%d')

    @staticmethod
    def clear_cache():
        """Clear deduplication cache"""
        global ALERT_CACHE
        ALERT_CACHE.clear()
        logger.info("Alert deduplication cache cleared")

    @staticmethod
    def _check_deduplication(symbol: str, reason: str) -> bool:
        """
        Check if alert should be suppressed due to deduplication.
        Returns True if should be suppressed (duplicate), False otherwise.
        """
        key = f"{symbol}_{reason}"
        current_trading_date = DingTalkAlert.get_trading_date()
        
        # Check if key exists and date matches
        if key in ALERT_CACHE:
            last_date = ALERT_CACHE[key]
            if last_date == current_trading_date:
                # Already sent in this trading session
                return True
        
        # Update cache with current trading date
        ALERT_CACHE[key] = current_trading_date
        return False

    @staticmethod
    async def send_alert(title: str, content: str, symbol: str, reason: str, force: bool = False):
        """
        Send alert to DingTalk with retry and deduplication
        
        :param title: Alert title
        :param content: Alert content
        :param symbol: Stock symbol (e.g., US.AAPL)
        :param reason: Alert reason (e.g., price_change_rate, bid_ask_spread)
        :param force: If True, bypass deduplication check
        """
        if not Settings.DINGTALK_ALERT_ENABLE:
            return

        if not Settings.DINGTALK_WEBHOOK:
            logger.warning("DINGTALK_WEBHOOK not configured")
            return

        # Deduplication check
        if not force and DingTalkAlert._check_deduplication(symbol, reason):
            logger.info(f"Alert suppressed (duplicate): {symbol} - {reason}")
            return

        webhook = Settings.DINGTALK_WEBHOOK
        secret = Settings.DINGTALK_SECRET
        
        # Debug: Log masked webhook
        if webhook and len(webhook) > 20:
            logger.info(f"Using DingTalk Webhook: {webhook[:20]}... (Length: {len(webhook)})")
        else:
            logger.warning(f"DingTalk Webhook might be invalid: {webhook}")

        url = webhook
        if secret:
            timestamp, sign = DingTalkAlert._get_sign(secret)
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
