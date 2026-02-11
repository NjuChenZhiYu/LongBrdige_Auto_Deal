import time
import logging
import signal
from longport.openapi import QuoteContext, Config as LongPortConfig, SubType
from longport.quote import Quote
from src.config import Config
from src.analysis.strategy import StrategyAnalyzer
from src.api.notification import AlertManager
from src.api.trade import TradeManager

logger = logging.getLogger(__name__)

class MonitorSystem:
    def __init__(self):
        self.running = True
        self.ctx = None
        self.strategy = StrategyAnalyzer()
        self.trade_manager = TradeManager()
        
        # Validate config
        Config.validate()
        
        # Init LongPort Config
        self.lp_config = LongPortConfig(
            app_key=Config.LB_APP_KEY,
            app_secret=Config.LB_APP_SECRET,
            access_token=Config.LB_ACCESS_TOKEN
        )

    def on_quote(self, symbol: str, quote: Quote):
        """Callback for real-time quote updates"""
        try:
            # Filter symbols if needed (though we only subscribe to what we want)
            if symbol not in Config.MONITOR_SYMBOLS:
                return

            logger.debug(f"Received quote for {symbol}: {quote}")
            
            # Run analysis
            signals = self.strategy.analyze(quote)
            
            for sig in signals:
                logger.info(f"Signal triggered: {sig}")
                
                # Send Alert
                AlertManager.send_alert(
                    title=f"Strategy Signal: {sig.signal_type} - {sig.symbol}",
                    content=f"Price: {sig.price}\nTime: {sig.timestamp}\nDetails: {sig.details}"
                )
                
                # Execute Trade (Optional)
                if Config.ENABLE_TRADING:
                    try:
                        # Placeholder for trading logic
                        # self.trade_manager.submit_order(sig.symbol, "Buy", sig.price, 100)
                        pass 
                    except Exception as e:
                        AlertManager.send_alert("Trade Failed", str(e))

        except Exception as e:
            logger.error(f"Error processing quote for {symbol}: {e}")

    def start(self):
        """Start the monitoring system"""
        logger.info("Starting LongBridge Auto Deal System...")
        logger.info(f"Monitored Symbols: {Config.MONITOR_SYMBOLS}")
        
        try:
            self.ctx = QuoteContext(self.lp_config)
            self.ctx.set_on_quote(self.on_quote)
            
            # Subscribe to quotes
            self.ctx.subscribe(Config.MONITOR_SYMBOLS, [SubType.Quote], is_first_push=True)
            logger.info("Subscribed to quotes successfully. Waiting for data...")
            
            # Keep main thread alive
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            logger.critical(f"System crashed: {e}")
            AlertManager.send_alert("System Crashed", str(e))
        finally:
            if self.ctx:
                # self.ctx.unsubscribe(Config.MONITOR_SYMBOLS, [SubType.Quote]) # Optional cleanup
                pass

    def stop(self, signum, frame):
        logger.info("Stopping system...")
        self.running = False
