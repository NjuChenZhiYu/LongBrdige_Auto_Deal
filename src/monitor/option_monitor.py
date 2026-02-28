
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from config.settings import Settings
from src.api.longport.client import longport_client
from src.services.signal_recorder import signal_recorder
from src.utils.greeks import calculate_black_scholes
from longport.openapi import SubType

logger = logging.getLogger(__name__)

class OptionMonitor:
    def __init__(self):
        self.monitored_options = Settings.MONITORED_OPTIONS
        self.monitored_stocks = Settings.MONITOR_SYMBOLS
        self.underlying_prices = {}
        self.risk_free_rate = 0.045
        self.ctx = None
        self.loop = None
        self._is_running = False

    async def start(self):
        """Start monitoring option quotes."""
        self.loop = asyncio.get_running_loop()
        if not self.monitored_options:
            logger.warning("No option symbols configured for monitoring.")
            return

        try:
            self.ctx = await longport_client.get_quote_context()
            # Set callback
            self.ctx.set_on_quote(self._on_quote_update)
            
            # Subscribe to quotes (options + stocks)
            subscribe_list = list(set(self.monitored_options + self.monitored_stocks))
            await self.ctx.subscribe(subscribe_list, [SubType.Quote])
            logger.info(f"Subscribed to quotes: {subscribe_list}")
            self._is_running = True
        except Exception as e:
            logger.error(f"Failed to start OptionMonitor: {e}")

    def _on_quote_update(self, symbol: str, event: Any):
        """
        Handle push event.
        Since PushQuote might lack Greeks, we fetch full snapshot for options.
        For stocks, we just update the price.
        """
        # Create task for async processing
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._process_quote_async(symbol, event), self.loop)

    async def _process_quote_async(self, symbol: str, event: Any):
        try:
            # Check if it's a stock (assume monitored_stocks contains it)
            if symbol in self.monitored_stocks:
                # Update underlying price
                # We can try to extract price from event if possible, or fetch snapshot
                # event is usually PushQuote
                price = getattr(event, 'last_done', None)
                if price:
                    self.underlying_prices[symbol] = float(price)
                    # logger.debug(f"Updated price for {symbol}: {price}")
                return

            if symbol not in self.monitored_options:
                return

            # For options, fetch full snapshot to get IV and other fields
            quotes = await self.ctx.option_quote([symbol])
            if not quotes:
                return
            
            q = quotes[0]
            self._process_quote(symbol, q)
            
        except Exception as e:
            logger.error(f"Error processing update for {symbol}: {e}")

    def _process_quote(self, symbol: str, quote: Any):
        try:
            # Extract data
            last_price = float(getattr(quote, 'last_done', 0))
            volume = int(getattr(quote, 'volume', 0))
            open_interest = int(getattr(quote, 'open_interest', 0))
            implied_volatility = float(getattr(quote, 'implied_volatility', 0))
            strike_price = float(getattr(quote, 'strike_price', 0))
            expiry_date_str = getattr(quote, 'expiry_date', None)
            underlying_symbol = getattr(quote, 'underlying_symbol', None)
            
            timestamp = datetime.now()
            time_str = timestamp.strftime("%H:%M:%S")

            # Strategy A: IV Deviation
            # Try to use historical volatility as baseline if available
            historical_volatility = float(getattr(quote, 'historical_volatility', 0) or 0)
            
            iv_threshold = 0.5 # Default fallback
            if historical_volatility > 0:
                iv_threshold = historical_volatility * 1.3
            
            if implied_volatility > iv_threshold:
                 signal_recorder.add_signal({
                     "symbol": symbol,
                     "type": "IV_SPIKE",
                     "value": implied_volatility,
                     "threshold": iv_threshold,
                     "timestamp": time_str,
                     "details": f"IV: {implied_volatility}, HV: {historical_volatility}"
                 })

            # Strategy B: Smart Money (Volume > OI * 0.20)
            if open_interest > 10 and volume > open_interest * 0.20:
                signal_recorder.add_signal({
                    "symbol": symbol,
                    "type": "SMART_MONEY_VOLUME",
                    "value": volume,
                    "threshold": open_interest * 0.20,
                    "timestamp": time_str,
                    "details": f"Vol: {volume}, OI: {open_interest}"
                })

            # Strategy C: Delta Crossing 0.5
            delta = getattr(quote, 'delta', None)
            
            # Calculate Delta if N/A
            if (delta is None or str(delta) == 'nan' or str(delta) == 'N/A') and strike_price > 0 and expiry_date_str and underlying_symbol:
                underlying_price = self.underlying_prices.get(underlying_symbol)
                
                if underlying_price:
                    # Calculate T (Time to expiry in years)
                    try:
                        expiry_date = datetime.strptime(str(expiry_date_str), "%Y-%m-%d")
                        time_to_expiry = (expiry_date - timestamp).days / 365.0
                        
                        if time_to_expiry > 0:
                                # Determine option type (call/put) from symbol or attribute
                                # Assuming Call for LEAPS monitoring as per user implied context, but check symbol
                                # Standard format: CCC...YYMMDD[C/P]...
                                # Or check 'direction' attribute? No, 'direction' usually means trade direction.
                                # We can guess from symbol or assume Call for now (Strategy C: "delta > 0.5" implies Call usually)
                                # Actually, Put delta is negative. So abs(delta) > 0.5 works for both ITM.
                                # But "delta 向上突破 0.5" usually means Call becoming ITM.
                                option_type = "call" 
                                symbol_parts = symbol.split(".")
                                if len(symbol_parts) >= 2:
                                    # Try to find C or P in the part before last (strike) or just check symbol string
                                    # Typical LongPort option symbol: AAPL.US.C.200 (Mock) or AAPL230120C00150000 (US Option)
                                    # If it is like AAPL.US.C.200
                                    if "P" in symbol_parts[-2] and "C" not in symbol_parts[-2]: 
                                        option_type = "put"
                                    elif "C" in symbol_parts[-2]:
                                        option_type = "call"
                                    
                                calculated_delta = calculate_black_scholes(
                                    S=underlying_price,
                                    K=strike_price,
                                    T=time_to_expiry,
                                    r=self.risk_free_rate,
                                    sigma=implied_volatility/100.0 if implied_volatility > 1 else implied_volatility, # IV might be % or decimal
                                    option_type=option_type
                                )
                                delta = calculated_delta
                                logger.info(f"Calculated Delta for {symbol}: {delta} (S={underlying_price}, K={strike_price}, T={time_to_expiry:.2f}, IV={implied_volatility})")
                        else:
                            logger.warning(f"Expired option {symbol}: {expiry_date_str}")
                    except Exception as e:
                        logger.warning(f"Failed to calculate Delta for {symbol}: {e}")

            # Use delta (calculated or provided)
            if delta and str(delta) != 'nan' and abs(float(delta)) > 0.5:
                 signal_recorder.add_signal({
                     "symbol": symbol,
                     "type": "DELTA_CROSS_0.5",
                     "value": float(delta),
                     "threshold": 0.5,
                     "timestamp": time_str
                 })

        except Exception as e:
            logger.error(f"Logic error for {symbol}: {e}")

option_monitor = OptionMonitor()
