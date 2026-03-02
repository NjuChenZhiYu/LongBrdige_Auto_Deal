
import unittest
import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, AsyncMock
from src.api.futu.client import FutuClient
from src.api.longport.client import LongPortClient
from longport.openapi import SubType as LongPortSubType
from futu import SubType as FutuSubType

class TestMarketRouting(unittest.TestCase):
    def setUp(self):
        # Mock logger to avoid clutter
        pass

    def test_futu_filtering(self):
        client = FutuClient()
        # Mock internal context
        client._quote_ctx = MagicMock()
        client._quote_ctx.subscribe.return_value = (0, "OK")
        
        symbols = ["HK.00700", "AAPL.US", "HK.09988", "SH.600000"]
        
        # Call subscribe
        ret, data = client.subscribe(symbols, [FutuSubType.QUOTE])
        
        # Verify only HK symbols were passed to ctx.subscribe
        client._quote_ctx.subscribe.assert_called_with(
            ["HK.00700", "HK.09988"], 
            [FutuSubType.QUOTE], 
            is_first_push=True
        )
        print("Futu Filtering Test Passed")

    def test_longport_filtering(self):
        client = LongPortClient()
        # Mock context
        ctx = AsyncMock()
        ctx.subscribe.return_value = ["AAPL.US"]
        
        symbols = ["HK.00700", "AAPL.US", "NVDA.US"]
        
        # Call subscribe (async)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(client.subscribe(ctx, symbols, [LongPortSubType.Quote]))
        loop.close()
        
        # Verify only non-HK symbols were passed
        ctx.subscribe.assert_called_with(
            ["AAPL.US", "NVDA.US"], 
            [LongPortSubType.Quote]
        )
        print("LongPort Filtering Test Passed")

if __name__ == '__main__':
    unittest.main()
