import sys
from unittest.mock import MagicMock

# Mock longport modules BEFORE importing src
sys.modules["longport"] = MagicMock()
sys.modules["longport.quote"] = MagicMock()
sys.modules["longport.openapi"] = MagicMock()

import unittest
from src.analysis.strategy import StrategyAnalyzer, StrategySignal
from src.config import Config

class TestStrategyAnalyzer(unittest.TestCase):
    def setUp(self):
        Config.PRICE_CHANGE_THRESHOLD = 2.0
        Config.SPREAD_THRESHOLD = 0.05
        self.analyzer = StrategyAnalyzer()

    def test_price_fluctuation_trigger(self):
        """Test if price fluctuation signal is triggered correctly"""
        quote = MagicMock()
        quote.symbol = "AAPL.US"
        quote.last_done = "105.0"
        quote.prev_close = "100.0" # 5% change
        quote.bid_price = ["104.9"]
        quote.ask_price = ["105.1"] # Spread 0.2 > 0.05

        signals = self.analyzer.analyze(quote)
        
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_type, "PRICE_FLUCTUATION")
        self.assertEqual(signals[0].price, 105.0)

    def test_spread_narrow_trigger(self):
        """Test if spread narrow signal is triggered correctly"""
        quote = MagicMock()
        quote.symbol = "AAPL.US"
        quote.last_done = "100.0"
        quote.prev_close = "100.0" # 0% change
        quote.bid_price = ["100.0"]
        quote.ask_price = ["100.04"] # Spread 0.04 <= 0.05

        signals = self.analyzer.analyze(quote)
        
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_type, "SPREAD_NARROW")

    def test_no_signal(self):
        """Test no signal scenario"""
        quote = MagicMock()
        quote.symbol = "AAPL.US"
        quote.last_done = "101.0"
        quote.prev_close = "100.0" # 1% change < 2%
        quote.bid_price = ["100.0"]
        quote.ask_price = ["100.2"] # Spread 0.2 > 0.05

        signals = self.analyzer.analyze(quote)
        
        self.assertEqual(len(signals), 0)

    def test_invalid_data(self):
        """Test with missing data"""
        quote = MagicMock()
        quote.last_done = None
        quote.prev_close = "100.0"
        
        signals = self.analyzer.analyze(quote)
        self.assertEqual(len(signals), 0)

if __name__ == '__main__':
    unittest.main()
