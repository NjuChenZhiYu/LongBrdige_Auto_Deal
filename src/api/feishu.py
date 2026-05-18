import aiohttp
import logging
import json
import time
import ssl
import certifi
from typing import Dict
from config.settings import Settings

logger = logging.getLogger(__name__)

class FeishuAlert:
    """
    Feishu Alert Sender with built-in deduplication.
    """
    
    # Alert cache: {title: last_alert_timestamp}
    _alert_cache: Dict[str, float] = {}
    
    # Deduplication window in seconds (default: 0, disabled)
    DEDUP_WINDOW_SECONDS = 0
    
    @classmethod
    def _should_send_alert(cls, title: str) -> bool:
        """Check if alert should be sent based on deduplication rules"""
        # If deduplication is disabled (window <= 0), always send
        if cls.DEDUP_WINDOW_SECONDS <= 0:
            return True

        current_time = time.time()
        
        if title in cls._alert_cache:
            last_alert_time = cls._alert_cache[title]
            time_since_last = current_time - last_alert_time
            
            if time_since_last < cls.DEDUP_WINDOW_SECONDS:
                logger.info(f"Feishu alert deduplicated: {title[:50]}... (last alert {time_since_last:.0f}s ago)")
                return False
        
        cls._alert_cache[title] = current_time
        return True
    
    @classmethod
    def clear_cache(cls):
        """Clear the alert cache"""
        cache_size = len(cls._alert_cache)
        cls._alert_cache.clear()
        logger.info(f"Feishu alert cache cleared ({cache_size} entries)")
    
    @classmethod
    async def send_alert(cls, title: str, content: str) -> bool:
        """
        Send async alert to Feishu with deduplication.
        """
        webhook = Settings.FEISHU_WEBHOOK
        if not webhook:
            logger.warning("FEISHU_WEBHOOK not configured")
            return False
        
        # Deduplication check
        if not cls._should_send_alert(title):
            return False

        # Ensure keyword is present for security verification
        keyword = getattr(Settings, 'FEISHU_KEYWORD', '告警')
        if keyword and keyword not in title and keyword not in str(content):
            # Feishu content is a bit complex (nested dict), so we prepend to title for simplicity
            title = f"【{keyword}】 {title}"

        headers = {'Content-Type': 'application/json'}
        
        # Feishu interactive card or post format
        data = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [
                            [
                                {
                                    "tag": "text",
                                    "text": content
                                }
                            ]
                        ]
                    }
                }
            }
        }

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook, json=data, headers=headers, ssl=ssl_context, timeout=10) as response:
                    result = await response.json()
                    if result.get("code") == 0:
                        logger.info(f"Feishu alert sent successfully: {title}")
                        return True
                    else:
                        logger.error(f"Feishu API error: {result}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Feishu alert: {e}")
            return False
