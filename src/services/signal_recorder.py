"""Signal recorder for tracking daily alerts across stocks and options."""
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SignalRecorder:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SignalRecorder, cls).__new__(cls)
            cls._instance.daily_signals_list = []
            cls._instance.stock_alerts_list = []  # For regular stock price alerts
        return cls._instance

    def add_signal(self, signal: Dict[str, Any]):
        """
        Add an option signal to the daily list.
        """
        logger.info(f"Recording option signal: {signal}")
        self.daily_signals_list.append(signal)

    def add_stock_alert(self, alert: Dict[str, Any]):
        """
        Add a stock price alert to the daily list.
        
        Args:
            alert (dict): {
                "symbol": "AAPL",
                "market_type": "US",
                "last_price": 175.50,
                "change_rate": 5.2,
                "volume": 50000000,
                "timestamp": "2024-05-20 10:00:00"
            }
        """
        logger.info(f"Recording stock alert: {alert}")
        # Avoid duplicates for same symbol (keep the latest)
        existing_idx = None
        for i, existing in enumerate(self.stock_alerts_list):
            if existing.get("symbol") == alert.get("symbol"):
                existing_idx = i
                break
        
        if existing_idx is not None:
            self.stock_alerts_list[existing_idx] = alert
        else:
            self.stock_alerts_list.append(alert)

    def get_daily_signals(self) -> List[Dict[str, Any]]:
        """Get all recorded option signals for the day."""
        return self.daily_signals_list

    def get_daily_stock_alerts(self) -> List[Dict[str, Any]]:
        """Get all recorded stock alerts for the day."""
        return self.stock_alerts_list

    def clear_signals(self):
        """Clear all recorded option signals."""
        logger.info("Clearing daily option signals list.")
        self.daily_signals_list = []

    def clear_stock_alerts(self):
        """Clear all recorded stock alerts."""
        logger.info("Clearing daily stock alerts list.")
        self.stock_alerts_list = []

    def clear_all(self):
        """Clear all recorded data."""
        self.clear_signals()
        self.clear_stock_alerts()

signal_recorder = SignalRecorder()
