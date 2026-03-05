
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from config.settings import Settings
from src.api.feishu import FeishuAlert

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_feishu():
    print(f"Feishu Webhook: {Settings.FEISHU_WEBHOOK}")
    print(f"Feishu Keyword: {Settings.FEISHU_KEYWORD}")
    
    if not Settings.FEISHU_WEBHOOK:
        logger.error("Feishu Webhook is not configured!")
        return

    logger.info("Sending test alert to Feishu...")
    await FeishuAlert.send_alert(
        title="[Test] Feishu Alert Verification",
        content="This is a test message to verify Feishu connectivity from scripts/test_feishu_alert.py."
    )
    
    logger.info("Sending long content test...")
    long_content = "This is a long report test.\n" * 10
    await FeishuAlert.send_alert(
        title="[Test] Feishu Long Content Verification",
        content=long_content
    )

if __name__ == "__main__":
    asyncio.run(test_feishu())
