import requests
import logging
import time
import hmac
import hashlib
import base64
import urllib.parse
from config.settings import Settings

logger = logging.getLogger(__name__)

class AlertManager:
    @staticmethod
    def _get_dingtalk_sign(secret: str) -> tuple[str, str]:
        """Generate DingTalk signature"""
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))
        return timestamp, sign

    @staticmethod
    def send_dingtalk(message: str):
        """Send alert to DingTalk"""
        if not Settings.DINGTALK_ALERT_ENABLE:
            return

        webhook = Settings.DINGTALK_WEBHOOK
        if not webhook:
            return

        # Ensure keyword is present for security verification
        keyword = getattr(Settings, 'DINGTALK_KEYWORD', '告警')
        if keyword and keyword not in message:
            message = f"【{keyword}】\n{message}"

        secret = Settings.DINGTALK_SECRET
        url = webhook
        if secret:
            timestamp, sign = AlertManager._get_dingtalk_sign(secret)
            if '?' in webhook:
                url = f"{webhook}&timestamp={timestamp}&sign={sign}"
            else:
                url = f"{webhook}?timestamp={timestamp}&sign={sign}"

        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            if result.get("errcode") == 0:
                logger.info("DingTalk alert sent successfully")
            else:
                logger.error(f"DingTalk API error: {result}")
        except Exception as e:
            logger.error(f"Failed to send DingTalk alert: {e}")

    @staticmethod
    def send_feishu(message: str, title: str = "美股期权监控"):
        """Send alert to Feishu"""
        if not Settings.FEISHU_ALERT_ENABLE:
            return
            
        webhook = Settings.FEISHU_WEBHOOK
        if not webhook:
            return

        # Ensure keyword is present
        keyword = getattr(Settings, 'FEISHU_KEYWORD', '告警')
        if keyword and keyword not in title and keyword not in message:
            title = f"【{keyword}】 {title}"

        headers = {'Content-Type': 'application/json'}
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
                                    "text": message
                                }
                            ]
                        ]
                    }
                }
            }
        }
        
        try:
            import json
            response = requests.post(webhook, headers=headers, data=json.dumps(data), timeout=10)
            response.raise_for_status()
            result = response.json()
            if result.get("code") == 0:
                logger.info("Feishu alert sent successfully")
            else:
                logger.error(f"Feishu API error: {result}")
        except Exception as e:
            logger.error(f"Failed to send Feishu alert: {e}")

    @staticmethod
    def send_alert(title: str, content: str, market: str = "US"):
        """
        Send alert to configured channels based on market routing.
        
        :param title: Alert title
        :param content: Alert content
        :param market: Market identifier ('HK' for Hong Kong, others default to US/DingTalk)
        """
        full_message = f"{title}\n\n{content}"
        
        # Log to console/file first
        logger.info(f"ALERT [{market}]: {full_message}")
        
        # Route based on market
        if market == "HK":
            # HK Market -> Feishu
            AlertManager.send_feishu(content, title=title)
        else:
            # US/Other Markets -> DingTalk
            AlertManager.send_dingtalk(full_message)
