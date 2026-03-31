
import asyncio
import sys
import logging
from unittest.mock import MagicMock, patch

# Configure logging
logging.basicConfig(level=logging.INFO)

# Mock config
sys.modules['config.settings'] = MagicMock()
from config.settings import Settings
Settings.LLM_API_KEY = "dummy_key" # Will be overridden by real import if not careful
Settings.LLM_BASE_URL = "dummy_url"
Settings.LLM_MODEL = "gemini-2.5-flash"
Settings.KIMI_API_KEY = "dummy_kimi"
Settings.KIMI_LLM_BASE_URL = "dummy_kimi_url"
Settings.KIMI_LLM_MODEL = "kimi-dummy"
Settings.PRICE_CHANGE_THRESHOLD = 5.0

# We need to import the real module but patch its dependencies
# Or just import and patch
from src.services.llm_analyst import LLMAnalyst

async def run_verification():
    print("Starting verification of HK Report Generation with gemini-2.5-flash...")
    
    analyst = LLMAnalyst()
    
    # Patch futu_client inside the method
    # Since it's imported inside, we need to patch sys.modules or use patch context
    # But it's easier to mock the function on the imported module if we can access it
    
    # Let's mock the internal import. 
    # Since `from src.api.futu.client import futu_client` is inside the method,
    # we can patch `src.api.futu.client.futu_client` BEFORE calling the method.
    
    with patch('src.api.futu.client.futu_client') as mock_futu:
        # Mock get_threshold_quotes to return dummy data
        mock_futu.get_threshold_quotes.return_value = [
            {
                'code': 'HK.00700',
                'name': 'Tencent',
                'last_price': 300.0,
                'change_rate': 5.5,
                'volume': 1000000,
                'turnover': 300000000
            },
            {
                'code': 'HK.09988',
                'name': 'Alibaba',
                'last_price': 80.0,
                'change_rate': -6.0,
                'volume': 500000,
                'turnover': 40000000
            }
        ]
        
        # Patch FeishuAlert to print instead of sending
        with patch('src.api.feishu.FeishuAlert.send_alert') as mock_alert:
            mock_alert.side_effect = lambda title, content: print(f"\n[MOCK ALERT]\nTitle: {title}\nContent:\n{content}\n")
            
            # Patch DB manager to avoid writing
            with patch('src.storage.db_manager') as mock_db:
                
                print("\nCalling generate_futu_hk_report...")
                try:
                    await analyst.generate_futu_hk_report(threshold=5.0, trigger_type='MANUAL')
                    print("\nVerification SUCCESS: Report generated without error.")
                except Exception as e:
                    print(f"\nVerification FAILED: {e}")
                    import traceback
                    traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_verification())
