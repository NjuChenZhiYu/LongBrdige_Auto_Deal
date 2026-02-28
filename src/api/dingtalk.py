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
    async def send_alert(title: str, content: str, symbol: str, reason: str):
        """
        Send alert to DingTalk
        
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
