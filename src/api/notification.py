import requests
import logging
from config.settings import Settings

logger = logging.getLogger(__name__)

class AlertManager:
    @staticmethod
    def send_feishu(message: str):
        """Send alert to Feishu"""
        webhook = Settings.FEISHU_WEBHOOK
        if not webhook:
            return

        headers = {'Content-Type': 'application/json'}
        data = {
            "msg_type": "text",
            "content": {
                "text": message
            }
        }
        
        try:
            response = requests.post(webhook, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            logger.info("Feishu alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Feishu alert: {e}")

    @staticmethod
    def send_dingtalk(message: str):
        """Send alert to DingTalk"""
        webhook = Settings.DINGTALK_WEBHOOK
        if not webhook:
            return

        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }

        try:
            response = requests.post(webhook, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            logger.info("DingTalk alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to send DingTalk alert: {e}")

    @staticmethod
    def send_alert(title: str, content: str):
        """Send alert to all configured channels"""
        full_message = f"【美股期权监控】\n{title}\n\n{content}"
        
        # Log to console/file first
        logger.info(f"ALERT: {full_message}")
        
        # Send to configured channels
        AlertManager.send_feishu(full_message)
        AlertManager.send_dingtalk(full_message)
