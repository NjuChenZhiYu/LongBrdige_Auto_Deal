import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.longport.push.watchlist import handle_watchlist_quote
from src.api.dingtalk import DingTalkAlert

class TestWatchlistMonitor(unittest.IsolatedAsyncioTestCase):
    async def test_handle_watchlist_quote_price_change(self):
        # Mock quote
        quote = MagicMock()
        quote.symbol = "US.AAPL"
        quote.last_done = 150.0
        quote.prev_close = 100.0 # 50% increase
        # Mock attributes that might be accessed via getattr
        quote.bid_price = 149.0
        quote.ask_price = 151.0
        
        config = {'price_change': 5.0} # 5% threshold
        
        with patch('src.api.dingtalk.DingTalkAlert.send_alert', new_callable=AsyncMock) as mock_send:
            triggered, data = await handle_watchlist_quote(quote.symbol, quote, config, send_alert=True)
            self.assertTrue(triggered)
            self.assertEqual(data['price_change'], 50.0)
            mock_send.assert_called()
            
    async def test_handle_watchlist_quote_no_trigger(self):
        # Mock quote
        quote = MagicMock()
        quote.symbol = "US.AAPL"
        quote.last_done = 101.0
        quote.prev_close = 100.0 # 1% increase
        
        config = {'price_change': 5.0}
        
        with patch('src.api.dingtalk.DingTalkAlert.send_alert', new_callable=AsyncMock) as mock_send:
            triggered, data = await handle_watchlist_quote(quote.symbol, quote, config, send_alert=True)
            self.assertFalse(triggered)
            mock_send.assert_not_called()

    async def test_deduplication(self):
        # Clear cache
        DingTalkAlert.clear_cache()
        DingTalkAlert.DEDUP_WINDOW_SECONDS = 3600
        
        # First call
        res = DingTalkAlert._should_send_alert("US.AAPL", "price_change")
        self.assertTrue(res) # Should be allowed
        
        # Second call
        res = DingTalkAlert._should_send_alert("US.AAPL", "price_change")
        self.assertFalse(res) # Should be suppressed

if __name__ == '__main__':
    unittest.main()
