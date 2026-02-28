
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
        return cls._instance

    def add_signal(self, signal: Dict[str, Any]):
        """
        Add a signal to the daily list.
        
        Args:
            signal (dict): A dictionary containing signal details.
                           e.g., {
                               "symbol": "LEGN270115C22500",
                               "type": "IV_SPIKE",
                               "value": 0.45,
                               "threshold": 0.30,
                               "timestamp": "2024-05-20 10:00:00"
                           }
        """
        logger.info(f"Recording signal: {signal}")
        self.daily_signals_list.append(signal)

    def get_daily_signals(self) -> List[Dict[str, Any]]:
        """Get all recorded signals for the day."""
        return self.daily_signals_list

    def clear_signals(self):
        """Clear all recorded signals."""
        logger.info("Clearing daily signals list.")
        self.daily_signals_list = []

signal_recorder = SignalRecorder()
