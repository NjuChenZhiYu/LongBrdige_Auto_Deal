from dataclasses import dataclass
from datetime import datetime
from config.settings import Settings
from longport.openapi import SecurityQuote
import logging

logger = logging.getLogger(__name__)

@dataclass
class StrategySignal:
    symbol: str
    signal_type: str  # 'PRICE_FLUCTUATION' or 'SPREAD_NARROW'
    price: float
    timestamp: datetime
    details: str

class Strategy:
    def __init__(self):
        self.price_threshold = Settings.PRICE_CHANGE_THRESHOLD
        self.spread_threshold = Settings.SPREAD_THRESHOLD
        
    def analyze(self, quote: SecurityQuote) -> list[StrategySignal]:
        signals = []
        
        # Ensure we have necessary data
        # Note: Depending on SDK version, quote might handle attributes differently.
        # Assuming quote object has standard attributes or dictionary access.
        try:
            last_done = float(getattr(quote, 'last_done', 0) or 0)
            prev_close = float(getattr(quote, 'prev_close', 0) or 0)
        except Exception:
            # If quote is a dict or other format
            return signals

        if last_done <= 0 or prev_close <= 0:
            return signals

        try:
            # 1. Price Fluctuation Analysis
            change_rate = ((last_done - prev_close) / prev_close) * 100
            if abs(change_rate) >= self.price_threshold:
                signal = StrategySignal(
                    symbol=getattr(quote, 'symbol', 'UNKNOWN'),
                    signal_type="PRICE_FLUCTUATION",
                    price=last_done,
                    timestamp=datetime.now(),
                    details=f"Price: {last_done}, Change: {change_rate:.2f}% (Threshold: {self.price_threshold}%)"
                )
                signals.append(signal)

            # 2. Spread Analysis (if bid/ask available)
            bid_price = getattr(quote, 'bid_price', [])
            ask_price = getattr(quote, 'ask_price', [])
            
            if bid_price and ask_price and len(bid_price) > 0 and len(ask_price) > 0:
                best_bid = float(bid_price[0])
                best_ask = float(ask_price[0])
                spread = best_ask - best_bid
                
                if 0 < spread <= self.spread_threshold:
                    signal = StrategySignal(
                        symbol=getattr(quote, 'symbol', 'UNKNOWN'),
                        signal_type="SPREAD_NARROW",
                        price=last_done,
                        timestamp=datetime.now(),
                        details=f"Spread: {spread:.2f} (Bid: {best_bid}, Ask: {best_ask}) <= Threshold: {self.spread_threshold}"
                    )
                    signals.append(signal)
        except Exception as e:
            logger.error(f"Error analyzing quote for {getattr(quote, 'symbol', 'UNKNOWN')}: {e}")

        return signals

# Alias for backward compatibility
StrategyAnalyzer = Strategy
