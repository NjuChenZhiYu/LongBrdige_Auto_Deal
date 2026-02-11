from longport.openapi import TradeContext, Config as LongPortConfig
from longport.openapi import OrderSide, OrderType, TimeInForce
from src.config import Config
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self):
        self.enabled = Config.ENABLE_TRADING
        self.ctx = None
        if self.enabled:
            self._init_context()

    def _init_context(self):
        try:
            lp_config = LongPortConfig(
                app_key=Config.LB_APP_KEY,
                app_secret=Config.LB_APP_SECRET,
                access_token=Config.LB_ACCESS_TOKEN
            )
            self.ctx = TradeContext(lp_config)
            logger.info("TradeContext initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TradeContext: {e}")
            self.enabled = False

    def submit_order(self, symbol: str, side: str, price: float, quantity: int):
        """
        Submit an order
        :param symbol: Stock symbol (e.g., "AAPL.US")
        :param side: "Buy" or "Sell"
        :param price: Order price
        :param quantity: Order quantity
        """
        if not self.enabled:
            logger.warning("Trading is disabled. Skipping order submission.")
            return

        try:
            # Map side string to OrderSide enum
            order_side = OrderSide.Buy if side.lower() == "buy" else OrderSide.Sell
            
            # Submit limit order
            resp = self.ctx.submit_order(
                symbol=symbol,
                order_type=OrderType.LO, # Limit Order
                side=order_side,
                submitted_price=Decimal(str(price)),
                submitted_quantity=int(quantity),
                time_in_force=TimeInForce.Day
            )
            
            logger.info(f"Order submitted successfully: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            raise e

    def close(self):
        """Close trade context"""
        pass
