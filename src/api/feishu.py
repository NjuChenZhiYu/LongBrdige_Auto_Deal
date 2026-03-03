import aiohttp
import logging
import json
from config.settings import Settings

logger = logging.getLogger(__name__)

class FeishuAlert:
    @staticmethod
    async def send_alert(title: str, content: str):
        """
        Send async alert to Feishu
        """
        webhook = Settings.FEISHU_WEBHOOK
        if not webhook:
            logger.warning("FEISHU_WEBHOOK not configured")
            return

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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook, json=data, headers=headers, timeout=10) as response:
                    result = await response.json()
                    if result.get("code") == 0:
                        logger.info(f"Feishu alert sent successfully: {title}")
                    else:
                        logger.error(f"Feishu API error: {result}")
        except Exception as e:
            logger.error(f"Failed to send Feishu alert: {e}")
