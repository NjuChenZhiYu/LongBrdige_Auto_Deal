from dataclasses import dataclass
from datetime import datetime
from src.config import Config
from longport.quote import Quote
import logging

logger = logging.getLogger(__name__)

@dataclass
class StrategySignal:
    symbol: str
    signal_type: str  # 'PRICE_FLUCTUATION' or 'SPREAD_NARROW'
    price: float
    timestamp: datetime
    details: str

class StrategyAnalyzer:
    def __init__(self):
        self.price_threshold = Config.PRICE_CHANGE_THRESHOLD
        self.spread_threshold = Config.SPREAD_THRESHOLD
        
    def analyze(self, quote: Quote) -> list[StrategySignal]:
        signals = []
        
        # Ensure we have necessary data
        if not quote.last_done or not quote.prev_close:
            return signals

        try:
            # 1. Price Fluctuation Analysis
            last_done = float(quote.last_done)
            prev_close = float(quote.prev_close)
            
            if prev_close == 0:
                return signals

            change_rate = ((last_done - prev_close) / prev_close) * 100
            if abs(change_rate) >= self.price_threshold:
                signal = StrategySignal(
                    symbol=quote.symbol,
                    signal_type="PRICE_FLUCTUATION",
                    price=last_done,
                    timestamp=datetime.now(),
                    details=f"Price: {last_done}, Change: {change_rate:.2f}% (Threshold: {self.price_threshold}%)"
                )
                signals.append(signal)

            # 2. Spread Analysis (if bid/ask available)
            if quote.bid_price and quote.ask_price and len(quote.bid_price) > 0 and len(quote.ask_price) > 0:
                best_bid = float(quote.bid_price[0])
                best_ask = float(quote.ask_price[0])
                spread = best_ask - best_bid
                
                if 0 < spread <= self.spread_threshold:
                    signal = StrategySignal(
                        symbol=quote.symbol,
                        signal_type="SPREAD_NARROW",
                        price=last_done,
                        timestamp=datetime.now(),
                        details=f"Spread: {spread:.2f} (Bid: {best_bid}, Ask: {best_ask}) <= Threshold: {self.spread_threshold}"
                    )
                    signals.append(signal)
        except Exception as e:
            logger.error(f"Error analyzing quote for {quote.symbol}: {e}")

        return signals
