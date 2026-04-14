import asyncio
import logging
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.api.dingtalk import DingTalkAlert
from config.settings import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_alert():
    print(f"DingTalk Enabled: {Settings.DINGTALK_ALERT_ENABLE}")
    print(f"Webhook Configured: {'Yes' if Settings.DINGTALK_WEBHOOK else 'No'}")
    if Settings.DINGTALK_WEBHOOK:
        print(f"Webhook URL (masked): {Settings.DINGTALK_WEBHOOK[:30]}...")
    
    print("Sending test alert...")
    # Add common keywords "告警" and "Test" to satisfy potential security settings
    await DingTalkAlert.send_alert(
        title="测试告警 (Test Alert)",
        content="这是一条测试消息。\n\nThis is a test message with keyword '告警'.",
        symbol="TEST.001",
        reason="manual_test"
    )
    print("Test alert function called.")

if __name__ == "__main__":
    asyncio.run(test_alert())
