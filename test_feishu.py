import asyncio
import logging
import aiohttp
from config.settings import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_alert_text():
    print(f"Feishu Enabled: {bool(Settings.FEISHU_WEBHOOK)}")
    webhook = Settings.FEISHU_WEBHOOK
    if not webhook:
        return

    print(f"Webhook URL (repr): {repr(webhook)}")
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "msg_type": "text",
        "content": {
            "text": "这是一条来自 Feishu 的测试消息 (Text Type)。"
        }
    }

    print("Sending test alert (Text Type)...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook, json=data, headers=headers, timeout=10) as response:
                result = await response.json()
                print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_alert_text())
