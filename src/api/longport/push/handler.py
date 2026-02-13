from src.utils.logger import logger
from src.analysis.strategy import Strategy
from src.api.notification import AlertManager
from config.settings import Settings

class PushHandler:
    def __init__(self):
        self.strategy = Strategy()

    def on_quote(self, symbol: str, event):
        """Handle quote push event"""
        try:
            # Note: The actual event object structure depends on LongPort SDK version
            # Here we assume 'event' has price/spread info or is the Quote object itself
            logger.debug(f"Received quote for {symbol}: {event}")
            
            # Use Strategy to analyze
            signals = self.strategy.analyze(event)
            
            for sig in signals:
                logger.info(f"Signal triggered: {sig}")
                AlertManager.send_alert(
                    title=f"Strategy Signal: {sig.signal_type} - {sig.symbol}",
                    content=f"Price: {sig.price}\nTime: {sig.timestamp}\nDetails: {sig.details}"
                )
        except Exception as e:
            logger.error(f"Error handling quote for {symbol}: {e}")

push_handler = PushHandler()
