import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.longport.personalized.watchlist import get_watchlist
from src.api.longport.pull.quote import get_quote

class TestLongPortWatchlist(unittest.IsolatedAsyncioTestCase):
    
    @patch('src.api.longport.personalized.watchlist.longport_client')
    async def test_get_watchlist_success(self, mock_client):
        # Mock Context
        mock_ctx = AsyncMock()
        # Setup get_quote_context to return mock_ctx when awaited
        mock_client.get_quote_context = AsyncMock(return_value=mock_ctx)
        
        # Mock Watchlist Group
        mock_group = MagicMock()
        mock_group.name = "My Watchlist"
        
        # Mock Security
        mock_security = MagicMock()
        mock_security.symbol = "US.AAPL"
        mock_security.name = "Apple"
        
        mock_group.securities = [mock_security]
        # Use watchlist() instead of get_watchlists()
        mock_ctx.watchlist.return_value = [mock_group]
        
        result = await get_watchlist()
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['symbol'], "US.AAPL")
        self.assertEqual(result[0]['watchlist_name'], "My Watchlist")

    @patch('src.api.longport.personalized.watchlist.longport_client')
    async def test_get_watchlist_error(self, mock_client):
        # Mock Error
        mock_client.get_quote_context = AsyncMock(side_effect=Exception("API Error"))
        
        result = await get_watchlist()
        self.assertEqual(result, [])

    @patch('src.api.longport.pull.quote.longport_client')
    async def test_get_quote_success(self, mock_client):
        mock_ctx = AsyncMock()
        mock_client.get_quote_context = AsyncMock(return_value=mock_ctx)
        
        # Mock Quote
        mock_q = MagicMock()
        mock_q.symbol = "US.AAPL"
        mock_q.last_done = "150.0"
        mock_q.prev_close = "145.0"
        
        # Mock Static Info
        mock_info = MagicMock()
        mock_info.symbol = "US.AAPL"
        mock_info.name_cn = "苹果"
        
        mock_ctx.quote.return_value = [mock_q]
        mock_ctx.static_info.return_value = [mock_info]
        
        result = await get_quote(["US.AAPL"])
        
        self.assertIn("US.AAPL", result)
        self.assertEqual(result["US.AAPL"]["last_price"], 150.0)
        self.assertEqual(result["US.AAPL"]["name"], "苹果")

    async def test_get_quote_empty(self):
        result = await get_quote([])
        self.assertEqual(result, {})

if __name__ == '__main__':
    unittest.main()
