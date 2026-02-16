import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.api.dingtalk import DingTalkAlert
from config.settings import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_alert():
    logger.info("Testing DingTalk Alert...")
    logger.info(f"Webhook configured: {Settings.DINGTALK_WEBHOOK[:10]}... (hidden)")
    
    title = "[LongBridge Alert] 美股监控告警测试"
    content = """
### Test Alert
* **Status**: Success
* **Time**: {}
* **Message**: This is a test message to verify DingTalk integration.
* **Keywords**: LongBridge, Alert, 美股, 监控, 告警
    """.format(asyncio.get_running_loop().time())
    
    try:
        # Use a unique reason to bypass deduplication for test
        import time
        unique_reason = f"test_alert_{int(time.time())}"
        
        await DingTalkAlert.send_alert(title, content, "TEST.US", unique_reason)
        logger.info("Alert sent successfully. Please check your DingTalk group.")
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")

if __name__ == "__main__":
    asyncio.run(test_alert())
