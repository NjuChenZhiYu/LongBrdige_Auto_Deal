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

# Time-based cooldown cache (symbol -> last_alert_timestamp)
# Prevents duplicate alerts within short time window
ALERT_TIME_CACHE: Dict[str, datetime] = {}

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
        
        US Stock Market Trading Hours (CST/北京时间):
        - Winter (当前): 22:30 - 次日 05:00
        - Summer: 21:30 - 次日 04:00
        
        Trading day mapping (CST):
        - 22:30 - 23:59: 新交易日开始，算今天
        - 00:00 - 05:00: 美股交易中，算昨天（昨晚开始的交易日）
        - 05:00 - 22:30: 美股休市，算昨天（昨晚结束的交易日）
        
        即：北京时间 05:00 才算一个美股交易日结束
        """
        now = datetime.now()
        
        # 美股交易日分界线：北京时间 05:00
        # 05:00 之前（包括凌晨交易时段）都算昨天的交易日
        if now.hour < 5:
            return (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        return now.strftime('%Y-%m-%d')

    @staticmethod
    def clear_cache():
        """Clear deduplication cache"""
        global ALERT_CACHE, ALERT_TIME_CACHE
        ALERT_CACHE.clear()
        ALERT_TIME_CACHE.clear()
        logger.info("Alert deduplication cache cleared")

    @staticmethod
    def _check_time_cooldown(symbol: str, cooldown_minutes: int = 5) -> bool:
        """
        Check if alert is in time cooldown window.
        Returns True if should be suppressed (in cooldown), False otherwise.
        """
        now = datetime.now()
        if symbol in ALERT_TIME_CACHE:
            last_alert = ALERT_TIME_CACHE[symbol]
            elapsed = (now - last_alert).total_seconds() / 60
            if elapsed < cooldown_minutes:
                logger.info(f"Alert suppressed (time cooldown): {symbol} - {elapsed:.1f}min < {cooldown_minutes}min")
                return True
        # Update cache
        ALERT_TIME_CACHE[symbol] = now
        return False

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

        # Deduplication check (trading day based)
        if not force and DingTalkAlert._check_deduplication(symbol, reason):
            logger.info(f"Alert suppressed (duplicate): {symbol} - {reason}")
            return
        
        # Time cooldown check (5 minutes)
        if not force and DingTalkAlert._check_time_cooldown(symbol, cooldown_minutes=5):
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
